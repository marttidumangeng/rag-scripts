"""Move Pangolin OEM URLs from description/features → information_sources."""
from __future__ import annotations

import sys
import time

_RESEARCH_DIR = __import__("pathlib").Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from fix_pangolin_qa import english_description, english_features
from fix_pangolin_robots import HERO


def main() -> None:
    client = ResearchApiClient()
    for rid, cfg in sorted(HERO.items()):
        body = {
            "description": english_description(cfg),
            "features": english_features(cfg),
            "information_source_urls": [
                {
                    "url": cfg["url"],
                    "title": f"{cfg['model']} product page",
                    "source_type": "website",
                }
            ],
        }
        patched = client._patch(f"robots/robots/{rid}/", body)
        srcs = patched.get("information_sources") or []
        desc = patched.get("description") or ""
        feat = patched.get("features") or ""
        bad = ("http://" in desc) or ("https://" in desc) or ("http" in feat)
        print(
            f"{'BAD' if bad else 'ok'} {rid} sources={len(srcs)} "
            f"desc_has_url={('http' in desc)} feat_has_url={('http' in feat)}"
        )
        time.sleep(0.1)


if __name__ == "__main__":
    main()
