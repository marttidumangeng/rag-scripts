"""Confirm AVIF placeholders are identical; map dead published KUKA to family renders."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter, defaultdict

import requests

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient

d = json.loads(open("staging/reports/kuka-1396-audit.json", encoding="utf-8").read())
dead_ids = [e["id"] for e in d["public_dead_heroes"]]
c = ResearchApiClient()

hashes: Counter = Counter()
meta = []
for rid in dead_ids:
    r = c._get(f"robots/robots/{rid}/")
    url = (r.get("s3_image") or r.get("image") or "").strip()
    body = requests.get(url, timeout=40).content
    md5 = hashlib.md5(body).hexdigest()
    hashes[md5] += 1
    fam = r.get("family_key") or r.get("family_name") or ""
    meta.append(
        {
            "id": rid,
            "name": r.get("name"),
            "family_key": r.get("family_key"),
            "family_name": r.get("family_name"),
            "family_url": r.get("family_url"),
            "url": r.get("url"),
            "md5": md5,
            "bytes": len(body),
            "magic": body[:12],
        }
    )
    print(rid, md5[:12], len(body), r.get("family_key"), r.get("name"))
    time.sleep(0.05)

print("hash clusters", dict(hashes))
out = {
    "dead_ids": dead_ids,
    "hash_clusters": dict(hashes),
    "robots": [
        {
            **{k: v for k, v in m.items() if k != "magic"},
            "magic_hex": m["magic"].hex(),
        }
        for m in meta
    ],
}
path = "staging/reports/kuka-1396-dead-avif.json"
open(path, "w", encoding="utf-8").write(json.dumps(out, indent=2) + "\n")
print("wrote", path)

# group by family_key
by_fam = defaultdict(list)
for m in meta:
    by_fam[m.get("family_key") or "?"].append(m["name"])
print("\nby family_key:")
for k, names in sorted(by_fam.items(), key=lambda x: -len(x[1])):
    print(f"  {k}: {len(names)} -> {names[:5]}...")
