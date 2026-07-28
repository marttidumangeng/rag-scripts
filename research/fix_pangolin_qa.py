"""Clear Pangolin (1413) QA Check ERRORs.

1. Point company website at alpha-robot.com.cn (clears url_domain_mismatch ×44).
2. Rewrite hero-robot descriptions without CJK (clears non_english_content).
3. Reject imageless duplicate/category shells (clears missing_image / missing_features
   from the pending queue — reversible via status).

Usage:
  python fix_pangolin_qa.py
  python fix_pangolin_qa.py --apply
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from fix_pangolin_robots import HERO, LEFTOVER_NOTES

COMPANY_ID = 1413
COMPANY_WEBSITE = "https://www.alpha-robot.com.cn/"


def english_description(cfg: dict) -> str:
    return (
        f"{cfg['model']} is a {cfg['role']} from Pangolin Robotics "
        f"(Suzhou Pangolin Robot Co., Ltd. / Alpha Robot, China)."
    )


def english_features(cfg: dict) -> str:
    return (
        f"Pangolin Robotics (CSJBOT / Alpha) {cfg['model']} — {cfg['role']}. "
        f"Manufacturer: Suzhou Pangolin Robot Co., Ltd. (China)."
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    co = client._get(f"companies/{COMPANY_ID}/")
    print(f"company website now={co.get('website')!r} -> {COMPANY_WEBSITE}")

    reject_ids = sorted(LEFTOVER_NOTES.keys())
    hero_ids = sorted(HERO.keys())
    print(f"heroes_to_fix_english={len(hero_ids)} leftovers_to_reject={len(reject_ids)}")

    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        for rid in hero_ids:
            print(f"  PATCH EN {rid} {HERO[rid]['model']}")
        for rid in reject_ids:
            print(f"  REJECT   {rid} {LEFTOVER_NOTES[rid][:70]}")
        return 0

    # 1) company website
    client._patch(f"companies/{COMPANY_ID}/", {"website": COMPANY_WEBSITE})
    print(f"ok company website={COMPANY_WEBSITE}")

    # 2) English-only copy on hero robots
    ok = fail = 0
    for rid in hero_ids:
        cfg = HERO[rid]
        body = {
            "source_locale": "en",
            "description": english_description(cfg),
            "purpose": cfg["purpose"],  # already English
            "features": english_features(cfg),
            "manufacturer_country": "China",
            "availability_status": 3,  # released
            "url": cfg["url"],
            "website_url": cfg["url"],
            "product_url_scope": (
                "family"
                if "speedybot" in cfg["url"] or "productnmw" in cfg["url"]
                else "exact_variant"
            ),
            "information_source_urls": [
                {
                    "url": cfg["url"],
                    "title": f"{cfg['model']} product page",
                    "source_type": "website",
                }
            ],
        }
        try:
            client._patch(f"robots/robots/{rid}/", body)
            print(f"ok EN {rid} {cfg['model']}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL EN {rid}: {e}")
            fail += 1
        time.sleep(0.1)

    # 3) reject leftovers
    for rid in reject_ids:
        reason = (
            "Duplicate / category shell / unlabeled variant — "
            + LEFTOVER_NOTES[rid]
        )[:500]
        body = {
            "status": "rejected",
            "rejection_reason": reason,
            "image": None,
            "s3_image": None,
            "images": [],
        }
        try:
            client._patch(f"robots/robots/{rid}/", body)
            print(f"ok REJECT {rid}")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL REJECT {rid}: {e}")
            fail += 1
        time.sleep(0.1)

    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
