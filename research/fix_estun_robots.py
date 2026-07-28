"""Full-fleet Estun (company 220) text/spec/video/tag enrich — no media wipe.

Sources:
- en.estun.com list cards (Reach / Payload / Axes / IP / industry)
- Name-encoded payload/reach for ER / iER / ECR / UNO / S / EMR patterns
- TagCatalog family tags
- Series-level YouTube (Estun title filter), reuse existing good videos

Does not invent prices. Release years only when already set (citation required).
Does not replace photos (replace_media=False; keeps current image/s3 URLs).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from estun_english_catalog import derive_estun_family_metadata  # noqa: E402
from import_staging import import_staging, resolve_created_by_id  # noqa: E402
from robot_auto_research import slugify_robot_name  # noqa: E402
from tag_suggest import TagCatalog  # noqa: E402
from web_extract import WebFetcher, parse_page  # noqa: E402
from youtube_metadata import enrich_video_list  # noqa: E402

COMPANY_ID = 220
COMPANY_SLUG = "estun-robotics"
COMPANY_NAME = "Estun Robotics"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

LIST_URLS = [
    "https://en.estun.com/?list_13/",
    "https://en.estun.com/?list_13_2/",
    "https://en.estun.com/?list_13_3/",
    "https://en.estun.com/?list_161/",
    "https://en.estun.com/?list_162/",
    "https://en.estun.com/?list_191/",
]

JUNK_FEATURE_MARKERS = (
    "about us",
    "filter criteria",
    "marketing activities",
    "ecological chain",
    "investor relations",
    "careers filter",
    "扫码关注",
)

# Exact TagCatalog names (pipe-separated).
TAGS_BY_FAMILY = {
    "estun:er": "Industrial|Industrial Robot|Industrial Arm|6-Axis|Manufacturing|Assembly|Factory Automation|Material Handling",
    "estun:ier": "Industrial|Industrial Robot|Industrial Arm|6-Axis|Manufacturing|Assembly|Factory Automation|Material Handling",
    "estun:er-db": "Industrial|Industrial Robot|Manufacturing|Factory Automation",
    "estun:ecr": "Industrial|Industrial Robot|palletizing|Material Handling|Warehouse Automation|Manufacturing",
    "estun:uno": "Industrial|Industrial Robot|Industrial Arm|6-Axis|Manufacturing|Factory Automation|Material Handling",
    "estun:collaborative": "Cobot|Collaborative|Industrial|Manufacturing|Assembly|6-Axis|Factory Automation",
    "estun:s-series": "Cobot|Collaborative|Industrial|Manufacturing|Assembly|6-Axis|Factory Automation",
    "estun:m-series": "AMR|Autonomous Mobile Robot|Mobile Manipulator|Industrial|Manufacturing|Warehouse Automation|Logistics",
    "estun:other": "Industrial|Industrial Robot|Manufacturing|Factory Automation",
}
TAGS_SCARA = "scara|Industrial|Industrial Robot|Manufacturing|Assembly|Pick-and-Place|Factory Automation|4-axis"

SERIES_YT_QUERIES = {
    "estun:er": "Estun industrial robot ER series",
    "estun:ier": "Estun iER industrial robot",
    "estun:er-db": "Estun robot",
    "estun:ecr": "Estun palletizing robot",
    "estun:uno": "Estun UNO robot",
    "estun:collaborative": "Estun collaborative robot EMR",
    "estun:s-series": "Estun S series collaborative robot",
    "estun:m-series": "Estun mobile manipulator Codroid",
    "estun:other": "Estun industrial robot",
    "scara": "Estun SCARA robot",
}

_YT_CACHE: dict[str, list[dict[str, str]]] = {}
SPEC_CATALOG_PATH = _RESEARCH_DIR / "staging" / "reports" / "estun_en_spec_catalog.json"
PREVIEW_PATH = _RESEARCH_DIR / "staging" / "reports" / "estun-fix-preview.json"


def _norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _core_name(name: str) -> str:
    n = (name or "").strip()
    for prefix in (
        "Estun Collaborative Robot ",
        "Estun M-Series Mobile Manipulator ",
        "Estun ",
    ):
        if n.startswith(prefix):
            n = n[len(prefix) :]
    return n.strip()


def is_junk_features(text: str) -> bool:
    low = (text or "").lower()
    if len(low.strip()) < 40:
        return True
    return any(m in low for m in JUNK_FEATURE_MARKERS)


def is_scara_name(name: str) -> bool:
    return bool(re.search(r"-(SC|SR)(?:-|$|/)", name or "", re.I))


def parse_specs_from_name(name: str) -> dict[str, Any]:
    """Best-effort Estun model-code payload/reach (cited as name convention)."""
    core = _core_name(name)
    upper = core.upper()
    out: dict[str, Any] = {}

    # ER-DB* are drive/SKU codes — do not treat digits as payload.
    if upper.startswith("ER-DB") or re.match(r"^ER-?DB", upper):
        return out

    # UNO-220-3100-HR
    m = re.match(r"^UNO-(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)", upper)
    if m:
        out["payload_kg"] = float(m.group(1))
        out["reach_mm"] = float(m.group(2))
        out["dof"] = 6
        return out

    # S20-180 Eco / S10-140 Pro
    m = re.match(r"^S(\d+)-(\d+(?:\.\d+)?)", upper)
    if m:
        out["payload_kg"] = float(m.group(1))
        out["reach_mm"] = float(m.group(2))
        if out["reach_mm"] < 20:
            out["reach_mm"] *= 10  # rare
        # S-series reaches are typically hundreds of mm already
        out["dof"] = 6
        return out

    # EMR-25 / EMR-25-Max
    m = re.match(r"^EMR-?(\d+)", upper)
    if m:
        out["payload_kg"] = float(m.group(1))
        out["dof"] = 6
        return out

    # M-15 / M-15-Pro
    m = re.match(r"^M-(\d+)", upper)
    if m:
        out["payload_kg"] = float(m.group(1))
        return out

    # ECR10-1300 / ECR20-1777.5
    m = re.match(r"^ECR(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)", upper)
    if m:
        out["payload_kg"] = float(m.group(1))
        out["reach_mm"] = float(m.group(2))
        return out

    # ER20/10-2000-HI — dual payload notation; use first payload + reach
    m = re.match(r"^I?ER(\d+)(?:[A-Z])?/(?:\d+)-(\d+(?:\.\d+)?)", upper)
    if m:
        out["payload_kg"] = float(m.group(1))
        out["reach_mm"] = float(m.group(2))
        out["dof"] = 6
        return out

    # iER8-720-MI / ER20-1780-MI / ER10-700-SR / ER60-2000-PL
    m = re.match(
        r"^I?ER(\d+(?:\.\d+)?)[A-Z]?-(\d+(?:\.\d+)?)(?:-|/|$)",
        upper,
    )
    if m:
        payload = float(m.group(1))
        reach = float(m.group(2))
        # Reject absurd (e.g. ER500-2800 is valid: 500kg / 2800mm)
        if payload <= 1000 and 200 <= reach <= 5000:
            out["payload_kg"] = payload
            out["reach_mm"] = reach
            if is_scara_name(name) or re.search(r"-(SC|SR)", upper):
                out["dof"] = 4
            elif re.search(r"-PL\b", upper):
                out["dof"] = 4
            else:
                out["dof"] = 6
    return out


def build_en_spec_catalog() -> dict[str, dict[str, Any]]:
    """Parse EN list cards into normalized model keys."""
    fetcher = WebFetcher(timeout=30, stealth=True)
    card_re = re.compile(
        r"(?P<name>"
        r"(?:i?ER[\w./\-]+|ECR[\w.\-]+|UNO-[\w\-]+|EMR-?[\w\-]+|"
        r"S\d+-[\d.]+(?:\s+(?:Eco|Pro))?|CO-RAY\s*\d+|CO-ARC\s*\d+|"
        r"Co-Palletizer\s*\d+[^\s]{0,30})"
        r")\s+"
        r"Reach[：:]\s*(?P<reach>[\d.]+)?\s*(?:MM|mm|m)?\s*"
        r"Payload[：:]\s*(?P<payload>[\d.]+)?\s*(?:KG|kg|Kg)?\s*"
        r"(?:Axes[：:]\s*(?P<axes>\d+(?:\s*-\s*\d+)?)\s*)?"
        r"(?:IP[：:]\s*(?P<ip>[Ii][Pp][\w；;，,\- ]{0,40}?)\s*)?"
        r"(?:Application industry[：:]\s*(?P<industry>.{0,80}?))?"
        r"(?=\s+(?:i?ER|ECR|UNO|EMR|S\d+|CO-|Co-Palletizer|Home page|Filter|Last page|Motion|\.ab_pag|\Z))",
        re.I,
    )
    catalog: dict[str, dict[str, Any]] = {}
    for url in LIST_URLS:
        page = parse_page(fetcher, url, rendered=False)
        if not page or not page.html:
            continue
        text = re.sub(r"<[^>]+>", " ", page.html)
        text = re.sub(r"\s+", " ", text)
        for m in card_re.finditer(text):
            name = re.sub(r"\s+", " ", (m.group("name") or "").strip())
            if len(name) < 4:
                continue
            payload_s = m.group("payload")
            reach_s = m.group("reach")
            if not payload_s and not reach_s:
                continue
            axes = m.group("axes") or ""
            dof = None
            am = re.match(r"(\d+)", axes.strip())
            if am:
                dof = int(am.group(1))
            ip = (m.group("ip") or "").strip()
            ip = re.split(r"\s+Application", ip, maxsplit=1)[0].strip(" ;,")
            # Normalize IP — take first IP token
            ip_m = re.search(r"IP\d+[A-Za-z0-9]*", ip, re.I)
            ip_rating = ip_m.group(0).upper() if ip_m else ""
            industry = (m.group("industry") or "").strip()
            industry = re.split(
                r"\s+(?:i?ER|ECR|UNO|EMR|S\d+|CO-|Co-Palletizer|Filter)",
                industry,
                maxsplit=1,
            )[0].strip(" .;：:")
            reach = float(reach_s) if reach_s else None
            if reach is not None and reach < 20:
                reach *= 1000
            entry = {
                "name": name,
                "payload_kg": float(payload_s) if payload_s else None,
                "reach_mm": reach,
                "dof": dof,
                "ip_rating": ip_rating,
                "industry": industry[:100],
                "source_url": url,
            }
            for key in {_norm_key(name), _norm_key(name.replace(" ", ""))}:
                if not key:
                    continue
                prev = catalog.get(key)
                if not prev or (entry.get("dof") and not prev.get("dof")):
                    catalog[key] = entry
    SPEC_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_CATALOG_PATH.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return catalog


def lookup_catalog(name: str, catalog: dict[str, dict]) -> dict | None:
    core = _core_name(name)
    keys = [
        _norm_key(core),
        _norm_key(name),
        _norm_key(core.removeprefix("i").removeprefix("I")),
        _norm_key("i" + core) if not core.lower().startswith("i") else "",
    ]
    # ER <-> iER
    if re.match(r"^ier", core, re.I):
        keys.append(_norm_key("ER" + core[3:]))
    elif re.match(r"^er", core, re.I):
        keys.append(_norm_key("i" + core))
    # S20-180 Eco spacing
    keys.append(_norm_key(core.replace(" ", "")))
    for k in keys:
        if k and k in catalog:
            return catalog[k]
    # fuzzy: same digits fingerprint
    fp = re.sub(r"[^0-9]", "", core)
    if len(fp) >= 4:
        for k, v in catalog.items():
            if re.sub(r"[^0-9]", "", v.get("name") or "") == fp:
                return v
    return None


def tags_for(name: str, family_key: str, catalog: TagCatalog) -> str:
    raw = TAGS_SCARA if is_scara_name(name) else TAGS_BY_FAMILY.get(family_key, TAGS_BY_FAMILY["estun:other"])
    names = [t.strip() for t in raw.split("|") if t.strip()]
    # Keep only names that exist in TagCatalog when catalog has data
    if catalog.tags:
        known = {
            str(t.get("name") or "").lower(): str(t.get("name") or "")
            for t in catalog.tags
            if t.get("name")
        }
        resolved = []
        for n in names:
            hit = known.get(n.lower())
            if hit:
                resolved.append(hit)
        if resolved:
            return "|".join(dict.fromkeys(resolved))
    return "|".join(dict.fromkeys(names))


def existing_video_urls(robot: dict) -> list[str]:
    out: list[str] = []
    for v in robot.get("videos") or robot.get("linked_videos") or []:
        if isinstance(v, dict) and v.get("url"):
            out.append(str(v["url"]).strip())
        elif isinstance(v, str) and v.strip():
            out.append(v.strip())
    return list(dict.fromkeys(out))


def search_youtube_series(cache_key: str, query: str, *, limit: int = 2) -> list[dict[str, str]]:
    if cache_key in _YT_CACHE:
        return list(_YT_CACHE[cache_key])
    try:
        resp = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers=HEADERS,
            timeout=30,
        )
    except requests.RequestException:
        _YT_CACHE[cache_key] = []
        return []
    ids = []
    for vid in re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', resp.text or ""):
        if vid not in ids:
            ids.append(vid)
        if len(ids) >= 8:
            break
    urls = [f"https://www.youtube.com/watch?v={v}" for v in ids]
    enriched = enrich_video_list(urls)
    # Prefer titles mentioning Estun / robot tokens. Keep the full enriched dict
    # ({url, title, description}) so imported RobotVideos carry a title.
    kept: list[dict[str, str]] = []
    for item in enriched:
        title = (item.get("title") or "").lower()
        url = item.get("url") or ""
        if not url or not title:
            continue
        if any(bad in title for bad in ("karaoke", "minecraft", "music video", "roblox")):
            continue
        if "estun" in title or "埃斯顿" in title or "robot" in title or "scara" in title:
            kept.append(item)
        if len(kept) >= limit:
            break
    if not kept:
        # fail open to first enriched with any title
        kept = [e for e in enriched if e.get("title") and e.get("url")][:limit]
    _YT_CACHE[cache_key] = kept
    return list(kept)


def build_features(
    *,
    name: str,
    family_name: str,
    payload: float | None,
    reach: float | None,
    dof: int | None,
    ip: str,
    industry: str,
) -> str:
    bits = [f"Estun {family_name} model {_core_name(name)}."]
    spec_bits = []
    if payload is not None:
        spec_bits.append(f"payload {payload:g} kg")
    if reach is not None:
        spec_bits.append(f"reach {reach:g} mm")
    if dof is not None:
        spec_bits.append(f"{dof} axes")
    if ip:
        spec_bits.append(ip)
    if spec_bits:
        bits.append("Cited specs: " + ", ".join(spec_bits) + ".")
    if industry:
        bits.append(f"Application industry: {industry}.")
    if is_scara_name(name):
        bits.append("SCARA configuration for high-speed pick-and-place and assembly.")
    elif "pallet" in industry.lower() or "ECR" in name.upper() or name.upper().startswith("ECR"):
        bits.append("Configured for palletizing / material handling workflows.")
    elif "collaborative" in family_name.lower() or name.upper().startswith("S") or "EMR" in name.upper():
        bits.append("Collaborative robot intended for human-nearby industrial tasks.")
    elif "mobile" in family_name.lower():
        bits.append("Mobile manipulator combining a mobile base with a robotic arm.")
    else:
        bits.append("Industrial articulated robot for manufacturing automation.")
    # The source URL is NOT inlined here — it travels in the row's "sources"
    # list and lands in Information Sources on import.
    return " ".join(bits)


def merge_specs(name: str, cat: dict | None) -> dict[str, Any]:
    named = parse_specs_from_name(name)
    out: dict[str, Any] = {}
    for key in ("payload_kg", "reach_mm", "dof", "ip_rating", "industry", "source_url"):
        if cat and cat.get(key) not in (None, ""):
            out[key] = cat[key]
    # Prefer catalog numeric when present; fill gaps from name
    if out.get("payload_kg") is None and named.get("payload_kg") is not None:
        out["payload_kg"] = named["payload_kg"]
        out.setdefault("spec_source", "model_name_convention")
    if out.get("reach_mm") is None and named.get("reach_mm") is not None:
        out["reach_mm"] = named["reach_mm"]
        out.setdefault("spec_source", "model_name_convention")
    if out.get("dof") is None and named.get("dof") is not None:
        out["dof"] = named["dof"]
    # Cross-check: if both disagree wildly on payload, prefer catalog
    if (
        cat
        and cat.get("payload_kg") is not None
        and named.get("payload_kg") is not None
        and abs(float(cat["payload_kg"]) - float(named["payload_kg"])) > 5
    ):
        out["payload_kg"] = float(cat["payload_kg"])
    if (
        cat
        and cat.get("reach_mm") is not None
        and named.get("reach_mm") is not None
        and abs(float(cat["reach_mm"]) - float(named["reach_mm"])) > 80
    ):
        out["reach_mm"] = float(cat["reach_mm"])
    if cat and cat.get("source_url"):
        out["source_url"] = cat["source_url"]
        out["spec_source"] = "en.estun.com_list_card"
    return out


def build_row(
    robot: dict,
    *,
    catalog: dict[str, dict],
    tag_catalog: TagCatalog,
) -> dict[str, Any]:
    name = robot["name"]
    family = derive_estun_family_metadata(name)
    family_key = robot.get("family_key") or family["family_key"]
    family_name = robot.get("family_name") or family["family_name"]
    cat = lookup_catalog(name, catalog)
    specs = merge_specs(name, cat)

    payload = specs.get("payload_kg")
    reach = specs.get("reach_mm")
    dof = specs.get("dof")
    ip = specs.get("ip_rating") or ""
    industry = specs.get("industry") or ""
    source_url = specs.get("source_url") or (robot.get("url") or "https://en.estun.com/")

    existing_feat = (robot.get("features") or "").strip()
    features = build_features(
        name=name,
        family_name=family_name or "industrial robot",
        payload=float(payload) if payload is not None else None,
        reach=float(reach) if reach is not None else None,
        dof=int(dof) if dof is not None else None,
        ip=ip,
        industry=industry,
    )
    if not is_junk_features(existing_feat) and len(existing_feat) > len(features) + 40:
        # Keep richer prior curated copy, append cited specs line if missing
        features = existing_feat
        if payload is not None and f"{payload:g} kg" not in features.lower():
            features = features.rstrip(".") + f". Cited payload {payload:g} kg."

    description = (robot.get("description") or "").strip()
    if is_junk_features(description) or len(description) < 40:
        bits = [f"Estun {_core_name(name)}"]
        if payload is not None:
            bits.append(f"{payload:g} kg payload")
        if reach is not None:
            bits.append(f"{reach:g} mm reach")
        description = " — ".join(bits) + f" ({family_name})."

    # Enrich existing videos so their titles are preserved (not re-blanked).
    videos = enrich_video_list(existing_video_urls(robot))
    if not videos:
        yt_key = "scara" if is_scara_name(name) else family_key
        query = SERIES_YT_QUERIES.get(yt_key) or SERIES_YT_QUERIES["estun:other"]
        videos = search_youtube_series(yt_key, query, limit=2)

    # Preserve media — never invent new image URLs here
    image = (robot.get("image") or "").strip()
    s3 = (robot.get("s3_image") or "").strip()
    # Prefer keeping OEM external if present; else leave image as current (may be CDN)
    keep_image = image if image.startswith("http") else s3

    notes_parts = []
    if payload is not None:
        notes_parts.append(f"Payload: {float(payload):g} kg")
    if reach is not None:
        notes_parts.append(f"Reach: {float(reach):g} mm")
    if specs.get("spec_source"):
        notes_parts.append(f"spec_source={specs['spec_source']}")

    row: dict[str, Any] = {
        "id": robot["id"],
        "name": name,
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "model_name": robot.get("model_name") or name,
        "manufacturer_country_code": "CN",
        "description": description[:1200],
        "purpose": (robot.get("purpose") or "").strip() or features[:1200],
        "features": features,
        "url": (robot.get("url") or "").strip() or source_url,
        "tags": tags_for(name, family_key, tag_catalog),
        "video_urls": videos,
        "movement_type_keys": "wheeled" if family_key == "estun:m-series" else "stationary",
        "category_slugs": "industrial-robots",
        "sub_category_slug": (
            "logistics-warehouse"
            if family_key in {"estun:m-series", "estun:ecr"}
            else "manufacturing-industrial"
        ),
        "availability_status_key": "available",
        "family_key": family_key,
        "family_name": family_name,
        "variant_code": robot.get("variant_code") or family.get("variant_code") or "",
        "product_url_scope": robot.get("product_url_scope") or family.get("product_url_scope") or "",
        "sources": [{"url": source_url, "type": "website", "title": name}],
        "research_notes": (
            "Estun full-fleet enrich 2026-07-16 from EN list cards + model-name conventions. "
            "Images preserved (no replace_media). Price omitted (not published by OEM)."
        ),
    }
    if keep_image:
        row["image"] = keep_image
    if notes_parts:
        row["notes"] = " | ".join(notes_parts)
    if payload is not None:
        row["payload_kg"] = float(payload)
    if reach is not None:
        row["reach_mm"] = float(reach)
    if dof is not None:
        row["dof"] = int(dof)
    if ip:
        row["ip_rating"] = ip
    # Preserve cited release_year only
    if robot.get("release_year"):
        row["release_year"] = robot["release_year"]
        row["research_notes"] += f" Kept existing release_year={robot['release_year']}."
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Full-fleet Estun enrich (no media wipe)")
    parser.add_argument("--company-id", type=int, default=COMPANY_ID)
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rebuild-catalog", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only-ids", nargs="*", type=int)
    args = parser.parse_args()

    if args.rebuild_catalog or not SPEC_CATALOG_PATH.is_file():
        print("Building EN spec catalog…", flush=True)
        catalog = build_en_spec_catalog()
    else:
        catalog = json.loads(SPEC_CATALOG_PATH.read_text(encoding="utf-8"))
    print(f"spec catalog entries: {len(catalog)}", flush=True)

    client = ResearchApiClient()
    tag_catalog = TagCatalog.load(client=client)
    robots = [
        r
        for r in client.list_robots_for_company(args.company_id)
        if (r.get("status") or "") == "pending_review"
    ]
    if args.only_ids:
        want = set(args.only_ids)
        robots = [r for r in robots if r["id"] in want]
    if args.limit:
        robots = robots[: args.limit]

    rows: list[dict] = []
    preview: list[dict] = []
    for robot in robots:
        row = build_row(robot, catalog=catalog, tag_catalog=tag_catalog)
        rows.append(row)
        preview.append(
            {
                "id": row["id"],
                "name": row["name"],
                "family_key": row.get("family_key"),
                "features_len": len(row.get("features") or ""),
                "payload_kg": row.get("payload_kg"),
                "reach_mm": row.get("reach_mm"),
                "dof": row.get("dof"),
                "ip_rating": row.get("ip_rating"),
                "tags": row.get("tags"),
                "videos": len(row.get("video_urls") or []),
                "junk_features_replaced": is_junk_features(robot.get("features") or ""),
                "kept_image": bool(row.get("image")),
            }
        )

    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREVIEW_PATH.write_text(json.dumps(preview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    stats = {
        "total": len(preview),
        "with_features": sum(1 for p in preview if p["features_len"] >= 40),
        "with_payload": sum(1 for p in preview if p.get("payload_kg") is not None),
        "with_reach": sum(1 for p in preview if p.get("reach_mm") is not None),
        "with_videos": sum(1 for p in preview if p["videos"] > 0),
        "with_tags": sum(1 for p in preview if p.get("tags")),
        "families": dict(Counter(p.get("family_key") for p in preview)),
    }
    print(json.dumps(stats, indent=2))
    print(f"preview: {PREVIEW_PATH}")

    missing_feat = [p for p in preview if p["features_len"] < 40]
    missing_tags = [p for p in preview if not p.get("tags")]
    missing_vids = [p for p in preview if p["videos"] < 1]
    if missing_feat or missing_tags or missing_vids:
        print(
            f"WARN incomplete: feat={len(missing_feat)} tags={len(missing_tags)} vids={len(missing_vids)}",
            flush=True,
        )
        for p in (missing_feat + missing_tags + missing_vids)[:15]:
            print(f"  {p['id']} {p['name']} feat={p['features_len']} vids={p['videos']} tags={bool(p.get('tags'))}")

    if not args.apply:
        print("Dry-run only. Re-run with --apply")
        return 0 if stats["with_features"] == stats["total"] else 1

    tmp = Path(tempfile.mkdtemp(prefix="estun-fix-"))
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
        replace_media=False,
        batch_size=args.batch_size,
        skip_company_update=True,
    )
    print(json.dumps({k: result.get(k) for k in ("ok", "updated_count", "error_count", "skipped_count", "created_count")}, indent=2))
    if result.get("errors"):
        print("errors sample:", json.dumps(result["errors"][:5], indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
