from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from map_to_bulk_import import staging_dict_to_bulk_import_row
from tag_suggest import TagCatalog
from youtube_metadata import enrich_video_list, is_reject_robot_video_title
from web_extract import WebFetcher, extract_specs_from_text, parse_page, robot_name_tokens


COMPANY_ID = 227
COMPANY_SLUG = "hanwha-robotics"
COMPANY_NAME = "Hanwha Robotics"
COMPANY_WEBSITE = "https://www.hanwharobotics.com"

COBOT_HUB_URL = "https://www.hanwharobotics.com/en/product/cobot?menuSeq=2"
AGV_AMR_HUB_URL = "https://www.hanwharobotics.com/en/product/agv_amr?menuSeq=3"

_AVAIL_IDS = {
    "announced": 10,
    "available": 11,
    "released": 3,
    "discontinued": 4,
    "pre_order": 12,
}


def _admin_base() -> str:
    api = (os.environ.get("IMPORT_SYNC_API_BASE_URL") or "").rstrip("/")
    if api.endswith("/api/v1"):
        return api[: -len("/api/v1")]
    return api.rsplit("/api/", 1)[0] if "/api/" in api else api


def _internal_secret() -> str:
    # Prefer explicit env var; then fall back to server .env files.
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


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = _internal_secret()
    api = _admin_base()
    if not secret:
        print("WARN: no INTERNAL_API_SECRET for copy-media", file=sys.stderr)
        return 0, len(robot_ids)
    if not api:
        print("WARN: no IMPORT_SYNC_API_BASE_URL for admin copy-media", file=sys.stderr)
        return 0, len(robot_ids)

    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            success = False
            body: dict[str, Any] = {}
            try:
                body = resp.json() if resp.content else {}
            except Exception:
                body = {}
            if "success" in body:
                success = bool(body.get("success"))
            else:
                success = bool(resp.ok)

            if resp.ok and success:
                ok += 1
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code} body={body}", flush=True)
        except requests.RequestException as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.15)
    return ok, fail


def _normalize_hanwha_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("//"):
        return "https:" + url
    # Some queue rows store "/www.hanwharobotics.com/..." (missing scheme).
    if url.startswith("/"):
        u = url.lstrip("/")
        if u.startswith("www."):
            return "https://" + u
    if url.startswith("www."):
        return "https://" + url
    # Best-effort for unexpected formats.
    return url


def _as_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        fv = float(value)
    except Exception:
        return None
    if abs(fv - int(fv)) < 1e-6:
        return int(fv)
    return None


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _extract_dof(text: str) -> int | None:
    # Hanwha cobot PDPs often contain "DOF 6" (label before number), which the
    # generic extract_specs_from_text does not parse.
    m = re.search(r"\bDOF\s*(\d{1,2})\b", text or "", flags=re.I)
    if m:
        v = int(m.group(1))
        if 1 <= v <= 20:
            return v
    return None


def _extract_dimensions_mm(text: str) -> dict[str, float] | None:
    text = text or ""
    # Cobot PDP: "Size (W x H x D) 550 x 482 x 251mm"
    cobot = re.search(
        r"Size\s*\(\s*W\s*[x×]\s*H\s*[x×]\s*D\s*\)\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*mm",
        text,
        flags=re.I,
    )
    if cobot:
        w, h, d = (float(cobot.group(i)) for i in range(1, 4))
        # RobotAIGeek expects length/width/height; map D to length.
        return {"width_mm": w, "height_mm": h, "length_mm": d}

    # Mobile robot PDP: "Hardware Dimension W580 x L850 x H350 mm"
    hw = re.search(
        r"Hardware\s*Dimension\s*W\s*(\d+(?:\.\d+)?)\s*[x×]\s*L\s*(\d+(?:\.\d+)?)\s*[x×]\s*H\s*(\d+(?:\.\d+)?)\s*mm",
        text,
        flags=re.I,
    )
    if hw:
        w, l, h = (float(hw.group(i)) for i in range(1, 4))
        return {"width_mm": w, "length_mm": l, "height_mm": h}

    # Fallback without the "Hardware Dimension" label.
    hw2 = re.search(
        r"\bW\s*(\d+(?:\.\d+)?)\s*[x×]\s*L\s*(\d+(?:\.\d+)?)\s*[x×]\s*H\s*(\d+(?:\.\d+)?)\s*mm\b",
        text,
        flags=re.I,
    )
    if hw2:
        w, l, h = (float(hw2.group(i)) for i in range(1, 4))
        return {"width_mm": w, "length_mm": l, "height_mm": h}

    return None


def _extract_payload_kg(text: str) -> float | None:
    # web_extract.extract_specs_from_text uses a broad "\d+ kg" payload pattern,
    # which can accidentally pick up prose "weight of only XX kg" before the
    # actual "Payload XX kg" label on Hanwha cobot pages.
    t = text or ""
    for pat in (
        r"\bPayload\s*Max\.?\s*(\d+(?:\.\d+)?)\s*kg\b",
        r"\bPayload\s*(\d+(?:\.\d+)?)\s*kg\b",
    ):
        m = re.search(pat, t, flags=re.I)
        if m:
            return float(m.group(1))
    return None


def _build_description_and_features(
    *,
    name: str,
    kind: str,
    specs: dict[str, Any],
    dims: dict[str, float] | None,
) -> tuple[str, str]:
    # Keep prose minimal, deterministic, and free from source URLs.
    if kind == "cobot":
        payload = specs.get("payload_kg")
        reach = specs.get("reach_mm")
        repeat = specs.get("repeatability_mm")
        dof = specs.get("dof")
        weight = specs.get("weight_kg")
        voltage = specs.get("voltage")
        dim_bits = []
        if dims:
            dim_bits.append(
                f"Size W{dims.get('width_mm'):g} x H{dims.get('height_mm'):g} x L{dims.get('length_mm'):g} mm"
            )
        spec_bits = []
        if payload is not None:
            spec_bits.append(f"max payload {payload:g} kg")
        if reach is not None:
            spec_bits.append(f"reach {reach:g} mm")
        if repeat is not None:
            spec_bits.append(f"repeatability ±{repeat:g} mm")
        if dof is not None:
            spec_bits.append(f"{dof:d} DOF")
        if weight is not None:
            spec_bits.append(f"mass {weight:g} kg")
        if voltage:
            spec_bits.append(f"power {voltage}")

        description = (
            f"{name} is a Hanwha Robotics collaborative robot for precision industrial automation "
            f"with {', '.join(spec_bits)}."
        ).strip()
        if not dim_bits:
            dim_bits = []
        features = (
            f"Official OEM product page lists: {', '.join(spec_bits) if spec_bits else 'key specifications'}. "
            + (" ".join(dim_bits) + ". " if dim_bits else "")
            + "6-axis articulated motion with configurable I/O for integration in manufacturing lines."
        ).strip()
        return description[:1200], features[:2500]

    # Mobile robot / AGV / AMR
    payload = specs.get("payload_kg")
    reach = specs.get("reach_mm")
    weight = specs.get("weight_kg")
    speed = specs.get("speed")
    dim_bits = []
    if dims:
        dim_bits.append(
            f"Hardware Dimension W{dims.get('width_mm'):g} x L{dims.get('length_mm'):g} x H{dims.get('height_mm'):g} mm"
        )

    spec_bits = []
    if payload is not None:
        spec_bits.append(f"payload {payload:g} kg")
    if speed is not None:
        spec_bits.append(f"max speed {speed:g} km/h")
    if weight is not None:
        spec_bits.append(f"weight {weight:g} kg")
    if reach is not None:
        spec_bits.append(f"reach {reach:g} mm")

    description = (
        f"{name} is a Hanwha Robotics autonomous mobile robot for industrial material transport "
        f"with {', '.join(spec_bits) if spec_bits else 'published mobility specifications'}."
    ).strip()
    features = (
        f"OEM specs cited on the product page: {', '.join(spec_bits) if spec_bits else 'key mobility and capacity figures'}. "
        + (" ".join(dim_bits) + ". " if dim_bits else "")
        + "Differential drive with SLAM navigation for indoor industrial environments."
    ).strip()
    return description[:1200], features[:2500]


def _desired_tags_for_robot(name: str, kind: str) -> str:
    # Tags must be exact catalog names; we resolve through TagCatalog later.
    if kind == "cobot":
        return "Cobot|Collaborative Robot|6-Axis|Stationary|Industrial|Manufacturing|Assembly|Pick-and-Place"

    is_amr = name.lower().startswith("amr")
    if is_amr:
        return "AMR|Autonomous Mobile Robot|Wheeled|Industrial|Logistics|Delivery"
    return "AGV|Autonomous Mobile Robot|Wheeled|Industrial|Logistics|Delivery"


def _resolve_tags(catalog: TagCatalog, tags_pipe: str) -> str:
    desired = [t.strip() for t in (tags_pipe or "").split("|") if t.strip()]
    out: list[str] = []
    missing: list[str] = []
    for t in desired:
        hit = catalog._by_name.get(t.lower())  # self-learning: catalog provides canonical exact names
        if hit:
            out.append(str(hit.get("name") or t))
        else:
            missing.append(t)
    if missing:
        raise RuntimeError(f"Unresolved tags in TagCatalog: {missing}")
    # Keep it deterministic and stable.
    return "|".join(dict.fromkeys(out))


def _search_youtube_watch_urls(query: str, limit: int = 6) -> list[str]:
    # Lightweight YouTube results parsing without an API key.
    # Note: This can intermittently fail due to rate limits; fail safe.
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers=headers,
            timeout=30,
        )
    except requests.RequestException:
        return []
    if not resp.ok:
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for vid in re.findall(r'"videoId":"([\w-]{11})"', resp.text or ""):
        if vid in seen:
            continue
        seen.add(vid)
        ids.append(vid)
        if len(ids) >= limit:
            break
    return [f"https://www.youtube.com/watch?v={vid}" for vid in ids]


def _video_matches_robot(video: dict[str, Any], robot_name: str) -> bool:
    tokens = robot_name_tokens(robot_name)
    digit_tokens = [t.lower() for t in tokens if any(ch.isdigit() for ch in t)]
    if not digit_tokens:
        return True
    blob = f"{video.get('title','')} {video.get('description','')} {video.get('url','')}".lower()
    # Require at least one model numeric token in title/description/url.
    return any(dt in blob for dt in digit_tokens)


def _enrich_and_filter_videos(*, robot_name: str, existing: list[dict[str, Any]]) -> list[dict[str, str]]:
    # 1) Filter existing to model-matching clips.
    out: list[dict[str, str]] = []
    for v in existing:
        title = str(v.get("title") or "")
        if not title:
            continue
        if is_reject_robot_video_title(title):
            continue
        if not _video_matches_robot(v, robot_name):
            continue
        out.append(
            {
                "url": str(v.get("url") or ""),
                "title": title[:255],
                "description": str(v.get("description") or "")[:2000],
            }
        )

    # 2) If empty, search YouTube and enrich.
    if not out:
        urls = _search_youtube_watch_urls(f"Hanwha Robotics {robot_name}", limit=8)
        if not urls:
            return []
        enriched = enrich_video_list(urls, skip_rejected=True)
        for v in enriched:
            if _video_matches_robot(v, robot_name):
                out.append(v)

    # 3) Rank by token score. This keeps deterministic top-N picks.
    # We cannot import score_video directly without creating tight coupling; instead,
    # use a coarse relevance heuristic: numeric token matches score highest.
    tokens = robot_name_tokens(robot_name)
    digit_tokens = [t.lower() for t in tokens if any(ch.isdigit() for ch in t)]
    def rel(v: dict[str, str]) -> int:
        text = f"{v.get('title','')} {v.get('description','')} {v.get('url','')}".lower()
        s = 0
        for dt in digit_tokens:
            if dt and dt in text:
                s += 20
        for tok in tokens:
            tl = tok.lower()
            if tl in text:
                s += 6
        return s

    out.sort(key=lambda v: (-rel(v), v.get("url") or ""))
    # Keep at most 3 clips.
    return out[:3]


def _is_image_candidate(url: str, *, robot_name: str) -> bool:
    u = (url or "").lower()
    if not u:
        return False
    if "bottom_inquiry_bg" in u or "inquiry" in u:
        return False
    # Prefer real uploaded product images.
    if "/uploads/product/" in u:
        return True
    # Rarely, product images might still be in the resources folder.
    if "/resources/images/" in u and any(ext in u for ext in (".png", ".jpg", ".webp")):
        return True
    return False


def _verify_image_bytes_and_md5(url: str, *, timeout: float = 45.0) -> tuple[str, bytes]:
    resp = requests.get(url, timeout=timeout, stream=True)
    resp.raise_for_status()
    data = b"".join(resp.iter_content(chunk_size=64 * 1024)) if hasattr(resp, "iter_content") else resp.content
    if not data:
        raise RuntimeError(f"no image bytes from {url}")
    # Basic magic-byte validation.
    magic_ok = (
        data[:8] == b"\x89PNG\r\n\x1a\n"
        or data[:3] == b"\xff\xd8\xff"
        or data[:4] == b"RIFF"
    )
    if not magic_ok:
        raise RuntimeError(f"not an image magic={data[:12]!r} from {url}")
    if len(data) < 8_000:
        raise RuntimeError(f"image too small {len(data)} bytes from {url}")
    md5 = hashlib.md5(data).hexdigest()
    return md5, data


def _pick_unique_hero_image(
    *,
    robot_id: int,
    robot_name: str,
    page_images: list[str],
    seen_md5: set[str],
    fetcher_timeout: float = 45.0,
) -> tuple[str, list[str], list[str]]:
    candidates = [u for u in page_images if _is_image_candidate(u, robot_name=robot_name)]
    # Deterministic ordering; OEM often uses numeric suffixes.
    candidates = sorted(dict.fromkeys(candidates))

    checked_urls: list[str] = []
    rejected: list[str] = []
    chosen = ""

    for u in candidates:
        checked_urls.append(u)
        try:
            md5, _data = _verify_image_bytes_and_md5(u, timeout=fetcher_timeout)
        except Exception as exc:
            rejected.append(f"{u[:80]}... {exc}")
            continue
        if md5 in seen_md5:
            rejected.append(f"{u[:80]}... duplicate md5={md5}")
            continue
        chosen = u
        seen_md5.add(md5)
        return chosen, [chosen], rejected

    # Fail closed: no unique hero found.
    return "", [], rejected


def _drop_stale_media_flags(client: ResearchApiClient, robot_ids: list[int]) -> None:
    drop_flags = {
        "duplicate_images",
        "image_mismatch",
        "video_mismatch",
        "url_content_mismatch",
        "content_contradiction",
        "unverifiable",
    }

    for rid in robot_ids:
        try:
            r = client._get(f"robots/robots/{rid}/")
        except Exception as exc:
            print(f"  flag-read fail {rid}: {exc}", file=sys.stderr)
            continue

        flags = r.get("quality_flags") or r.get("error_flags") or []
        if not isinstance(flags, list) or not flags:
            continue

        before = [(f.get("flag") if isinstance(f, dict) else f) for f in flags]
        after = [
            f
            for f in flags
            if (f.get("flag") if isinstance(f, dict) else f) not in drop_flags
        ]
        removed = sorted(set(before) - {(f.get("flag") if isinstance(f, dict) else f) for f in after})
        if not removed:
            continue

        try:
            client._patch(f"robots/robots/{rid}/", {"quality_flags": after})
            print(f"  dropped media flags {rid}: {removed}", flush=True)
        except Exception as exc:
            print(f"  flag-drop fail {rid}: {exc}", file=sys.stderr)


def _patch_typed_and_family(
    client: ResearchApiClient,
    rid: int,
    *,
    country_id: int,
    typed: dict[str, Any],
    family: dict[str, Any],
    availability_status: int = 11,
) -> None:
    body: dict[str, Any] = {
        "availability_status": availability_status,
        "manufacturer_countries": [country_id],
        "manufacturer_country_ref": country_id,
    }
    body.update(family)
    body.update({k: v for k, v in typed.items() if v is not None and v != ""})
    if "dof" in body and body["dof"] is not None:
        # Serializer expects int for dof.
        body["dof"] = int(body["dof"])
    client._patch(f"robots/robots/{rid}/", body)


def _spec_changed(key: str, old: Any, new: Any) -> bool:
    if new is None or new == "":
        return False
    if old is None or old == "":
        return True
    try:
        of = float(old)
        nf = float(new)
        return abs(of - nf) > 1e-6
    except Exception:
        return str(old) != str(new)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Hanwha Robotics company 227 content-queue robots")
    parser.add_argument("--apply", action="store_true", help="Apply changes to pending_review robots")
    parser.add_argument("--copy-media", action="store_true", help="Trigger copy-media after import")
    parser.add_argument("--verify-cdn", action="store_true", help="HTTP-GET verify owned CDN after copy-media")
    parser.add_argument("--only", type=int, nargs="*", help="Limit to specific robot ids")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)
    fetcher = WebFetcher(timeout=30)

    robots = [
        r
        for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    ]
    if args.only:
        want = set(int(x) for x in args.only)
        robots = [r for r in robots if int(r["id"]) in want]
    if not robots:
        print("ERROR: no pending_review robots found", file=sys.stderr)
        return 1

    # Determine KR country id from an existing robot (already cached on most rows).
    sample = next((r for r in robots if r.get("manufacturer_country_ref")), None)
    if not sample or not sample.get("manufacturer_country_ref", {}).get("id"):
        country_id = client.get_country_id("KR") or 14
    else:
        country_id = int(sample["manufacturer_country_ref"]["id"])

    seen_md5: set[str] = set()
    enriched: list[int] = []
    imageless: list[int] = []
    rejected: list[int] = []
    copied_ok: list[int] = []
    verify_rc: int | None = None

    spec_corrections: list[str] = []

    preview: list[dict[str, Any]] = []
    staged_rows: dict[int, dict[str, Any]] = {}
    typed_by_rid: dict[int, dict[str, Any]] = {}
    family_by_rid: dict[int, dict[str, Any]] = {}
    videos_by_rid: dict[int, list[dict[str, str]]] = {}

    for r in sorted(robots, key=lambda x: int(x["id"])):
        rid = int(r["id"])
        name = str(r.get("name") or "")
        raw_url = str(r.get("url") or "")
        url = _normalize_hanwha_url(raw_url)
        menu_seq = ""
        prdt_seq = ""
        m_menu = re.search(r"menuSeq=(\d+)", url, flags=re.I)
        m_prdt = re.search(r"prdtSeq=(\d+)", url, flags=re.I)
        if m_menu:
            menu_seq = m_menu.group(1)
        if m_prdt:
            prdt_seq = m_prdt.group(1)

        kind = "cobot" if name.upper().startswith("HCR-") else "mobile"
        is_cobot = kind == "cobot"

        # Fetch OEM page and extract specs.
        page = parse_page(fetcher, url)
        if not page:
            print(f"SKIP {rid} {name}: could not fetch/parse page {url}", file=sys.stderr)
            rejected.append(rid)
            continue

        page_text = page.text or ""
        specs = extract_specs_from_text(page_text)
        # Override payload extraction with label-based regex to avoid prose
        # "weight of only XX kg" poisoning the generic payload pattern.
        payload = _extract_payload_kg(page_text)
        if payload is not None:
            specs["payload_kg"] = payload
        dims = _extract_dimensions_mm(page_text)
        if "dof" not in specs:
            dof = _extract_dof(page_text)
            if dof is not None:
                specs["dof"] = dof
        # Ensure dof is int (serializer-friendly).
        if specs.get("dof") is not None:
            specs["dof"] = int(specs["dof"])

        if dims:
            # RobotSerializer uses length/width/height columns.
            specs.update(dims)

        # Replace obviously wrong typed values by trusting extracted specs
        # (fail closed if extracted is missing).
        for k in ("payload_kg", "reach_mm", "repeatability_mm", "weight_kg", "speed", "speed_ms", "length_mm", "width_mm", "height_mm", "dof"):
            if k in specs and _spec_changed(k, r.get(k), specs.get(k)):
                spec_corrections.append(f"{rid} {name} {k}: {r.get(k)} -> {specs.get(k)}")

        # Family + taxonomy.
        if is_cobot:
            family_key = f"{COMPANY_SLUG}:hcr"
            family_name = "HCR"
            family_url = COBOT_HUB_URL
            movement_type_keys = "stationary"
            category_slugs = "industrial-robots"
            sub_category_slug = "manufacturing-industrial"
            use_keys = "assembly|pick-and-place"
            industry_keys = "manufacturing"
            purpose = "Assembly\nPick-and-place"
        else:
            is_amr = name.lower().startswith("amr")
            family_key = f"{COMPANY_SLUG}:{'amr' if is_amr else 'agv'}"
            family_name = "AMR" if is_amr else "AGV"
            family_url = AGV_AMR_HUB_URL
            movement_type_keys = "wheeled"
            category_slugs = "industrial-robots|amr"
            sub_category_slug = "logistics-warehouse"
            use_keys = "delivery"
            industry_keys = "logistics|manufacturing"
            purpose = "Delivery"

        family = {
            "family_key": family_key,
            "family_name": family_name,
            "family_url": family_url,
            "product_url_scope": "exact_variant",
            "model_name": name,
            "variant_code": name,
            "variant_label": name,
        }

        # Description/features (minimal deterministic based on extracted specs).
        description, features = _build_description_and_features(
            name=name,
            kind=kind,
            specs=specs,
            dims=dims,
        )

        tags_pipe = _desired_tags_for_robot(name, kind)
        tags = _resolve_tags(catalog, tags_pipe)

        # Videos.
        existing_videos = r.get("videos") or []
        curated_videos = _enrich_and_filter_videos(robot_name=name, existing=existing_videos)
        videos_by_rid[rid] = curated_videos

        # Hero image (hash-dedup across this company run).
        hero, gallery, rejected_imgs = _pick_unique_hero_image(
            robot_id=rid,
            robot_name=name,
            page_images=page.images or [],
            seen_md5=seen_md5,
            fetcher_timeout=45.0,
        )

        image_to_do_note = ""
        row_notes_parts: list[str] = []
        row_notes_parts.append("[AI Research] Hanwha curated backfill from OEM PDP; typed specs parsed and validated; videos/tags filtered.")
        if not hero:
            imageless.append(rid)
            image_to_do_note = (
                "[IMAGE TO-DO — no hero, deliberate]\n"
                f"No unique model hero image found in OEM page for prdtSeq={prdt_seq} (menuSeq={menu_seq}).\n"
                "ACTION FOR TEAM: Source a model-specific OEM image and re-run this fixer."
            )
            row_notes_parts.append(image_to_do_note)

        # Build staged row payload.
        row: dict[str, Any] = {
            "id": rid,
            "name": name,
            "company_slug": COMPANY_SLUG,
            "company_name": COMPANY_NAME,
            "manufacturer_country_code": "KR",
            "source_locale": "en",
            "url": url,
            "image": hero,
            "images": [hero] if hero else [],
            "description": description,
            "purpose": purpose,
            "features": features,
            "availability_status_key": "available",
            "movement_type_keys": movement_type_keys,
            "use_keys": use_keys,
            "industry_keys": industry_keys,
            "category_slugs": category_slugs,
            "sub_category_slug": sub_category_slug,
            "tags": tags,
            **family,
            "video_urls": curated_videos if curated_videos else [],
            "sources": [{"url": url, "type": "website", "title": name}, {"url": family_url, "type": "website", "title": family_name}],
            "research_notes": (
                "Hanwha Robotics content-queue backfill: parsed specs from OEM PDP "
                f"(menuSeq={menu_seq} prdtSeq={prdt_seq}); extracted payload/reach/weight/speed and dimensions; "
                "filtered videos by numeric model token match; resolved tags via TagCatalog."
            ),
            "notes": "\n".join(row_notes_parts),
        }

        # Also stage typed columns now (then repatch after copy-media).
        for k in (
            "payload_kg",
            "reach_mm",
            "repeatability_mm",
            "weight_kg",
            "speed",
            "speed_ms",
            "length_mm",
            "width_mm",
            "height_mm",
            "dof",
            "voltage",
        ):
            if k in specs and specs[k] is not None:
                row[k] = specs[k]

        staged_rows[rid] = row
        typed_by_rid[rid] = {
            k: specs.get(k)
            for k in (
                "payload_kg",
                "reach_mm",
                "repeatability_mm",
                "weight_kg",
                "speed",
                "speed_ms",
                "length_mm",
                "width_mm",
                "height_mm",
                "dof",
                "voltage",
            )
            if k in specs
        }
        family_by_rid[rid] = family

        preview.append(
            {
                "id": rid,
                "name": name,
                "url": url,
                "hero": bool(hero),
                "videos": len(curated_videos),
                "typed_keys": [k for k, v in typed_by_rid[rid].items() if v is not None],
                "family_key": family_key,
                "availability_status_key": row.get("availability_status_key"),
                "purpose": purpose.replace("\n", " / "),
            }
        )

        if hero:
            enriched.append(rid)

    if not preview:
        print("ERROR: no targets to stage", file=sys.stderr)
        return 1

    preview_path = _RESEARCH_DIR / "staging" / "reports" / f"hanwha-227-enrichment.md"
    preview_path.parent.mkdir(parents=True, exist_ok=True)

    # CDN verify is only meaningful after apply + copy-media.
    report_lines: list[str] = []
    report_lines.append("---")
    report_lines.append("type: log")
    report_lines.append("title: Hanwha Robotics 227 Enrichment")
    report_lines.append("status: running" if not args.apply else "applied")
    report_lines.append("version: 1.0")
    report_lines.append("owner: AI")
    report_lines.append(f"last_updated: {time.strftime('%Y-%m-%d')}")
    report_lines.append("tags:")
    report_lines.append("  - robots")
    report_lines.append("  - content-queue-enrichment")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("# Hanwha Robotics (Company 227) Content Queue Enrichment")
    report_lines.append("")
    report_lines.append(f"- Targets: {len(preview)} pending_review robots")
    report_lines.append(f"- Enriched (hero found): {len(enriched)}")
    report_lines.append(f"- Imageless: {len(imageless)}")
    report_lines.append(f"- Rejected: {len(rejected)}")
    report_lines.append("")
    report_lines.append("## Result")
    report_lines.append(f"- Apply mode: `{args.apply}`")
    report_lines.append(f"- copy-media: `{args.copy_media}`")
    report_lines.append(f"- verify-cdn: `{args.verify_cdn}`")
    report_lines.append("")
    report_lines.append("## Robots (preview)")
    for p in preview:
        report_lines.append(
            f"- {p['id']} {p['name']}: hero={p['hero']} typed={len(p['typed_keys'])} videos={p['videos']} family={p['family_key']}"
        )
    if spec_corrections:
        report_lines.append("")
        report_lines.append("## Key typed spec corrections")
        for c in spec_corrections[:60]:
            report_lines.append(f"- {c}")
        if len(spec_corrections) > 60:
            report_lines.append(f"- ... and {len(spec_corrections) - 60} more")

    if not args.apply:
        report_lines.append("")
        report_lines.append("## Dry-run notes")
        report_lines.append("- No API writes performed.")
        report_lines.append("")
        preview_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
        print(f"Dry-run preview written: {preview_path}")
        return 0

    # Apply mode.
    created_by_id = int(args.created_by_id)
    imported: list[int] = []
    for rid in sorted(staged_rows.keys()):
        row = staged_rows[rid]
        bulk = staging_dict_to_bulk_import_row(row)
        try:
            result = client.bulk_import_robots(
                [bulk],
                update_existing=True,
                patch_existing=False,
                replace_media=True,
                replace_videos=True,
                status="pending_review",
                skip_company_update=True,
                created_by_id=created_by_id,
            )
        except Exception as exc:
            print(f"IMPORT FAIL {rid}: {exc}", file=sys.stderr)
            rejected.append(rid)
            continue

        created = int(result.get("created_count") or 0)
        if created:
            # Safety: force overwrite should not create new rows for this batch.
            print(f"IMPORT FAIL {rid}: unexpected created_count={created} result={result}", file=sys.stderr)
            rejected.append(rid)
            continue

        imported.append(rid)

        # After import, we patch typed+family+availability to be deterministic post-copy-media.
        _patch_typed_and_family(
            client,
            rid,
            country_id=country_id,
            typed=typed_by_rid.get(rid) or {},
            family=family_by_rid.get(rid) or {},
            availability_status=_AVAIL_IDS["available"],
        )

        time.sleep(0.1)

    if args.copy_media and imported:
        # Best-effort: only copy-media when we actually staged a hero image.
        copy_targets = [rid for rid in imported if staged_rows.get(rid, {}).get("image")]
        ok, fail = trigger_copy_media(copy_targets)
        copied_ok = copy_targets
        report_lines.append("")
        report_lines.append(f"## copy-media")
        report_lines.append(f"- ok={ok} fail={fail} for {len(copy_targets)} robots (imageless skipped)")

        # Copy-media / subsequent serializers can wipe availability/typed fields.
        # Re-patch typed + family + availability after copy-media for determinism.
        for rid in copied_ok:
            _patch_typed_and_family(
                client,
                rid,
                country_id=country_id,
                typed=typed_by_rid.get(rid) or {},
                family=family_by_rid.get(rid) or {},
                availability_status=_AVAIL_IDS["available"],
            )

    if args.verify_cdn and imported:
        verify_rc = subprocess.call(
            [
                sys.executable,
                str(_RESEARCH_DIR / "verify_cdn_images.py"),
                "--company-id",
                str(COMPANY_ID),
            ],
            cwd=str(_RESEARCH_DIR),
        )
        report_lines.append("")
        report_lines.append("## CDN verification")
        report_lines.append(f"- exit_code={verify_rc}")

    if copied_ok:
        # Clear media mismatch flags after the copy.
        _drop_stale_media_flags(client, imported)

    # Final allowlist: enriched robots with hero; imageless are held for manual image sourcing.
    allowlist_ids = [rid for rid in enriched if rid in imported]
    hold_ids = [rid for rid in imageless if rid in imported]

    report_lines.append("")
    report_lines.append("## Approval allowlist and holds")
    report_lines.append(f"- approve_allowlist: {allowlist_ids}")
    if hold_ids:
        report_lines.append(f"- holds (imageless): {hold_ids}")
        report_lines.append("- reason: fail-closed when OEM page produced only duplicate/non-robot images or no verified unique hero bytes.")

    if verify_rc is not None:
        report_lines.append("")
        report_lines.append("## Verification result")
        report_lines.append(f"- verify_cdn_images.py exit_code: {verify_rc}")

    report_lines.append("")
    report_lines.append("## Script")
    report_lines.append(f"- path: `{__file__}`")

    preview_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"Apply report written: {preview_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

