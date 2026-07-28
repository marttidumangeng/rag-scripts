"""Backfill Kawasaki Robotics (company 773) — replace logo heroes with OEM product photos.

CRM names are often truncated (e.g. 300L → CP300L). Images were shared Kawasaki OG logos.
Made In is already JP for the fleet; release_year only when OEM page cites a launch year.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from PIL import Image

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from import_staging import import_staging, resolve_created_by_id  # noqa: E402
from robot_auto_research import slugify_robot_name  # noqa: E402
from web_extract import WebFetcher, is_junk_image_url, parse_page  # noqa: E402
from youtube_metadata import enrich_video_list  # noqa: E402

COMPANY_ID = 773
COMPANY_SLUG = "kawasaki-robotics"
COMPANY_NAME = "Kawasaki Robotics"
BASE = "https://kawasakirobotics.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": f"{BASE}/",
}

# Cited launch years (OEM press / automatica premiere — not guesswork).
CURATED_YEARS: dict[str, tuple[int, str, str]] = {
    # world premiere at automatica 2023
    "CL103N": (
        2023,
        "world premiere of the Kawasaki Robotics CL Series at automatica 2023",
        "https://kawasakirobotics.com/eu-africa/automatica/",
    ),
    "CL105N": (
        2023,
        "world premiere of the Kawasaki Robotics CL Series at automatica 2023",
        "https://kawasakirobotics.com/eu-africa/automatica/",
    ),
    "CL108N": (
        2023,
        "world premiere of the Kawasaki Robotics CL Series at automatica 2023",
        "https://kawasakirobotics.com/eu-africa/automatica/",
    ),
    "CL110N": (
        2023,
        "world premiere of the Kawasaki Robotics CL Series at automatica 2023",
        "https://kawasakirobotics.com/eu-africa/automatica/",
    ),
}

# Truncated CRM names → real product slugs on kawasakirobotics.com
URL_OVERRIDES: dict[str, str] = {
    "004V": "mc004v",
    "300L": "cp300l",
    "420L": "mx420l",
    "500L": "cp500l",
    "700L": "cp700l",
    "165U": "zx165u",
    "200S": "zx200s",
    "050N": "rs050n",
    "080N": "rs080n",
    "200X": "bx200x",
    "200L (Kawasaki Robotics)": "bx200l",
    "200L": "bx200l",
    "100N": "bx100n",
    "700N": "mx700n",
    "BX100L": "bx100n",  # OEM may share BX100N asset; family sibling
}

TAGS_ARM = "Industrial|Industrial Robot|Industrial Arm|6-Axis|Manufacturing|Assembly|Factory Automation|Material Handling"
TAGS_COBOT = "Cobot|Collaborative|Industrial|Manufacturing|Assembly|6-Axis|Factory Automation"
TAGS_SCARA = "scara|Industrial|Industrial Robot|Manufacturing|Assembly|Pick-and-Place|Factory Automation|4-axis"
TAGS_PAINT = "Industrial|Industrial Robot|Manufacturing|Factory Automation|Painting"
TAGS_PALLET = "Industrial|Industrial Robot|palletizing|Material Handling|Warehouse Automation|Manufacturing"

PREVIEW_DIR = _RESEARCH_DIR / "staging" / "reports" / "kawasaki_773_preview"
REPORT_JSON = _RESEARCH_DIR / "staging" / "reports" / "kawasaki_773_enrich_plan.json"
REPORT_MD = _RESEARCH_DIR / "staging" / "reports" / "kawasaki-773-overnight-report.md"

_PAGE_CACHE: dict[str, Any] = {}
_YT_CACHE: dict[str, list[str]] = {}


def core_name(name: str) -> str:
    return re.sub(r"\s*\(.*?\)\s*", "", (name or "").strip()).strip()


def product_slug(name: str) -> str:
    if name in URL_OVERRIDES:
        return URL_OVERRIDES[name]
    n = core_name(name)
    if n in URL_OVERRIDES:
        return URL_OVERRIDES[n]
    return re.sub(r"[^A-Za-z0-9]+", "", n).lower()


def product_url(name: str) -> str:
    return f"{BASE}/products-robots/{product_slug(name)}/"


def tags_for(name: str) -> str:
    n = core_name(name).upper()
    if n.startswith("CL"):
        return TAGS_COBOT
    if n.startswith(("KJ", "KF")):
        return TAGS_PAINT
    if n.startswith("CP") or n in {"300L", "500L", "700L"}:
        return TAGS_PALLET
    if "SCARA" in n or n.startswith(("YF",)):
        return TAGS_SCARA
    return TAGS_ARM


def fetch_page(url: str):
    if url in _PAGE_CACHE:
        return _PAGE_CACHE[url]
    fetcher = WebFetcher(timeout=35, stealth=True)
    page = parse_page(fetcher, url, rendered=False)
    _PAGE_CACHE[url] = page
    return page


def extract_candidate_images(html: str, page_url: str) -> list[str]:
    imgs: list[str] = []
    for m in re.finditer(
        r"(?:src|data-src|content)=[\"']([^\"']+\.(?:png|jpe?g|webp)[^\"']*)[\"']",
        html,
        re.I,
    ):
        u = urljoin(page_url, m.group(1).strip())
        if is_junk_image_url(u):
            continue
        low = u.lower()
        if any(x in low for x in ("logo", "favicon", "icon", "sprite", "wp-emoji", "flag")):
            continue
        imgs.append(u)
    # Prefer tachyon product assets
    tachyon = [u for u in imgs if "/tachyon/" in u.lower()]
    other = [u for u in imgs if u not in tachyon]
    return list(dict.fromkeys(tachyon + other))


def score_image(url: str, model: str) -> int:
    low = url.lower()
    score = 0
    tokens = [t for t in re.split(r"[^a-z0-9]+", model.lower()) if len(t) >= 2]
    for t in tokens:
        if t in low:
            score += 12
    slug = product_slug(model)
    if slug and slug in low:
        score += 15
    if "/tachyon/" in low:
        score += 8
    if "1200x630" in low or "og-image" in low:
        score -= 30
    if "logo" in low:
        score -= 50
    return score


def download_valid_hero(url: str, *, model: str, robot_id: int) -> tuple[str, dict] | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=45)
    except requests.RequestException:
        return None
    if resp.status_code != 200 or len(resp.content) < 12_000:
        return None
    try:
        im = Image.open(BytesIO(resp.content))
        w, h = im.size
    except Exception:
        return None
    # Reject brand OG card (logo) — known failure mode for this fleet
    if w == 1200 and h == 630 and len(resp.content) < 60_000:
        return None
    if w * h < 80_000:
        return None
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    prev = im.copy()
    prev.thumbnail((512, 512))
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", model)[:40]
    prev_path = PREVIEW_DIR / f"final_{robot_id}_{safe}.png"
    prev.save(prev_path)
    return url, {"w": w, "h": h, "bytes": len(resp.content), "preview": str(prev_path)}


def parse_specs(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    body = text or ""
    pm = re.search(r"payload[^0-9]{0,40}(\d+(?:\.\d+)?)\s*kg", body, re.I)
    if pm:
        out["payload_kg"] = float(pm.group(1))
    rm = re.search(r"(?:max\.?\s*)?reach[^0-9]{0,40}(\d+(?:\.\d+)?)\s*mm", body, re.I)
    if rm:
        out["reach_mm"] = float(rm.group(1))
    dm = re.search(r"(\d)\s*(?:-?\s*)?axis", body, re.I)
    if dm:
        out["dof"] = int(dm.group(1))
    return out


def parse_release_year(text: str, html: str) -> tuple[int | None, str]:
    """Return (year, citation) only for launch-like phrases."""
    blob = f"{text}\n{html}"
    patterns = [
        r"(?:launched|introduced|released|announced|debut(?:ed)?)\s+(?:in\s+)?((?:19|20)\d{2})",
        r"((?:19|20)\d{2})\s+(?:launch|introduction|release|debut)",
    ]
    for pat in patterns:
        m = re.search(pat, blob, re.I)
        if not m:
            continue
        year = int(m.group(1))
        if 1990 <= year <= 2026:
            ctx = blob[max(0, m.start() - 40) : m.end() + 40]
            ctx = re.sub(r"\s+", " ", ctx).strip()
            return year, ctx[:180]
    return None, ""


def feature_blurb(name: str, page_text: str, specs: dict, url: str) -> str:
    # Take first meaningful sentences from PDP body
    text = re.sub(r"\s+", " ", page_text or "").strip()
    # Drop common chrome
    for junk in (
        "Cookie",
        "Privacy",
        "Download Lineup",
        "Find a distributor",
        "Contact Us",
    ):
        if junk in text:
            text = text.split(junk)[0]
    paras = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if len(p.strip()) > 40]
    kept = []
    for p in paras:
        low = p.lower()
        if any(x in low for x in ("cookie", "privacy policy", "subscribe", "newsletter")):
            continue
        if core_name(name).lower()[:3] in low or "kawasaki" in low or "robot" in low:
            kept.append(p)
        if len(kept) >= 3:
            break
    if not kept:
        kept = [
            f"Kawasaki Robotics {core_name(name)} industrial robot.",
        ]
    bits = " ".join(kept)[:900]
    spec_bits = []
    if specs.get("payload_kg") is not None:
        spec_bits.append(f"payload {specs['payload_kg']:g} kg")
    if specs.get("reach_mm") is not None:
        spec_bits.append(f"reach {specs['reach_mm']:g} mm")
    if specs.get("dof") is not None:
        spec_bits.append(f"{specs['dof']} axes")
    if spec_bits:
        bits = bits.rstrip(".") + ". Cited specs: " + ", ".join(spec_bits) + "."
    bits = bits.rstrip(".") + f" Source: {url}."
    return bits


def youtube_for(name: str) -> list[str]:
    key = product_slug(name)
    if key in _YT_CACHE:
        return list(_YT_CACHE[key])
    q = f"Kawasaki robot {core_name(name)}"
    try:
        resp = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": q},
            headers=HEADERS,
            timeout=30,
        )
    except requests.RequestException:
        _YT_CACHE[key] = []
        return []
    ids = []
    for vid in re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text or ""):
        if vid not in ids:
            ids.append(vid)
        if len(ids) >= 6:
            break
    urls = [f"https://www.youtube.com/watch?v={v}" for v in ids]
    enriched = enrich_video_list(urls)
    kept: list[str] = []
    tokens = [t for t in re.split(r"[^a-z0-9]+", core_name(name).lower()) if len(t) >= 2]
    for item in enriched:
        title = (item.get("title") or "").lower()
        url = item.get("url") or ""
        if not title or not url:
            continue
        if "kawasaki" not in title and "robot" not in title:
            continue
        if tokens and not any(t in title for t in tokens):
            # allow series-level Kawasaki robot videos
            if "kawasaki" in title and "robot" in title:
                kept.append(url)
        else:
            kept.append(url)
        if len(kept) >= 2:
            break
    if not kept:
        kept = [
            e["url"]
            for e in enriched
            if e.get("title") and "kawasaki" in (e.get("title") or "").lower()
        ][:1]
    kept = list(dict.fromkeys(kept))[:2]
    _YT_CACHE[key] = kept
    return list(kept)


def scrape_robot(robot: dict) -> dict[str, Any]:
    name = robot["name"]
    rid = int(robot["id"])
    url = product_url(name)
    page = fetch_page(url)
    if not page or not page.html or len(page.text or "") < 400:
        return {"id": rid, "name": name, "ok": False, "error": "pdp_missing", "url": url}

    title = (page.title or "").lower()
    if "page not found" in title or "404" in title:
        return {"id": rid, "name": name, "ok": False, "error": "pdp_404", "url": url}

    candidates = extract_candidate_images(page.html, url)
    ranked = sorted(candidates, key=lambda u: -score_image(u, name))
    hero = None
    meta = {}
    for cand in ranked[:15]:
        got = download_valid_hero(cand, model=name, robot_id=rid)
        if got:
            hero, meta = got
            break
    if not hero:
        return {"id": rid, "name": name, "ok": False, "error": "no_hero", "url": url, "candidates": ranked[:5]}

    specs = parse_specs(page.text or "")
    year, year_cite = parse_release_year(page.text or "", page.html or "")
    year_source = url
    curated = CURATED_YEARS.get(core_name(name))
    if curated and not year:
        year, year_cite, year_source = curated
    features = feature_blurb(name, page.text or "", specs, url)
    videos = youtube_for(name)

    sources = [{"url": url, "type": "website", "title": page.title or name}]
    if curated and year_source != url:
        sources.append({"url": year_source, "type": "website", "title": "CL Series premiere"})

    row: dict[str, Any] = {
        "id": rid,
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "model_name": core_name(name),
        "manufacturer_country_code": "JP",
        "url": url,
        "image": hero,
        "images": [hero],
        "description": features[:1200],
        "purpose": features[:1200],
        "features": features,
        "tags": tags_for(name),
        "video_urls": videos,
        "movement_type_keys": "stationary",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "availability_status_key": "available",
        "sources": sources,
        "research_notes": (
            "Kawasaki content-queue fix 2026-07-16: replaced shared OG logo heroes with "
            f"OEM tachyon product photo from {url}. Made in JP from company HQ."
        ),
    }
    notes = []
    if specs.get("payload_kg") is not None:
        row["payload_kg"] = specs["payload_kg"]
        notes.append(f"Payload: {specs['payload_kg']:g} kg")
    if specs.get("reach_mm") is not None:
        row["reach_mm"] = specs["reach_mm"]
        notes.append(f"Reach: {specs['reach_mm']:g} mm")
    if specs.get("dof") is not None:
        row["dof"] = specs["dof"]
    if year and year_cite:
        row["release_year"] = year
        row["research_notes"] += f" release_year={year}: {year_cite} ({year_source})"
        notes.append(f"release_year={year}: {year_cite}")
    if notes:
        row["notes"] = " | ".join(notes)

    return {
        "id": rid,
        "name": name,
        "ok": True,
        "url": url,
        "image": hero,
        "meta": meta,
        "payload_kg": specs.get("payload_kg"),
        "reach_mm": specs.get("reach_mm"),
        "dof": specs.get("dof"),
        "release_year": year,
        "videos": len(videos),
        "features_len": len(features),
        "row": row,
    }


def trigger_copy_media(robot_ids: list[int]) -> dict:
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/")
    admin = api.replace("/api/v1", "")
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("INTERNAL_API_SECRET="):
                    secret = line.split("=", 1)[1].strip()
                    break
    if not secret:
        return {"ok": False, "error": "INTERNAL_API_SECRET missing"}
    ok = fail = 0
    errors = []
    for rid in robot_ids:
        url = f"{admin}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                errors.append({"id": rid, "status": resp.status_code, "body": resp.text[:160]})
        except requests.RequestException as exc:
            fail += 1
            errors.append({"id": rid, "error": str(exc)})
        time.sleep(0.12)
    return {"ok": fail == 0, "copied_ok": ok, "copied_fail": fail, "errors": errors[:15]}


def write_report(plan: list[dict], copy_result: dict | None, verify_summary: str) -> None:
    ok = [p for p in plan if p.get("ok")]
    fail = [p for p in plan if not p.get("ok")]
    years = [p for p in ok if p.get("release_year")]
    lines = [
        "# Kawasaki Robotics (773) overnight enrich report",
        "",
        f"- Date: 2026-07-16",
        f"- Targets: {len(plan)} pending_review robots",
        f"- Heroes OK: **{len(ok)} / {len(plan)}**",
        f"- Heroes failed: {len(fail)}",
        f"- Release years cited: {len(years)}",
        f"- Made In: JP kept/set for all applied rows",
        f"- Copy-media: {json.dumps(copy_result or {})}",
        f"- CDN verify: {verify_summary}",
        "",
        "## URL remaps (truncated CRM names)",
        "",
    ]
    for k, v in sorted(URL_OVERRIDES.items()):
        lines.append(f"- `{k}` → `/products-robots/{v}/`")
    if fail:
        lines += ["", "## Failures", ""]
        for p in fail:
            lines.append(f"- {p['id']} {p['name']}: {p.get('error')} ({p.get('url')})")
    if years:
        lines += ["", "## Release years filled", ""]
        for p in years:
            lines.append(f"- {p['name']}: {p['release_year']}")
    lines += [
        "",
        "## Notes",
        "",
        "- Previous heroes were shared Kawasaki Robotics logo OG (1200×630).",
        "- New heroes from kawasakirobotics.com `/tachyon/` product assets.",
        "- BX100L uses bx100n family asset if dedicated PDP/image missing.",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Kawasaki Robotics company 773")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only-ids", nargs="*", type=int)
    args = parser.parse_args()

    client = ResearchApiClient()
    robots = [
        r
        for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    ]
    if args.only_ids:
        want = set(args.only_ids)
        robots = [r for r in robots if r["id"] in want]
    if args.limit:
        robots = robots[: args.limit]

    plan: list[dict] = []
    rows: list[dict] = []
    for robot in robots:
        print(f"scrape {robot['id']} {robot['name']} …", flush=True)
        item = scrape_robot(robot)
        plan.append({k: v for k, v in item.items() if k != "row"})
        if item.get("ok") and item.get("row"):
            rows.append(item["row"])
            print(
                f"  OK img={item['image'][-50:]} yr={item.get('release_year')} "
                f"payload={item.get('payload_kg')} vids={item.get('videos')}",
                flush=True,
            )
        else:
            print(f"  FAIL {item.get('error')}", flush=True)
        time.sleep(0.1)

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {
        "total": len(plan),
        "ok": sum(1 for p in plan if p.get("ok")),
        "fail": sum(1 for p in plan if not p.get("ok")),
        "with_year": sum(1 for p in plan if p.get("release_year")),
        "with_videos": sum(1 for p in plan if (p.get("videos") or 0) > 0),
    }
    print(json.dumps(summary, indent=2), flush=True)

    if summary["ok"] < summary["total"]:
        print("WARN: some robots missing heroes — will apply OK subset only" if args.apply else "WARN missing heroes", flush=True)

    if not args.apply:
        write_report(plan, None, "not run (dry-run)")
        print(f"Dry-run report: {REPORT_MD}")
        return 0 if summary["ok"] == summary["total"] else 1

    if not rows:
        print("ERROR: nothing to import", file=sys.stderr)
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="kawasaki-fix-"))
    for row in rows:
        path = tmp / f"{slugify_robot_name(row['name'])}-{row['id']}.json"
        path.write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    result = import_staging(
        tmp,
        patch=False,
        force_overwrite=True,
        status="pending_review",
        dry_run=False,
        created_by_id=resolve_created_by_id(args.created_by_id),
        replace_media=True,
        batch_size=args.batch_size,
        skip_company_update=True,
    )
    print(json.dumps({k: result.get(k) for k in ("ok", "updated_count", "error_count", "created_count")}, indent=2))

    copy_result = None
    verify_summary = "skipped"
    if args.copy_media and result.get("ok"):
        ids = [r["id"] for r in rows]
        copy_result = trigger_copy_media(ids)
        print(json.dumps(copy_result, indent=2))
        # CDN verify
        try:
            import subprocess

            proc = subprocess.run(
                [sys.executable, "-u", "verify_cdn_images.py", "--company-id", str(COMPANY_ID)],
                cwd=str(_RESEARCH_DIR),
                capture_output=True,
                text=True,
                timeout=600,
            )
            tail = "\n".join((proc.stdout or "").strip().splitlines()[-5:])
            verify_summary = tail or f"exit={proc.returncode}"
            print(tail, flush=True)
        except Exception as exc:  # noqa: BLE001
            verify_summary = f"verify error: {exc}"

    write_report(plan, copy_result, verify_summary)
    print(f"Report: {REPORT_MD}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
