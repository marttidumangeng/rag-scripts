#!/usr/bin/env python3
"""Expand Realman (882) galleries with model-specific OEM angles from PDPs.

- Scrapes each pending robot's OEM page for /prop/products-images/ assets
- Downloads, magic-byte + md5 dedupe (within robot + across company primaries)
- Caps at 4 distinct product renders; keeps current hero first when still valid
- Fail-closed: logos, tiny assets, shared site chrome

Usage:
  python fix_realman_galleries.py
  python fix_realman_galleries.py --apply --copy-media
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id

COMPANY_ID = 882
COMPANY_NAME = "Realman (Beijing) Intelligent Technology Co., Ltd."
BASE = "https://www.realman-robotics.com"
OUT_DIR = _RESEARCH_DIR / "staging" / "realman_galleries"
REPORT = _RESEARCH_DIR / "staging" / "reports" / "realman-galleries.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
SESS = requests.Session()
SESS.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})

LOGO_RE = re.compile(
    r"(?i)logo|favicon|icon|avatar|wechat|qrcode|sprite|share|banner|footer"
)
SKIP_PATH_RE = re.compile(r"(?i)/static/|/assets/css|/fonts/")
PRODUCT_IMG_RE = re.compile(
    r'(?:src|data-src|href)=["\']([^"\']*products-images[^"\']+\.(?:png|jpe?g|webp)[^"\']*)["\']',
    re.I,
)
PROP_IMG_RE = re.compile(
    r'(?:src|data-src|href)=["\']([^"\']*/prop/[^"\']+\.(?:png|jpe?g|webp)[^"\']*)["\']',
    re.I,
)

# Model folder tokens that must appear in path for a candidate (casefolded).
# Empty list = accept any products-images / prop product shot on that page.
MODEL_PATH_TOKENS: dict[str, list[str]] = {
    "eco62": ["eco62"],
    "eco63": ["eco63"],
    "eco65": ["eco65"],
    "rm65": ["rm65"],
    "rm75": ["rm75"],
    "rml63": ["rml63"],
    "rx71": ["rx71"],
    "rx75": ["rx75"],
    "dual-arm": ["双臂", "dual"],
    "single-arm": ["单臂", "single", "复合升降"],
    "realbot-01": ["realbot", "realbot-01", "轮式人形"],
    "realbot-l2": ["realbot-l2", "l2"],
    "realbot-s2": ["realbot-s2", "s2"],
    "four-steer": ["four-steer", "chassis"],
    "dual-wheel": ["dual-wheel", "chassis", "两轮", "差速"],
}


def encode_url(url: str) -> str:
    parts = urlsplit(url)
    segs = parts.path.split("/")
    enc = "/".join(quote(seg, safe="!$&'()*+,;=:@-~.") for seg in segs)
    return urlunsplit((parts.scheme, parts.netloc, enc, parts.query, parts.fragment))


def model_key_from_name(name: str, url: str) -> str:
    blob = f"{name} {url}".casefold()
    checks = [
        ("eco62", "eco62"),
        ("eco63", "eco63"),
        ("eco65", "eco65"),
        ("rml63", "rml63"),
        ("rm65", "rm65"),
        ("rm75", "rm75"),
        ("rx71", "rx71"),
        ("rx75", "rx75"),
        ("dual-arm", "dual-arm"),
        ("single-arm", "single-arm"),
        ("realbot-l2", "realbot-l2"),
        ("realbot-s2", "realbot-s2"),
        ("realbot", "realbot-01"),
        ("four-steer", "four-steer"),
        ("four steer", "four-steer"),
        ("two-wheel", "dual-wheel"),
        ("dual-wheel", "dual-wheel"),
        ("differential", "dual-wheel"),
    ]
    for needle, key in checks:
        if needle in blob:
            return key
    return "unknown"


def path_matches_model(img_url: str, model_key: str) -> bool:
    tokens = MODEL_PATH_TOKENS.get(model_key) or []
    if not tokens:
        return True
    low = img_url.casefold()
    # decode percent for chinese folder match loosely via original too
    return any(t.casefold() in low or t in img_url for t in tokens)


def fetch_html(url: str) -> str | None:
    try:
        r = SESS.get(encode_url(url), timeout=45)
        if r.status_code != 200 or len(r.text) < 500:
            return None
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except requests.RequestException:
        return None


def extract_candidates(html: str, page_url: str, model_key: str) -> list[str]:
    found: list[str] = []
    for rx in (PRODUCT_IMG_RE, PROP_IMG_RE):
        for m in rx.finditer(html):
            raw = m.group(1).strip()
            full = urljoin(page_url, raw).split("#")[0].split("?")[0]
            if LOGO_RE.search(full) or SKIP_PATH_RE.search(full):
                continue
            if "/prop/" not in full.lower() and "products-images" not in full.lower():
                continue
            if not path_matches_model(full, model_key):
                # still allow prop root product shots that aren't in a sibling folder
                if "products-images" in full.lower():
                    continue
            if full not in found:
                found.append(full)
    return found


def download(url: str) -> bytes | None:
    try:
        r = SESS.get(encode_url(url), timeout=60)
        if r.status_code != 200:
            return None
        body = r.content
        if len(body) < 25_000:
            return None
        if not (
            body[:2] == b"\xff\xd8"
            or body[:8] == b"\x89PNG\r\n\x1a\n"
            or body[:4] == b"RIFF"
        ):
            return None
        return body
    except requests.RequestException:
        return None


def score_url(url: str) -> int:
    low = url.casefold()
    score = 0
    if "正视图" in url or "main" in low or "standard" in low:
        score += 50
    if "角度" in url or "angle" in low or "侧视" in url or "顶视" in url:
        score += 40
    if "结构渲染" in url or "渲染" in url:
        score += 30
    if "thumb" in low or "icon" in low:
        score -= 100
    # Prefer larger path specificity
    score += min(len(url) // 40, 20)
    return score


def copy_media(rid: int, *, attempts: int = 5) -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    if not secret or not api:
        return "no-secret"
    url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    last = "ERR"
    for attempt in range(attempts):
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
            if resp.ok:
                return "ok"
            last = f"HTTP {resp.status_code}"
            if resp.status_code not in (502, 503, 504):
                return last
        except requests.RequestException as e:
            last = f"ERR {e}"
        time.sleep(2 ** attempt)
    return last


def list_pending(client: ResearchApiClient) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        data = client._get(
            "robots/robots/",
            params={
                "company_ref": COMPANY_ID,
                "status": "pending_review",
                "page": page,
                "page_size": 50,
            },
        )
        batch = data.get("results") or []
        rows.extend(batch)
        if not data.get("next") or not batch:
            break
        page += 1
    return rows


def plan_galleries(robots: list[dict[str, Any]]) -> dict[str, Any]:
    # md5 -> model_key that first claimed it (reuse OK within same key; block across keys)
    hash_owner_key: dict[str, str] = {}
    plans: list[dict[str, Any]] = []

    for r in sorted(robots, key=lambda x: int(x["id"])):
        rid = int(r["id"])
        name = r.get("name") or ""
        page_url = (r.get("url") or "").strip()
        model_key = model_key_from_name(name, page_url)
        is_force = "force" in name.casefold() or "六维力" in name
        is_vision = "vision" in name.casefold() or "视觉" in name
        is_standard = ("standard" in name.casefold() or "标准" in name) and not is_force

        entry: dict[str, Any] = {
            "id": rid,
            "name": name,
            "model_key": model_key,
            "page_url": page_url,
            "selected": [],
            "skipped": [],
            "note": "",
        }
        if not page_url or "realman" not in page_url.lower():
            entry["note"] = "no OEM url"
            plans.append(entry)
            continue

        html = fetch_html(page_url)
        if not html:
            entry["note"] = "page fetch failed"
            plans.append(entry)
            continue

        cands = extract_candidates(html, page_url, model_key)

        def _rank(url: str) -> int:
            s = score_url(url)
            low = url.casefold()
            if is_force and ("六维力" in url or "force" in low):
                s += 120
            if is_force and ("标准版" in url or "standard" in low):
                s -= 80
            if is_standard and ("六维力" in url or "force" in low):
                s -= 120
            if is_standard and ("标准版" in url or "standard" in low):
                s += 60
            if is_vision and ("视觉" in url or "vision" in low or "带视觉" in url):
                s += 120
            if (not is_vision) and ("视觉" in url or "带视觉" in url):
                s -= 40
            return s

        cands.sort(key=_rank, reverse=True)
        # Hard filter for Standard vs Force folders when enough remain
        if is_force:
            preferred = [u for u in cands if "六维力" in u or "force" in u.casefold()]
            if len(preferred) >= 2:
                cands = preferred + [u for u in cands if u not in preferred]
        elif is_standard:
            preferred = [
                u
                for u in cands
                if ("标准版" in u or "standard" in u.casefold())
                and "六维力" not in u
                and "force" not in u.casefold()
            ]
            if len(preferred) >= 2:
                cands = preferred + [u for u in cands if u not in preferred]
        elif is_vision:
            preferred = [
                u for u in cands if ("视觉" in u or "vision" in u.casefold() or "带视觉" in u)
            ]
            if preferred:
                cands = preferred + [u for u in cands if u not in preferred]

        selected: list[dict[str, Any]] = []
        seen_md5: set[str] = set()

        for url in cands:
            if len(selected) >= 4:
                break
            body = download(url)
            if not body:
                entry["skipped"].append({"url": url, "why": "download/magic"})
                continue
            md5 = hashlib.md5(body).hexdigest()
            if md5 in seen_md5:
                entry["skipped"].append({"url": url, "why": "dup_in_robot"})
                continue
            owner_key = hash_owner_key.get(md5)
            if owner_key is not None and owner_key != model_key:
                entry["skipped"].append(
                    {"url": url, "why": f"dup_other_model:{owner_key}"}
                )
                continue
            fname = OUT_DIR / f"{rid}_{md5[:12]}.png"
            fname.write_bytes(body)
            selected.append(
                {
                    "url": url,
                    "md5": md5,
                    "bytes": len(body),
                    "file": fname.name,
                }
            )
            seen_md5.add(md5)
            hash_owner_key.setdefault(md5, model_key)

        entry["selected"] = selected
        entry["note"] = (
            f"{len(selected)} angles"
            if selected
            else "no model-specific OEM angles found"
        )
        plans.append(entry)
        print(
            f"{rid} {name[:40]:40s} key={model_key:12s} +{len(selected)} / {len(cands)} cands"
        )

    return {
        "company_id": COMPANY_ID,
        "plans": plans,
        "with_4plus": sum(1 for p in plans if len(p["selected"]) >= 4),
        "with_2to3": sum(1 for p in plans if 2 <= len(p["selected"]) <= 3),
        "with_0to1": sum(1 for p in plans if len(p["selected"]) <= 1),
    }


def apply_plans(
    client: ResearchApiClient,
    report: dict[str, Any],
    *,
    do_copy: bool,
    only_ids: set[int] | None = None,
) -> int:
    ok = fail = 0
    for p in report["plans"]:
        rid = int(p["id"])
        if only_ids is not None and rid not in only_ids:
            continue
        urls = [x["url"] for x in p.get("selected") or []]
        if len(urls) < 2:
            # nothing useful to expand
            continue
        body = {"image": urls[0], "images": urls}
        patched = False
        for attempt in range(5):
            try:
                client._patch(f"robots/robots/{rid}/", body)
                print(f"ok patch {rid} n={len(urls)}")
                ok += 1
                patched = True
                break
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if "502" in msg or "503" in msg or "504" in msg:
                    wait = 2 ** attempt
                    print(f"retry patch {rid} after {wait}s: {e}")
                    time.sleep(wait)
                    continue
                print(f"FAIL patch {rid}: {e}")
                fail += 1
                break
        else:
            print(f"FAIL patch {rid}: exhausted retries")
            fail += 1
        if not patched:
            continue
        if do_copy:
            cm = copy_media(rid)
            print(f"  copy-media {rid}: {cm}")
            if cm != "ok":
                fail += 1
        time.sleep(0.4)
    print(f"DONE patched={ok} fail={fail}")
    return 0 if fail == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument(
        "--from-report",
        action="store_true",
        help="Reuse staging/reports/realman-galleries.json instead of re-planning",
    )
    ap.add_argument(
        "--copy-only",
        action="store_true",
        help="Only run copy-media for selected/report robots (no patch)",
    )
    args = ap.parse_args()

    only_ids = set(args.ids) if args.ids else None

    if args.from_report or args.copy_only:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
    else:
        client = ResearchApiClient()
        robots = list_pending(client)
        if only_ids is not None:
            robots = [r for r in robots if int(r["id"]) in only_ids]
        report = plan_galleries(robots)
        REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"\nsummary 4+:{report['with_4plus']} 2-3:{report['with_2to3']} "
            f"0-1:{report['with_0to1']} wrote {REPORT}"
        )

    if args.copy_only:
        fail = 0
        for p in report["plans"]:
            rid = int(p["id"])
            if only_ids is not None and rid not in only_ids:
                continue
            if len(p.get("selected") or []) < 2:
                continue
            cm = copy_media(rid)
            print(f"copy-media {rid}: {cm}")
            if cm != "ok":
                fail += 1
            time.sleep(0.4)
        return 0 if fail == 0 else 1

    if not args.apply:
        print("dry-run only; pass --apply --copy-media")
        return 0
    client = ResearchApiClient()
    return apply_plans(client, report, do_copy=args.copy_media, only_ids=only_ids)


if __name__ == "__main__":
    raise SystemExit(main())
