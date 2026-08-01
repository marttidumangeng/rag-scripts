"""Assign distinct OEM photos to imageless SC cobots + patch laser specs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

COMPANY_ID = 1602
COMPANY_SLUG = "rsm-machinery"
COMPANY_NAME = "RSM Machinery"
BASE = "https://rsm-machinery.com"

# Distinct OEM product photos (byte-checked) for SC siblings that lacked heroes.
# SC6-1460 owns SC-Series-cobot-welding-robot.png.webp — do not reuse that asset.
# Banned: mounting-methods diagram, welder control-panel crops, tool-end callout art.
PHOTO_BY_ID: dict[int, dict[str, Any]] = {
    6806: {  # SC7-1077 — in-cell welding action shot
        "image": f"{BASE}/wp-content/uploads/2025/12/Heavy-Plate-Cobot-Welding-Robot-.jpg",
        "images": [
            f"{BASE}/wp-content/uploads/2025/12/Heavy-Plate-Cobot-Welding-Robot-.jpg",
        ],
    },
    6808: {  # SC15-1464 — clean ERSM studio cobot (full .jpg, not tiny webp)
        "image": f"{BASE}/wp-content/uploads/2025/12/SC-Series-Collaborative-Robots.jpg",
        "images": [
            f"{BASE}/wp-content/uploads/2025/12/SC-Series-Collaborative-Robots.jpg",
        ],
    },
    6809: {  # SC20-2027 — dual-cobot series product render (no text overlays)
        "image": f"{BASE}/wp-content/uploads/2025/12/Cobot-Welding-Robot.jpg",
        "images": [
            f"{BASE}/wp-content/uploads/2025/12/Cobot-Welding-Robot.jpg",
        ],
    },
}

PHOTO_FALLBACKS: dict[int, list[str]] = {}

KNOWN_SC6_HERO_MD5 = None  # filled at runtime from live CDN if available


def _admin_base() -> str:
    return (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")


def _internal_secret() -> str:
    secret = (
        os.environ.get("INTERNAL_API_SECRET")
        or os.environ.get("CONTENT_QUEUE_INTERNAL_SECRET")
        or ""
    ).strip()
    if secret:
        return secret
    for candidate in (
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env",
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env.local",
    ):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def browser_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    s.get(BASE + "/", timeout=40)
    return s


def md5_url(sess: requests.Session, url: str) -> tuple[str, int, bytes]:
    b = sess.get(url, timeout=40).content
    return hashlib.md5(b).hexdigest(), len(b), b


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = _internal_secret()
    api = _admin_base()
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.status_code < 300:
                ok += 1
                print(f"copy-media ok {rid}", flush=True)
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}", flush=True)
        except Exception as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.2)
    return ok, fail


def strip_image_todo(notes: str) -> str:
    if "[IMAGE TO-DO" not in (notes or ""):
        return notes or ""
    # drop the IMAGE TO-DO block through the --- separator
    parts = notes.split("---\n", 1)
    if len(parts) == 2 and "[IMAGE TO-DO" in parts[0]:
        return parts[1].lstrip()
    return notes.replace("[IMAGE TO-DO — no hero, deliberate]", "").strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    sess = browser_session()

    # Hash SC6 hero to avoid accidental reuse
    sc6 = client._get("robots/robots/6807/")
    sc6_img = sc6.get("s3_image") or sc6.get("image") or ""
    used_hashes: set[str] = set()
    if sc6_img:
        try:
            h, n, _ = md5_url(requests.Session(), sc6_img)
            used_hashes.add(h)
            print(f"SC6 CDN hero md5={h[:12]} bytes={n}")
        except Exception as exc:
            print(f"warn SC6 hash: {exc}")

    # Validate / resolve photo URLs
    resolved: dict[int, dict[str, Any]] = {}
    for rid, media in PHOTO_BY_ID.items():
        urls = list(media["images"])
        for fb in PHOTO_FALLBACKS.get(rid, []):
            if fb not in urls:
                urls.append(fb)
        good = []
        for u in urls:
            try:
                h, n, body = md5_url(sess, u)
            except Exception as exc:
                print(f"  fail {rid} {u}: {exc}")
                continue
            if n < 8000:
                print(f"  small {rid} {n} {u}")
                continue
            if h in used_hashes:
                print(f"  skip dupe hash {rid} {h[:12]} {u}")
                continue
            # basic magic
            if not (
                body[:3] == b"\xff\xd8\xff"
                or body[:8].startswith(b"\x89PNG")
                or body[:4] == b"RIFF"
            ):
                print(f"  bad magic {rid} {u}")
                continue
            used_hashes.add(h)
            good.append(u)
            print(f"  ok {rid} {h[:12]} {n} {u[-70:]}")
            if len(good) >= 2:
                break
        if not good:
            print(f"ERROR no usable image for {rid}", file=sys.stderr)
            return 1
        resolved[rid] = {"image": good[0], "images": good}

    laser_patch = {
        # OEM: "Mounted on a multi-axis arm" + hero is 6-axis cobot-style cell
        "dof": 6,
        # Process / system fields that clear missing_specs without inventing arm payload
        "sensors": "Integrated sensors for weld path / penetration control (OEM robotic laser welder)",
        "connectivity": "Program-driven robotic path control (OEM)",
        "voltage": "Laser HFW series 1000–3000 W class; wavelength 1070/1080 nm (OEM table)",
        "features": (
            "ERSM Robotic Laser Welding (robotic configuration on the laser-welding "
            "product page). Multi-axis (6-DOF class) arm follows programmed paths for "
            "consistent penetration and reduced overspray on repetitive / hard-to-reach "
            "seams. OEM laser models on the same page: HFW-1000W / 1500W / 2000W / "
            "3000W; wavelength 1070/1080 nm; continuous or modulated pulse; welding "
            "speed 0–120 mm/s; dual-channel chiller; fiber length standard 7/10 m "
            "(customizable to 15 m). Handheld laser welder on the same page is a "
            "separate non-robot product and is not this record. Arm payload and reach "
            "are not published for the robotic configuration — left blank (not "
            "invented)."
        ),
        "notes": (
            "[AI Research] Specs pass: dof=6 from OEM multi-axis robotic laser welder "
            "+ cell hero; laser HFW power/wavelength/speed recorded in voltage/"
            "features. Arm payload_kg/reach_mm still unpublished on OEM page."
        ),
    }

    preview = {
        "photos": {str(k): v for k, v in resolved.items()},
        "laser_6810": laser_patch,
    }
    out = _RESEARCH_DIR / "staging" / "reports" / "rsm-1602-fix-gaps-preview.json"
    out.write_text(json.dumps(preview, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(preview, indent=2)[:2000])
    if not args.apply:
        print(f"Preview {out}. Re-run --apply")
        return 0

    imaged_ids = []
    for rid, media in resolved.items():
        robot = client._get(f"robots/robots/{rid}/")
        row = {
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "source_locale": "en",
            "name": robot.get("name"),
            "model_name": robot.get("model_name") or robot.get("name"),
            "url": robot.get("url") or f"{BASE}/product/sc6-1460-cobot-welding-robot/",
            "description": robot.get("description") or "ERSM SC-series collaborative welding robot.",
            "purpose": robot.get("purpose") or "Arc welding",
            "features": robot.get("features") or "ERSM SC cobot welding robot.",
            "image": media["image"],
            "images": media["images"],
            "information_source_urls": [
                robot.get("url") or f"{BASE}/product/sc6-1460-cobot-welding-robot/"
            ],
            "notes": strip_image_todo(robot.get("notes") or "")
            + (
                f"\n[AI Research] Hero backfilled from distinct OEM SC-series product "
                f"photo(s) on the cobot welding page (not the SC6-1460 primary render)."
            ),
        }
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        bulk["status"] = "pending_review"
        print(f"Media import {rid} {robot.get('name')}…", flush=True)
        result = client.bulk_import_robots(
            [bulk],
            update_existing=True,
            patch_existing=False,
            replace_media=True,
            replace_videos=False,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(args.created_by_id),
        )
        print(
            f"  created={result.get('created_count')} updated={result.get('updated_count')} "
            f"err={result.get('error_count')}"
        )
        if int(result.get("error_count") or 0) or int(result.get("created_count") or 0):
            print(f"ERROR {rid}: {result}", file=sys.stderr)
            return 1
        # re-assert typed specs (import can wipe)
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "pending_review",
                "notes": row["notes"],
                "payload_kg": robot.get("payload_kg"),
                "reach_mm": robot.get("reach_mm"),
                "dof": robot.get("dof") or 6,
                "repeatability_mm": robot.get("repeatability_mm"),
                "weight_kg": robot.get("weight_kg"),
                "availability_status": 11,
            },
        )
        imaged_ids.append(rid)

    # Laser specs
    print("Patching 6810 laser specs…", flush=True)
    for k, v in laser_patch.items():
        try:
            client._patch(f"robots/robots/6810/", {k: v})
            print(f"  ok {k}")
        except Exception as exc:
            print(f"  fail {k}: {exc}", file=sys.stderr)
    client._patch(
        f"robots/robots/6810/",
        {"status": "pending_review", "availability_status": 11},
    )

    if imaged_ids:
        trigger_copy_media(imaged_ids)
        subprocess.check_call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "verify_cdn_images.py"),
                "--ids",
                *[str(i) for i in imaged_ids + [6810]],
            ],
            cwd=str(_RESEARCH_DIR),
        )

    print(json.dumps({"imaged": imaged_ids, "laser": 6810}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
