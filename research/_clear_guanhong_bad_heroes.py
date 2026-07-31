"""Fail-closed Guanhong robots that got LinkedIn logo / shared tiny PNG as hero."""
from __future__ import annotations

import sys
from pathlib import Path

_RESEARCH = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH))

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from web_extract import WebFetcher, parse_page

BAD_IDS = [2288, 2291, 2292, 2298, 2300]
NOTE = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "OEM All-In-One PDP primary gallery slot resolved to a shared LinkedIn logo "
    "placeholder (md5 13ca6b0658e7, 5.5KB) — not a robot photo. Cleared after "
    "research-staging upload failed the duplicate-hero gate.\n"
    "ACTION FOR TEAM: source a model-specific product photo from Guanhong "
    "(szghrobot.com) or OEM brochure; do not reuse sibling All-In-One banners.\n"
    "---\n"
)


def main() -> int:
    client = ResearchApiClient()
    fetcher = WebFetcher()
    for rid in BAD_IDS:
        r = client._get(f"robots/robots/{rid}/")
        url = r.get("url") or ""
        print(f"{rid} {r.get('name')} url={url}")
        # try secondary cms images
        alt = None
        if url:
            p = parse_page(fetcher, url, rendered=False)
            for img in p.images or []:
                u = img.get("url") if isinstance(img, dict) else str(img)
                if not u or "cms/image" not in u.lower():
                    continue
                if "omo-oss-image" not in u:
                    continue
                # skip known tiny / social
                if any(x in u.lower() for x in ("linkedin", "facebook", "wechat")):
                    continue
                alt = u.split("?")[0]
                # don't pick first if it's the logo we already used — prefer later
        # Clear media via empty images + notes
        notes = NOTE + (r.get("notes") or "")
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {
                    "image": "",
                    "images": [],
                    "notes": notes,
                },
            )
            print(f"  cleared image; alt_candidate={alt}")
        except Exception as exc:
            print(f"  FAIL patch {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
