"""Trigger prod admin copy-media for Estun robots with external en.estun.com images."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env()

from api_client import ResearchApiClient  # noqa: E402

COMPANY_ID = 220


def _admin_base() -> str:
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/")
    return api.replace("/api/v1", "")


def _internal_secret() -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if secret:
        return secret
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-id", type=int, default=COMPANY_ID)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    secret = _internal_secret()
    if not secret:
        print("INTERNAL_API_SECRET not configured", file=sys.stderr)
        return 1

    client = ResearchApiClient()
    robots = client.list_robots_for_company(args.company_id)
    targets = [
        r for r in robots
        if (r.get("image") or "").startswith("https://en.estun.com") and not r.get("s3_image")
    ]
    if args.limit:
        targets = targets[: args.limit]

    print(f"copy-media targets: {len(targets)}")
    ok = fail = 0
    for robot in targets:
        rid = robot["id"]
        url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                print(f"fail {rid}: HTTP {resp.status_code}")
        except requests.RequestException as exc:
            fail += 1
            print(f"fail {rid}: {exc}")
        time.sleep(0.15)

    print(f"done ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
