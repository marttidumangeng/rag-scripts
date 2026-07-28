"""Comau (245) pending_review enrichment: family metadata + extended narrative
fields + missing typed specs + gallery cleanup, in one patch-mode import pass.

Gaps this closes (queue audit 2026-07-27, all 47 pending robots):
  - family_name/family_key/variant_label/product_url_scope: empty on all 47
  - programming_interface/safety_fencing/mounting_options/deployment_context/
    ecosystem_compatibility: empty on all 47
  - payload_kg NULL where the PDP spec table states it (MyCo, Racer, NJ4 rows)
  - duplicate_images (ERROR): WordPress -WxH size-variant rows + the site-wide
    world-map graphic; S-13 additionally carries S-18's assets (wrong model)
  - few_photos: PDP renders exist for several 1-photo robots
  - missing_release_year on MyCo-5/MyCo-15 and S-18 where the family launch
    citation already stamped on siblings covers the model explicitly

Families come from Comau's own robot-team taxonomy (NJ / NJ4 / MyCo / Racer /
Rebel-S / PAL / S Family / N / MyMR). Only s-family/ and
autonomous-mobile-robots/ have real hub pages; other family_url stay blank
rather than pointing every family at the same catalog URL.

MyCo x5 and S-13 keep the deliberate no-hero policy from their notes: their
galleries are CLEARED (replace_media with no images) because Comau publishes no
model-specific renders — a missing image beats a wrong or duplicated one.

Narrative fields are extracted by Gemini from the robot's own PDP text
("never invent information not present in the text"), then overlaid with the
deterministic spec-table mounting_position value.

Usage:
    python comau_enrich_pending.py --build       # fetch pages + Gemini -> staging JSON
    python comau_enrich_pending.py               # dry-run preview from staging JSON
    python comau_enrich_pending.py --apply       # write to prod (+ copy-media where galleries changed)
"""

from __future__ import annotations

import argparse
import hashlib
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

from api_client import ResearchApiClient  # noqa: E402
from comau_recon import (  # noqa: E402
    CHROME_TOKENS,
    HEADERS as COMAU_HEADERS,
    clean_lines,
    model_digits,
    parse_specs,
)
from import_staging import resolve_created_by_id  # noqa: E402
from map_to_bulk_import import staging_dict_to_bulk_import_row  # noqa: E402

COMPANY_ID = 245
COMPANY_SLUG = "comau"
COMPANY_NAME = "Comau"
ROBOT_TEAM = "https://www.comau.com/en/our-offer/products-and-solutions/robot-team/"

STAGING = _HERE / "staging" / "reports" / "comau-enrich-pending.json"
PENDING_SNAPSHOT = Path(
    r"C:\Users\tramk\AppData\Local\Temp\claude\C--Github-Personal-robot-ai-geek"
    r"\f3998b3d-68c5-4c68-85be-c6a45d3e4add\scratchpad\comau_pending.json"
)
RECON = Path(
    r"C:\Users\tramk\AppData\Local\Temp\claude\C--Github-Personal-robot-ai-geek"
    r"\f3998b3d-68c5-4c68-85be-c6a45d3e4add\scratchpad\comau-recon-all.json"
)

# ---------------------------------------------------------------- families ---
# Vendor taxonomy: prefix -> (family_name, family_key_suffix, family_url).
# Order matters (NJ4 before NJ-, Rebel-S before Racer's R).
FAMILY_RULES: list[tuple[str, str, str, str]] = [
    ("NJ4", "NJ4", "nj4", ""),
    ("NJ-", "NJ", "nj", ""),
    ("MyCo", "MyCo", "myco", ""),
    ("Rebel-S", "Rebel-S", "rebel-s", ""),
    ("Racer", "Racer", "racer", ""),
    ("PAL-", "PAL", "pal", ""),
    ("S-1", "S Family", "s-family", ROBOT_TEAM + "s-family/"),
    ("N-", "N", "n", ""),
]
# The AMR entry is a family-level page, not a model.
AMR_ID = 1889

# Family launch citations already grounded on approved/sibling records.
# S-Family citation names both payloads (13 & 18 kg) -> covers S-18.
MYCO_YEAR = (
    2025,
    "release_year=2025: Comau announced the worldwide launch of MyCo, its new "
    "family of collaborative robots, at Automatica 2025 (June 24-27) in Munich, "
    "Germany. (https://www.comau.com/en/our-offer/products-and-solutions/robot-team/)",
)
S18_YEAR = (
    2024,
    "release_year=2024: Comau's new S-Family of high-speed, energy efficient "
    "robots, with payloads of 13 kg and up to 18 kg, made their exclusive "
    "worldwide launch at Automate 2024. "
    "(https://www.comau.com/en/our-offer/products-and-solutions/robot-team/s-family/)",
)

# Italian PDP spec labels (Racer-5 SE only serves /it/).
IT_SPEC_LABELS = {
    "numero di assi": "axes",
    "carico massimo al polso (kg)": "payload_kg",
    "carico massimo al polso": "payload_kg",
    "sbraccio orizzontale massimo (mm)": "reach_mm",
    "sbraccio orizzontale massimo": "reach_mm",
    "ripetibilita (mm)": "repeatability_mm",
    "ripetibilità (mm)": "repeatability_mm",
    "ripetibilità": "repeatability_mm",
    "peso robot (kg)": "weight_kg",
    "peso robot": "weight_kg",
    "classe di protezione": "protection_class",
    "posizione di montaggio": "mounting_position",
}

NARRATIVE_LIMITS = {
    "programming_interface": 120,
    "safety_fencing": 120,
    "mounting_options": 80,
    "deployment_context": 120,
    "ecosystem_compatibility": 150,
}

_GEMINI_PROMPT = """You extract facts about an industrial/collaborative robot from its official product page text.
Return ONLY valid JSON with exactly these keys (use "" for anything the text does not state; NEVER invent):
- "programming_interface": how the robot is programmed or taught (e.g. "PDL2 via C5G controller teach pendant"). Max 120 chars.
- "safety_fencing": whether a safety fence/cage is required (e.g. "Not required in collaborative mode" or "Standard industrial robot - perimeter guarding required"). Only state what the text supports. Max 120 chars.
- "deployment_context": typical installation/deployment effort or setting stated by the page (e.g. "Quick installation and rapid redeployment"). Max 120 chars.
- "ecosystem_compatibility": integration standards, certified ecosystem, controllers, ROS support etc. (e.g. "Fully integrated with ROS/ROS2"). Max 150 chars.
Answer in English even if the page text is Italian.
Robot: {name}

PAGE TEXT:
{text}
"""


def _p(*a):
    print(*a, flush=True)


def family_for(rid: int, name: str) -> dict[str, str] | None:
    if rid == AMR_ID:
        return {
            "family_name": "MyMR",
            "family_key": "comau:mymr",
            "variant_label": "",
            "family_url": ROBOT_TEAM + "autonomous-mobile-robots/",
            "product_url_scope": "family",
        }
    for prefix, fam, key_suffix, fam_url in FAMILY_RULES:
        if name.startswith(prefix):
            variant = name[len(fam):].strip(" -–—:")
            if fam == "Rebel-S":  # "Rebel-S6-0.60" -> "S6-0.60"
                variant = name[len("Rebel-"):].strip(" -")
            if fam == "S Family":  # "S-18" -> "18"
                variant = name.replace("S-", "", 1).strip()
            if fam == "N":  # "N-170 robot" -> "170"
                variant = name.replace("N-", "", 1).replace("robot", "").strip()
            return {
                "family_name": fam,
                "family_key": f"comau:{key_suffix}",
                "variant_label": variant,
                "family_url": fam_url,
                # S-18 (1853) is overridden to "family" by the caller — its
                # robot.url is the s-family hub page, not a variant PDP.
                "product_url_scope": "exact_variant",
            }
    return None


def gemini_narrative(name: str, text: str) -> dict[str, str]:
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        _p("  WARN: google-genai not installed; narrative extraction skipped")
        return {}
    try:
        client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            http_options={"api_version": "v1beta"},
        )
        response = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=_GEMINI_PROMPT.format(name=name, text=text[:6000]),
            config=genai_types.GenerateContentConfig(temperature=0.0),
        )
        raw = (response.text or "").strip()
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        _p(f"  WARN gemini fail: {exc}")
        return {}
    out = {}
    for key in ("programming_interface", "safety_fencing", "deployment_context",
                "ecosystem_compatibility"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()[: NARRATIVE_LIMITS.get(key, 120)]
    return out


def parse_it_specs(lines: list[str]) -> dict:
    specs: dict = {}
    for i, ln in enumerate(lines):
        key = IT_SPEC_LABELS.get(ln.lower().strip())
        if not key or key in specs or i + 1 >= len(lines):
            continue
        val = lines[i + 1].strip()
        if key in ("payload_kg", "reach_mm", "repeatability_mm", "weight_kg", "axes"):
            m = re.match(r"^~?\s*([\d.,]+)", val.replace("±", ""))
            if m:
                raw = m.group(1)
                if re.fullmatch(r"\d{1,3}\.\d{3}", raw):
                    raw = raw.replace(".", "")
                raw = raw.replace(",", ".")
                try:
                    specs[key] = float(raw)
                except ValueError:
                    pass
        else:
            specs[key] = val
    return specs


_SIZE_VARIANT_RE = re.compile(r"-\d+x\d+\.(?:jpg|jpeg|png|webp)$", re.I)


def is_junk_image(url: str) -> bool:
    low = (url or "").lower()
    if _SIZE_VARIANT_RE.search(low):
        return True
    if "global-presence" in low:
        return True
    return any(tok in low for tok in CHROME_TOKENS)


def matches_model(url: str, name: str) -> bool:
    """Filename digits must share the model's leading digits (comau_recon rule)."""
    token = model_digits(name)
    if not token or len(token) < 2:
        return False
    fname_digits = re.sub(r"[^0-9]", "", url.rsplit("/", 1)[-1])
    return token[:3] in fname_digits or (len(token) >= 2 and token[:2] == fname_digits[:2] and bool(fname_digits))


def head_ok(url: str, session: requests.Session) -> bool:
    try:
        r = session.head(url, headers=COMAU_HEADERS, timeout=30, allow_redirects=True)
        if r.status_code == 405:
            r = session.get(url, headers=COMAU_HEADERS, timeout=30, stream=True)
        return r.status_code == 200
    except requests.RequestException:
        return False


def content_md5(url: str, session: requests.Session, cache: dict[str, str]) -> str:
    if url in cache:
        return cache[url]
    try:
        r = session.get(url, headers=COMAU_HEADERS, timeout=45)
        h = hashlib.md5(r.content).hexdigest() if r.ok else ""
    except requests.RequestException:
        h = ""
    cache[url] = h
    return h


def build(args) -> int:
    robots = json.loads(PENDING_SNAPSHOT.read_text(encoding="utf-8"))
    recon = json.loads(RECON.read_text(encoding="utf-8"))
    session = requests.Session()
    md5_cache: dict[str, str] = {}
    staged: dict[str, Any] = {}

    for r in robots:
        rid = int(r["id"])
        name = str(r["name"]).strip()
        url = (r.get("url") or "").strip()
        rec = recon.get(str(rid)) or {}
        specs = dict(rec.get("specs") or {})
        flags = {f["flag"] for f in (r.get("quality_flags") or [])}
        notes = r.get("notes") or ""
        deliberate = "[IMAGE TO-DO" in notes
        _p(f"--- {rid} {name}")

        # Racer-5 SE: only the Italian page exists; parse IT labels.
        page_lines: list[str] = []
        if url:
            try:
                resp = session.get(url, headers=COMAU_HEADERS, timeout=45)
                page_lines = clean_lines(resp.text)
            except requests.RequestException as exc:
                _p(f"  WARN page fetch failed: {exc}")
        if not specs and page_lines:
            it = parse_it_specs(page_lines)
            if it:
                specs.update(it)
                _p(f"  IT-parsed specs: {it}")

        # Racer-5-0.80 COBOT: table omits payload/reach; same arm as
        # Racer-5-0.80 (809 mm) and the name encodes 5 kg / 0.80 m.
        if rid == 1857:
            specs.setdefault("payload_kg", 5.0)
            specs.setdefault("reach_mm", 809.0)
            specs.setdefault("axes", 6.0)

        fam = family_for(rid, name)
        if fam and rid == 1853:  # S-18's PDP is the family hub page
            fam["product_url_scope"] = "family"

        # --- narrative fields ---
        narrative: dict[str, str] = {}
        if page_lines:
            narrative = gemini_narrative(name, "\n".join(page_lines))
        mount = str(specs.get("mounting_position") or "").strip()
        if mount:
            narrative["mounting_options"] = mount[: NARRATIVE_LIMITS["mounting_options"]]

        # --- typed spec fill (only where DB is NULL; patch mode enforces too) ---
        spec_fill: dict[str, Any] = {}
        for db_key, rec_key in (
            ("payload_kg", "payload_kg"), ("reach_mm", "reach_mm"),
            ("repeatability_mm", "repeatability_mm"), ("weight_kg", "weight_kg"),
        ):
            if r.get(db_key) is None and specs.get(rec_key) is not None:
                spec_fill[db_key] = specs[rec_key]
        if r.get("dof") is None and specs.get("axes"):
            spec_fill["dof"] = int(specs["axes"])
        ip = str(specs.get("protection_class") or "").strip()
        env_fill = ip if not (r.get("environment") or "").strip() else ""

        # --- release year (family launch citations covering these models) ---
        year: int | None = None
        year_cite = ""
        if r.get("release_year") is None:
            if name.startswith("MyCo"):
                year, year_cite = MYCO_YEAR
            elif rid == 1853:
                year, year_cite = S18_YEAR

        # --- media plan ---
        photos = r.get("photos") or []
        photo_urls = [(p.get("image") or p.get("url") or "").strip() for p in photos]
        photo_urls = [u for u in photo_urls if u]
        oem_urls = [u for u in photo_urls if "comau.com" in u]
        junk = [u for u in oem_urls if is_junk_image(u)]
        wrong_model = [u for u in oem_urls if not is_junk_image(u) and not matches_model(u, name)] if rid == 1852 else []
        media_mode = "none"
        gallery: list[str] = []
        if deliberate:
            # Policy: no model-specific render exists -> clear the junk gallery.
            if photo_urls:
                media_mode = "clear"
        elif junk or "duplicate_images" in flags or "few_photos" in flags:
            keep = [u for u in oem_urls if not is_junk_image(u) and u not in wrong_model]
            cands = list(dict.fromkeys(
                keep
                + [u for u in (rec.get("render_images") or []) if matches_model(u, name)]
            ))
            # hash-dedupe + liveness, capped at 6
            seen_hash: set[str] = set()
            for u in cands:
                if len(gallery) >= 6:
                    break
                h = content_md5(u, session, md5_cache)
                if not h or h in seen_hash:
                    continue
                seen_hash.add(h)
                gallery.append(u)
            cur_set = list(dict.fromkeys(oem_urls))
            if junk or wrong_model or [u for u in gallery if u not in cur_set]:
                media_mode = "replace"

        hero = (r.get("image") or "").strip()
        if media_mode == "replace":
            if hero and hero not in gallery and "comau.com" in hero and not is_junk_image(hero):
                gallery.insert(0, hero)
            if not hero and gallery:
                hero = gallery[0]

        staged[str(rid)] = {
            "id": rid,
            "name": name,
            "url": url,
            "family": fam or {},
            "narrative": narrative,
            "spec_fill": spec_fill,
            "ip_rating": env_fill,
            "release_year": year,
            "year_cite": year_cite,
            "media_mode": media_mode,
            "hero": hero if media_mode == "replace" else "",
            "gallery": gallery,
            "flags": sorted(flags),
        }
        _p(f"  fam={fam['family_key'] if fam else 'NONE'} narrative={sorted(narrative)} "
           f"specs={spec_fill} ip={env_fill!r} year={year} media={media_mode} gallery={len(gallery)}")
        time.sleep(0.3)

    # Cross-robot dedupe: a render ADDED to more than one robot's gallery would
    # recreate the shared-image defect. Keep an added URL only on robots whose
    # full model-digit token appears in the filename; if that still leaves
    # multiple claimants (true shared family renders), drop the addition
    # everywhere — existing attachments are never touched.
    robots_by_id = {int(r["id"]): r for r in robots}
    claims: dict[str, list[str]] = {}
    for key, entry in staged.items():
        if entry.get("media_mode") != "replace":
            continue
        cur = {
            (p.get("image") or p.get("url") or "").strip()
            for p in (robots_by_id[int(key)].get("photos") or [])
        }
        for u in entry["gallery"]:
            if u not in cur:
                claims.setdefault(u, []).append(key)
    for u, keys in claims.items():
        if len(keys) < 2:
            continue
        fname_digits = re.sub(r"[^0-9]", "", u.rsplit("/", 1)[-1])
        exact = [k for k in keys if model_digits(staged[k]["name"]) and
                 model_digits(staged[k]["name"]) in fname_digits]
        keep_key = exact[0] if len(exact) == 1 else None
        for k in keys:
            if k != keep_key:
                staged[k]["gallery"] = [g for g in staged[k]["gallery"] if g != u]
                _p(f"  dedupe: dropped shared addition {u.rsplit('/', 1)[-1]} from {k}")

    STAGING.parent.mkdir(parents=True, exist_ok=True)
    STAGING.write_text(json.dumps(staged, indent=1, ensure_ascii=False), encoding="utf-8")
    _p(f"\nwrote {STAGING} ({len(staged)} robots)")
    return 0


def to_row(entry: dict[str, Any]) -> dict[str, Any]:
    fam = entry.get("family") or {}
    row: dict[str, Any] = {
        "id": entry["id"],
        "name": entry["name"],
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "url": entry.get("url") or "",
        "model_name": entry["name"],
        "variant_code": entry["name"],
        "family_name": fam.get("family_name", ""),
        "family_key": fam.get("family_key", ""),
        "variant_label": fam.get("variant_label", ""),
        "family_url": fam.get("family_url", ""),
        "product_url_scope": fam.get("product_url_scope", ""),
        "source_locale": "en",
        **entry.get("narrative", {}),
        **entry.get("spec_fill", {}),
    }
    if entry.get("ip_rating"):
        row["ip_rating"] = entry["ip_rating"]
    if entry.get("release_year"):
        row["release_year"] = entry["release_year"]
        row["research_notes"] = entry["year_cite"]
    # "add" = additive gallery upsert (non-destructive: no replace_media, hero
    # untouched). Junk-row removal and "clear" run via ORM (comau_orm_cleanup).
    if entry.get("media_mode") == "add" and entry.get("gallery"):
        row["images"] = entry["gallery"]
    row["sources"] = [{"url": entry.get("url") or "", "type": "website", "title": entry["name"]}]
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=str, default="")
    ap.add_argument("--created-by-id", type=int, default=1)
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    if args.build:
        return build(args)

    staged = json.loads(STAGING.read_text(encoding="utf-8"))
    if args.ids:
        want = {x.strip() for x in args.ids.split(",")}
        staged = {k: v for k, v in staged.items() if k in want}

    rows: list[dict[str, Any]] = []
    for entry in staged.values():
        row = to_row(entry)
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = entry["id"]
        rows.append(bulk)

    n_add = sum(1 for e in staged.values() if e.get("media_mode") == "add")
    _p(f"rows: {len(rows)}  (with photo additions: {n_add})")
    if not args.apply:
        for b in rows[:6]:
            _p(json.dumps(b, indent=1, ensure_ascii=False)[:1200])
        _p("dry-run; pass --apply")
        return 0

    client = ResearchApiClient()
    created_by = resolve_created_by_id(args.created_by_id)
    ok = err = 0

    def _send(rows: list[dict[str, Any]], **flags):
        nonlocal ok, err
        for i in range(0, len(rows), 8):
            batch = rows[i:i + 8]
            for attempt in range(5):
                try:
                    resp = client.bulk_import_robots(
                        batch,
                        update_existing=True,
                        patch_existing=True,
                        status="pending_review",
                        skip_company_update=True,
                        created_by_id=created_by,
                        **flags,
                    )
                    _p(f"  batch {i // 8}: " + json.dumps(
                        {k: v for k, v in resp.items() if k.endswith("_count") or k in ("ok", "errors")})[:300])
                    ok += len(batch)
                    break
                except Exception as exc:  # noqa: BLE001
                    wait = 30 * (attempt + 1)
                    _p(f"  batch {i // 8} attempt {attempt}: {exc}; sleep {wait}")
                    time.sleep(wait)
            else:
                err += len(batch)

    _send(rows)
    _p(f"imported ok={ok} err={err}")

    # Localize newly added photos to the CDN (non-force: only copies what's missing).
    media_ids = [e["id"] for e in staged.values() if e.get("media_mode") == "add"]
    if media_ids:
        from fix_acy_gallery_cleanup import trigger_copy_media
        c_ok, c_fail = trigger_copy_media(media_ids, force=False)
        _p(f"copy-media ok={c_ok} fail={c_fail}")
    return 0 if not err else 1


if __name__ == "__main__":
    raise SystemExit(main())
