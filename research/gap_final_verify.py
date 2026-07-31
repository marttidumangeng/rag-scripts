"""Final integrity verification of staging/gap_discovery/staged_import.json.

Checks: counts, website coverage, orphan robots, duplicate slugs/domains,
residual alias suspects vs prod baseline, nav-noise/CJK residue, robots-per-
company distribution, and dir/JSON sync. Run after every QA/cull/sync pass.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parent
BASE = _HERE / "staging" / "gap_discovery"
STAGED = BASE / "staged_import.json"
BASELINE = _HERE / "staging" / "reports" / "prod_baseline.json"
ROBOTS_DIR = BASE / "robots"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "robot"


data = json.loads(STAGED.read_text(encoding="utf-8"))
cos, robs = data["companies"], data["robots"]
print(f"companies={len(cos)} robots={len(robs)} "
      f"low_signal={len(data.get('low_signal_companies', []))} "
      f"alias_skips={len(data.get('skipped_alias_domains', []))}")

slugs = [c["slug"] for c in cos]
dupe_slugs = [s for s, n in Counter(slugs).items() if n > 1]
print("dup company slugs:", dupe_slugs or "none")

no_web = [c["name"] for c in cos if not c.get("website")]
print(f"companies without website: {len(no_web)}", no_web[:5])

hosts = Counter(urlparse(c["website"]).netloc.replace("www.", "").lower()
                for c in cos if c.get("website"))
dupe_hosts = {h: n for h, n in hosts.items() if n > 1}
print("dup domains:", dupe_hosts or "none")

co_set = set(slugs)
orphans = [r["name"] for r in robs if r["company_slug"] not in co_set]
print(f"orphan robots (company not staged): {len(orphans)}", orphans[:5])

nav_re = re.compile(r"^\s*(about|contact|faq|news|blog|home|products?|"
                    r"à propos|über uns|会社概要|关于我们)\s*$", re.I)
nav = [r["name"] for r in robs if nav_re.match(r["name"] or "")]
print(f"nav-noise robot names: {len(nav)}", nav[:5])

cjk = [r["name"] for r in robs
       if any("\u4e00" <= ch <= "\u9fff" or "\u3040" <= ch <= "\u30ff" for ch in r["name"])]
print(f"CJK robot names: {len(cjk)}", cjk[:5])

per_co = Counter(r["company_slug"] for r in robs)
top = per_co.most_common(8)
print("top robots/company:", top)

# alias residue vs prod baseline hosts
if BASELINE.exists():
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    prod_hosts = set(base.get("website_index", {}).keys()) if isinstance(
        base.get("website_index"), dict) else set(base.get("website_index", []))
    residue = [c["name"] for c in cos if c.get("website") and
               urlparse(c["website"]).netloc.replace("www.", "").lower() in prod_hosts]
    print(f"staged companies whose domain is in prod: {len(residue)}", residue[:5])

# dir sync check
if ROBOTS_DIR.exists():
    dirs = [d for d in ROBOTS_DIR.iterdir() if d.is_dir()]
    files = sum(len(list(d.glob('*.json'))) for d in dirs)
    stale = [d.name for d in dirs if d.name not in co_set]
    print(f"dirs={len(dirs)} files={files} (expect {len(robs)}) stale_dirs={len(stale)}")
    print("SYNC OK" if files == len(robs) and not stale else "SYNC MISMATCH!")
