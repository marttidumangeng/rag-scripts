#!/usr/bin/env python3
"""Re-verify variant URLs after repair for companies 1028 + 239."""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from _audit_company_media import collect_variant_urls, ok

c = ResearchApiClient()
SESSION = requests.Session()

IDS_1028 = [2214, 3335, 3349, 3350, 3372, 3377]
IDS_239 = [5326]


def check(ids: list[int], label: str) -> list[dict]:
    bad = []
    for rid in ids:
        r = c._get(f"robots/robots/{rid}/")
        urls = collect_variant_urls(r)
        dead = []
        for lab, u in urls:
            good, code = ok(u)
            if not good:
                dead.append({"label": lab, "code": code, "url": u})
        print(f"{label} {rid} {r.get('name')}: variants={len(urls)} dead={len(dead)}")
        if dead:
            bad.append({"id": rid, "name": r.get("name"), "dead": dead})
    return bad


b1 = check(IDS_1028, "NL")
b2 = check(IDS_239, "RC")
out = {"noblelift_still_dead": b1, "robco_still_dead": b2}
Path("staging/reports/company-1028-239-variant-recheck.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print("still_dead", len(b1) + len(b2))
raise SystemExit(0 if not (b1 or b2) else 1)
