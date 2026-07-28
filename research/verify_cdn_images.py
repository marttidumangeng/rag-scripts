"""Verify robot CDN/S3 image URLs are publicly HTTP 200.

CDN path strings in the DB (or copy-media HTTP 200) are NOT enough —
owned URLs can still return CloudFront/S3 AccessDenied for missing objects.

Usage:
  python verify_cdn_images.py --company-id 882
  python verify_cdn_images.py --ids 5233 5266
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

OWNED_HOSTS = ("cdn.robotaigeek.com", "cdn-dev.robotaigeek.com")


def _is_owned(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in OWNED_HOSTS)


def _pick_urls(robot: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("s3_image", "image"):
        u = (robot.get(key) or "").strip()
        if u and u not in out:
            out.append(u)
    return out


def probe_url(url: str, timeout: float = 30.0) -> dict[str, Any]:
    result: dict[str, Any] = {
        "url": url,
        "owned": _is_owned(url),
        "status": None,
        "content_type": "",
        "ok": False,
        "error": "",
    }
    try:
        resp = requests.get(url, timeout=timeout, stream=True, headers={"User-Agent": "RobotAIGeekCDNCheck/1.0"})
        result["status"] = resp.status_code
        result["content_type"] = (resp.headers.get("content-type") or "").split(";")[0].strip()
        chunk = next(resp.iter_content(2048), b"") or b""
        body_head = chunk[:200]
        if resp.status_code == 200 and result["content_type"].startswith("image/"):
            result["ok"] = True
        elif resp.status_code == 200 and body_head.startswith((b"\xff\xd8", b"\x89PNG", b"GIF8", b"RIFF")):
            result["ok"] = True
            result["content_type"] = result["content_type"] or "image/*"
        elif b"AccessDenied" in body_head or b"<Error>" in body_head:
            result["error"] = "AccessDenied"
        else:
            result["error"] = f"HTTP {resp.status_code} ct={result['content_type']}"
        resp.close()
    except requests.RequestException as exc:
        result["error"] = str(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="HTTP-GET verify robot CDN images")
    parser.add_argument("--company-id", type=int)
    parser.add_argument("--ids", type=int, nargs="*")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    if not args.company_id and not args.ids:
        print("Need --company-id or --ids", file=sys.stderr)
        return 2

    client = ResearchApiClient()
    robots: list[dict[str, Any]] = []
    if args.company_id:
        robots.extend(client.list_robots_for_company(args.company_id))
    if args.ids:
        want = set(args.ids)
        if robots:
            robots = [r for r in robots if int(r["id"]) in want]
        else:
            for rid in args.ids:
                robots.append(client._get(f"robots/robots/{rid}/"))

    rows = []
    bad = 0
    for robot in sorted(robots, key=lambda r: int(r["id"])):
        rid = int(robot["id"])
        name = robot.get("name") or ""
        urls = _pick_urls(robot)
        if not urls:
            bad += 1
            rows.append({"id": rid, "name": name, "ok": False, "probes": [], "error": "no_image"})
            print(f"FAIL {rid} {name}: no image/s3_image")
            continue
        probes = [probe_url(u) for u in urls]
        # Prefer s3_image probe if present; else any owned URL; else first URL.
        owned = [p for p in probes if p["owned"]]
        check = owned[0] if owned else probes[0]
        ok = bool(check["ok"])
        if not ok:
            bad += 1
        rows.append({"id": rid, "name": name, "ok": ok, "probes": probes})
        mark = "OK" if ok else "FAIL"
        print(f"{mark} {rid} {name}: status={check['status']} err={check.get('error') or '-'} url={check['url'][:90]}")

    summary = {"checked": len(rows), "bad": bad, "ok": len(rows) - bad, "rows": rows}
    out = args.json_out or (
        _RESEARCH_DIR / "staging" / "reports" / f"cdn-verify-{args.company_id or 'ids'}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Summary checked={summary['checked']} ok={summary['ok']} bad={summary['bad']} -> {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
