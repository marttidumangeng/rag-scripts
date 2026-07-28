"""Rebuild Comau (company 245) features / tags / cited specs.

A bad scrape left 37 of 42 pending robots with the site's COOKIE-CONSENT BANNER
as `features` (identical 774-char blob: "Products & Solutions - Comau Consent
Details [#IABV2SETTINGS#] ... This website uses cookies"), and auto-tagging put
`Humanoid` / `Mobile Robot` on industrial arms.

Why targeted PATCH instead of bulk-import:
  * patch mode fills only BLANK fields -> cannot displace non-blank junk.
  * force_overwrite sends '' for every unsent field -> WIPES media/specs
    (learned on Noblelift). We just repaired media; we will not risk it.
  * `client._patch('robots/robots/<id>/')` writes exactly the named fields.
    RobotSerializer exposes `features` (text) and `tags` (ListField) as writable.

Specs come from comau-recon-all.json (comau_recon.py), which enforces:
  * two Comau table dialects (unit-in-label vs unit-in-value)
  * European separators ('1.300 mm' = 1300 dot-thousands; '2,5 m/s' = 2.5)
  * per-field unit binding (so 'Power consumption 350W' can't become weight)
  * a name-convention cross-check (spec_warnings) -- a flagged spec is DROPPED,
    never imported.

payload_kg / reach_mm / repeatability_mm are NOT Robot columns -> they live in
features + notes. release_year stays NULL (no per-model launch citation).

    python fix_comau_text.py                 # dry-run
    python fix_comau_text.py --apply --ids 1867
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from tag_suggest import TagCatalog

COMPANY_ID = 245
RECON = _RESEARCH_DIR / "staging" / "reports" / "comau-recon-all.json"

# Junk signatures: if features match, they must be rebuilt.
JUNK_RE = re.compile(r"consent|this website uses cookies|IABV2SETTINGS|Products & Solutions - Comau", re.I)

# --- Family typing -----------------------------------------------------------
# Comau is NOT an all-6-axis-arm maker: MyCo and the Racer COBOT are cobots,
# Rebel-S6 is a 4-axis SCARA (its PDP says Robot Type: SCARA / Axes: 4 -- 'S6'
# is the 6 kg payload, the name lies), PAL are 4/5-axis palletizers, and 1889 is
# a genuine AMR. Tags are assigned per family, never blanket.
TAGS: dict[str, list[str]] = {
    "arm": ["industrial", "industrial robot", "industrial arm", "6-axis", "robotic arm",
            "manufacturing", "factory automation", "material handling"],
    "press": ["industrial", "industrial robot", "industrial arm", "6-axis", "robotic arm",
              "press-tending", "automotive", "material handling"],
    "arm_small": ["industrial", "industrial robot", "industrial arm", "6-axis", "robotic arm",
                  "manufacturing", "assembly", "high-speed automation"],
    "cobot": ["collaborative robot", "collaborative robotics", "human-robot collaboration",
              "industrial", "6-axis", "robotic arm", "manufacturing", "assembly"],
    "scara": ["scara", "4-axis", "industrial", "industrial robot", "robotic arm",
              "assembly", "pick-and-place", "high-speed automation"],
    "pal4": ["industrial", "industrial robot", "robotic arm", "4-axis", "palletizing",
             "pallet handling", "material handling", "factory automation"],
    "pal5": ["industrial", "industrial robot", "robotic arm", "5-axis", "palletizing",
             "pallet handling", "material handling", "factory automation"],
    "amr": ["autonomous mobile robot", "mobile robot", "mobile robotics", "logistics",
            "warehouse automation", "industrial", "automation", "factory logistics"],
}

BLURB: dict[str, str] = {
    "arm": ("Comau {name} is a six-axis industrial robot for manufacturing, handling and "
            "welding duty, engineered for high uptime and a compact installed footprint."),
    "press": ("Comau {name} is a six-axis press-shop robot for press-to-press automation in "
              "cold-stamping and hot-forming lines, delivering coordinated, synchronised cycles."),
    "arm_small": ("Comau {name} is a compact, high-speed six-axis industrial robot for assembly, "
                  "material handling and light manufacturing where cycle time and precision matter."),
    "cobot": ("Comau {name} is a collaborative robot combining collaborative safety features with "
              "industrial performance, designed to work alongside operators without heavy guarding."),
    "scara": ("Comau {name} is a four-axis SCARA robot built on a modular concept for high-speed "
              "pick-and-place, assembly and precision insertion tasks."),
    "pal4": ("Comau {name} is a dedicated four-axis palletising robot built for fast, robust, "
             "high-throughput end-of-line palletising."),
    "pal5": ("Comau {name} is a dedicated five-axis palletising robot built for fast, robust, "
             "high-throughput end-of-line palletising."),
    "amr": ("Comau MyMR autonomous mobile robots move materials through production and warehouse "
            "environments, navigating autonomously to link cells and logistics flows."),
}


def classify(rid: int, name: str, specs: dict) -> str:
    n = name.lower()
    if rid == 1889 or "autonomous mobile" in n:
        return "amr"
    if "press" in n:
        return "press"
    if (specs.get("robot_type") or "").strip().lower() == "scara" or n.startswith("rebel"):
        return "scara"
    if n.startswith("myco") or "cobot" in n:
        return "cobot"
    if n.startswith("pal"):
        ax = specs.get("axes")
        return "pal5" if ax and int(ax) == 5 else "pal4"
    if n.startswith("racer") or n.startswith("s-"):
        return "arm_small"
    return "arm"


def spec_bits(specs: dict) -> list[str]:
    bits = []
    if specs.get("payload_kg") is not None:
        bits.append(f"maximum wrist payload {specs['payload_kg']:g} kg")
    if specs.get("forearm_load_kg") is not None:
        bits.append(f"additional forearm load {specs['forearm_load_kg']:g} kg")
    if specs.get("reach_mm") is not None:
        bits.append(f"maximum horizontal reach {specs['reach_mm']:g} mm")
    if specs.get("vertical_reach_mm") is not None:
        bits.append(f"vertical reach (Z-stroke) {specs['vertical_reach_mm']:g} mm")
    if specs.get("repeatability_mm") is not None:
        bits.append(f"repeatability +/-{specs['repeatability_mm']:g} mm")
    if specs.get("weight_kg") is not None:
        bits.append(f"robot weight {specs['weight_kg']:g} kg")
    if specs.get("axes") is not None:
        bits.append(f"{int(specs['axes'])} axes")
    if specs.get("protection_class"):
        bits.append(f"protection {specs['protection_class']}")
    if specs.get("mounting_position"):
        bits.append(f"mounting {specs['mounting_position']}")
    return bits


def build(rid: int, name: str, info: dict) -> dict[str, Any]:
    specs = dict(info.get("specs") or {})
    warns = info.get("spec_warnings") or []
    # A spec the cross-check flagged is untrustworthy -> drop it rather than ship
    # an invented number.
    if warns:
        for w in warns:
            for key in ("payload_kg", "reach_mm", "weight_kg"):
                if w.startswith(key.split("_")[0]):
                    specs.pop(key, None)
    kind = classify(rid, name, specs)
    parts = [BLURB[kind].format(name=name)]
    bits = spec_bits(specs)
    if bits:
        parts.append("Technical specifications (Comau datasheet): " + "; ".join(bits) + ".")
    features = " ".join(parts)

    notes_bits = []
    if specs.get("payload_kg") is not None:
        notes_bits.append(f"Payload: {specs['payload_kg']:g} kg")
    if specs.get("reach_mm") is not None:
        notes_bits.append(f"Reach: {specs['reach_mm']:g} mm")
    if specs.get("repeatability_mm") is not None:
        notes_bits.append(f"Repeatability: +/-{specs['repeatability_mm']:g} mm")
    if specs.get("weight_kg") is not None:
        notes_bits.append(f"Weight: {specs['weight_kg']:g} kg")
    return {
        "kind": kind,
        "features": features[:1800],
        "tags": TAGS[kind],
        "notes_specs": " | ".join(notes_bits),
        "dof": int(specs["axes"]) if specs.get("axes") else None,
        "weight_kg": specs.get("weight_kg"),
        "warnings": warns,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", type=str, default="")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    recon = json.loads(RECON.read_text(encoding="utf-8"))
    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)
    valid = set(catalog._by_name.keys())
    for kind, tags in TAGS.items():
        bad = [t for t in tags if t not in valid]
        if bad:
            print(f"FATAL: tags not in TagCatalog for {kind}: {bad}", file=sys.stderr)
            return 1

    robots = {int(r["id"]): r for r in client.list_robots_for_company(COMPANY_ID)}
    want = {int(x) for x in args.ids.split(",") if x.strip().isdigit()} if args.ids.strip() else None

    plan: list[dict] = []
    for rid_s, info in recon.items():
        rid = int(rid_s)
        if want and rid not in want:
            continue
        r = robots.get(rid)
        if not r:
            continue
        if (r.get("status") or "") != "pending_review":
            print(f"SKIP {rid}: status={r.get('status')}", file=sys.stderr)
            continue
        b = build(rid, info["name"], info)
        cur_feat = r.get("features") or ""
        plan.append({
            "id": rid, "name": info["name"], "kind": b["kind"],
            "junk_before": bool(JUNK_RE.search(cur_feat)),
            "feat_before": len(cur_feat), "feat_after": len(b["features"]),
            "tags_before": r.get("tags") or [], "tags_after": b["tags"],
            "notes_specs": b["notes_specs"], "warnings": b["warnings"],
            "features": b["features"], "dof": b["dof"], "weight_kg": b["weight_kg"],
            "notes_before": r.get("notes") or "", "pdp": info.get("url") or "",
        })

    junk = [p for p in plan if p["junk_before"]]
    print(f"targets: {len(plan)} | with cookie-banner junk features: {len(junk)}")
    from collections import Counter
    print("family split:", dict(Counter(p["kind"] for p in plan)))
    warned = [p for p in plan if p["warnings"]]
    if warned:
        print(f"spec warnings (dropped): {len(warned)}")
        for p in warned:
            print(f"   {p['id']} {p['name']}: {p['warnings']}")

    out = _RESEARCH_DIR / "staging" / "reports" / "comau-text-preview.json"
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for p in plan:
        print(f"  {p['id']} {p['name'][:24]:24} {p['kind']:9} junk={int(p['junk_before'])} "
              f"feat {p['feat_before']}->{p['feat_after']} tags={len(p['tags_after'])} | {p['notes_specs'][:46]}")

    if not args.apply:
        print(f"\nDry-run. preview: {out}")
        return 0

    ok = fail = 0
    for p in plan:
        body: dict[str, Any] = {"features": p["features"], "tags": p["tags_after"]}
        # dof / weight_kg ARE real Robot columns -- set them.
        # payload_kg / reach_mm / repeatability_mm are NOT columns (they silently
        # drop), so they ride in features + notes instead.
        if p.get("dof"):
            body["dof"] = p["dof"]
        if p.get("weight_kg") is not None:
            body["weight_kg"] = p["weight_kg"]
        if p["notes_specs"]:
            existing = (p.get("notes_before") or "").strip()
            cited = f"Cited specs (Comau datasheet {p['pdp']}): {p['notes_specs']}"
            body["notes"] = (f"{existing} | {cited}" if existing and cited not in existing else cited)[:2000]
        try:
            client._patch(f"robots/robots/{p['id']}/", body)
            ok += 1
            print(f"  patched {p['id']} {p['name']}")
        except Exception as exc:
            fail += 1
            print(f"  PATCH FAIL {p['id']}: {str(exc)[:140]}", file=sys.stderr)
    print(json.dumps({"patched": ok, "failed": fail}, indent=2))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
