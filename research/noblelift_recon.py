"""Recon pass for Noblelift (1028): per-robot verified facts for description writing.

Emits staging/reports/noblelift_recon.json with, per pending_review robot:
  - resolved OEM url + how it resolved
  - the OEM LIST-PAGE label (url-map key, e.g. 'RT20G 2000kg Sit-on Reach Truck') —
    model-specific and independently verified against the PDP title
  - PDP title/subtitle
  - column-aware specs (see fix_noblelift_sources.parse_specs; refuses family-table
    column-1 guesses and pages that don't document the model)
  - kind classification

Read-only. Writes nothing to prod.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from fix_noblelift_robots import classify, load_url_map, model_key, resolve_url, scrape_pdp
from fix_noblelift_sources import parse_specs

COMPANY_ID = 1028
OUT = _RESEARCH_DIR / "staging" / "reports" / "noblelift_recon.json"


def main() -> int:
    client = ResearchApiClient()
    robots = [
        r for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    ]
    load_url_map()
    out: list[dict[str, Any]] = []
    for r in robots:
        rid = int(r["id"])
        name = r["name"]
        url, res = resolve_url(name, (r.get("url") or "").strip())
        label = res.split(":", 1)[1] if res.startswith("map") else ""
        row: dict[str, Any] = {
            "id": rid,
            "name": name,
            "url": url,
            "resolution": res,
            "list_label": label,
            "cur_description": (r.get("description") or "").strip(),
            "cur_desc_len": len((r.get("description") or "").strip()),
            "kind": classify(name, url, ""),
            "has_availability": bool(r.get("availability_status")),
        }
        try:
            pdp = scrape_pdp(url)
            row["tit"] = pdp.get("tit") or pdp.get("page_name") or ""
            row["subtit"] = pdp.get("subtit") or ""
            specs = parse_specs(url, name)
            row["page_name"] = specs.get("page_name")
            row["covered"] = specs.get("covered")
            row["coverage"] = specs.get("coverage")
            row["model_cols"] = specs.get("model_cols")
            for k in ("weight_kg", "weight_text", "length_mm", "width_mm", "height_mm",
                      "speed", "voltage", "battery_capacity", "payload_kg", "lift_mm"):
                if specs.get(k) is not None:
                    row[k] = specs.get(k)
        except requests.RequestException as exc:
            row["error"] = str(exc)
        out.append(row)
        print(f"{rid:5} {name[:26]:26} kind={row['kind']:8} cov={row.get('covered')} "
              f"label={label[:44]!r}")
        time.sleep(0.15)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {len(out)} rows -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
