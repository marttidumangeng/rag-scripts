"""Batch-scrape Motoman PDPs for weight / repeatability / applications."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()

UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeek/1.0)"}
OUT = Path("staging/reports/yaskawa-pdp-extras.json")
CATALOG = json.loads(Path("staging/reports/yaskawa-motoman-catalog.json").read_text(encoding="utf-8"))

# Series → Motoman URL path segment
SERIES_PATH = {
    "gp": ("industrial", "assembly-handling", "gp-series"),
    "hc": ("collaborative", None, "hc-series"),
    "nex": ("industrial", "assembly-handling", "nex-series"),
    "pl": ("industrial", "assembly-handling", "pl-series"),
    "mpp": ("industrial", "assembly-handling", "mpp-series"),
    "sg": ("industrial", "assembly-handling", "sg-series"),
    "motomini": ("industrial", "assembly-handling", "motomini-series"),
    "mh": ("industrial", "assembly-handling", "mh-series"),
    "ph": ("industrial", "assembly-handling", "ph-series"),
    "mys": ("industrial", "assembly-handling", "mys-series"),
    "ar": ("industrial", "welding-cutting", "ar-series"),
    "ga": ("industrial", "welding-cutting", "ga-series"),
    "sp": ("industrial", "welding-cutting", "sp-series"),
    "mpx": ("industrial", "painting-dispensing", "mpx-series"),
}


def clean_model(name: str) -> str:
    n = re.sub(r"(?i)^motoman\s+", "", name.strip())
    n = re.sub(r"(?i)\s+robot$", "", n).strip()
    return n


def series_of(model: str) -> str:
    m = model.upper().replace(" ", "")
    for prefix in (
        "MOTOMINI",
        "MPX",
        "MPP",
        "MYS",
        "NEX",
        "GP",
        "HC",
        "PL",
        "SG",
        "MH",
        "PH",
        "AR",
        "GA",
        "SP",
    ):
        if m.startswith(prefix):
            return "motomini" if prefix == "MOTOMINI" else prefix.lower()
    return "gp"


def pdp_url(model: str) -> str:
    series = series_of(model)
    kind, cat, series_slug = SERIES_PATH[series]
    slug = model.lower()
    if kind == "collaborative":
        return f"https://www.motoman.com/en-us/products/robots/collaborative/{series_slug}/{slug}"
    return (
        f"https://www.motoman.com/en-us/products/robots/{kind}/{cat}/{series_slug}/{slug}"
    )


def parse_pdp(html: str) -> dict:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    out: dict = {}
    # Common Motoman labels
    patterns = [
        ("payload_kg", r"Payload\s*[|:]\s*([\d.]+)\s*kg", 1.0),
        ("hor_reach_mm", r"Horizontal\s+Reach\s*[|:]\s*([\d.]+)\s*mm", 1.0),
        ("vert_reach_mm", r"Vertical\s+Reach\s*[|:]\s*([\d.]+)\s*mm", 1.0),
        ("weight_kg", r"(?:Mass|Weight)\s*[|:]\s*([\d.]+)\s*kg", 1.0),
        ("repeatability_mm", r"Repeatability\s*[|:]\s*[±+]?\s*([\d.]+)\s*mm", 1.0),
        ("dof", r"(?:Controlled\s+Axes|Axes)\s*[|:]\s*(\d+)", 1.0),
    ]
    for key, pat, _ in patterns:
        m = re.search(pat, text, re.I)
        if m:
            out[key] = float(m.group(1)) if key != "dof" else int(m.group(1))

    apps = []
    m = re.search(r"Applications?\s*[|:]\s*(.+?)(?:Controller|Protection|Mounting|$)", text, re.I)
    if m:
        chunk = m.group(1)
        apps = [a.strip() for a in re.split(r"[,;/]", chunk) if a.strip() and len(a.strip()) < 40]
        out["applications"] = apps[:12]

    ctrl = re.search(r"Controller\s*[|:]\s*([A-Za-z0-9/\s\-]+?)(?:Applications|Protection|Mounting|$)", text, re.I)
    if ctrl:
        out["controller"] = ctrl.group(1).strip()[:80]

    return out


def main() -> None:
    c = ResearchApiClient()
    robots = [r for r in (c.list_robots_for_company(772) or []) if r.get("status") == "pending_review"]
    results = {}
    ok = fail = 0
    for r in sorted(robots, key=lambda x: x["id"]):
        model = clean_model(r.get("name") or "")
        url = pdp_url(model)
        # Prefer existing model-specific URL if it looks like a PDP
        existing = ""
        d = c._get(f"robots/robots/{r['id']}/")
        existing = (d.get("url") or "").strip()
        candidates = []
        if existing and model.lower() in existing.lower() and existing.count("/") >= 6:
            candidates.append(existing)
        candidates.append(url)
        # Also try without en-us
        candidates.append(url.replace("/en-us/", "/"))

        hit = None
        used = None
        for cand in candidates:
            try:
                resp = requests.get(cand, headers=UA, timeout=40, allow_redirects=True)
            except Exception as e:
                continue
            if resp.status_code != 200 or len(resp.text) < 5000:
                continue
            if "No robots were found" in resp.text or "Page Not Found" in resp.text:
                continue
            parsed = parse_pdp(resp.text)
            if parsed.get("payload_kg") or parsed.get("weight_kg") or parsed.get("applications"):
                hit = parsed
                used = resp.url
                break
            # accept if page mentions model
            if model.lower() in resp.text.lower() and len(resp.text) > 20000:
                hit = parsed
                used = resp.url
                break
        cat = CATALOG["models"].get(model) or CATALOG["models"].get(model.upper())
        entry = {
            "id": r["id"],
            "name": r.get("name"),
            "model": model,
            "pdp_url": used,
            "catalog": cat,
            "pdp": hit,
        }
        results[r["id"]] = entry
        if hit:
            ok += 1
            print(f"OK {r['id']} {model}: { {k: hit.get(k) for k in ('payload_kg','weight_kg','repeatability_mm','applications') if k in hit} }")
        else:
            fail += 1
            print(f"MISS {r['id']} {model} tried={candidates[0][:70]}")
        time.sleep(0.15)

    OUT.write_text(json.dumps({"ok": ok, "fail": fail, "robots": results}, indent=2), encoding="utf-8")
    print(f"done ok={ok} fail={fail} -> {OUT}")


if __name__ == "__main__":
    main()
