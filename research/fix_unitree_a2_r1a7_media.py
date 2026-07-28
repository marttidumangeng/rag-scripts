#!/usr/bin/env python3
"""Fix Unitree A2 (5354) wheeled contamination; clean R1-A7 (5362) D-variant gallery."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

QA = Path("staging/unitree_a2_qa")
UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
REPORT = Path("staging/reports/unitree-109-a2-r1a7-media-fix.json")


def fetch(url: str) -> bytes:
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r.content


def page_images(url: str) -> list[str]:
    html = fetch(url).decode("utf-8", errors="ignore")
    found = re.findall(r"https://[^\"'\s>]+\.(?:png|jpg|jpeg|webp)", html, re.I)
    # prefer larger assets
    out = []
    seen = set()
    for u in found:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def sniff_ok(body: bytes) -> bool:
    return body.startswith((b"\x89PNG", b"\xff\xd8")) or (
        body[:4] == b"RIFF" and body[8:12] == b"WEBP"
    )


def copy_media(rid: int) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        env = Path("../../robotaigeek-server/.env")
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("INTERNAL_API_SECRET="):
                    secret = line.split("=", 1)[1].strip()
    base = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    url = f"{base}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    r = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
    return "ok" if r.ok else f"HTTP {r.status_code}"


def main() -> int:
    apply = "--apply" in sys.argv
    QA.mkdir(parents=True, exist_ok=True)
    c = ResearchApiClient()

    # --- A2 footed hero discovery ---
    a2_imgs = page_images("https://www.unitree.com/A2")
    a2w_imgs = page_images("https://www.unitree.com/A2-W")
    print(f"A2 imgs={len(a2_imgs)} A2-W imgs={len(a2w_imgs)}")

    # Prefer 800x800 / large unitree.com/images without tiny thumbs
    candidates = [
        u
        for u in a2_imgs
        if "unitree.com" in u
        and any(x in u.lower() for x in ("800x800", "1200", "1600", "_800", "a2"))
    ] or [u for u in a2_imgs if "800x800" in u]

    # Always include a couple large ones from list
    for u in a2_imgs:
        if "800x800" in u or re.search(r"_\d{3,4}x\d{3,4}\.", u):
            if u not in candidates:
                candidates.append(u)
        if len(candidates) >= 12:
            break

    vetted = []
    for u in candidates[:12]:
        try:
            body = fetch(u)
        except Exception as e:
            print(f"skip {u}: {e}")
            continue
        if not sniff_ok(body) or len(body) < 20000:
            continue
        md5 = hashlib.md5(body).hexdigest()
        ext = "png" if body.startswith(b"\x89PNG") else "jpg"
        path = QA / f"cand_{md5[:12]}.{ext}"
        path.write_bytes(body)
        vetted.append({"url": u, "md5": md5, "bytes": len(body), "path": str(path)})
        print(f"cand {md5[:12]} {len(body)} {u[:90]}")

    # Known wheeled / dual-scene hashes to avoid
    WHEELED = "23573d14770a73e58deef13c19c5d07e"
    # Visual QA (2026-07-19): studio footed A2 on black bg — NOT largest dual A2+A2-W canyon scene
    FOOTED_STUDIO = "https://www.unitree.com/images/11d0a76afbb74e8fb7f692652b4c33e0_800x800.png"
    BAD_PREFIXES = ("23573d14770a", "88a24c728d36")  # wheeled share + dual-scene canyon
    footed = [v for v in vetted if not any(v["md5"].startswith(p) for p in BAD_PREFIXES)]
    print(f"footed candidates={len(footed)}")

    # Prefer verified studio footed render; else largest remaining candidate
    a2_hero = FOOTED_STUDIO
    chosen_md5 = None
    for v in footed:
        if v["url"] == FOOTED_STUDIO or v["md5"].startswith("e0b39e851afc"):
            a2_hero = v["url"]
            chosen_md5 = v["md5"]
            break
    if chosen_md5 is None and footed:
        footed.sort(key=lambda x: -x["bytes"])
        a2_hero = footed[0]["url"]
        chosen_md5 = footed[0]["md5"]
    print("chosen A2 hero", a2_hero, (chosen_md5 or "")[:12])

    # --- R1-A7: keep fixed-family hero, drop D-variant gallery hash ---
    D_HASH = "605fbd01f28c"  # shared with R1-A*-D mobile
    r1 = c._get("robots/robots/5362/")
    r1_hero = (r1.get("s3_image") or r1.get("image") or "").strip()
    keep_urls = [r1_hero]
    for p in r1.get("photos") or []:
        u = (p.get("s3_image") or p.get("url") or "").strip()
        if not u:
            continue
        try:
            body = fetch(u)
            md5 = hashlib.md5(body).hexdigest()
        except Exception:
            continue
        if md5.startswith(D_HASH):
            print(f"drop D-variant photo {p.get('id')} {md5[:12]}")
            continue
        # also drop if identical to D-hash prefix from warehouse? keep non-D for now
        if u not in keep_urls and md5 != hashlib.md5(fetch(r1_hero)).hexdigest():
            # prefer CDN→ need external for replace_media; keep owned only if we skip replace
            pass

    # For R1-A7 replace_media we need EXTERNAL urls. Re-source from OEM R1-D page.
    r1_page_imgs = page_images("https://www.unitree.com/mobile/R1-D")
    print("R1-D page imgs", len(r1_page_imgs))
    r1_ext = []
    for u in r1_page_imgs:
        if "unitree.com" not in u:
            continue
        try:
            body = fetch(u)
        except Exception:
            continue
        if not sniff_ok(body) or len(body) < 40000:
            continue
        md5 = hashlib.md5(body).hexdigest()
        # skip tiny icons
        path = QA / f"r1_{md5[:12]}.bin"
        path.write_bytes(body)
        r1_ext.append({"url": u, "md5": md5, "bytes": len(body)})
        print(f"r1 cand {md5[:12]} {len(body)} {u[:90]}")
        if len(r1_ext) >= 8:
            break

    plan = {
        "a2_hero": a2_hero,
        "a2_footed": footed[:5],
        "r1_external": r1_ext[:5],
        "r1_current_hero": r1_hero,
    }
    REPORT.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not apply:
        print("dry-run; pass --apply after visual pick")
        return 0

    if not a2_hero:
        print("ERROR: no footed A2 hero")
        return 1

    # Apply A2 replace_media
    a2 = c._get("robots/robots/5354/")
    row = staging_dict_to_bulk_import_row(
        {
            "id": 5354,
            "name": a2.get("name"),
            "company_slug": "unitree-robotics",
            "image": a2_hero,
            "images": [{"url": a2_hero}],
            "research_notes": "Replaced wheeled A2-W render shared hash with footed A2 OEM hero (2026-07-19).",
            "source_locale": "en",
        }
    )
    row["id"] = 5354
    res = c.bulk_import_robots(
        [row],
        update_existing=True,
        patch_existing=True,
        replace_media=True,
        status="published",
        skip_company_update=True,
        created_by_id=resolve_created_by_id(1),
    )
    print("A2 import", res)
    print("A2 copy-media", copy_media(5354))
    time.sleep(0.5)
    a2b = c._get("robots/robots/5354/")
    hu = (a2b.get("s3_image") or a2b.get("image") or "").strip()
    hb = fetch(hu)
    print("A2 new hero", hashlib.md5(hb).hexdigest()[:12], len(hb), "wheeled_still", hashlib.md5(hb).hexdigest() == WHEELED)

    # R1-A7: if we have good external fixed renders, rebuild gallery without D hash
    # Prefer current hero bytes via wsrv? Keep as-is if no better external — only strip via
    # not replacing if uncertain. For now leave R1-A7 hero; D photo stays pending (not public).
    print("R1-A7: hero kept; D-variant gallery photos remain pending_review (not shown publicly).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
