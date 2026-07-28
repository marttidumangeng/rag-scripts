"""YASKAWA / Motoman (772) full soft enrich — capture max OEM specs.

Sources (2026-07-20):
  - Motoman Spec Finder catalog → payload_kg + reach_mm (horizontal)
  - Motoman PDPs → applications / purpose / model URL
  - Motoman datasheet PDFs → weight_kg + repeatability_mm
  - Japan manufacturer country; Available; family_* by series
  - Rename Motoman <X> Robot → clean model name
  - Wipe identical nav-chrome features blob

Usage:
  python discover_yaskawa_robots.py
  python discover_yaskawa_robots.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 772
JP_ID = 11
AVAILABLE = 11
CATALOG_URL = "https://www.motoman.com/en-us/products/robots/industrial"
REPORT = _RESEARCH / "staging" / "reports" / "yaskawa-772-enrich.json"
CATALOG = json.loads(
    (_RESEARCH / "staging" / "reports" / "yaskawa-motoman-catalog.json").read_text(encoding="utf-8")
)
EXTRAS = json.loads(
    (_RESEARCH / "staging" / "reports" / "yaskawa-pdp-extras.json").read_text(encoding="utf-8")
)
SHEETS = json.loads(
    (_RESEARCH / "staging" / "reports" / "yaskawa-datasheet-specs.json").read_text(encoding="utf-8")
)

SERIES_META = {
    "gp": ("GP Series", "assembly-handling", "Material handling and general-purpose industrial automation"),
    "hc": ("HC Series", "collaborative", "Human-robot collaborative assembly and machine tending"),
    "nex": ("NEX Series", "assembly-handling", "Next-generation handling, assembly, and pick-and-pack"),
    "pl": ("PL Series", "assembly-handling", "Palletizing and pick-and-pack logistics"),
    "mpp": ("MPP Series", "assembly-handling", "High-speed pick-and-place and part transfer"),
    "sg": ("SG Series", "assembly-handling", "Compact SCARA assembly and dispensing"),
    "motomini": ("MotoMini Series", "assembly-handling", "Ultra-compact assembly and machine tending"),
    "mh": ("MH Series", "assembly-handling", "Ultra-heavy material handling and part transfer"),
    "ph": ("PH Series", "assembly-handling", "Press tending and heavy material handling"),
    "mys": ("MYS Series", "assembly-handling", "SCARA assembly, handling, and pick-and-place"),
    "ar": ("AR Series", "welding-cutting", "Arc welding"),
    "ga": ("GA Series", "welding-cutting", "Arc welding, dispensing, and material removal"),
    "sp": ("SP Series", "welding-cutting", "Spot welding and heavy industrial fabrication"),
    "mpx": ("MPX Series", "painting-dispensing", "Industrial painting and dispensing"),
}

USE_BY_SERIES = {
    "gp": "material-handling|assembly|machine-tending",
    "hc": "assembly|material-handling|machine-tending",
    "nex": "material-handling|assembly",
    "pl": "palletizing|material-handling",
    "mpp": "pick-and-place|assembly",
    "sg": "assembly|dispensing",
    "motomini": "assembly|machine-tending",
    "mh": "material-handling",
    "ph": "material-handling|press-tending",
    "mys": "assembly|pick-and-place",
    "ar": "welding",
    "ga": "welding|material-removal",
    "sp": "welding",
    "mpx": "painting|dispensing",
}

CAT_BY_SERIES = {
    "gp": "industrial-robots|articulated-robots",
    "hc": "collaborative-robots|industrial-robots",
    "nex": "industrial-robots|articulated-robots",
    "pl": "industrial-robots|articulated-robots",
    "mpp": "industrial-robots|delta-robots",
    "sg": "industrial-robots|scara-robots",
    "motomini": "industrial-robots|articulated-robots",
    "mh": "industrial-robots|articulated-robots",
    "ph": "industrial-robots|articulated-robots",
    "mys": "industrial-robots|scara-robots",
    "ar": "industrial-robots|welding-robots",
    "ga": "industrial-robots|welding-robots",
    "sp": "industrial-robots|welding-robots",
    "mpx": "industrial-robots|painting-robots",
}

JUNK_FEATURES_PREFIX = "Search for:, Contact Sales"


def clean_model(name: str) -> str:
    n = re.sub(r"(?i)^motoman\s+", "", (name or "").strip())
    n = re.sub(r"(?i)\s+robot$", "", n).strip()
    return n


def series_of(model: str) -> str:
    m = model.upper().replace(" ", "")
    for prefix, key in (
        ("MOTOMINI", "motomini"),
        ("MPX", "mpx"),
        ("MPP", "mpp"),
        ("MYS", "mys"),
        ("NEX", "nex"),
        ("GP", "gp"),
        ("HC", "hc"),
        ("PL", "pl"),
        ("SG", "sg"),
        ("MH", "mh"),
        ("PH", "ph"),
        ("AR", "ar"),
        ("GA", "ga"),
        ("SP", "sp"),
    ):
        if m.startswith(prefix):
            return key
    return "gp"


def clean_apps(apps: list[str] | None) -> list[str]:
    out = []
    for a in apps or []:
        a = re.sub(r"\s+\d+\.?\d*\s*kg.*$", "", a, flags=re.I).strip()
        a = re.sub(r"\s+YRC\d+.*$", "", a, flags=re.I).strip()
        a = re.sub(r"\s+DX\d+.*$", "", a, flags=re.I).strip()
        a = re.sub(r"\s+FS\d+.*$", "", a, flags=re.I).strip()
        a = re.sub(r"\s+YNX\d+.*$", "", a, flags=re.I).strip()
        a = re.sub(r"\s*IP\d+.*$", "", a, flags=re.I).strip()
        if a and len(a) < 40 and a.lower() not in {x.lower() for x in out}:
            out.append(a)
    return out[:10]


def map_keys(tax: dict[str, dict[str, int]], kind: str, pipe: str) -> list[int]:
    ids = []
    for k in pipe.split("|"):
        k = k.strip()
        if k and k in tax.get(kind, {}):
            ids.append(tax[kind][k])
    return ids


def taxonomy_ids(client: ResearchApiClient) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {"uses": {}, "industries": {}, "movement": {}}
    for kind, path in (
        ("uses", "robots/uses/"),
        ("industries", "robots/industries/"),
        ("movement", "robots/movement-types/"),
    ):
        try:
            for u in client._get(path) or []:
                if isinstance(u, dict) and u.get("key"):
                    out[kind][u["key"]] = u["id"]
        except Exception:
            pass
    return out


def build_features(model: str, cat: dict, sheet: dict, apps: list[str]) -> str:
    parts = [
        f"OEM Motoman {model} (Yaskawa): payload {cat['payload_kg']:g} kg; "
        f"horizontal reach {cat['hor_reach_mm']:g} mm; "
        f"vertical reach {cat['vert_reach_mm']:g} mm"
    ]
    if sheet.get("weight_kg"):
        parts.append(f"mass {sheet['weight_kg']:g} kg")
    if sheet.get("repeatability_mm") is not None:
        parts.append(f"repeatability ±{sheet['repeatability_mm']:g} mm")
    parts.append("6 controlled axes")
    if apps:
        parts.append("applications: " + ", ".join(apps[:8]))
    parts.append(f"source: {CATALOG_URL} + Motoman datasheet/PDP")
    return "; ".join(parts) + "."


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    client = ResearchApiClient()
    tax = taxonomy_ids(client)
    robots = [
        r
        for r in (client.list_robots_for_company(COMPANY_ID) or [])
        if r.get("status") == "pending_review"
    ]
    robots = sorted(robots, key=lambda x: x["id"])
    if args.limit:
        robots = robots[: args.limit]

    results: list[dict[str, Any]] = []
    for r in robots:
        rid = r["id"]
        old_name = r.get("name") or ""
        model = clean_model(old_name)
        series = series_of(model)
        fam_name, _bucket, series_blurb = SERIES_META[series]
        cat = CATALOG["models"].get(model)
        extra = EXTRAS["robots"].get(str(rid), {})
        sheet = SHEETS.get("specs", {}).get(str(rid), {})
        apps = clean_apps((extra.get("pdp") or {}).get("applications"))
        pdp_url = extra.get("pdp_url") or CATALOG_URL

        if not cat:
            results.append({"id": rid, "model": model, "error": "no catalog match"})
            print(f"SKIP {rid} {model}: no catalog")
            continue

        existing = client._get(f"robots/robots/{rid}/")
        existing_weight = existing.get("weight_kg")

        purpose_lines = apps[:] if apps else [series_blurb]
        purpose = "\n".join(purpose_lines)
        features = build_features(model, cat, sheet, apps)
        description = (
            f"Yaskawa Motoman {model} is a {fam_name} industrial robot with "
            f"{cat['payload_kg']:g} kg payload and {cat['hor_reach_mm']:g} mm horizontal reach"
            + (
                f" ({sheet['weight_kg']:g} kg mass, ±{sheet['repeatability_mm']:g} mm repeatability)"
                if sheet.get("weight_kg") and sheet.get("repeatability_mm") is not None
                else ""
            )
            + "."
        )
        notes = (
            f"[AI Research] Yaskawa/Motoman enrich 2026-07-20: Japan; family "
            f"yaskawa:{series}; Available; Spec Finder payload/reach; "
            f"datasheet weight/repeatability where parsed; OEM applications purpose. "
            f"Vert reach {cat['vert_reach_mm']:g} mm."
        )

        body: dict[str, Any] = {
            "name": model,
            "model_name": model,
            "variant_code": model,
            "manufacturer_countries": [JP_ID],
            "manufacturer_country_ref": JP_ID,
            "availability_status": AVAILABLE,
            "family_key": f"yaskawa:{series}",
            "family_name": fam_name,
            "family_url": pdp_url if "/products/robots/" in (pdp_url or "") else CATALOG_URL,
            "product_url_scope": "exact_variant",
            "url": pdp_url,
            "payload_kg": cat["payload_kg"],
            "reach_mm": cat["reach_mm"],
            "dof": 6,
            "description": description,
            "purpose": purpose,
            "features": features,
            "notes": notes,
            "tags": [
                "Yaskawa",
                "Motoman",
                model,
                fam_name.replace(" Series", ""),
                "Japan",
                "Industrial",
            ],
            "information_source_urls": [
                pdp_url,
                CATALOG_URL,
                "https://www.yaskawa-global.com",
            ],
            "uses": map_keys(tax, "uses", USE_BY_SERIES.get(series, "material-handling")),
            "industries": map_keys(tax, "industries", "industrial|manufacturing|automotive"),
            "movement_types": map_keys(tax, "movement", "stationary"),
        }
        # Prefer fixed-base for arms; ignore if key missing
        if not body["movement_types"]:
            body.pop("movement_types")
        if sheet.get("weight_kg") and sheet["weight_kg"] >= 5:
            body["weight_kg"] = sheet["weight_kg"]
        elif model == "MotoMini" and sheet.get("weight_kg"):
            body["weight_kg"] = sheet["weight_kg"]
        else:
            # Keep prior typed weight when datasheet parse missed (NEX/MYS)
            prior_w = existing_weight
            if prior_w:
                body["weight_kg"] = prior_w
        if sheet.get("repeatability_mm") is not None:
            body["repeatability_mm"] = sheet["repeatability_mm"]

        entry = {
            "id": rid,
            "old_name": old_name,
            "model": model,
            "series": series,
            "payload": cat["payload_kg"],
            "reach": cat["reach_mm"],
            "weight": body.get("weight_kg"),
            "repeat": body.get("repeatability_mm"),
            "apps": apps,
            "url": pdp_url,
        }
        print(
            f"{'APPLY' if args.apply else 'PLAN'} {rid} {old_name!r} → {model} "
            f"pay={cat['payload_kg']} reach={cat['reach_mm']} w={body.get('weight_kg')} "
            f"r={body.get('repeatability_mm')}"
        )

        if args.apply:
            try:
                client._patch(f"robots/robots/{rid}/", body)
                client._patch(
                    f"robots/robots/{rid}/",
                    {
                        "availability_status": AVAILABLE,
                        "manufacturer_countries": [JP_ID],
                        "payload_kg": cat["payload_kg"],
                        "reach_mm": cat["reach_mm"],
                    },
                )
                entry["ok"] = True
            except Exception as e:
                entry["ok"] = False
                entry["error"] = str(e)
                print(f"  ERR {e}")
            time.sleep(0.08)
        results.append(entry)

    REPORT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = sum(1 for x in results if x.get("ok"))
    print(f"report {REPORT} apply={args.apply} ok={ok}/{len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
