"""Track A descriptions for all 55 Noblelift (1028) pending_review robots.

Why: every row flags `short_description` — current values are 32–69 chars (median 48)
and are just the OEM subtitle, e.g. "RT20G — 2000kg Sit-on Reach Truck". Worse, on
~15 rows the CRM URL resolved to a SIBLING's page, so the stored description names the
WRONG model ("PTE20N PLUS" described as "PTE15/20N PRO", "PS15CB" as "PS12/16/18CB",
"ES15 1500kg Electric Stacker" as "Stacker Truck"). `MIN_DESCRIPTION_CHARS = 100`
(robots/quality.py).

These are HAND-WRITTEN per robot, not templated — a fixed skeleton at catalog scale is
detectable boilerplate and violates the content brief (docs/Robot_Description_Content_Brief.md)
and the Track A banned-boilerplate rule. Facts come only from what was verified:

  * the OEM list-page label / PDP title+subtitle for that exact model,
  * the column-aware spec parse (fix_noblelift_sources.parse_specs) where the PDP
    actually documents the model,
  * capacity stated in the robot's OWN name,
  * a small number of externally verified facts (see EVIDENCE below).

Where the PDP documents a DIFFERENT model, no capacity or spec is asserted — the
description falls back to the product class (which the OEM's own category taxonomy
establishes) and stays shorter. Never padded, never invented.

Applied surgically via PATCH robots/robots/{id}/ {"description": ...} — bulk-import
patch mode will NOT overwrite a non-blank description, and force_overwrite would wipe
features/media.

EVIDENCE for facts not on the current noblelift.com model page:
  * T60 (3372) — "T60 is an electric tow tractor with rated capacity of 6000kg",
    nobleliftrussia.ru/files/uploads/T60N.pdf + DirectIndustry Noblelift listing.
  * PS15CB (3370) — "PS12/15CB-C is an electric counterbalanced stacker",
    nobleliftrussia.ru/files/uploads/PS1215CB-C.pdf (1500 kg for PS15CB).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

COMPANY_ID = 1028

# Track A banned words (content brief §BANNED WORDS).
BANNED = (
    "advanced", "innovative", "cutting-edge", "state-of-the-art", "high-performance",
    "enhanced", "next-generation", "revolutionary", "seamless", "robust", "powerful",
    "versatile", "sophisticated", "exceptional", "superior", "premier",
)
BANNED_MOVES = ("represents the company's vision", "has evolved through multiple iterations")

# Type nouns used to assert the entity-defining first sentence carries a robot type.
TYPE_NOUNS = (
    "agv", "forklift", "reach truck", "pallet truck", "stacker", "tow tractor",
    "order picker", "scrubber", "truck", "customisation", "tractor",
)

DESCRIPTIONS: dict[int, str] = {
    # --- AGVs -------------------------------------------------------------
    2210: "The PS20/35CB is a counterbalance AGV from Noblelift that lifts and stacks pallet loads of 2,000–3,500 kg in warehouses without a driver.",
    2214: "PS10/15CB, a driverless counterbalance stacker AGV built by Noblelift, handles 1,000–1,500 kg pallet loads on warehouse floors.",
    3186: "Noblelift's APT15 is a pallet-handling AGV rated to 1,500 kg, moving loads between pick and drop stations in a warehouse on its own.",
    3187: "RT16P/20P is a reach-truck AGV from Noblelift, carrying 1,600–2,000 kg and stacking pallets into racking with no operator aboard.",
    3331: "Built by Noblelift, the PT20/30/50 is a pallet-handling AGV that shifts 2,000–5,000 kg loads along fixed routes inside warehouses.",
    3332: "The PS20 pallet stacker AGV from Noblelift lifts 2,000 kg pallets into racking and travels warehouse aisles unattended.",
    3333: "PS15-MT is Noblelift's narrow-aisle pallet-stacking AGV, working 1,500 kg loads in racking too tight for a conventional truck.",
    3334: "Among Noblelift's narrow-aisle AGVs, the 0PX15 is a three-way truck that handles 1,500 kg pallets in high-density racking.",
    3335: "Noblelift's PS10/15CB counterbalance AGV stacks 1,000–1,500 kg pallets, driving itself between racking and staging areas.",
    3336: "As Noblelift's counterbalance AGV, the PS20/35CB moves and stacks 2,000–3,500 kg pallet loads across warehouse floors unattended.",
    3368: "PS15/20 is a pallet stacker AGV from Noblelift, lifting pallets into racking and navigating warehouse aisles without a driver.",
    # --- Electric forklifts ----------------------------------------------
    3337: "FE3D16/18/20N1 is a three-wheel electric counterbalance forklift in Noblelift's N1 Series, rated for 1,600–2,000 kg in warehouses and factories.",
    3338: "Noblelift's FEP-20-50NP belongs to its NP Series of electric forklifts, handling 2,000–5,000 kg loads in industrial material handling.",
    3339: "The FE3R16NC is a lithium-powered three-wheel electric forklift from Noblelift's N Series, rated to 1,600 kg for indoor warehouse work.",
    3340: "FE4P16/18/20/25/30/35N covers Noblelift's four-wheel N Series electric forklifts, spanning 1,600–3,500 kg for warehouse and yard handling.",
    # FEP-30/35/38P: PDP is the FEP-16-20P/25-38P family table — no per-variant
    # column for this record, so no capacity is asserted.
    3341: "Part of Noblelift's P Series, the FEP-30/35/38P is an electric counterbalance forklift for heavier pallet work in warehouses and factories.",
    3342: "FE4P16/20Q is a Q Series electric forklift from Noblelift, rated for 1,600–2,000 kg loads in warehouse and light industrial use.",
    # --- Reach trucks ------------------------------------------------------
    3343: "Noblelift's RT15Q is a sit-on reach truck rated to 1,500 kg, running on a 24 V battery to stack pallets in narrow warehouse aisles.",
    3344: "The RRS-150/180 is a stand-on reach truck from Noblelift, handling 1,500–1,800 kg loads at up to 9.5 km/h in narrow racking aisles.",
    3345: "RT16Li is Noblelift's lithium-battery sit-on reach truck, lifting 1,600 kg pallets to 9.5 m in narrow warehouse aisles.",
    3346: "Noblelift builds the RT20G as a sit-on reach truck that lifts 2,000 kg pallets to 9.5 m and travels at 14 km/h in narrow aisles.",
    3347: "The RT16/20P-CS is a cold-storage reach truck from Noblelift, built for 1,600–2,000 kg pallet work in refrigerated warehouses.",
    3348: "RT16/20Pro-RT16/20B groups Noblelift's sit-on reach trucks for 1,600–2,000 kg loads, lifting to 9.5 m on a 48 V system in narrow aisles.",
    # --- Pallet trucks -----------------------------------------------------
    3349: "PWB-150/200/300 is Noblelift's Avant lithium pallet truck range, moving 1,500–3,000 kg loads across warehouse and dock floors.",
    3350: "Noblelift's PTE15/20Q2 is an ATOM-series lithium pallet truck rated for 1,500–2,000 kg of horizontal load transport in warehouses.",
    3351: "The PTE15/20N is an EDGE-series electric pallet truck from Noblelift, moving 1,500–2,000 kg pallets across warehouse floors.",
    3352: "PTE15/20N PRO is the lithium version of Noblelift's EDGE-series pallet truck, rated for 1,500–2,000 kg in warehouse transport.",
    # 3353 PTE20N PLUS: CRM URL resolves to the PTE15/20N PRO page (PLUS != PRO) —
    # class only, no capacity.
    3353: "PTE20N PLUS is a Noblelift electric pallet truck for moving palletised loads across warehouse and distribution-centre floors.",
    # 3354-3359 PT*: CRM URLs all resolve to one PT20/25N page (columns PT20N/PT25N),
    # which documents none of these variants — class only, no capacity.
    3354: "Noblelift lists the PT15/20/25/30/36 among its electric pallet trucks, used to move palletised goods across warehouse floors.",
    3355: "The PT20/25/30PLUS is an electric pallet truck from Noblelift for horizontal pallet transport in warehouses and distribution centres.",
    3356: "PT20/25/30PRO is a Noblelift electric pallet truck, moving palletised loads between docks, staging areas and racking.",
    3357: "As part of Noblelift's pallet truck line, the PT20/25/30L moves palletised loads at floor level in warehouses and distribution centres.",
    3358: "PT20/25/30C is an electric pallet truck built by Noblelift for moving loaded pallets across warehouse and logistics floors.",
    3359: "Noblelift's PT20/25/30R is an electric pallet truck for shifting palletised goods around warehouses and loading docks.",
    # --- Hand / special pallet trucks -------------------------------------
    3374: "AC20/25/30 covers Noblelift's AC/DF Series hand pallet trucks, manually moving 2,000–3,000 kg pallets across warehouse floors.",
    # AG Series is rated 1500 kg while the record is named 20/25/30 — the two conflict,
    # so no capacity is stated for 3375/3376.
    3375: "Noblelift's AC20/25/30L belongs to its ACE/ACL Series of special-purpose pallet trucks for moving palletised loads on warehouse floors.",
    3376: "The AC20/25/30G is a hand pallet truck in Noblelift's AG Series, moving palletised goods manually across warehouse and shop floors.",
    # --- Stackers ----------------------------------------------------------
    3360: "PSE12N is a 1,200 kg electric stacker in Noblelift's EDGE series, lifting pallets into racking on warehouse floors.",
    3361: "The PSE12N PRO is an EDGE-series electric stacker from Noblelift, used to lift and move palletised loads inside warehouses.",
    3362: "PS12/16/20N is Noblelift's N Series electric stacker, lifting 1,200–2,000 kg pallets into racking in warehouses.",
    3363: "The PS12/16/20N PRO is an N Series electric stacker from Noblelift, raising palletised loads into warehouse racking.",
    3364: "Noblelift's PS12/16/20L is a walkie electric stacker handling 1,200–2,000 kg pallets in warehouse aisles.",
    3365: "PS12/16/20C is a walkie electric stacker from Noblelift, lifting palletised loads into racking on warehouse floors.",
    3366: "The PS12/16/20D is an electric stacker in Noblelift's walkie range, used to raise and move pallets inside warehouses.",
    3367: "PS12/16/20R is an electric stacker from Noblelift for lifting and transporting palletised loads in warehouse aisles.",
    3369: "Noblelift's PS14/16RP is an electric stacker used to lift palletised goods into racking and move them across warehouse floors.",
    3370: "PS15CB is Noblelift's counterbalanced electric stacker, rated to 1,500 kg for lifting pallets without straddle legs in warehouses.",
    3381: "ES15 is a 1,500 kg electric stacker offered by Noblelift for lifting and moving palletised loads inside warehouses.",
    # --- Tow tractors ------------------------------------------------------
    3371: "The T20/30/40/50 is an electric tow tractor from Noblelift, pulling trailers and load trains through warehouses and factories.",
    3372: "T60 is Noblelift's electric tow tractor with a rated towing capacity of 6,000 kg, hauling carts and trailers in industrial plants.",
    # --- Order picker ------------------------------------------------------
    # OPL10: no OPL10 exists in the OEM catalog; its PDP documents OPL12N/OPL25N.
    # Class only — flagged separately for human review.
    3373: "OPL10 is a low-level order picker from Noblelift, carrying an operator along warehouse aisles to pick items onto pallets.",
    # --- Cleaning ----------------------------------------------------------
    3377: "NR530 is a ride-on floor scrubber from Noblelift with a 530 mm cleaning path, weighing 120 kg, for cleaning warehouse and factory floors.",
    # --- Non-standard customisation programmes ----------------------------
    3378: "Counterbalanced Forklift is Noblelift's non-standard customisation programme, adapting its counterbalance forklifts to specific site requirements.",
    3379: "Listed by Noblelift as a non-standard customisation option, Reach Truck covers reach trucks adapted to customer-specific racking needs.",
    3380: "Pallet Truck is a non-standard customisation line from Noblelift, covering pallet trucks built to customer-specified requirements.",
}


def validate(rid: int, name: str, text: str) -> list[str]:
    """Mechanical post-validation, per content brief 'Post-validate mechanically'."""
    errs: list[str] = []
    n = len(text)
    if n < 100:
        errs.append(f"too short ({n} < 100 MIN_DESCRIPTION_CHARS)")
    if n > 200:
        errs.append(f"too long ({n} > 200)")
    low = text.lower()
    for w in BANNED:
        if re.search(rf"\b{re.escape(w)}\b", low):
            errs.append(f"banned word: {w}")
    for m in BANNED_MOVES:
        if m in low:
            errs.append(f"banned move: {m}")
    first = re.split(r"(?<=[.!?])\s", text)[0]
    if "noblelift" not in first.lower():
        errs.append("first sentence does not name the maker")
    if not any(t in first.lower() for t in TYPE_NOUNS):
        errs.append("first sentence has no robot-type noun")
    # entity check: the robot's model token must appear in the first sentence
    tok = re.sub(r"^Noblelift\s+", "", name, flags=re.I).split()[0]
    if tok.lower() not in first.lower():
        errs.append(f"first sentence does not name the robot ({tok})")
    if re.search(r"\b(19|20)\d{2}\b", text):
        errs.append("contains a year (no release_year is verified for this fleet)")
    return errs


def opener_key(text: str) -> str:
    """Coarse first-clause shape, to enforce 'no two descriptions open alike'."""
    return " ".join(w.lower().strip(",") for w in text.split()[:3])


def main() -> int:
    ap = argparse.ArgumentParser(description="Track A descriptions for Noblelift 1028")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", nargs="*", type=int)
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    }

    ids = args.ids or sorted(DESCRIPTIONS)
    missing = [i for i in robots if i not in DESCRIPTIONS]
    if missing:
        print(f"ERROR: no description written for {missing}", file=sys.stderr)
        return 1

    all_errs = 0
    openers: dict[str, list[int]] = {}
    for rid in ids:
        r = robots.get(rid)
        if not r:
            print(f"SKIP {rid}: not pending_review")
            continue
        text = DESCRIPTIONS[rid]
        errs = validate(rid, r["name"], text)
        openers.setdefault(opener_key(text), []).append(rid)
        if errs:
            all_errs += 1
            print(f"FAIL {rid} {r['name'][:24]}: {errs}", file=sys.stderr)
        else:
            print(f"ok   {rid} {r['name'][:24]:24} {len(text):3}c  {text[:58]}…")

    dup_openers = {k: v for k, v in openers.items() if len(v) > 1}
    if dup_openers:
        print("\nWARN duplicate opening clauses (brief: no two may open alike):")
        for k, v in dup_openers.items():
            print(f"  {k!r} -> {v}")

    if all_errs:
        print(f"\nERROR: {all_errs} descriptions failed validation", file=sys.stderr)
        return 1
    print(f"\nvalidated {len(ids)} descriptions, 0 errors, "
          f"{len(dup_openers)} repeated opener shapes")

    if not args.apply:
        print("Dry-run. Re-run with --apply")
        return 0

    ok = fail = 0
    for rid in ids:
        if rid not in robots:
            continue
        try:
            client._patch(f"robots/robots/{rid}/", {"description": DESCRIPTIONS[rid]})
            ok += 1
            print(f"patched {rid}")
        except Exception as exc:
            fail += 1
            print(f"FAIL patch {rid}: {exc}", file=sys.stderr)
        time.sleep(0.15)
    print(json.dumps({"patched": ok, "failed": fail}, indent=2))
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
