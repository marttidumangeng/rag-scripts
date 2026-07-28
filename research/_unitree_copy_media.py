#!/usr/bin/env python3
"""Trigger copy-media for Unitree (109) robots that have an external image."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

COMPANY_ID = 109


def _admin_base() -> str:
    return (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "")
        .rstrip("/")
        .replace("/api/v1", "")
        .replace("/api/v1/", "")
    )


def _secret() -> str:
    s = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if s:
        return s
    env = Path(__file__).resolve().parents[1] / "robotaigeek-server" / ".env"
    # parents[1] is scripts/; server is sibling of scripts under repo root
    env = Path(__file__).resolve().parents[2] / "robotaigeek-server" / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    secret = _secret()
    api = _admin_base()
    if not secret or not api:
        print("Missing INTERNAL_API_SECRET or IMPORT_SYNC_API_BASE_URL")
        return 1

    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID, page_size=50)
    ok = fail = skip = 0
    for r in robots:
        rid = r["id"]
        img = (r.get("image") or r.get("s3_image") or "").strip()
        if not img:
            skip += 1
            print(f"skip {rid} {r.get('name')} (no image)")
            continue
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
        try:
            resp = requests.post(
                url, headers={"X-Internal-Secret": secret}, timeout=180
            )
            if resp.ok:
                ok += 1
                print(f"ok {rid} {r.get('name')}")
            else:
                fail += 1
                print(f"fail {rid} {r.get('name')}: HTTP {resp.status_code} {resp.text[:120]}")
        except requests.RequestException as exc:
            fail += 1
            print(f"fail {rid} {r.get('name')}: {exc}")
        time.sleep(0.3)

    print(f"\ncopy-media ok={ok} fail={fail} skip_no_image={skip}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
