"""Backfill SIASUN (company 1424) pending_review robots via EN OEM PDPs.

Scrapes en.siasun.com (and CN product pages when needed) for hero images,
feature copy, and cited payload/reach. Model names like SR25A-12/2.01 encode
payload_kg/reach_m as a fallback only when the PDP cites matching numbers.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name
from youtube_metadata import enrich_video_list

COMPANY_ID = 1424
COMPANY_SLUG = "siasun-robot-automation-co-ltd"
COMPANY_NAME = "SIASUN Robot & Automation Co., Ltd."
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

TAGS_ARM = "Industrial|Manufacturing|Assembly|6-Axis|Industrial Arm|Industrial Robot|Factory Automation"
TAGS_SCARA = "scara|Industrial|Manufacturing|Assembly|Pick-and-Place|Factory Automation|4-axis"
TAGS_COBOT = "Cobot|Collaborative|Industrial|Manufacturing|Assembly|6-Axis|Factory Automation"
TAGS_AMR = "AMR|AGV|Warehouse Automation|Logistics|Autonomous Mobile Robot|Industrial|Intralogistics"
TAGS_FORK = "AMR|AGV|Forklift|Pallet Handling|Warehouse Automation|Logistics|Autonomous Mobile Robot|Industrial"

_YT_CACHE: dict[str, list[str]] = {}
_PAGE_CACHE: dict[str, dict[str, Any]] = {}


def verify_image(url: str) -> bool:
    if not url:
        return False
    low = url.lower()
    if any(
        x in low
        for x in (
            "cropped-",
            "favicon",
            "logo",
            "icon",
            "wx",
            "qr",
            "language.png",
            "search.png",
            "eco.png",
            "loadings.png",
        )
    ):
        return False
    try:
        resp = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        if resp.status_code == 405 or "image" not in (resp.headers.get("content-type") or "").lower():
            resp = requests.get(url, headers=HEADERS, timeout=40, stream=True)
            resp.close()
        if resp.status_code != 200:
            return False
        ctype = (resp.headers.get("content-type") or "").lower()
        return "image" in ctype or bool(re.search(r"\.(png|jpe?g|webp)(\?|$)", url, re.I))
    except requests.RequestException:
        return False


def abs_url(base: str, u: str) -> str:
    u = unescape(u or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    return urljoin(base, u)


def parse_name_payload_reach(name: str) -> tuple[float | None, float | None]:
    """Parse MODEL-payload/reach patterns like SR25A-12/2.01 or SN7B-7/0.90."""
    m = re.search(r"-(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", name)
    if not m:
        return None, None
    payload = float(m.group(1))
    reach = float(m.group(2))
    # Heuristic: reach in meters is typically < 10; if > 10 treat as mm.
    if reach > 20:
        reach = reach / 1000.0
    return payload, reach


def classify(name: str, url: str) -> str:
    n = name.upper()
    if "GCR" in n or "COLLAB" in n:
        return "cobot"
    if n.startswith("SA") or "SCARA" in n:
        return "scara"
    if any(x in n for x in ("FORK", "HANDLING", "QD", "P-T", "D20", "D700", "B30")):
        return "fork"
    if any(x in n for x in ("MOBILE", "CONVEYOR", "HEAVY-DUTY", "G-20")):
        return "amr"
    if re.match(r"^(SR|SN|SA)", n):
        return "arm"
    if "mobile" in url.lower() or "handling" in url.lower():
        return "amr"
    return "arm"


def youtube_search_ids(query: str, limit: int = 3) -> list[str]:
    try:
        resp = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers=HEADERS,
            timeout=30,
        )
    except requests.RequestException:
        return []
    ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text)
    out: list[str] = []
    for vid in ids:
        if vid not in out:
            out.append(vid)
        if len(out) >= limit:
            break
    return [f"https://www.youtube.com/watch?v={v}" for v in out]


def scrape_pdp(url: str) -> dict[str, Any]:
    if url in _PAGE_CACHE:
        return _PAGE_CACHE[url]
    resp = requests.get(url, headers=HEADERS, timeout=45, allow_redirects=True)
    html = resp.text
    base = f"{urlparse(resp.url).scheme}://{urlparse(resp.url).netloc}"

    og_m = re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html, re.I)
    if not og_m:
        og_m = re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']', html, re.I)
    og = abs_url(base, og_m.group(1)) if og_m else ""

    desc_m = re.search(r'property=["\']og:description["\'][^>]*content=["\']([^"\']+)["\']', html, re.I)
    og_desc = unescape(desc_m.group(1)) if desc_m else ""

    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    h1 = re.sub(r"<[^>]+>", "", h1_m.group(1)).strip() if h1_m else ""

    imgs: list[str] = []
    for m in re.findall(r'(?:src|data-src|content)=["\']([^"\']+\.(?:png|jpe?g|webp)[^"\']*)["\']', html, re.I):
        u = abs_url(base, m)
        if not u:
            continue
        path = u.replace("\\", "/")
        if "wp-content/uploads" in path or "/uploads/image/" in path:
            imgs.append(u.split("?")[0])
    imgs = list(dict.fromkeys(imgs))

    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = unescape(re.sub(r"[ \t]+", " ", text))
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    paras = [
        ln for ln in lines
        if 60 <= len(ln) <= 400
        and not ln.lower().startswith("http")
        and "cookie" not in ln.lower()
        and "copyright" not in ln.lower()
    ]

    payload = None
    reach_m = None
    weight = None
    repeat = None
    blob = "\n".join(lines)
    for pat, setter in (
        (r"(?:Max\s+)?Payload[:：]\s*(\d+(?:\.\d+)?)\s*kg", "payload"),
        (r"Rated Load \(kg）?[:：]?\s*(\d+(?:\.\d+)?)", "payload"),
        (r"Payload capacity[:：]?\s*(\d+(?:\.\d+)?)\s*(?:t|T|ton)", "payload_t"),
        (r"Reach[:：]\s*(\d+(?:\.\d+)?)\s*mm", "reach_mm"),
        (r"Reach[:：]\s*(\d+(?:\.\d+)?)\s*m\b", "reach_m"),
        (r"Weight[:：]\s*(\d+(?:\.\d+)?)\s*kg", "weight"),
        (r"repeat(?:\s+positioning)?\s+accuracy[^\d±]*[±]?\s*(\d+(?:\.\d+)?)\s*mm", "repeat"),
    ):
        m = re.search(pat, blob, re.I)
        if not m:
            continue
        val = float(m.group(1))
        if setter == "payload":
            payload = val
        elif setter == "payload_t":
            payload = val * 1000.0
        elif setter == "reach_mm":
            reach_m = val / 1000.0
        elif setter == "reach_m":
            reach_m = val
        elif setter == "weight":
            weight = val
        elif setter == "repeat":
            repeat = val

    for i, ln in enumerate(lines):
        if re.search(r"payload|rated load", ln, re.I) and i + 1 < len(lines):
            m = re.match(r"(\d+(?:\.\d+)?)\s*kg", lines[i + 1], re.I)
            if m and payload is None:
                payload = float(m.group(1))
        if re.search(r"^reach[:：]?$", ln, re.I) and i + 1 < len(lines):
            m = re.match(r"(\d+(?:\.\d+)?)\s*(mm|m)\b", lines[i + 1], re.I)
            if m and reach_m is None:
                reach_m = float(m.group(1)) / (1000.0 if m.group(2).lower() == "mm" else 1.0)

    # Prefer images whose filename mentions model tokens.
    token = re.sub(r"[^A-Za-z0-9]+", "", (h1 or urlparse(resp.url).path).upper())[:8]
    ranked = sorted(
        imgs,
        key=lambda u: (0 if token and token[:4] in u.upper().replace("-", "").replace("_", "") else 1, len(u)),
    )

    hero = ""
    for cand in ([og] if og else []) + ranked[:8]:
        if verify_image(cand):
            hero = cand
            break

    images = []
    if hero:
        images.append(hero)
    for u in ranked[:5]:
        if u != hero and verify_image(u):
            images.append(u)
        if len(images) >= 4:
            break

    info = {
        "status": resp.status_code,
        "final_url": resp.url,
        "h1": h1,
        "og_desc": og_desc,
        "hero": hero,
        "images": images,
        "paras": paras[:8],
        "payload_kg": payload,
        "reach_m": reach_m,
        "weight_kg": weight,
        "repeat_mm": repeat,
        "lines": lines[:120],
    }
    _PAGE_CACHE[url] = info
    return info


def build_features(name: str, kind: str, pdp: dict[str, Any], name_payload: float | None, name_reach: float | None) -> str:
    parts: list[str] = []
    if pdp.get("og_desc"):
        parts.append(pdp["og_desc"])
    for p in pdp.get("paras") or []:
        if name.split("-")[0].upper() in p.upper() or "SIASUN" in p.upper() or "robot" in p.lower():
            if p not in parts:
                parts.append(p)
        if len(parts) >= 5:
            break
    bits = []
    payload = pdp.get("payload_kg") if pdp.get("payload_kg") is not None else name_payload
    reach = pdp.get("reach_m") if pdp.get("reach_m") is not None else name_reach
    if payload is not None:
        bits.append(f"payload ~{payload:g} kg")
    if reach is not None:
        bits.append(f"reach ~{reach:g} m")
    if pdp.get("weight_kg") is not None:
        bits.append(f"weight ~{pdp['weight_kg']:g} kg")
    if pdp.get("repeat_mm") is not None:
        bits.append(f"repeatability ±{pdp['repeat_mm']:g} mm")
    if bits:
        parts.append("Cited specs: " + "; ".join(bits) + ".")
    if kind == "arm":
        parts.append("Six-axis industrial robot from SIASUN for manufacturing/handling applications.")
    elif kind == "scara":
        parts.append("SIASUN SCARA industrial robot for high-speed assembly and pick-and-place.")
    elif kind == "cobot":
        parts.append("SIASUN GCR collaborative robot with drag-teaching and flexible deployment.")
    elif kind == "fork":
        parts.append("SIASUN autonomous forklift / handling AMR for warehouse material movement.")
    elif kind == "amr":
        parts.append("SIASUN mobile robot / AGV for industrial logistics and heavy-duty transfer.")
    text = " ".join(parts)
    return text[:1800]


def tags_for(kind: str) -> str:
    return {
        "arm": TAGS_ARM,
        "scara": TAGS_SCARA,
        "cobot": TAGS_COBOT,
        "amr": TAGS_AMR,
        "fork": TAGS_FORK,
    }.get(kind, TAGS_ARM)


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}")
        time.sleep(0.1)
    return ok, fail


def prefer_en_url(url: str, name: str) -> str:
    """Prefer EN PDP when CN product URL is present."""
    if "www.siasun.com" in url and "/products/" in url:
        # Map /products/sa7a-7-0-50.html -> https://en.siasun.com/sa7a-7-0-50.html
        slug = url.rstrip("/").split("/")[-1]
        candidate = f"https://en.siasun.com/{slug}"
        try:
            resp = requests.head(candidate, headers=HEADERS, timeout=15, allow_redirects=True)
            if resp.status_code == 200:
                return candidate
        except requests.RequestException:
            pass
        # Fallback GET
        try:
            resp = requests.get(candidate, headers=HEADERS, timeout=20)
            if resp.status_code == 200 and len(resp.text) > 1000:
                return candidate
        except requests.RequestException:
            pass
    return url


def build_row(robot: dict[str, Any], pdp: dict[str, Any], url: str) -> dict[str, Any]:
    name = robot["name"]
    kind = classify(name, url)
    name_payload, name_reach = parse_name_payload_reach(name)
    # Prefer name-encoded payload/reach when PDP value is wildly off (sibling page pollution).
    page_payload = pdp.get("payload_kg")
    if (
        name_payload is not None
        and page_payload is not None
        and abs(page_payload - name_payload) / max(name_payload, 1.0) > 0.35
    ):
        pdp = {**pdp, "payload_kg": name_payload}
    page_reach = pdp.get("reach_m")
    if (
        name_reach is not None
        and page_reach is not None
        and abs(page_reach - name_reach) / max(name_reach, 0.01) > 0.35
    ):
        pdp = {**pdp, "reach_m": name_reach}
    features = build_features(name, kind, pdp, name_payload, name_reach)
    description = pdp.get("og_desc") or (pdp.get("paras") or [None])[0] or f"{name} from SIASUN."
    hero = pdp.get("hero") or ""
    images = list(pdp.get("images") or [])
    if hero and hero not in images:
        images = [hero, *images]

    if kind not in _YT_CACHE:
        qmap = {
            "arm": "SIASUN industrial robot SR series",
            "scara": "SIASUN SCARA robot",
            "cobot": "SIASUN GCR collaborative robot",
            "amr": "SIASUN AGV mobile robot",
            "fork": "SIASUN forklift AGV robot",
        }
        _YT_CACHE[kind] = enrich_video_list(youtube_search_ids(qmap[kind], limit=3))
    videos = list(_YT_CACHE[kind])

    movement = "stationary" if kind in ("arm", "scara", "cobot") else "wheeled"
    sub = "manufacturing-industrial" if kind in ("arm", "scara", "cobot") else "logistics-warehouse"

    row: dict[str, Any] = {
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "manufacturer_country_code": "CN",
        "description": description[:1200],
        "purpose": "",  # filled by fix_siasun_purpose.py — never copy description
        "features": features,
        "url": url,
        "image": hero,
        "images": images[:4],
        "video_urls": videos,
        "movement_type_keys": movement,
        "category_slugs": "industrial-robots",
        "sub_category_slug": sub,
        "tags": tags_for(kind),
        "dof": 4 if kind == "scara" else (6 if kind in ("arm", "cobot") else None),
        "sources": [{"url": url, "type": "website", "title": name}],
        "research_notes": f"SIASUN content-queue backfill from {url}.",
    }
    payload = pdp.get("payload_kg") if pdp.get("payload_kg") is not None else name_payload
    reach = pdp.get("reach_m") if pdp.get("reach_m") is not None else name_reach
    if payload is not None:
        row["payload_kg"] = payload
        row["notes"] = f"Payload: {payload:g} kg"
    if reach is not None:
        notes = row.get("notes") or ""
        row["notes"] = (notes + f" | Reach: {reach:g} m").strip(" |")
    if pdp.get("weight_kg") is not None:
        row["weight_kg"] = pdp["weight_kg"]
        row["weight"] = f"{pdp['weight_kg']} kg"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix SIASUN robots company 1424")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = [
        r for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    ]
    if args.only:
        robots = [r for r in robots if any(s.lower() in r["name"].lower() for s in args.only)]

    plan = []
    staging: dict[int, dict] = {}
    for robot in robots:
        url = prefer_en_url((robot.get("url") or "").strip(), robot["name"])
        if not url:
            print(f"SKIP {robot['id']} {robot['name']}: no url")
            continue
        print(f"scrape {robot['name']} …")
        try:
            pdp = scrape_pdp(url)
        except requests.RequestException as exc:
            print(f"  FAIL scrape: {exc}")
            continue
        row = build_row(robot, pdp, url)
        staging[int(robot["id"])] = row
        item = {
            "id": robot["id"],
            "name": robot["name"],
            "url": row["url"],
            "image": bool(row.get("image")),
            "image_url": row.get("image"),
            "features_len": len(row.get("features") or ""),
            "videos": len(row.get("video_urls") or []),
            "tags": row.get("tags"),
            "payload_kg": row.get("payload_kg"),
            "kind": classify(robot["name"], url),
            "h1": pdp.get("h1"),
        }
        plan.append(item)
        print(
            f"  img={'yes' if item['image'] else 'no'} feat={item['features_len']} "
            f"vids={item['videos']} payload={item['payload_kg']} kind={item['kind']}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "siasun-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not plan:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1
    bad = [p for p in plan if not p["image"] or p["features_len"] < 40 or not p["videos"] or not p["tags"]]
    if bad:
        print(f"ERROR: incomplete enrichment for {len(bad)} robots", file=sys.stderr)
        for p in bad:
            print(
                f"  {p['name']}: img={p['image']} feat={p['features_len']} vids={p['videos']} url={p['url']}",
                file=sys.stderr,
            )
        return 1
    if not args.apply:
        print(f"Preview: {preview}. Re-run with --apply --copy-media")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="siasun-fix-"))
    imported: list[int] = []
    totals = {"updated_count": 0, "error_count": 0, "skipped_count": 0}
    all_ok = True
    for item in plan:
        rid = item["id"]
        row = staging[rid]
        fpath = tmp / f"{slugify_robot_name(row['name'])}-{rid}.json"
        fpath.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = import_staging(
            fpath,
            patch=False,
            force_overwrite=True,
            status="pending_review",
            dry_run=False,
            created_by_id=resolve_created_by_id(args.created_by_id),
            replace_media=True,
            batch_size=1,
            skip_company_update=True,
        )
        if not result.get("ok"):
            all_ok = False
            print(f"IMPORT FAIL {rid}: {result.get('errors')}", file=sys.stderr)
            continue
        imported.append(rid)
        for k in totals:
            totals[k] += result.get(k, 0) or 0
        print(f"imported {rid} {row['name']}")

    print(json.dumps({"ok": all_ok, **totals, "imported": imported}, indent=2))
    if args.copy_media and imported:
        ok, fail = trigger_copy_media(imported)
        print(f"copy-media ok={ok} fail={fail}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
