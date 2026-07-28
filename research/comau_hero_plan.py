"""Choose a genuine, distinct hero + gallery per Comau robot.

Selection rules (fail closed — an empty slot beats a wrong image):
  1. Never the banned corporate world-map graphic (by content hash).
  2. Never an image whose bytes are shared with another model (sibling
     contamination / family banners).
  3. Prefer per-model product renders; Comau publishes these at 1179x401 with a
     model-token filename. Shared 1280x485 / 1920x606 "header" crops are banners.
  4. Filename must carry this model's token, so a sibling's render can't be
     adopted.
  5. No duplicate bytes within a robot's own gallery.
  6. No hash may serve as the primary of two different robots.

Drawings (dimension/work-envelope line art) cannot be detected by hash alone —
they are excluded via DRAWING_MD5, populated from the contact-sheet review.

    python comau_hero_plan.py            # writes staging/reports/comau-hero-plan.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

AUDIT = _RESEARCH_DIR / "staging" / "reports" / "comau-image-audit.json"
RECON = _RESEARCH_DIR / "staging" / "reports" / "comau-recon-all.json"
PLAN_OUT = _RESEARCH_DIR / "staging" / "reports" / "comau-hero-plan.json"
DRAWING_FILE = _RESEARCH_DIR / "staging" / "reports" / "comau-drawing-hashes.json"

BANNED_MD5 = {"f9f947f91fd616172a68268be1ae7758"}

# Heroes pinned after visual review (contact-sheet QA). Ranking alone cannot
# tell a full-robot render from a detail crop, so a human/agent look decides.
HERO_OVERRIDE: dict[str, str] = {
    # NJ370_3.jpg (auto-ranked first) is a wrist/flange close-up, not the robot.
    "1879": "https://www.comau.com/wp-content/uploads/2024/05/Comau_NJ-370-3-0_1280x485.png",
    # Racer-7's own render: filename carries the family name but not the reach
    # ('1.4'), so the digit-based matcher scores it 'weak' and its presence on
    # sibling Racer pages (cross-nav) then disqualifies it. Racer-7 is the only
    # Racer-7 in the fleet, so this is unambiguous. Visually verified.
    "1865": "https://www.comau.com/wp-content/uploads/2024/05/comau_racer7_1280x485.jpg",
}


def load_drawing_hashes() -> set[str]:
    if DRAWING_FILE.is_file():
        return set(json.loads(DRAWING_FILE.read_text(encoding="utf-8")))
    return set()


GENERIC_BANNER_RE = re.compile(
    r"(^|[-_])header|header([-_]|\.)|r1c_header|comau-cobot|s-family|family", re.I
)


def name_signature(name: str) -> tuple[str | None, str | None]:
    """Payload / reach digit signature from a Comau model name.

    'NJ-220-2.7'    -> ('220', '27')
    'Rebel-S6-0.45' -> ('6', '045')
    'S-13'          -> ('13', None)
    """
    n = name.replace("robot", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", n)
    if m:
        return m.group(1).replace(".", ""), m.group(2).replace(".", "")
    m = re.search(r"[A-Za-z](\d+(?:\.\d+)?)\b", n)  # Rebel-S6 / S-13 / N-170
    if m:
        return m.group(1).replace(".", ""), None
    m = re.search(r"-(\d+)\b", n)
    if m:
        return m.group(1), None
    return None, None


def filename_owner_match(url: str, name: str) -> str:
    """Decide whether `url`'s filename identifies THIS model.

    Returns 'own' (payload+reach both present), 'weak' (payload only),
    'banner' (generic family/header art) or 'other' (another model's tokens).

    Comau names product renders by family prefix + payload + reach
    (NJ4_220_2.7-a.jpg belongs to NJ-220-2.7), so digit groups are the reliable
    identity — the family prefix is not.
    """
    fn = url.rsplit("/", 1)[-1]
    stem = fn.rsplit(".", 1)[0]
    pay, reach = name_signature(name)
    if not pay:
        return "banner" if GENERIC_BANNER_RE.search(stem) else "other"
    groups = re.findall(r"\d+", stem)
    # Ignore pixel-dimension groups (1280x485 etc.) that carry no model identity.
    groups = [g for g in groups if g not in {"1280", "485", "1920", "606", "1024", "388", "1179", "401"}]
    joined = "".join(groups)
    has_pay = pay in groups or (reach and f"{pay}{reach}" in joined)
    if not has_pay:
        # A sibling's payload in the filename means this is not our render.
        return "other"
    if reach:
        reach_variants = {reach, reach.rstrip("0") or reach, reach.lstrip("0") or reach}
        # '2.7' may appear as groups ['2','7'] or ['27']
        if len(reach) == 2:
            reach_variants |= {reach[0] + reach[1]}
        strong = (
            any(v in groups for v in reach_variants)
            or f"{pay}{reach}" in joined
            # reach digits split across groups, e.g. NJ4_220_2.7 -> ['4','220','2','7']
            or (len(reach) == 2 and reach[0] in groups and reach[1] in groups)
        )
        if strong:
            # A model-specific banner (NJ210-31-SH_header.jpg) is a real render of
            # THIS model -- only unattributable header art is a generic banner.
            return "own"
        return "banner" if GENERIC_BANNER_RE.search(stem) else "weak"
    return "banner" if GENERIC_BANNER_RE.search(stem) else "own"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    recon = json.loads(RECON.read_text(encoding="utf-8"))
    clusters = audit["clusters"]
    drawings = load_drawing_hashes()

    # url -> md5, and md5 -> number of distinct robots referencing it
    u2m: dict[str, str] = {}
    m2robots: dict[str, set] = {}
    for md5, c in clusters.items():
        for u in c["urls"]:
            u2m[u] = md5
        m2robots[md5] = {t.split(":")[0] for t in c["robots"]}

    plan: dict[str, dict] = {}
    used_primary: dict[str, str] = {}  # md5 -> robot id (company-wide uniqueness)

    for rid, info in recon.items():
        name = info.get("name") or ""
        cands: list[str] = []
        for u in info.get("render_images", []) + info.get("header_images", []):
            if u not in cands:
                cands.append(u)

        eligible: list[tuple[str, str, str]] = []  # (url, md5, strength)
        rejected: list[dict] = []
        for u in cands:
            md5 = u2m.get(u)
            if not md5:
                rejected.append({"url": u, "why": "fetch-failed"})
                continue
            if md5 in BANNED_MD5:
                rejected.append({"url": u, "why": "banned-world-map"})
                continue
            if md5 in drawings:
                rejected.append({"url": u, "why": "dimension-drawing"})
                continue
            match = filename_owner_match(u, name)
            if match == "other":
                rejected.append({"url": u, "why": "sibling-model-filename"})
                continue
            if match == "banner":
                rejected.append({"url": u, "why": "generic-family-banner"})
                continue
            n_pages = len(m2robots.get(md5, set()))
            # A 'weak' filename (payload only, no reach) is ambiguous between
            # spec variants -- only trust it when this is the sole page using it.
            if match == "weak" and n_pages > 1:
                rejected.append({"url": u, "why": f"ambiguous-weak-match-on-{n_pages}-pages"})
                continue
            eligible.append((u, md5, match))

        # Strong (payload+reach) filenames rank ahead of weak ones.
        eligible.sort(key=lambda t: 0 if t[2] == "own" else 1)

        # de-dup by hash inside the robot's own gallery
        seen: set[str] = set()
        gallery: list[str] = []
        for u, md5, _strength in eligible:
            if md5 in seen:
                continue
            seen.add(md5)
            gallery.append(u)

        hero = ""
        hero_md5 = ""
        override = HERO_OVERRIDE.get(rid)
        if override and override in u2m and u2m[override] not in used_primary:
            hero, hero_md5 = override, u2m[override]
        else:
            for u in gallery:
                md5 = u2m[u]
                if md5 in used_primary:  # already another robot's primary
                    continue
                hero, hero_md5 = u, md5
                break
        if hero_md5:
            used_primary[hero_md5] = rid
        # Hero leads the gallery; never duplicated inside it.
        if hero:
            gallery = [hero] + [u for u in gallery if u2m.get(u) != hero_md5]

        plan[rid] = {
            "name": name,
            "url": info.get("url"),
            "hero": hero,
            "hero_md5": hero_md5,
            "gallery": gallery,
            "gallery_md5": [u2m[u] for u in gallery],
            "candidates": cands,
            "rejected": rejected,
            "n_distinct": len(gallery),
            "imageless": not hero,
        }

    dest = Path(args.out) if args.out else PLAN_OUT
    dest.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    imageless = [f"{k} {v['name']}" for k, v in plan.items() if v["imageless"]]
    print(f"robots planned: {len(plan)}")
    print(f"with hero     : {len(plan) - len(imageless)}")
    print(f"IMAGELESS     : {len(imageless)}")
    for x in imageless:
        print(f"   - {x}")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
