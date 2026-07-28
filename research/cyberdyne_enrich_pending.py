"""Cyberdyne Inc. (145) queue enrichment: 34 pending_review + published HAL (178).

Queue defects (audit 2026-07-27):
  - family blank on the 19 older records (55xx set + singletons already carry the
    teammate-pipeline taxonomy: hal-medical / hal-wellbeing / hal-lumbar /
    hal-peripheral / cyberdyne-autonomous / cyberdyne-digital / cyin / acoustic-x
    / hal) -> ADOPT those keys for the blanks, fill variant_label/scope on all
  - all 35 lack the 5 extended narrative fields
  - missing_category on the 13 newer (R) records -> copy from their older twin
  - published HAL (178): no tags, no taxonomy, no family, 86-char description
  - duplicate_images x10: same file with/without ?ver= querystring + cross-model
    contamination (Medical images in Well-Being galleries and vice versa);
    JUKUSUI galleries are site banners/og-image junk (-> verify score 9);
    Medicalcare Pit(R) holds CYVIS product images
  - 4642 Transportation Robot: no photos at all

Phases:
    python cyberdyne_enrich_pending.py --build      # fetch pages + Gemini -> staging json
    python cyberdyne_enrich_pending.py              # dry-run
    python cyberdyne_enrich_pending.py --apply
Media junk removal runs separately via ORM (see cyberdyne_orm_cleanup.py).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

import os  # noqa: E402
from html import unescape  # noqa: E402

from api_client import ResearchApiClient  # noqa: E402
from import_staging import resolve_created_by_id  # noqa: E402
from map_to_bulk_import import staging_dict_to_bulk_import_row  # noqa: E402

COMPANY_ID = 145
COMPANY_SLUG = "cyberdyne-inc"
COMPANY_NAME = "Cyberdyne Inc."

SNAP = Path(r"C:\Users\tramk\AppData\Local\Temp\claude\C--Github-Personal-robot-ai-geek"
            r"\f3998b3d-68c5-4c68-85be-c6a45d3e4add\scratchpad\c145_all.json")
STAGING = _HERE / "staging" / "reports" / "cyberdyne-enrich-pending.json"

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
     "Accept-Language": "en-US,en;q=0.9"}

# id -> (family_key, family_name, variant_label, scope)
# Keys MATCH the teammate-pipeline taxonomy already live on the 55xx records.
FAMILY: dict[int, tuple[str, str, str, str]] = {
    178:  ("hal", "HAL® (Hybrid Assistive Limb)", "", "family"),
    1890: ("hal-lumbar", "HAL® Lumbar Type", "Well-being (BB04)", "exact_variant"),
    3046: ("hal-lumbar", "HAL® Lumbar Type", "Labor Support", "exact_variant"),
    4402: ("hal-medical", "HAL® Medical", "Lower Limb", "exact_variant"),
    4403: ("hal-medical", "HAL® Medical", "Single Joint", "exact_variant"),
    4404: ("hal-wellbeing", "HAL® Well-Being", "Lower Limb FL08", "exact_variant"),
    4405: ("hal-wellbeing", "HAL® Well-Being", "Lower Limb FL07", "exact_variant"),
    4406: ("hal-wellbeing", "HAL® Well-Being", "Lower Limb FL05", "exact_variant"),
    4407: ("hal-lumbar", "HAL® Lumbar Type", "Labor Support LB03-SSSJP", "exact_variant"),
    4408: ("hal-lumbar", "HAL® Lumbar Type", "Labor Support LB01", "exact_variant"),
    4635: ("hal-wellbeing", "HAL® Well-Being", "Lower Limb", "exact_variant"),
    4636: ("hal-wellbeing", "HAL® Well-Being", "Single Joint", "exact_variant"),
    4637: ("hal-peripheral", "HAL® Peripheral Equipment", "Medicalcare Pit", "exact_variant"),
    4638: ("hal-peripheral", "HAL® Peripheral Equipment", "HALTREAD", "exact_variant"),
    4639: ("hal-peripheral", "HAL® Peripheral Equipment", "All-in-One", "exact_variant"),
    4640: ("acoustic-x", "Acoustic X® (Photoacoustic Imaging)", "", "exact_variant"),
    4641: ("cyberdyne-autonomous", "Cyberdyne Autonomous Robots", "CL02", "exact_variant"),
    4642: ("cyberdyne-autonomous", "Cyberdyne Autonomous Robots", "Transport", "exact_variant"),
    4643: ("hal", "HAL® (Hybrid Assistive Limb)", "Neuro HALFIT", "exact_variant"),
    4644: ("cyberdyne-digital", "Cyberdyne Digital Health", "JUKUSUI", "exact_variant"),
    4645: ("cyin", "CYIN®", "", "exact_variant"),
    4646: ("hal", "HAL® (Hybrid Assistive Limb)", "", "family"),
    # variant/scope fills for the 55xx set (family fields already set there)
    5578: ("", "", "Well-being (BB04)", "exact_variant"),
    5579: ("", "", "Labor Support", "exact_variant"),
    5580: ("", "", "Lower Limb", "exact_variant"),
    5581: ("", "", "Single Joint", "exact_variant"),
    5582: ("", "", "Lower Limb FL08", "exact_variant"),
    5583: ("", "", "Single Joint", "exact_variant"),
    5584: ("", "", "Medicalcare Pit", "exact_variant"),
    5585: ("", "", "HALTREAD", "exact_variant"),
    5586: ("", "", "", "exact_variant"),
    5587: ("", "", "Neuro HALFIT", "exact_variant"),
    5588: ("", "", "JUKUSUI", "exact_variant"),
    5589: ("", "", "", "exact_variant"),
    5590: ("", "", "", "family"),
}

# duplicate twin pairs: newer (R) record <- older record (categories copied ->)
TWIN_OF = {5578: 1890, 5579: 3046, 5580: 4402, 5581: 4403, 5582: 4404,
           5583: 4636, 5584: 4637, 5585: 4638, 5586: 4640, 5587: 4643,
           5588: 4644, 5589: 4645, 5590: 4646}

SPEC_KEYS = ("payload_kg", "reach_mm", "repeatability_mm", "weight_kg", "dof")

NARRATIVE_LIMITS = {
    "programming_interface": 120,
    "safety_fencing": 120,
    "mounting_options": 80,
    "deployment_context": 120,
    "ecosystem_compatibility": 150,
}

_GEMINI_PROMPT = """You extract facts about a product from its official page text (Cyberdyne medical/assistive robotics).
Return ONLY valid JSON with exactly these keys (use "" for anything the text does not state; NEVER invent):
- "programming_interface": how the device is operated/controlled/configured (e.g. "Controlled via bioelectric signal sensors; settings via controller"). Max 120 chars.
- "safety_fencing": safety context stated by the page (for wearable/assistive devices e.g. "Not applicable - wearable device worn by the user"). Only what the text supports. Max 120 chars.
- "mounting_options": how/where the device is worn, mounted or installed (e.g. "Worn on lower back", "Floor-standing unit"). Max 80 chars.
- "deployment_context": typical installation/deployment setting or effort (e.g. "Used in hospitals and rehabilitation facilities"). Max 120 chars.
- "ecosystem_compatibility": integrations, certifications, standards, companion services stated (e.g. "Medical device certification; cloud data service"). Max 150 chars.
Answer in English even if the text is Japanese.
Product: {name}

PAGE TEXT:
{text}
"""


def _p(*a):
    print(*a, flush=True)


def fetch_page(url: str) -> tuple[list[str], list[str], str]:
    """-> (text lines, product image urls, og_image)"""
    r = requests.get(url, headers=H, timeout=45)
    html = r.text
    og = re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', html)
    og_img = unescape(og.group(1)) if og else ""
    imgs = re.findall(r'(https?://[^"\'\s]+?/wp-content/uploads/[^"\'\s]+?\.(?:jpg|jpeg|png|webp))', html, re.I)
    junk = ("banner_", "ogimage", "information-", "top-first-view", "logo", "icon",
            "favicon", "cropped-", "-360x", "-528x", "e1756731338618")
    imgs = [u for u in dict.fromkeys(imgs) if not any(j in u.lower() for j in junk)]
    t = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    t = re.sub(r"<style[\s\S]*?</style>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "\n", t)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in unescape(t).splitlines()]
    return [ln for ln in lines if ln], imgs, og_img


def gemini_narrative(name: str, text: str) -> dict[str, str]:
    try:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""),
                              http_options={"api_version": "v1beta"})
        resp = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=_GEMINI_PROMPT.format(name=name, text=text[:6000]),
            config=genai_types.GenerateContentConfig(temperature=0.0))
        raw = re.sub(r"^```[a-z]*\n?|\n?```$", "", (resp.text or "").strip())
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        _p(f"  WARN gemini: {exc}")
        return {}
    out = {}
    for k, cap in NARRATIVE_LIMITS.items():
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[:cap]
    return out


def build() -> int:
    robots = json.loads(SNAP.read_text(encoding="utf-8"))
    by_id = {int(r["id"]): r for r in robots}

    # one fetch + one Gemini call per unique URL
    url_cache: dict[str, dict[str, Any]] = {}
    staged: dict[str, Any] = {}
    for r in sorted(robots, key=lambda x: x["id"]):
        rid = int(r["id"])
        url = (r.get("url") or "").strip()
        base_url = url.split("#")[0]
        if rid == 178:
            base_url = "https://www.cyberdyne.jp/en/products/about-hal"
        if base_url not in url_cache:
            _p(f"fetch {base_url}")
            try:
                lines, imgs, og_img = fetch_page(base_url)
            except requests.RequestException as exc:
                _p(f"  FAIL {exc}")
                lines, imgs, og_img = [], [], ""
            narrative = gemini_narrative(r["name"], "\n".join(lines)) if lines else {}
            url_cache[base_url] = {"imgs": imgs, "og": og_img, "narrative": narrative}
            time.sleep(0.4)
        cache = url_cache[base_url]

        fam = FAMILY.get(rid, ("", "", "", ""))
        # twin cross-fill for typed specs (fill my blanks from my twin, both directions)
        twin_id = TWIN_OF.get(rid) or next((k for k, v in TWIN_OF.items() if v == rid), None)
        twin = by_id.get(twin_id) if twin_id else None
        spec_fill = {}
        for k in SPEC_KEYS:
            if r.get(k) is None and twin is not None and twin.get(k) is not None:
                spec_fill[k] = twin[k]

        staged[str(rid)] = {
            "id": rid,
            "name": r["name"],
            "status": r.get("status"),
            "url": url,
            "family_key": fam[0],
            "family_name": fam[1],
            "variant_label": fam[2],
            "product_url_scope": fam[3],
            "narrative": cache["narrative"],
            "spec_fill": spec_fill,
            "page_images": cache["imgs"][:8],
            "og_image": cache["og"],
            "twin": twin_id,
            "categories": [c.get("id") if isinstance(c, dict) else c for c in (r.get("categories") or [])],
        }
        _p(f"  {rid} {r['name'][:36]:36} fam={fam[0] or '(keep)'} narr={sorted(cache['narrative'])} "
           f"specfill={spec_fill}")

    STAGING.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(json.dumps(staged, indent=1, ensure_ascii=False), encoding="utf-8")
    _p(f"wrote {STAGING}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    if args.build:
        return build()

    staged = json.loads(STAGING.read_text(encoding="utf-8"))
    rows = []
    for e in staged.values():
        row: dict[str, Any] = {
            "id": e["id"], "name": e["name"],
            "company_slug": COMPANY_SLUG, "company_name": COMPANY_NAME,
            "url": e["url"], "model_name": e["name"], "variant_code": e["name"],
            "source_locale": "en",
            "family_key": e["family_key"], "family_name": e["family_name"],
            "variant_label": e["variant_label"], "product_url_scope": e["product_url_scope"],
            **e.get("narrative", {}), **e.get("spec_fill", {}),
            "sources": [{"url": e["url"].split("#")[0] or "https://www.cyberdyne.jp/en/",
                         "type": "website", "title": e["name"]}],
        }
        rows.append(staging_dict_to_bulk_import_row(row) | {"id": e["id"]})

    _p(f"rows: {len(rows)}")
    if not args.apply:
        _p(json.dumps(rows[0], indent=1, ensure_ascii=False)[:900])
        _p("dry-run")
        return 0

    client = ResearchApiClient()
    created_by = resolve_created_by_id(args.created_by_id)
    for i in range(0, len(rows), 8):
        batch = rows[i:i + 8]
        for attempt in range(5):
            try:
                resp = client.bulk_import_robots(batch, update_existing=True, patch_existing=True,
                                                 status="pending_review", skip_company_update=True,
                                                 created_by_id=created_by)
                _p(f"batch {i // 8}: " + json.dumps({k: v for k, v in resp.items() if k.endswith('_count')}))
                break
            except Exception as exc:  # noqa: BLE001
                _p(f"batch {i // 8} attempt {attempt}: {exc}")
                time.sleep(30 * (attempt + 1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
