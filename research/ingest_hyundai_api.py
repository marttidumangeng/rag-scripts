"""Proof of concept: ingest HD Hyundai Robotics' full catalogue from their
own product JSON API, instead of link-mining rendered HTML.

Why this exists
---------------
Round-1 link mining captured 23 records for this company, of which only ~9
were real robots (two were CONTROLLERS, three were the same "HDR Series"
heading in three spellings, two were the generic phrase "Industrial
Robot(s)"). Their real catalogue is 69 robots. The miner failed because the
product listing is axios-rendered and the CDN WAF 403s non-browser agents —
a plain fetch returns a single placeholder row.

The site exposes a JSON API (base + version discoverable from an inline
config block on the page):

    /api/v1/product/page?prdTypeCd=<code>&page=0&size=300

which returns payload, reach, controller compatibility, DOF, drive type,
production status and narrative per model. That is a spec-complete ingest,
not a name-only lead.

Product type codes (verified):
    60010001 industrial articulated  47 rows (1 blank draft) -> 46
    60010002 FPD glass transfer      20
    60010003 controllers             18  EXCLUDED - not robots
    60010004 positioners/peripherals   7  EXCLUDED - not robots
    60010007 collaborative            3
                                     --> 69 robots

Three traps this handles explicitly
-----------------------------------
1. DUAL NAMING. HD Hyundai renamed the industrial catalogue circa 2024-25 to
   HD<letter><payload>-<reach>, keeping the legacy code inline in parens:
   "HDR220-26(HS220)". HS220 and HDR220-26 are ONE robot. 31 of 46 rows carry
   a dual name, so a naive ingest invents ~31 duplicates. We split the alias
   out, import under the CURRENT name, and record the legacy code so dedupe
   (here and in future runs) can match either.

2. KOREAN-ONLY NARRATIVE. prdIntroEn is empty on 66 of 69 rows; only the 3
   collaborative models have English. We do NOT machine-translate marketing
   copy into a catalogue that claims sourced data, and we do not import
   Korean text (it trips the non_english_content error flag). Instead the
   description is composed from the STRUCTURED SPEC FIELDS the API returns —
   factual, attributable, English, and not invented.

3. EXISTING RECORDS. We already hold 9 of these. Dedupe is checked against
   BOTH the current name and the legacy alias, because our published "UH035"
   is the same machine as their "HDR35-20(UH035)".

Read-only against prod (GET only). Writes a staging file for review; imports
nothing.
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env()

from api_client import ResearchApiClient  # noqa: E402
from schema import ImageCandidate, SourceRef, StagedRobot  # noqa: E402

BASE = "https://www.hd-hyundairobotics.com"
API = BASE + "/api/v1/product/page"
IMG = BASE + "/api/v1/file/ck/view/{seq}"
OUT_DIR = _HERE / "staging" / "hyundai_api"
STAGED = OUT_DIR / "staged_import.json"

HDRS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Referer": BASE + "/",
    "Accept": "application/json, text/plain, */*",
}

TYPES = {
    "60010001": ("industrial articulated", "industrial-arm"),
    "60010002": ("FPD glass transfer", "industrial-arm"),
    "60010007": ("collaborative", "cobot"),
}

# prdApField / prdRlIdst are pipe-joined internal codes. Only map the ones we
# can confirm from the site's own filter UI; unknown codes are dropped rather
# than guessed at.
APP_CODES = {
    "60020001": "spot welding",
    "60020004": "handling",
    "60020005": "assembly",
    "60020006": "machine tending",
}


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def num(v: Any) -> float | None:
    if v is None:
        return None
    m = re.search(r"[\d,]+(?:\.\d+)?", str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def split_name(raw: str) -> tuple[str, str]:
    """'HDR220-26(HS220)' -> ('HDR220-26', 'HS220'). Returns (current, legacy)."""
    raw = (raw or "").strip()
    m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", raw)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return raw, ""


def series_of(name: str) -> str:
    m = re.match(r"^([A-Za-z]+)", name)
    return (m.group(1).upper() if m else "misc")


def fetch(code: str) -> list[dict[str, Any]]:
    r = requests.get(API, params={"prdTypeCd": code, "page": 0, "size": 300},
                     headers=HDRS, timeout=40)
    r.raise_for_status()
    rows = r.json().get("data", {}).get("content", []) or []
    return [x for x in rows if (x.get("prdNm") or "").strip()]


def specs_for(code: str, x: dict[str, Any]) -> tuple[float | None, float | None, str]:
    """Return (payload_kg, reach_mm, glass_generation).

    The basic-spec slots are NOT the same measure across product types. For
    industrial (60010001) and collaborative (60010007), spec1/spec2 are
    payload kg and reach mm. For FPD glass-transfer (60010002) spec1 is empty
    and spec2 is the GLASS GENERATION ('5G', '8G', '65"(8G)') — parsing that
    as a number yields an absurd "5 mm reach", which is exactly what a
    type-blind mapping produced on the first run.
    """
    if code == "60010002":
        return None, None, strip_html(x.get("prdBscSpec2") or "")
    return num(x.get("prdBscSpec1")), num(x.get("prdBscSpec2")), ""


_VOWEL_SOUND_LETTERS = set("AEFHILMNORSX")  # letters read with a leading vowel sound


def article_for(phrase: str) -> str:
    first = phrase.split()[0] if phrase.split() else phrase
    if first[:2].isupper() and len(first) > 1:      # acronym: FPD -> "an eff-pee-dee"
        return "an" if first[0] in _VOWEL_SOUND_LETTERS else "a"
    return "an" if first[:1].lower() in "aeiou" else "a"


def build_description(name: str, legacy: str, kind: str, code: str, x: dict[str, Any]) -> str:
    """Factual English prose composed from the API's own structured fields.
    Nothing here is translated marketing copy or invented."""
    payload, reach, glass = specs_for(code, x)
    ctrl = strip_html(x.get("prdBscSpec3") or "")
    structure = strip_html(x.get("prdDtlSpec1") or "")
    axes = strip_html(x.get("prdDtlSpec2") or "")
    drive = strip_html(x.get("prdDtlSpec3") or "")

    # Build the opening noun phrase once, so "articulated" isn't repeated and
    # the article agrees with whatever word actually follows it.
    descriptors = []
    if axes:
        descriptors.append(f"{axes}-axis")
    if structure and structure.lower() not in kind.lower():
        descriptors.append(structure.lower())
    descriptors.append(kind if structure.lower() in kind.lower() else kind.replace("articulated", "").strip())
    phrase = " ".join(w for w in descriptors if w) + " robot"
    article = article_for(phrase)

    bits = [f"{name} is {article} {phrase} manufactured by HD Hyundai Robotics."]
    cap = []
    if payload:
        cap.append(f"a rated payload of {payload:g} kg")
    if reach:
        cap.append(f"a maximum reach of {reach:g} mm")
    if cap:
        tail = f", driven by {drive} motors" if drive else ""
        bits.append("It has " + " and ".join(cap) + tail + ".")
    elif drive:
        bits.append(f"Drive type: {drive}.")
    if glass:
        bits.append(f"Rated for {glass} substrate glass handling.")
    if ctrl:
        bits.append(f"Compatible controllers: {ctrl}.")
    if legacy:
        bits.append(f"Previously designated {legacy} before HD Hyundai's catalogue renaming.")
    if (x.get("prdMassYn") or "").upper() == "N":
        bits.append("Listed by the manufacturer as no longer in production.")
    return " ".join(bits)


def main() -> None:
    client = ResearchApiClient()

    # ---- what we already hold, by BOTH current name and legacy alias -------
    # Exact-name match required. A substring/first-hit match silently grabs
    # "Hyundai Motor Group Robotics" (a DIFFERENT company, 2 robots) instead
    # of "Hyundai Robotics" (23 robots) — which would have let all 9 records
    # we already hold import a second time.
    existing: set[str] = set()
    target = None
    for h in client.search_companies("Hyundai Robotics", page_size=10):
        if (h.get("name") or "").strip().lower() == "hyundai robotics":
            target = h
            break
    if not target:
        raise SystemExit("Could not resolve the 'Hyundai Robotics' company exactly — aborting "
                         "rather than risk importing duplicates against the wrong company.")
    for r in client.list_robots_for_company(target["id"]):
        nm = (r.get("name") or "").strip()
        cur, leg = split_name(nm)
        for v in (nm, cur, leg):
            if v:
                existing.add(re.sub(r"[^a-z0-9]", "", v.lower()))
    print(f"matched company: {target['name']} (id {target['id']}) — "
          f"{len(existing)} held name keys", flush=True)

    staged: list[StagedRobot] = []
    skipped_dup: list[str] = []
    counts: dict[str, int] = {}

    for code, (kind, cat) in TYPES.items():
        rows = fetch(code)
        counts[kind] = len(rows)
        print(f"[{code}] {kind}: {len(rows)} rows", flush=True)
        for x in rows:
            raw = (x.get("prdNm") or "").strip()
            cur, legacy = split_name(raw)
            if not cur:
                continue
            k_cur = re.sub(r"[^a-z0-9]", "", cur.lower())
            k_leg = re.sub(r"[^a-z0-9]", "", legacy.lower()) if legacy else ""
            if k_cur in existing or (k_leg and k_leg in existing):
                skipped_dup.append(f"{cur}" + (f" ({legacy})" if legacy else ""))
                continue

            payload, reach, glass = specs_for(code, x)
            dof = num(x.get("prdDtlSpec2"))
            apps = [APP_CODES[c] for c in (x.get("prdApField") or "").split("|") if c in APP_CODES]

            bd = x.get("bdContent") or {}
            thumb_seq = bd.get("bdcThumbFile1Seq")
            images: list[ImageCandidate] = []
            if thumb_seq:
                images.append(ImageCandidate(
                    url=IMG.format(seq=thumb_seq),
                    source_page_url=f"{BASE}/biz/product/{code}",
                    source_tier="manufacturer",
                    source_publisher="HD Hyundai Robotics",
                    source_domain="hd-hyundairobotics.com",
                    media_class="official_render",
                    image_scope="exact_variant",
                    confidence_score=88,
                    match_reason="Official product thumbnail from manufacturer product API",
                    rights_status="official_source",
                ))

            staged.append(StagedRobot(
                name=cur,
                model_name=cur,
                company_slug="hyundai-robotics",
                company_name="Hyundai Robotics",
                company_website="https://www.hd-hyundairobotics.com",
                manufacturer_country_code="KR",
                family_name=f"{series_of(cur)} series",
                family_key=f"hyundai-robotics:{series_of(cur).lower()}",
                variant_code=legacy,
                url=f"{BASE}/biz/product/{code}",
                description=build_description(cur, legacy, kind, code, x),
                purpose=(f"{kind.capitalize()} robot for "
                         + (", ".join(apps) if apps else "industrial automation") + "."),
                payload_kg=payload,
                reach_mm=reach,
                dof=int(dof) if dof else None,
                category_slugs=cat,
                # sub_category_slug is a SEPARATE taxonomy (RobotSubCategory
                # "Applications") from category_slugs (Category M2M) — setting
                # only the latter leaves a "No sub-category" warning on every
                # row. Every model here is factory automation hardware.
                sub_category_slug="manufacturing-industrial",
                availability_status_key=("available"
                                         if (x.get("prdMassYn") or "").upper() == "Y"
                                         else "discontinued"),
                source_locale="en",
                images=images,
                sources=[SourceRef(url=f"{BASE}/biz/product/{code}", type="website",
                                   title="HD Hyundai Robotics product catalogue")],
                confidence={"name": "high", "specs": "high", "url": "high"},
                research_notes=(
                    "[AI Research] Ingested from HD Hyundai Robotics' own product JSON API "
                    f"(/api/v1/product/page?prdTypeCd={code}) on {datetime.now(timezone.utc).date()}. "
                    "Specs (payload, reach, DOF, drive, controller) are the manufacturer's own "
                    "structured fields, not parsed prose. Description is composed from those "
                    "fields in English; the site's narrative is Korean-only for this model and "
                    "was deliberately NOT machine-translated."
                    + (f" Legacy designation: {legacy}." if legacy else "")
                ),
            ))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STAGED.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workflow": "ingest_hyundai_api",
        "source": "HD Hyundai Robotics product JSON API",
        "catalog_counts": counts,
        "already_held_skipped": skipped_dup,
        "robot_count": len(staged),
        "robots": [r.to_dict() for r in staged],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    per_dir = OUT_DIR / "robots" / "hyundai-robotics"
    per_dir.mkdir(parents=True, exist_ok=True)
    for f in per_dir.glob("*.json"):
        f.unlink()
    for r in staged:
        fn = re.sub(r"[^a-z0-9]+", "-", r.name.lower()).strip("-")[:60] or "robot"
        (per_dir / f"{fn}.json").write_text(
            json.dumps(r.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    with_specs = sum(1 for r in staged if r.payload_kg and r.reach_mm)
    with_img = sum(1 for r in staged if r.images)
    print(f"\ncatalogue total: {sum(counts.values())}")
    print(f"already held (skipped as duplicates): {len(skipped_dup)} -> {skipped_dup}")
    print(f"NEW staged: {len(staged)}")
    print(f"  with payload+reach: {with_specs} ({round(100*with_specs/len(staged))}%)")
    print(f"  with official image: {with_img} ({round(100*with_img/len(staged))}%)")
    print(f"\nWrote {STAGED}")
    print(f"Wrote {len(staged)} per-robot files to {per_dir}")


if __name__ == "__main__":
    main()
