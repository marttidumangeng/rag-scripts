#!/usr/bin/env python3
"""Enrich newly discovered KUKA robots (company 1396, ids >= 5374).

Pass goals (per stakeholder 2026-07-18):
  - OEM family-table specs (payload_kg / reach_mm via DRF PATCH)
  - Family product renders (accepted KUKA trade: per-family, not per-variant)
  - Outside sources via Serper (RoboDK, DigiKey, robots.com, my.KUKA, …)
    with evidence that the page names the model — stored as citations +
    RobotInformationSource
  - Price/videos optional — only attach when a clear hit exists
  - Imageless families get an IMAGE TO-DO note (fail closed)

Usage:
  python -u enrich_kuka_depth.py                 # dry-run
  python -u enrich_kuka_depth.py --apply
  python -u enrich_kuka_depth.py --apply --copy-media
  python -u enrich_kuka_depth.py --only 5374 5375 --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from citations import sync_information_sources
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row
from product_url_search import _serper_google_search
from web_extract import WebFetcher

COMPANY_ID = 1396
COMPANY_SLUG = "kuka"
COMPANY_NAME = "KUKA"
RECON_PATH = _RESEARCH_DIR / "staging" / "reports" / "kuka-recon.json"
IMPORT_RESULT = _RESEARCH_DIR / "staging" / "reports" / "kuka_recommend_import_result.json"
EVIDENCE_DIR = _RESEARCH_DIR / "staging" / "evidence" / "kuka-depth-20260718"
PLAN_PATH = _RESEARCH_DIR / "staging" / "reports" / "kuka_enrich_plan.json"
MIN_NEW_ID = 5374

# Visually screened family heroes (logo/svg rejected; iiwa generic lineup rejected).
FAMILY_RENDER: dict[str, str] = {
    "kr-agilus": "https://www.kuka.com/-/media/kuka-corporate/images/products/robots/kr-agilus/kr-agilus.jpg",
    "kr-cybertech": "https://www.kuka.com/-/media/kuka-corporate/images/products/robots/kr-cybertech/cybertech_2.jpg",
    "kr-cybertech-arc": "https://www.kuka.com/-/media/kuka-corporate/images/products/robots/kr-cybertech/cybertech-arc.jpg",
    "kr-cybertech-nano": "https://www.kuka.com/-/media/kuka-corporate/images/products/robots/kr-cybertech/kr-cybertech_nano_2.jpg",
    "kr-cybertech-nano-arc": "https://www.kuka.com/-/media/kuka-corporate/images/products/robots/kr-cybertech/kr-cybertech_nano_2.jpg",
    "kr-iontec": "https://www.kuka.com/-/media/kuka-corporate/images/products/robots/kr-iontec/kr_iontec_robot_features.jpg",
    # kr-fortec / kr-fortec-ultra: only 22MB PNG or multi-family promo lineup found — leave imageless
    "kr-fortec-pa": "https://www.kuka.com/-/media/kuka-corporate/images/products/robots/kr-fortec/kr-fortec-pa/kr-470-r3200-2-pa_teaser.jpg",
    "kr-1000-titan": "https://www.kuka.com/-/media/kuka-corporate/images/products/robots/kr-titan/kr-1000-titan_header.jpg",
    "kr-quantec": "https://www.kuka.com/-/media/kuka-corporate/images/products/robots/cta-images/kr-quantec.png?rev=-1",
    "kr-quantec-pa": "https://www.kuka.com/-/media/kuka-corporate/images/products/robots/kr-quantec/kr_quantec_pa_header_teaser.jpg",
    "kr-scara-robot": "https://www.kuka.com/-/media/kuka-corporate/images/products/robots/kr-scara/kuka-kr-scara-industrial-robot-with-4-axes.jpg",
    "lbr-iisy": "https://www.kuka.com/-/media/kuka-corporate/images/products/robots/lbr-iisy-cobot/kuka-lbr-iisy-industrial-cobot-flexible-automation.jpg",
    # lbr-iiwa / kr-fortec / kr-fortec-ultra / kr-fortec-ultra-pa: no accepted single-family hero
}

ALLOWED_EXT_HOSTS = (
    "robodk.com",
    "digikey.com",
    "robots.com",
    "directindustry.com",
    "my.kuka.com",
    "kuka.com",
    "ieee.org",
    "automationworld.com",
    "robotics.org",
    "therobotreport.com",
)

IMAGE_TODO = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "KUKA family page for {family} did not yield a verified model-specific or "
    "accepted family render during 2026-07-18 enrich (generic lineup / logo only).\n"
    "ACTION FOR TEAM: source a licensed/model-specific image or attach a vetted "
    "family render from KUKA media library.\n"
    "Do NOT substitute a sibling render, a family banner, or marketing/diagram art.\n"
    "---\n"
)


def _admin_base() -> str:
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")


def _secret() -> str:
    s = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if s:
        return s
    env = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def _copy_media(rid: int, secret: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    try:
        resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
        return "ok" if resp.ok else f"HTTP {resp.status_code} {resp.text[:120]}"
    except requests.RequestException as exc:
        return f"ERR {exc}"


def parse_kg(text: str) -> float | None:
    m = re.search(r"([\d.]+)\s*kg", text or "", re.I)
    return float(m.group(1)) if m else None


def parse_mm(text: str) -> float | None:
    m = re.search(r"([\d.]+)\s*mm", text or "", re.I)
    return float(m.group(1)) if m else None


def model_tokens(name: str) -> list[str]:
    """Tokens that should appear on a citing page (order-insensitive)."""
    n = re.sub(r"[^A-Za-z0-9]+", " ", name).upper().split()
    # keep significant tokens (drop lone letters)
    return [t for t in n if len(t) >= 2]


def page_mentions_model(text: str, name: str) -> bool:
    if not text:
        return False
    upper = text.upper()
    tokens = model_tokens(name)
    if len(tokens) < 2:
        return name.upper() in upper
    # require majority of tokens
    hits = sum(1 for t in tokens if t in upper)
    return hits >= max(2, (len(tokens) + 1) // 2)


def host_allowed(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return any(host == h or host.endswith("." + h) for h in ALLOWED_EXT_HOSTS)


def find_recon(catalog: dict[str, dict[str, Any]], name: str) -> dict[str, Any] | None:
    if name in catalog:
        return catalog[name]
    # soft: collapse whitespace
    soft = {re.sub(r"\s+", " ", k).strip(): v for k, v in catalog.items()}
    return soft.get(re.sub(r"\s+", " ", name).strip())


_search_cache: dict[str, list[dict[str, Any]]] = {}
_fetch_cache: dict[str, str] = {}


def serper_external(name: str, *, fetcher: WebFetcher) -> list[dict[str, Any]]:
    """Return verified external citations for this model."""
    q = f'KUKA "{name}" robot'
    if q not in _search_cache:
        _search_cache[q] = _serper_google_search(q, max_results=8)
        time.sleep(0.35)
    hits = _search_cache[q]
    cites: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in hits:
        url = (item.get("link") or "").strip()
        title = (item.get("title") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        if not url or url in seen or not host_allowed(url):
            continue
        # Skip pure family marketing pages on kuka.com (already have OEM family URL)
        if "kuka.com" in urlparse(url).netloc and "/industrial-robots/" in url and name.lower().replace(" ", "-") not in url.lower():
            # allow my.kuka product SKUs
            if "my.kuka.com" not in urlparse(url).netloc:
                continue
        seen.add(url)
        # Evidence: snippet or fetched text must mention model
        blob = f"{title}\n{snippet}"
        if not page_mentions_model(blob, name):
            if url not in _fetch_cache:
                page = fetcher.get(url) or ""
                _fetch_cache[url] = page[:50000]
                time.sleep(0.2)
            blob = _fetch_cache[url]
            if not page_mentions_model(blob, name):
                continue
        cites.append(
            {
                "url": url,
                "title": title[:120],
                "snippet": snippet[:240],
                "source_type": "website",
            }
        )
        if len(cites) >= 3:
            break
    return cites


def build_features(name: str, rec: dict[str, Any], cites: list[dict[str, Any]]) -> str:
    bits = [f"KUKA industrial robot: {name}"]
    if rec.get("total_load"):
        bits.append(f"Total load: {rec['total_load']} (OEM family table)")
    if rec.get("max_reach") or rec.get("maximum_reach"):
        bits.append(
            f"Maximum reach: {rec.get('max_reach') or rec.get('maximum_reach')} (OEM family table)"
        )
    if rec.get("version_environment"):
        bits.append(f"Version / environment: {rec['version_environment']}")
    if rec.get("construction_type"):
        bits.append(f"Construction type: {rec['construction_type']}")
    if rec.get("protection_class"):
        bits.append(f"Protection class: {rec['protection_class']}")
    if rec.get("mounting_positions"):
        bits.append(f"Mounting positions: {rec['mounting_positions']}")
    if rec.get("controller"):
        bits.append(f"Controller: {rec['controller']}")
    if cites:
        bits.append("External references (verified model mention):")
        for c in cites:
            bits.append(f"- {c['title'] or c['url']}: {c['url']}")
    return "\n".join(bits)


def build_notes(
    existing: str,
    *,
    family: str,
    oem_url: str,
    cites: list[dict[str, Any]],
    image_note: str,
) -> str:
    source_urls = [oem_url] + [c["url"] for c in cites]
    sources_line = "Sources: " + " | ".join(dict.fromkeys(u for u in source_urls if u))
    cite_block = (
        "[ENRICH 2026-07-18 — KUKA depth]\n"
        f"OEM family={family}\n"
        f"{sources_line}\n"
        "Specs (payload_kg/reach_mm) from KUKA family products table "
        "(data-load-capacity / data-reach); external URLs verified to mention model tokens.\n"
    )
    if image_note:
        cite_block = image_note + cite_block
    # keep prior notes without duplicating enrich block
    if "[ENRICH 2026-07-18 — KUKA depth]" in (existing or ""):
        return existing
    return (cite_block + ("---\n" + existing if existing else "")).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--only", type=int, nargs="*")
    ap.add_argument("--skip-serper", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0, help="Cap robots processed (0=all)")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    catalog = json.loads(RECON_PATH.read_text(encoding="utf-8"))
    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID)
    targets = [
        r
        for r in robots
        if int(r.get("id") or 0) >= MIN_NEW_ID
        and str(r.get("status") or "").lower() == "pending_review"
    ]
    if args.only:
        only = set(args.only)
        targets = [r for r in targets if int(r["id"]) in only]
    if args.limit:
        targets = targets[: args.limit]

    fetcher = WebFetcher(stealth=False)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    plan: list[dict[str, Any]] = []

    for r in targets:
        rid = int(r["id"])
        name = r.get("name") or ""
        rec = find_recon(catalog, name) or {}
        family = rec.get("family") or ""
        oem_url = (
            rec.get("url")
            or r.get("website_url")
            or r.get("url")
            or ""
        )
        cites: list[dict[str, Any]] = []
        if not args.skip_serper:
            cites = serper_external(name, fetcher=fetcher)

        payload = parse_kg(rec.get("total_load") or "")
        reach = parse_mm(rec.get("max_reach") or rec.get("maximum_reach") or "")
        # reject zero placeholders
        if payload == 0:
            payload = None
        if reach == 0:
            reach = None

        render = FAMILY_RENDER.get(family) if family else None
        image_note = ""
        if not render:
            image_note = IMAGE_TODO.format(family=family or "(unknown)")

        features = build_features(name, rec, cites)
        notes = build_notes(
            r.get("notes") or "",
            family=family,
            oem_url=oem_url,
            cites=cites,
            image_note=image_note,
        )
        info_urls = [oem_url] + [c["url"] for c in cites]

        entry = {
            "id": rid,
            "name": name,
            "family": family,
            "oem_url": oem_url,
            "payload_kg": payload,
            "reach_mm": reach,
            "image": render,
            "external_count": len(cites),
            "external": cites,
            "features": features,
            "notes": notes,
            "information_source_urls": [u for u in info_urls if u],
        }
        plan.append(entry)

        # evidence file
        ev = EVIDENCE_DIR / f"{rid}-{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}.json"
        ev.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        print(
            f"{rid} {name[:28]:<28} fam={family:<18} "
            f"payload={payload} reach={reach} img={'Y' if render else 'N'} "
            f"ext={len(cites)}"
        )

    PLAN_PATH.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nplan {len(plan)} → {PLAN_PATH}")
    print(f"evidence → {EVIDENCE_DIR}")
    with_img = sum(1 for p in plan if p.get("image"))
    with_ext = sum(1 for p in plan if p.get("external_count"))
    with_specs = sum(1 for p in plan if p.get("payload_kg") or p.get("reach_mm"))
    print(f"summary: img={with_img}/{len(plan)} specs={with_specs}/{len(plan)} ext_cites={with_ext}/{len(plan)}")

    if not args.apply:
        print("dry-run only; pass --apply to write")
        return 0

    secret = _secret() if args.copy_media else ""
    created_by = resolve_created_by_id(args.created_by_id)
    ok = fail = 0
    for p in plan:
        rid = p["id"]
        # 1) Surgical PATCH for narrative + typed specs + sources
        # (bulk patch_existing will not overwrite non-blank features)
        patch_body: dict[str, Any] = {
            "source_locale": "en",
            "features": p["features"],
            "notes": p["notes"],
            "information_source_urls": p["information_source_urls"],
        }
        if p.get("oem_url"):
            patch_body["url"] = p["oem_url"]
            patch_body["website_url"] = p["oem_url"]
        if p.get("payload_kg") is not None:
            patch_body["payload_kg"] = p["payload_kg"]
        if p.get("reach_mm") is not None:
            patch_body["reach_mm"] = p["reach_mm"]
        try:
            patched = client._patch(f"robots/robots/{rid}/", patch_body)
            print(
                f"patch {rid}: payload={patched.get('payload_kg')} "
                f"reach={patched.get('reach_mm')} "
                f"feat_len={len(patched.get('features') or '')} "
                f"sources={len(patched.get('information_sources') or [])}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL patch {rid}: {exc}")
            fail += 1
            continue

        # 2) Media via bulk replace_media only when we have a vetted family render
        if p.get("image"):
            row = staging_dict_to_bulk_import_row(
                {
                    "id": rid,
                    "name": p["name"],
                    "company_slug": COMPANY_SLUG,
                    "image": p["image"],
                    "images": [{"url": p["image"]}],
                    "source_locale": "en",
                    "research_notes": (
                        f"[media] 2026-07-18: official KUKA {p['family']} family render; "
                        "KUKA publishes per-family not per-variant (accepted trade)."
                    ),
                }
            )
            row["id"] = rid
            try:
                res = client.bulk_import_robots(
                    [row],
                    update_existing=True,
                    patch_existing=True,
                    replace_media=True,
                    status="pending_review",
                    skip_company_update=True,
                    created_by_id=created_by,
                )
                print(
                    f"  media updated={res.get('updated_count')} "
                    f"errors={res.get('error_count')}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  FAIL media {rid}: {exc}")
                fail += 1
                continue

        try:
            sync_information_sources(client, rid)
        except Exception as exc:  # noqa: BLE001
            print(f"  WARN sources {rid}: {exc}")

        if args.copy_media and p.get("image") and secret:
            status = _copy_media(rid, secret)
            print(f"  copy-media {status}")
            if not status.startswith("ok"):
                fail += 1
            else:
                ok += 1
        else:
            ok += 1
        time.sleep(0.12)

    print(f"\nDONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
