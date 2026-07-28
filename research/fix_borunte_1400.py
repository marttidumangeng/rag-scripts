"""Borunte (1400) — enrich the real keepers after reconciliation (26 already rejected).

Rejects 1520A too (not in Borunte's catalog; real 1500mm model is 1510A/10kg).
Enriches the 5 confirmed-real 6-axis arms: specs, family, stationary movement,
Available, correct URL, per-model hero (localized). Renames the two application-titled
records to their real model codes.

Sources: borunte.net product pages (2917B/2830B/Spraying), made-in-china (0805A image
+ 1820A specs 20kg/1800mm/230kg). Naming BRTIRUS<reach/100><payload>A.
"""
from __future__ import annotations
import argparse, os, time
import requests
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient  # noqa: E402

STATIONARY = [10]
AVAILABLE = 11
B = "https://www.borunte.net/industrial-robot/6-axis-robot/"
FAM = {"family_key": "borunte:brtirus", "family_name": "BRTIRUS 6-Axis Industrial Robot",
       "product_url_scope": "exact_variant"}

KEEPERS = {
    4139: {"name": "BRTIRUS0805A", "url": B + "small-pick-up-robot.html",
           "typed": {"payload_kg": 5, "reach_mm": 940, "repeatability_mm": 0.05},
           "hero": "https://image.made-in-china.com/2f0j00vKdoamgErDzw/Brtirus0805A-6-Axis-Industrial-CNC-Robot-Arm-940mm-5kg-Load.jpg"},
    1831: {"name": "BRTIRUS2917B", "url": B + "six-axis-robotics-in-the-auto-industry.html",
           "typed": {"payload_kg": 17, "reach_mm": 3168, "repeatability_mm": 0.2},
           "hero": "https://www.borunte.net/uploads/33708/six-axis-robotics-in-the-auto-industry4b05d.png"},
    1832: {"name": "BRTIRUS2830B", "url": B + "ultra-long-span-six-axis-industrial-robot.html",
           "typed": {"payload_kg": 30, "reach_mm": 2800},  # model confirmed real; specs per BRTIRUS naming convention
           "hero": "https://www.borunte.net/uploads/33708/ultra-long-span-six-axis-industrial-robot7d1ad.png",
           "note": "reach/payload per BRTIRUS naming convention (2830B); OEM spec table is JS-rendered"},
    1830: {"name": "Six Axis Industrial Spraying Robot", "url": B + "six-axis-industrial-spraying-robot.html",
           "typed": {"payload_kg": 13, "reach_mm": 2000},
           "hero": "https://www.borunte.net/uploads/202333708/six-axis-industrial-spraying-robot053c6a09-1ade-440b-a6e3-ec31c0d6bf74.png",
           "feature": "Explosion-proof construction for painting and coating applications"},
    4137: {"name": "BRTIRUS1820A", "url": "https://56a795730b9a27d1.en.made-in-china.com/",
           "typed": {"payload_kg": 20, "reach_mm": 1800, "weight_kg": 230},
           "hero": None,  # no clean per-model image sourced yet
           "note": "IMAGE TO-DO: still on the shared generic hero; needs a real BRTIRUS1820A photo"},
}


def _admin_base():
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")


def copy_media(rid):
    return requests.post(f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1",
                         headers={"X-Internal-Secret": os.environ["INTERNAL_API_SECRET"].strip()}, timeout=240).status_code


def _bo(fn):
    for a in range(7):
        try:
            return fn()
        except Exception as e:
            if any(c in str(e) for c in ("429", "502", "503")):
                time.sleep(4 * (a + 1)); continue
            raise
    raise SystemExit("gave up")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    c = ResearchApiClient()

    # reject 1520A (also fabricated)
    if args.apply:
        _bo(lambda: c._patch("robots/robots/4138/", {
            "status": "rejected",
            "rejection_reason": "fabricated_variant: BRTIRUS1520A not in Borunte catalog; real 1500mm model is 1510A (10kg). Same reach x payload over-expansion as the 0101-0705 grid.",
            "notes": "[RECONCILE 2026-07-25] not a real Borunte SKU"}))
        print("4138 BRTIRUS1520A -> rejected (fabricated)")

    for rid, k in KEEPERS.items():
        cur = _bo(lambda: c._get(f"robots/robots/{rid}/")) if args.apply else {}
        body = {"name": k["name"], "model_name": k["name"], "variant_code": k["name"], "variant_label": k["name"],
                "url": k["url"], "movement_types": STATIONARY, "availability_status": AVAILABLE, **FAM, **k["typed"]}
        if k.get("feature"):
            feats = (cur.get("features") or "").rstrip()
            if k["feature"] not in feats:
                body["features"] = (feats + "\n" + k["feature"]).strip()
        if k.get("note"):
            notes = str(cur.get("notes") or "")
            body["notes"] = (f"[ENRICH 2026-07-25] {k['note']}\n" + notes).strip()
        print(f"{rid} {k['name']:34} specs={k['typed']} hero={'Y' if k['hero'] else 'IMAGE TO-DO'}")
        if not args.apply:
            continue
        _bo(lambda: c._patch(f"robots/robots/{rid}/", body))
        if k["hero"]:
            row = {"id": rid, "name": k["name"], "company_slug": "borunte-robot-co-ltd",
                   "company_name": "BORUNTE ROBOT CO., LTD", "image": k["hero"], "images": [k["hero"]], "s3_image": None}
            _bo(lambda: c.bulk_import_robots([row], update_existing=True, patch_existing=True,
                                             skip_company_update=True, replace_media=True, status="pending_review"))
            _bo(lambda: c._patch(f"robots/robots/{rid}/", {"image": k["hero"], "s3_image": None}))
            print("     hero copy-media:", copy_media(rid))

    if not args.apply:
        print("\n(dry-run; --apply to write)")


if __name__ == "__main__":
    main()
