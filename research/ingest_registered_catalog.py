"""Stage a manufacturer's full catalogue from its own structured API.

This is the generic successor to `ingest_hyundai_api.py`. That script proved
the approach but hard-coded one company; adding the next manufacturer the same
way would have started the sixty-seventh bespoke `discover_<company>.py` in
this repo, each with its own fetch loop, parsing and staging, sharing nothing.

Here the per-company knowledge lives in two places, both DATA:

  * `extractors/manufacturer_api.py` — where the JSON is and how its fields map
  * `PROFILES` below — how this company's products map onto OUR taxonomy

Everything else (dedupe, description composition, staging, reporting) is shared.

Read-only against prod (GET only). Writes a staging file for review; imports
nothing.

Usage:
    python ingest_registered_catalog.py nachirobotics.com
    python ingest_registered_catalog.py tm-robot.com
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env()

from api_client import ResearchApiClient  # noqa: E402
from extractors.base import ExtractedProduct  # noqa: E402
from extractors.manufacturer_api import ManufacturerAPIExtractor  # noqa: E402
from schema import ImageCandidate, SourceRef, StagedRobot  # noqa: E402

OUT_ROOT = _HERE / "staging" / "registered_catalog"


# --------------------------------------------------------------------------
# Taxonomy mapping
#
# These keys were read from prod's own /robots/uses/ and /robots/industries/
# endpoints, not guessed. An application label with no confident key goes to
# `uses_other` verbatim rather than being forced onto the nearest-looking slug
# — "Finishing" is not "polishing", and a wrong key is worse than a free-text
# note a human can resolve later.
# --------------------------------------------------------------------------
USE_BY_LABEL = {
    "arc welding": "arc-welding",
    "spot welding": "spot-welding",
    "welding": "welding",
    "machine tending": "machine-tending",
    "material handling": "material-handling",
    "palletizing": "palletizing",
    "dispensing": "dispensing",
    "assembly": "assembly",
    "inspection": "inspection",
    "painting": "painting",
    "pick and place": "pick-and-place",
    "packaging": "packaging",
    "sorting": "sorting",
}


def normalise_label(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()


def map_uses(labels: list[str]) -> tuple[list[str], list[str]]:
    """-> (mapped use keys, unmapped labels kept verbatim)."""
    keys, other = [], []
    for raw in labels:
        key = USE_BY_LABEL.get(normalise_label(raw))
        (keys if key else other).append(key or raw)
    return sorted(set(keys)), sorted(set(other))


@dataclass
class Profile:
    """How one manufacturer's catalogue maps onto our schema."""

    domain: str
    company_name: str            # EXACT prod name; matched exactly, never fuzzily
    company_slug: str
    company_website: str
    manufacturer_country_code: str
    sub_category_slug: str
    movement_type_keys: str
    industry_keys: str
    default_category: str
    # series prefix -> category slug, for catalogues that mix arm geometries.
    category_by_series: dict[str, str] = field(default_factory=dict)
    availability_default: str = "available"
    kind_label: str = "industrial robot"
    series_label: Callable[[str], str] | None = None
    extra_tags: tuple[str, ...] = ()


def _series_of(name: str) -> str:
    m = re.match(r"^([A-Za-z]+)", name)
    return (m.group(1).upper() if m else "MISC")


PROFILES: dict[str, Profile] = {
    # Nachi ships SCARAs (EC/EZ) alongside 6-axis arms and 4-axis palletisers,
    # so category is resolved per series rather than stamped company-wide —
    # the same mistake that put `collaborative-robot` on industrial arms in the
    # broad discovery run.
    "nachirobotics.com": Profile(
        domain="nachirobotics.com",
        company_name="Nachi-Fujikoshi Corp. (Robotics Division)",
        company_slug="nachi-fujikoshi-robotics",
        company_website="https://www.nachirobotics.com",
        # Nachi-Fujikoshi is a Japanese manufacturer (Toyama); nachirobotics.com
        # is its North American sales arm. The machines are Japanese-built.
        manufacturer_country_code="JP",
        sub_category_slug="manufacturing-industrial",
        movement_type_keys="stationary",
        industry_keys="manufacturing,automotive",
        default_category="industrial-robot",
        category_by_series={"EC": "scara-robot", "EZ": "scara-robot"},
        kind_label="industrial robot",
        extra_tags=("industrial", "japan"),
    ),
    "tm-robot.com": Profile(
        domain="tm-robot.com",
        company_name="Techman Robot",
        company_slug="techman-robot",
        company_website="https://www.tm-robot.com",
        manufacturer_country_code="TW",
        sub_category_slug="manufacturing-industrial",
        movement_type_keys="stationary",
        industry_keys="manufacturing,electronics",
        default_category="collaborative-robot",
        kind_label="collaborative robot",
        extra_tags=("collaborative", "cobot", "taiwan", "vision"),
    ),
}


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def display_name(company_name: str) -> str:
    """'Nachi-Fujikoshi Corp. (Robotics Division)' -> 'Nachi-Fujikoshi Corp'.

    The trailing period is stripped because every caller appends sentence
    punctuation; leaving it produced "manufactured by Nachi-Fujikoshi Corp..".
    """
    return company_name.split(" (")[0].strip().rstrip(".")


def article_for(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def humanise(label: str) -> str:
    """Lower-case a label for mid-sentence use, but leave acronyms alone.

    'Machine Tending' -> 'machine tending', 'AMMR Cloning' -> 'AMMR cloning'.
    """
    return " ".join(w if w.isupper() and len(w) > 1 else w.lower()
                    for w in label.split())


_KIND_BY_CATEGORY = {
    "scara-robot": "SCARA robot",
    "collaborative-robot": "collaborative robot",
    "delta-robot": "delta robot",
}


def kind_label_for(p: ExtractedProduct, prof: Profile) -> str:
    """Keep the prose and the category telling the same story.

    Nachi's EC/EZ models are categorised `scara-robot` but the company-wide
    label is "industrial robot", so the description called a SCARA something
    the category page disagreed with.
    """
    return _KIND_BY_CATEGORY.get(category_for(p, prof), prof.kind_label)


def build_description(p: ExtractedProduct, prof: Profile) -> str:
    """Factual English composed from the source's own structured fields.

    Nothing here is translated marketing copy or invented: every clause is
    conditional on a value the API actually returned.
    """
    bits: list[str] = []
    phrase = (f"{p.dof}-axis " if p.dof else "") + kind_label_for(p, prof)
    bits.append(f"{p.name} is {article_for(phrase)} {phrase} manufactured by "
                f"{display_name(prof.company_name)}.")

    cap = []
    if p.payload_kg:
        cap.append(f"a rated payload of {p.payload_kg:g} kg")
    if p.reach_mm:
        cap.append(f"a maximum reach of {p.reach_mm:g} mm")
    if cap:
        bits.append("It has " + " and ".join(cap) + ".")

    wt = p.extra.get("weight_kg")
    if wt:
        bits.append(f"The robot itself weighs {wt} kg.")
    ip = p.extra.get("ip_rating")
    if ip:
        bits.append(f"Rated IP{ip}.")
    mount = p.extra.get("mounting")
    if mount:
        bits.append(f"Supported mounting positions: {mount}.")
    apps = p.extra.get("applications")
    if apps:
        bits.append(f"Manufacturer-listed applications: {apps}.")
    if p.controllers:
        bits.append(f"Compatible controllers: {p.controllers}.")
    if p.in_production is False:
        bits.append("Listed by the manufacturer as no longer in production.")
    return " ".join(bits)


def build_features(p: ExtractedProduct) -> str:
    """One fact per line, all of it from the source's typed fields.

    Left blank previously on imports that HAD this data, which is the specific
    complaint this addresses: if a value was gathered, it gets written.
    """
    lines: list[str] = []
    if p.payload_kg:
        lines.append(f"Rated payload: {p.payload_kg:g} kg")
    if p.reach_mm:
        lines.append(f"Maximum reach: {p.reach_mm:g} mm")
    if p.dof:
        lines.append(f"Degrees of freedom: {p.dof}")
    if p.extra.get("weight_kg"):
        lines.append(f"Robot mass: {p.extra['weight_kg']} kg")
    if p.extra.get("ip_rating"):
        lines.append(f"Ingress protection: IP{p.extra['ip_rating']}")
    if p.drive:
        lines.append(f"Drive: {p.drive}")
    if p.controllers:
        lines.append(f"Compatible controllers: {p.controllers}")
    if p.extra.get("mounting"):
        lines.append(f"Mounting options: {p.extra['mounting']}")
    if p.extra.get("applications"):
        lines.append(f"Applications: {p.extra['applications']}")
    return "\n".join(lines)


def build_tags(p: ExtractedProduct, prof: Profile, use_keys: list[str],
               allowed: set[str]) -> str:
    """Candidate tags, filtered to slugs the catalogue already uses.

    Reusing existing tags rather than minting new ones keeps the tag cloud
    navigable; a tag that exists once is noise, not a facet.
    """
    cand = list(prof.extra_tags) + list(use_keys)
    if p.dof:
        cand.append(f"{p.dof}-axis")
    if p.payload_kg and p.payload_kg >= 100:
        cand.append("high-payload")
    if p.extra.get("ip_rating"):
        cand.append(f"ip{p.extra['ip_rating']}")
    if "cleanroom" in (p.extra.get("mounting") or "").lower():
        cand.append("cleanroom")
    if _series_of(p.name) in ("EC", "EZ"):
        cand.append("scara")
    return ",".join(sorted({c for c in cand if c in allowed}))


def category_for(p: ExtractedProduct, prof: Profile) -> str:
    return prof.category_by_series.get(_series_of(p.name), prof.default_category)


def main(domain: str) -> None:
    prof = PROFILES.get(domain)
    if not prof:
        raise SystemExit(f"No profile for {domain}. Known: {sorted(PROFILES)}")

    client = ResearchApiClient()

    # ---- resolve the company EXACTLY ---------------------------------------
    # A substring/first-hit match once grabbed a different company with a
    # similar name and would have imported 9 duplicates against it. Exact or
    # abort.
    target = None
    for h in client.search_companies(prof.company_name.split(" (")[0], page_size=25):
        if (h.get("name") or "").strip().lower() == prof.company_name.strip().lower():
            target = h
            break
    if not target:
        raise SystemExit(f"Could not resolve '{prof.company_name}' exactly — aborting "
                         "rather than risk staging against the wrong company.")

    held: set[str] = set()
    for r in client.list_robots_for_company(target["id"]):
        held.add(norm_key(r.get("name") or ""))
    print(f"matched company: {target['name']} (id {target['id']}) — {len(held)} held", flush=True)

    # ---- extract ------------------------------------------------------------
    result = ManufacturerAPIExtractor().extract(f"https://www.{domain}/")
    if not result:
        raise SystemExit(f"Extraction declined: {result.declined_reason}")
    print(f"catalogue: {len(result.products)} products ({result.notes})", flush=True)

    allowed_tags = {(t.get("slug") or "") for t in client.list_tags()}

    staged: list[StagedRobot] = []
    skipped: list[str] = []
    now = datetime.now(timezone.utc)

    for p in result.products:
        if norm_key(p.name) in held or (p.alias_key() and p.alias_key() in held):
            skipped.append(p.name)
            continue

        apps = [a.strip() for a in (p.extra.get("applications") or "").split(",") if a.strip()]
        use_keys, uses_other = map_uses(apps)
        series = _series_of(p.name)

        images = [ImageCandidate(
            url=u,
            source_page_url=p.source_url,
            source_tier="manufacturer",
            source_publisher=display_name(prof.company_name),
            source_domain=prof.domain,
            media_class="official_render",
            image_scope="exact_variant",
            confidence_score=88,
            match_reason="Official product image from the manufacturer's own product API",
            rights_status="official_source",
        ) for u in p.image_urls]

        staged.append(StagedRobot(
            name=p.name,
            model_name=p.name,
            company_slug=prof.company_slug,
            company_name=target["name"],
            company_website=prof.company_website,
            manufacturer_country_code=prof.manufacturer_country_code,
            family_name=f"{series} series",
            family_key=f"{prof.company_slug}:{series.lower()}",
            variant_code=p.alias,
            url=p.source_url,
            description=build_description(p, prof),
            purpose=(f"{kind_label_for(p, prof).capitalize()} for "
                     + (", ".join(humanise(a) for a in apps) if apps else "industrial automation")
                     + "."),
            features=build_features(p),
            payload_kg=p.payload_kg,
            reach_mm=p.reach_mm,
            dof=p.dof,
            weight_kg=float(p.extra["weight_kg"]) if p.extra.get("weight_kg") else None,
            ip_rating=f"IP{p.extra['ip_rating']}" if p.extra.get("ip_rating") else "",
            mounting_options=(p.extra.get("mounting") or "")[:80],
            category_slugs=category_for(p, prof),
            # sub_category_slug is a SEPARATE taxonomy from category_slugs;
            # setting only the latter leaves "No sub-category" on every row.
            sub_category_slug=prof.sub_category_slug,
            movement_type_keys=prof.movement_type_keys,
            industry_keys=prof.industry_keys,
            use_keys=",".join(use_keys),
            uses_other=", ".join(uses_other),
            tags=build_tags(p, prof, use_keys, allowed_tags),
            availability_status_key=(
                "discontinued" if p.in_production is False else prof.availability_default),
            source_locale="en",
            images=images,
            sources=[SourceRef(url=p.source_url, type="website",
                               title=f"{display_name(prof.company_name)} product catalogue")],
            confidence={"name": "high", "specs": "high", "url": "high"},
            research_notes=(
                f"[AI Research] Ingested from {display_name(prof.company_name)}'s own product "
                f"JSON API on {now.date()}. Specs are the manufacturer's structured fields, not "
                "parsed prose. Description and features are composed from those fields."
                + (f" Application labels with no matching taxonomy key were kept verbatim in "
                   f"uses_other: {', '.join(uses_other)}." if uses_other else "")
            ),
        ))

    out_dir = OUT_ROOT / prof.company_slug
    out_dir.mkdir(parents=True, exist_ok=True)
    staged_path = out_dir / "staged_import.json"
    staged_path.write_text(json.dumps({
        "generated_at": now.isoformat(),
        "workflow": "ingest_registered_catalog",
        "domain": prof.domain,
        "company": {"id": target["id"], "name": target["name"], "slug": prof.company_slug},
        "catalogue_total": len(result.products),
        "already_held_skipped": sorted(skipped),
        "robot_count": len(staged),
        "robots": [r.to_dict() for r in staged],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    per_dir = out_dir / "robots"
    per_dir.mkdir(parents=True, exist_ok=True)
    for f in per_dir.glob("*.json"):
        f.unlink()
    for r in staged:
        fn = re.sub(r"[^a-z0-9]+", "-", r.name.lower()).strip("-")[:60] or "robot"
        (per_dir / f"{fn}.json").write_text(
            json.dumps(r.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def pct(n: int) -> str:
        return f"{n} ({round(100 * n / len(staged))}%)" if staged else "0"

    print(f"\ncatalogue total : {len(result.products)}")
    print(f"already held    : {len(skipped)} -> {sorted(skipped)}")
    print(f"NEW staged      : {len(staged)}")
    print(f"  payload+reach : {pct(sum(1 for r in staged if r.payload_kg and r.reach_mm))}")
    print(f"  image         : {pct(sum(1 for r in staged if r.images))}")
    print(f"  features      : {pct(sum(1 for r in staged if r.features))}")
    print(f"  tags          : {pct(sum(1 for r in staged if r.tags))}")
    print(f"  uses          : {pct(sum(1 for r in staged if r.use_keys))}")
    print(f"  industries    : {pct(sum(1 for r in staged if r.industry_keys))}")
    print(f"\nWrote {staged_path}")
    print(f"Wrote {len(staged)} per-robot files to {per_dir}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(__file__).name} <domain>   known: {sorted(PROFILES)}")
    main(sys.argv[1])
