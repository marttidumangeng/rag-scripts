"""Check Yaskawa 772 merge pairs still live + sample features."""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()


def norm(name: str) -> str:
    n = re.sub(r"(?i)^motoman\s+", "", name.strip())
    n = re.sub(r"(?i)\s+robot$", "", n)
    return re.sub(r"[^a-z0-9]", "", n.lower())


def is_moto(name: str) -> bool:
    return bool(re.match(r"(?i)^motoman\s+.+\brobot$", name.strip()))


c = ResearchApiClient()
robots = c.list_robots_for_company(772) or []
print("total", len(robots), Counter(r.get("status") for r in robots))
moto, short = {}, {}
for r in robots:
    k = norm(r.get("name") or "")
    (moto if is_moto(r.get("name") or "") else short).setdefault(k, []).append(r)
pairs = sorted(set(moto) & set(short))
print("pair keys", len(pairs))
for k in pairs[:10]:
    print(" ", k, "moto", [x["id"] for x in moto[k]], "short", [x["id"] for x in short[k]])
print("motoman-only", len(set(moto) - set(short)))
print("short-only", len(set(short) - set(moto)))

# features fingerprint
fps = Counter()
for r in robots[:20]:
    d = c._get(f"robots/robots/{r['id']}/")
    feat = (d.get("features") or "").strip()
    fps[feat[:60]] += 1
    if r["id"] in (2594, 2600, 3007):
        print(f"SAMPLE {r['id']} {r['name']}")
        print("  feat:", feat[:200])
        print("  purpose:", (d.get("purpose") or "")[:120])
        print("  url:", (d.get("url") or "")[:100])
print("feat prefixes among first 20:", fps)
