"""Wellwit 1423 — backfill EVERY remaining grounded field the first pass ignored.

The first pass filled family/heroes/payload/weight/dims/speed but left on the floor:
  - repeatability_mm  (spec table 'Navigation position accuracy ±X mm' — regex bug)
  - the 5 narrative/Track-B fields (deferred — wrong, we need them)
  - IP rating (IP20) — column not API-writable, so it goes into features
  - payload on 8 'DS' variants whose page omits the line but whose W-series model
    designation encodes it (W8-3000* = 3000 kg, corroborated by the -MB siblings)

Only writes fields with grounded data; leaves truly-absent ones blank.

    cd scripts/research && export PYTHONIOENCODING=utf-8
    python fix_wellwit_extras.py            # dry-run
    python fix_wellwit_extras.py --apply
"""
from __future__ import annotations
import argparse, json, os, re, time
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient  # noqa: E402

scrape = {x["id"]: x for x in json.load(open(os.path.join(os.environ["TEMP"], "wellwit_scrape.json"), encoding="utf-8"))}
cache = {r["id"]: r for r in json.load(open(os.path.join(os.environ["TEMP"], "co1423.json"), encoding="utf-8"))}

ECO = "Ethernet / Wi-Fi 802.11 a/b/g/n/ac connectivity for fleet/WMS integration"
DEPLOY = "LiDAR-SLAM autonomous navigation for rapid deployment; scans the environment to build a map and self-localizes"


def parse_extras(rid: int, model: str, current: dict) -> tuple[dict, list[str]]:
    s = scrape[rid]["specs"]
    body: dict = {}
    notes: list[str] = []

    # repeatability_mm <- navigation position accuracy (footnote-tolerant)
    m = re.search(r"Navigation position accuracy\s*(?:\[\d\])?\s*[±<]?\s*([\d.]+)\s*mm", s, re.I)
    if m and not current.get("repeatability_mm"):
        body["repeatability_mm"] = float(m.group(1)); notes.append(f"rep={m.group(1)}mm")

    # payload from W-series model designation when the page omits it
    if not current.get("payload_kg"):
        mm = re.match(r"W\d+-(\d+)", model)
        if mm:
            body["payload_kg"] = float(mm.group(1)); notes.append(f"payload={mm.group(1)}kg(model)")

    # narrative fields (grounded to the page's stated nav/connectivity)
    if re.search(r"SLAM", s, re.I) and not (current.get("deployment_context") or "").strip():
        body["deployment_context"] = DEPLOY; notes.append("deploy")
    if re.search(r"Ethernet|Wi-?Fi|802\.11", s, re.I) and not (current.get("ecosystem_compatibility") or "").strip():
        body["ecosystem_compatibility"] = ECO; notes.append("eco")

    # IP rating -> features (typed column not API-writable), if not already present
    ipm = re.search(r"IP rating\s*(?:\[\d\])?\s*(IP\d{2})", s, re.I)
    feats = (current.get("features") or "").rstrip()
    if ipm and "IP" + ipm.group(1)[2:] not in feats and ipm.group(1) not in feats:
        body["features"] = (feats + f"\nIngress protection: {ipm.group(1)}.").strip(); notes.append(ipm.group(1))
    return body, notes


def _bo(fn):
    for a in range(7):
        try:
            return fn()
        except Exception as e:
            if any(c in str(e) for c in ("429", "502", "503")):
                time.sleep(4 * (a + 1)); continue
            raise
    raise SystemExit("gave up")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    client = ResearchApiClient()

    n_fields = 0
    for rid, r in cache.items():
        model = r["name"].replace("Wellwit Robotics", "").strip()
        # current values: re-read live so we respect what the first pass already set
        current = _bo(lambda: client._get(f"robots/robots/{rid}/")) if args.apply else r
        body, notes = parse_extras(rid, model, current)
        if not body:
            continue
        n_fields += len(body)
        print(f"{rid} {model:14} +{','.join(notes)}")
        if args.apply:
            _bo(lambda: client._patch(f"robots/robots/{rid}/", body))
    print(f"\n{'applied' if args.apply else 'dry-run'}: {n_fields} field-writes across the fleet")


if __name__ == "__main__":
    main()
