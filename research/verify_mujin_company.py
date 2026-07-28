"""Verify Mujin (810) enriched robots via research-side verify_lib (same as manage.py verify_content).

Scoped to company 810 only — 11 Gemini calls max. Writes report JSON; does not
touch the DB (prod verify_content must run on a prod workload to persist flags).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()

# Prefer GEMINI from server .env if research env lacks it (do not print).
if not os.environ.get("GEMINI_API_KEY"):
    server_env = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if server_env.is_file():
        for line in server_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY=") and "=" in line:
                os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

from api_client import ResearchApiClient
from schema import StagedRobot, VideoRef
from verify_lib import gemini_client, server_verification, verification_flags, verify_staged_robot

COMPANY_ID = 810
OUT = _RESEARCH_DIR / "staging" / "reports" / "mujin-verify.json"


def robot_to_staged(r: dict) -> StagedRobot:
    videos = r.get("videos") or r.get("video_urls") or []
    video_urls = []
    for v in videos:
        if isinstance(v, dict):
            u = v.get("url") or v.get("video_url") or ""
            if u:
                video_urls.append(VideoRef(url=u, title=v.get("title") or ""))
        elif isinstance(v, str) and v:
            video_urls.append(VideoRef(url=v))
    images = []
    hero = r.get("s3_image") or r.get("image") or ""
    if hero:
        images.append(hero)
    for g in r.get("images") or []:
        if isinstance(g, str) and g and g not in images:
            images.append(g)
    return StagedRobot(
        name=r.get("name") or "",
        company_slug="mujin",
        company_name="Mujin",
        description=r.get("description") or "",
        purpose=r.get("purpose") or "",
        features=r.get("features") or "",
        url=r.get("url") or "",
        image=images[0] if images else "",
        images=images[1:],
        video_urls=video_urls,
    )


def main() -> int:
    client = gemini_client()
    if client is None:
        print("ERROR: GEMINI_API_KEY not available", file=sys.stderr)
        return 1

    api = ResearchApiClient()
    robots = [
        r for r in api.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    ]
    print(f"Verifying {len(robots)} Mujin pending_review robots (1 Gemini call each)")
    session = requests.Session()
    results = []
    for i, r in enumerate(robots, 1):
        rid = r["id"]
        name = r["name"]
        print(f"[{i}/{len(robots)}] {rid} {name} …")
        try:
            staged = robot_to_staged(r)
            verification = verify_staged_robot(
                staged,
                client=client,
                session=session,
                company_name="Mujin",
                company_website="https://www.mujin.co.jp",
            )
            flags = verification_flags(verification)
            conf = verification.get("confidence")
            print(f"  confidence={conf} flags={[f.get('flag') for f in flags]} summary={(verification.get('summary') or '')[:120]}")
            results.append({
                "id": rid,
                "name": name,
                "url": r.get("url"),
                "confidence": conf,
                "flags": flags,
                "verification": verification,
                "ok": True,
            })
        except server_verification.VerificationError as exc:
            print(f"  ERROR: {exc}")
            results.append({"id": rid, "name": name, "ok": False, "error": str(exc)})
        time.sleep(1.0)

    report = {
        "company_id": COMPANY_ID,
        "count": len(results),
        "ok_count": sum(1 for x in results if x.get("ok")),
        "error_count": sum(1 for x in results if not x.get("ok")),
        "flagged": [
            {"id": x["id"], "name": x["name"], "confidence": x.get("confidence"),
             "flags": [f.get("flag") for f in (x.get("flags") or [])]}
            for x in results if x.get("ok") and (x.get("flags") or (x.get("confidence") or 100) < 50)
        ],
        "results": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    print(json.dumps({
        "ok_count": report["ok_count"],
        "error_count": report["error_count"],
        "flagged": report["flagged"],
    }, indent=2, ensure_ascii=False))
    return 0 if report["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
