"""Dismiss stale verification flags on SC family siblings (company 1602)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

API = (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")


def secret() -> str:
    s = (
        os.environ.get("INTERNAL_API_SECRET")
        or os.environ.get("CONTENT_QUEUE_INTERNAL_SECRET")
        or ""
    ).strip()
    if s:
        return s
    for p in (
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env",
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env.local",
    ):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def dismiss(rid: int, flag: str) -> str:
    url = f"{API}/admin/robots/robot/content-queue/api/robot/{rid}/dismiss-flag/"
    resp = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "X-Internal-Secret": secret(),
        },
        json={"flag": flag},
        timeout=60,
    )
    return f"{resp.status_code} {(resp.text or '')[:180]}"


def main() -> int:
    client = ResearchApiClient()
    for rid in (6806, 6808, 6809):
        for flag in ("url_content_mismatch", "content_contradiction"):
            print(rid, flag, dismiss(rid, flag))
        r = client._get(f"robots/robots/{rid}/")
        errs = [
            f.get("flag")
            for f in (r.get("quality_flags") or [])
            if isinstance(f, dict) and f.get("severity") == "error"
        ]
        print("  remaining errors", errs)
    # confirm rejections
    for rid in (6721, 6722, 6725, 6734, 6735, 6736):
        r = client._get(f"robots/robots/{rid}/")
        print(
            "reject-check",
            rid,
            r.get("status"),
            r.get("auto_fix_status"),
            (r.get("rejection_reason") or "")[:60],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
