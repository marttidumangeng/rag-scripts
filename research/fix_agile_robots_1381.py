"""Curated enrichment for Agile Robots AG (company 1381).

Fills the gaps left by the original pass on the 8 real robots:
  - family_* metadata (all were blank) — Thor series, Yu, Agile Hand, ConTrax
  - typed specs from the OEM pages (payload/reach/repeatability; Yu dof)
  - movement_types: the arms + hand were wrongly "Wheeled" -> stationary
  - narrative fields (programming_interface / safety_fencing / ecosystem_compatibility)
  - availability normalized (stale "Released" -> Available; Thor 20 stays Announced)
  - max TCP speed appended to features (not the km/h locomotion `speed` column)

Media, videos, categories, uses, industries, tags and descriptions are LEFT AS-IS
(minimal partial PATCH is wipe-safe; unsent fields are preserved). Robot 1559
"Mobile Robotics (AMR/AGV)" is a solutions/category shell and is handled only under
--reject-1559 (Agile's AMR/AGV is partner hardware; ConTrax Module One is the kept product).

Sources: agile-robots.com Thor-series / Yu-5-Industrial / Agile-Hand / AMR-AGV pages.

    cd scripts/research
    export PYTHONIOENCODING=utf-8
    python fix_agile_robots_1381.py            # dry-run (prints each PATCH body)
    python fix_agile_robots_1381.py --apply
    python fix_agile_robots_1381.py --reject-1559 --apply   # reject the shell too
"""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any

from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient  # noqa: E402

COMPANY_ID = 1381
SLUG = "agile-robots"
AVAILABLE = 11
ANNOUNCED = 10
MOV_STATIONARY = [10]
MOV_WHEELED = [4]

THOR_URL = "https://www.agile-robots.com/en/solutions/thor-series/"
YU_URL = "https://www.agile-robots.com/en/solutions/yu-5-industrial/"
HAND_URL = "https://www.agile-robots.com/en/solutions/agile-hand/"
AMR_URL = "https://www.agile-robots.com/en/solutions/amr/agv/"

THOR_FAMILY = {
    "family_key": f"{SLUG}:thor", "family_name": "Thor Series",
    "family_url": THOR_URL, "product_url_scope": "family",
}
# Thor arms: graphical programming + hand-guiding, collaborative collision detection.
THOR_NARR = {
    "programming_interface": "Graphical programming and hand-guiding; no advanced coding required",
    "safety_fencing": "Collision detection for safe operation alongside people",
}

# rid -> curated PATCH inputs
KEEPERS: dict[int, dict[str, Any]] = {
    1552: {  # Thor 3
        "variant": "Thor 3", "url": THOR_URL + "#thor-3", "family": THOR_FAMILY,
        "typed": {"payload_kg": 3, "reach_mm": 600, "repeatability_mm": 0.03},
        "tcp": "1.8 m/s", "movement": MOV_STATIONARY, "availability": AVAILABLE,
        "narrative": THOR_NARR, "source": THOR_URL,
    },
    1553: {  # Thor 7
        "variant": "Thor 7", "url": THOR_URL + "#thor-7", "family": THOR_FAMILY,
        "typed": {"payload_kg": 7, "reach_mm": 900, "repeatability_mm": 0.03},
        "tcp": "3.1 m/s", "movement": MOV_STATIONARY, "availability": AVAILABLE,
        "narrative": THOR_NARR, "source": THOR_URL,
    },
    1554: {  # Thor 7 Pro (force-controlled)
        "variant": "Thor 7 Pro", "url": THOR_URL + "#thor-7-pro", "family": THOR_FAMILY,
        "typed": {"payload_kg": 7, "reach_mm": 900, "repeatability_mm": 0.03},
        "tcp": "2.5 m/s", "movement": MOV_STATIONARY, "availability": AVAILABLE,
        "narrative": THOR_NARR, "source": THOR_URL,
    },
    1555: {  # Thor 12
        "variant": "Thor 12", "url": THOR_URL + "#thor-12", "family": THOR_FAMILY,
        "typed": {"payload_kg": 12, "reach_mm": 1300, "repeatability_mm": 0.05},
        "tcp": "3.7 m/s", "movement": MOV_STATIONARY, "availability": AVAILABLE,
        "narrative": THOR_NARR, "source": THOR_URL,
    },
    1556: {  # Thor 20 (coming soon)
        "variant": "Thor 20", "url": THOR_URL + "#thor-20", "family": THOR_FAMILY,
        "typed": {"payload_kg": 20, "reach_mm": 1700, "repeatability_mm": 0.1},
        "tcp": "2.8 m/s", "movement": MOV_STATIONARY, "availability": ANNOUNCED,
        "narrative": THOR_NARR, "source": THOR_URL,
    },
    1557: {  # Yu 5 Industrial
        "variant": "Yu 5 Industrial", "url": YU_URL,
        "family": {"family_key": f"{SLUG}:yu", "family_name": "Yu",
                   "family_url": YU_URL, "product_url_scope": "exact_variant"},
        "typed": {"payload_kg": 5, "reach_mm": 1000, "repeatability_mm": 0.05, "dof": 6},
        "movement": MOV_STATIONARY, "availability": AVAILABLE, "source": YU_URL,
        "narrative": {
            "programming_interface": "Teaching by demonstration; drag-and-drop templates; no expert knowledge",
            "safety_fencing": "No safety fence required; ISO 10218-1/13849, force monitoring per ISO/TS 15066",
            "ecosystem_compatibility": "Integrated camera + NPU; plug-and-play peripherals; AgileTags; TUV certified",
        },
    },
    1558: {  # Agile Hand (anthropomorphic hand / end-effector)
        "variant": "Agile Hand", "url": HAND_URL,
        "family": {"family_key": f"{SLUG}:agile-hand", "family_name": "Agile Hand",
                   "family_url": HAND_URL, "product_url_scope": "exact_variant"},
        "typed": {"weight_kg": 1.5, "dof": 15},
        "movement": MOV_STATIONARY, "availability": AVAILABLE, "source": HAND_URL,
        "narrative": {
            "programming_interface": "C++/Python API, ROS-compatible; active compliant control",
            "ecosystem_compatibility": "ISO 9409-1-50-4-M6 flange adapter; ROS API (C++/Python); 1 kHz control",
        },
    },
    1560: {  # ConTrax Module One (mobile manipulator: BÄR ConTrax platform + Yu 5)
        "variant": "ConTrax Module One", "url": AMR_URL + "#contrax-module-one",
        "family": {"family_key": f"{SLUG}:contrax", "family_name": "ConTrax",
                   "family_url": AMR_URL, "product_url_scope": "exact_variant"},
        "typed": {}, "movement": MOV_WHEELED, "availability": AVAILABLE, "source": AMR_URL,
        "narrative": {
            "ecosystem_compatibility": "Integrates Agile Robots Yu 5 Industrial arm on a BAR Automation ConTrax mobile platform",
        },
    },
}

# The original pass cross-contaminated `features` across products (Thor arms carried
# Yu 5's text, Yu 5 carried Thor's, Agile Hand described "Diana 7", ConTrax carried
# Thor's). Descriptions were per-model correct; features are REPLACED with curated,
# per-model, OEM-sourced text (house style: short phrases, no banned words).
FEATURES: dict[int, str] = {
    1552: ("3 kg payload; 600 mm reach\n"
           "±0.03 mm repeatability\n"
           "Max TCP speed 1.8 m/s\n"
           "Graphical programming with hand-guiding teach; no coding required\n"
           "Collision detection for collaborative operation\n"
           "Compact arm for precise, light assembly in confined workspaces"),
    1553: ("7 kg payload; 900 mm reach\n"
           "±0.03 mm repeatability\n"
           "Max TCP speed 3.1 m/s\n"
           "Graphical programming with hand-guiding teach; no coding required\n"
           "Collision detection for collaborative operation\n"
           "Medium-duty handling and assembly"),
    1554: ("7 kg payload; 900 mm reach\n"
           "±0.03 mm repeatability\n"
           "Max TCP speed 2.5 m/s\n"
           "Force-controlled: joint torque sensors for precise force detection\n"
           "Graphical programming with hand-guiding teach; no coding required\n"
           "Collision detection for collaborative operation"),
    1555: ("12 kg payload; 1,300 mm reach\n"
           "±0.05 mm repeatability\n"
           "Max TCP speed 3.7 m/s\n"
           "Graphical programming with hand-guiding teach; no coding required\n"
           "Collision detection for collaborative operation\n"
           "Heavier assembly, machine tending and material handling"),
    1556: ("20 kg payload; 1,700 mm reach\n"
           "±0.1 mm repeatability\n"
           "Max TCP speed 2.8 m/s\n"
           "Graphical programming with hand-guiding teach; no coding required\n"
           "Collision detection for collaborative operation\n"
           "Heavy-duty loading, unloading, handling and palletizing"),
    1557: ("5 kg payload (7 kg at 850 mm reach)\n"
           "Up to 1,000 mm reach; 6 axes\n"
           "Up to ±0.05 mm repeatability\n"
           "Teaching by demonstration with drag-and-drop templates; no expert knowledge needed\n"
           "No safety fence required; complies with ISO 10218-1 and ISO 13849, force monitoring per ISO/TS 15066\n"
           "Integrated camera with on-board NPU; plug-and-play peripherals; AgileTags localization\n"
           "TUV-certified for collaborative operation"),
    1558: ("Anthropomorphic five-finger hand; 15-16 degrees of freedom across 21 joints\n"
           "1.5 kg weight; 10 N active fingertip force\n"
           "360°/s joint velocity\n"
           "Joint torque and position sensors in every actuated joint\n"
           "Active compliant control from multi-sensory feedback at 1 kHz\n"
           "C++/Python API with ROS compatibility\n"
           "ISO 9409-1-50-4-M6 fast-changer flange adapter"),
    1560: ("Mobile manipulator combining a BAR Automation ConTrax mobile platform with an "
           "Agile Robots Yu 5 Industrial arm\n"
           "Co-developed with BAR Automation and Idealworks\n"
           "Autonomous material transport and manipulation for intralogistics\n"
           "Combines autonomous navigation with collaborative arm manipulation"),
}

REJECT_1559 = {
    "status": "rejected",
    "rejection_reason": (
        "non_robot: solutions/category page, not a distinct model. Agile Robots' AMR/AGV "
        "offering is partner hardware (Idealworks iw.hub, BAR Automation driverless transport); "
        "the co-developed product ConTrax Module One (id 1560) is kept."
    ),
}


def _load_existing() -> dict[int, dict[str, Any]]:
    path = os.path.join(os.environ.get("TEMP", "/tmp"), "co1381_robots.json")
    try:
        return {r["id"]: r for r in json.load(open(path, encoding="utf-8"))}
    except Exception:
        return {}


def build_body(rid: int, spec: dict[str, Any], existing: dict[int, dict[str, Any]]) -> dict[str, Any]:
    fam = spec["family"]
    body: dict[str, Any] = {
        "url": spec["url"],
        "variant_code": spec["variant"],
        "variant_label": spec["variant"],
        "family_key": fam["family_key"],
        "family_name": fam["family_name"],
        "family_url": fam["family_url"],
        "product_url_scope": fam["product_url_scope"],
        "movement_types": spec["movement"],
        "availability_status": spec["availability"],
    }
    body.update(spec.get("typed") or {})
    body.update(spec.get("narrative") or {})

    # Replace the cross-contaminated features with curated per-model text.
    if rid in FEATURES:
        body["features"] = FEATURES[rid]

    # Add the OEM page as an information source (preserves any existing on the server).
    src = spec.get("source")
    if src:
        cur = [s.get("url") if isinstance(s, dict) else s
               for s in (existing.get(rid, {}).get("information_sources") or [])]
        urls = [u for u in cur if u]
        if src not in urls:
            urls.append(src)
        body["information_source_urls"] = urls
    return body


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--reject-1559", action="store_true", help="also reject the AMR/AGV shell (1559)")
    args = ap.parse_args()

    existing = _load_existing()
    client = ResearchApiClient()

    def patch(path: str, body: dict[str, Any]) -> Any:
        for a in range(7):
            try:
                return client._patch(path, body)
            except Exception as e:
                if any(c in str(e) for c in ("429", "502", "503")):
                    time.sleep(4 * (a + 1)); continue
                raise
        raise SystemExit(f"gave up: {path}")

    for rid, spec in KEEPERS.items():
        body = build_body(rid, spec, existing)
        print("=" * 70)
        print(f"{rid} {spec['variant']}  ({'APPLY' if args.apply else 'dry-run'})")
        print(json.dumps(body, ensure_ascii=False, indent=2))
        if args.apply:
            patch(f"robots/robots/{rid}/", body)
            print("  -> patched")

    if args.reject_1559:
        print("=" * 70)
        print(f"1559 Mobile Robotics (AMR/AGV)  REJECT  ({'APPLY' if args.apply else 'dry-run'})")
        print(json.dumps(REJECT_1559, ensure_ascii=False, indent=2))
        if args.apply:
            patch("robots/robots/1559/", REJECT_1559)
            print("  -> rejected")
    else:
        print("=" * 70)
        print("1559 held (pass --reject-1559 to reject the AMR/AGV shell)")


if __name__ == "__main__":
    main()
