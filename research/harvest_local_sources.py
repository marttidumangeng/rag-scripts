"""Harvest robot manufacturers from locally saved source files (seeds/gap_sources/).

Part of the Manufacturer & Robot Gap Discovery workflow. Parses the user-provided
source lists (BVP Atlas, Built In, CompaniesMarketCap, Upwork, Clutch, Wellfound,
awesome-robotics-ai-companies) and uses Gemini to extract only actual robot/hardware
manufacturers (excluding service agencies, dev shops, VCs, and component suppliers).

Output: staging/gap_discovery/local_sources_harvest.json
  [{"name", "website", "country", "category", "source", "is_manufacturer", "note"}]

Usage:
  python harvest_local_sources.py             # harvest all files
  python harvest_local_sources.py --file X.md # single file
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from load_env import load_research_env

load_research_env()

from google import genai  # noqa: E402

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "seeds" / "gap_sources"
OUT_DIR = ROOT / "staging" / "gap_discovery"
OUT_PATH = OUT_DIR / "local_sources_harvest.json"


def set_round(n: int) -> None:
    """Switch source dir and output file for a later discovery round."""
    global SRC_DIR, OUT_PATH
    if n and n > 1:
        SRC_DIR = ROOT / "seeds" / f"gap_sources_{n}"
        OUT_PATH = OUT_DIR / f"local_sources_{n}_harvest.json"

MODEL = "gemini-2.5-flash"

SOURCE_LABELS = {
    "bvp_atlas": "bvp-atlas",
    "builtin_roundup": "builtin",
    "marketcap_robotics": "companiesmarketcap",
    "upwork_agencies": "upwork",
    "clutch_ph": "clutch",
    "awesome_robotics": "awesome-robotics-github",
    "awesome_robotics_full": "awesome-robotics-github",
}

PROMPT = """You are helping build a robot manufacturer database. Below is raw text scraped
from a listing page of robotics-related companies.

Extract EVERY company mentioned as a listed entry (not example clients, investors,
or partner brands mentioned in passing). For each company, decide whether it is an
actual MANUFACTURER of physical robots or robotic hardware products (industrial arms,
cobots, AMRs, humanoids, drones, medical robots, exoskeletons, robotic kitchens, etc.).

NOT manufacturers (set is_manufacturer=false): software-only companies, AI platforms,
service agencies, engineering consultancies, dev shops, system integrators without own
robot products, VC firms, component suppliers (lidar, batteries, sensors, ballscrews),
BPO/call centers, web design agencies.

Return STRICT JSON array, no markdown fences, each item:
{"name": "<clean official company name in English>",
 "website": "<official website URL if present in text, else empty string>",
 "country": "<country if determinable, else empty string>",
 "category": "<one short category like 'humanoid', 'industrial-arm', 'amr', 'drone', 'medical', 'agriculture', 'defense', 'consumer', 'logistics', 'other'>",
 "is_manufacturer": true/false,
 "note": "<one short sentence: what they make>"}

Rules:
- Clean names: strip suffixes like "(We're Hiring!)", ratings, employee counts.
- Deduplicate within your output.
- If the text contains no companies, return [].

SOURCE TEXT:
"""


def llm_extract(client: genai.Client, text: str, retries: int = 3) -> list[dict]:
    for attempt in range(retries):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=PROMPT + text[:60000],
            )
            raw = (resp.text or "").strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S)
            data = json.loads(raw)
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict) and d.get("name")]
            return []
        except Exception as exc:  # noqa: BLE001
            print(f"    LLM attempt {attempt + 1} failed: {exc}")
            time.sleep(5 * (attempt + 1))
    return []


def source_label(fname: str) -> str:
    stem = Path(fname).stem
    if stem.startswith("wellfound"):
        return "wellfound"
    return SOURCE_LABELS.get(stem, stem)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="harvest a single file only")
    ap.add_argument("--round", type=int, default=1, help="discovery round (2 -> gap_sources_2, local_sources_2_harvest.json)")
    args = ap.parse_args()
    set_round(args.round)

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY not set (load_env should provide it)")
    client = genai.Client(api_key=api_key)

    files = sorted(SRC_DIR.glob("*.*"))
    if args.file:
        files = [SRC_DIR / args.file]
    # Skip duplicate truncated copy of awesome list
    files = [f for f in files if f.name != "awesome_robotics.md"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    if OUT_PATH.exists():
        for item in json.loads(OUT_PATH.read_text(encoding="utf-8")):
            existing[item["name"].lower()] = item

    for path in files:
        label = source_label(path.name)
        text = path.read_text(encoding="utf-8", errors="replace")
        print(f"[{path.name}] ({label}) {len(text)} chars")
        items = llm_extract(client, text)
        added = 0
        for it in items:
            key = it["name"].strip().lower()
            if not key:
                continue
            it["source"] = label
            if key in existing:
                # merge: prefer entry with website; append source
                prev = existing[key]
                if not prev.get("website") and it.get("website"):
                    prev["website"] = it["website"]
                if label not in prev.get("source", ""):
                    prev["source"] = prev["source"] + "," + label
            else:
                existing[key] = it
                added += 1
        print(f"  extracted {len(items)} entries, {added} new (cumulative {len(existing)})")
        OUT_PATH.write_text(
            json.dumps(sorted(existing.values(), key=lambda x: x["name"].lower()),
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        time.sleep(2)

    manu = [e for e in existing.values() if e.get("is_manufacturer")]
    print(f"\nDone. {len(existing)} unique companies, {len(manu)} manufacturers")
    print(f"Output: {OUT_PATH}")


if __name__ == "__main__":
    main()
