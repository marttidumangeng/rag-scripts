#!/usr/bin/env python3
"""Audit Unitree (109) pending robots for content-queue QA gaps."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_client import ResearchApiClient

COMPANY_ID = 109


def has_image(robot: dict) -> bool:
    if robot.get("s3_image") or robot.get("image"):
        return True
    variants = robot.get("image_variants") or robot.get("image_variants_webp") or {}
    return bool(variants)


def features_len(robot: dict) -> int:
    feats = robot.get("features")
    if isinstance(feats, list):
        return sum(len(str(x)) for x in feats)
    if isinstance(feats, str):
        return len(feats.strip())
    return 0


def gap_flags(robot: dict, company_host: str) -> list[str]:
    flags: list[str] = []
    if not has_image(robot):
        flags.append("missing_image")
    url = (robot.get("website_url") or robot.get("url") or "").strip()
    if not url:
        flags.append("missing_url")
    else:
        host = urlparse(url).netloc.lower()
        if host and company_host and company_host not in host and host not in company_host:
            if "unitree" not in host:
                flags.append("url_domain_mismatch")
        if "favicon" in url.lower() or url.rstrip("/").endswith(".svg"):
            flags.append("bad_url_asset")
    desc = (robot.get("description") or "").strip()
    if not desc:
        flags.append("missing_description")
    elif len(desc) < 80:
        flags.append("short_description")
    if features_len(robot) < 40:
        flags.append("missing_features")
    if not (robot.get("purpose") or "").strip():
        flags.append("missing_purpose")
    cats = robot.get("categories") or []
    uses = robot.get("uses") or []
    if not cats and not uses:
        flags.append("missing_taxonomy")
    tags = robot.get("tags") or []
    if not tags:
        flags.append("missing_tags")
    if not robot.get("release_year"):
        flags.append("missing_release_year")
    # specs proxy
    if not any(
        robot.get(k)
        for k in (
            "weight_kg",
            "payload_kg",
            "height_mm",
            "speed",
            "battery_capacity",
            "degrees_of_freedom",
        )
    ):
        flags.append("missing_specs")
    return flags


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    client = ResearchApiClient()
    company = client.get_company(COMPANY_ID)
    host = urlparse(company.get("website") or "").netloc.lower().removeprefix("www.")
    robots: list[dict] = []
    page = 1
    while True:
        last_exc: Exception | None = None
        for attempt in range(5):
            try:
                data = client._get(
                    "robots/robots/",
                    params={
                        "company_ref": COMPANY_ID,
                        "page": page,
                        "page_size": 20,
                    },
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                import time

                time.sleep(2 ** attempt)
        else:
            raise last_exc  # type: ignore[misc]
        batch = data.get("results") or []
        robots.extend(batch)
        if not data.get("next"):
            break
        page += 1
        if page > 50:
            break
        print(f"  fetched page {page}, total {len(robots)}")
    counts: Counter[str] = Counter()
    rows = []
    for r in robots:
        flags = gap_flags(r, host)
        for f in flags:
            counts[f] += 1
        rows.append(
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "status": r.get("status"),
                "url": r.get("website_url") or r.get("url"),
                "flags": flags,
            }
        )

    out = {
        "company_id": COMPANY_ID,
        "company": company.get("name"),
        "robot_count": len(robots),
        "flag_counts": dict(counts),
        "robots": rows,
        "needs_image": [r for r in rows if "missing_image" in r["flags"]],
        "bad_url": [r for r in rows if "bad_url_asset" in r["flags"] or "missing_url" in r["flags"]],
    }
    path = Path(__file__).resolve().parent / "staging" / "reports" / "unitree_qa_audit.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("robots", len(robots))
    print("flag_counts", json.dumps(counts, indent=2))
    print("needs_image", len(out["needs_image"]))
    print("bad_url", len(out["bad_url"]))
    print("wrote", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
