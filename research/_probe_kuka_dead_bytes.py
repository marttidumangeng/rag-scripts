"""Probe first bytes of 'not_image' KUKA CDN heroes."""
from __future__ import annotations

import json
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = json.loads(open("staging/reports/kuka-1396-audit.json", encoding="utf-8").read())
# rebuild full URL from public_robots
by_id = {x["id"]: x for x in d["public_robots"]}
for e in d["public_dead_heroes"][:5]:
    rid = e["id"]
    # need full URL - fetch from API
    print("---", rid, e["name"])

sys.path.insert(0, ".")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

c = ResearchApiClient()
for e in d["public_dead_heroes"][:6]:
    r = c._get(f"robots/robots/{e['id']}/")
    url = (r.get("s3_image") or r.get("image") or "").strip()
    resp = requests.get(url, timeout=40)
    body = resp.content[:64]
    print(e["id"], resp.status_code, resp.headers.get("content-type"), body[:24], "len", len(resp.content), url[-60:])
