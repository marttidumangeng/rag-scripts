"""QA round 5 — deep junk sweep after the alias cull.

Targets the residual noise found in the reviewer's random sample:

  1. Non-manufacturer companies: retailers ("Robot Pi Shop"), market-research
     sites, generic placeholders ("Robot Industries") — verdict list plus
     heuristics (shop/store/marketplace tokens, resolved domain is a known
     retail/aggregator pattern).
  2. Nav-noise robot names in any language ("À propos", "Über uns",
     "会社概要", "Contact", "FAQ", "Support", "Download"...).
  3. Non-robot products that slipped the per-company screen ("... Tester",
     "... Resin", "... Filament", materials/consumables/instruments).
  4. LLM rescreen of every company holding >= CAP_SUSPECT robots (the mining
     cap concentrates noise): each such company's robot list is re-screened by
     Gemini in one call; robots judged non-robot/nav/article are dropped.

All drops recorded under qa_dropped.qa5. Supports --dry-run and
--skip-llm (heuristics only). Run gap_sync_import_dirs.py afterwards.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from load_env import load_research_env  # noqa: E402

BASE = _HERE / "staging" / "gap_discovery"
STAGED = BASE / "staged_import.json"

CAP_SUSPECT = 35  # companies with >= this many robots get a full LLM rescreen

# Companies that are not manufacturers — explicit verdicts from review.
COMPANY_CULL: dict[str, str] = {
    "robot-pi-shop": "Retailer/storefront, not a manufacturer",
    "robot-industries": "Generic placeholder name; no evidence of a real OEM",
    "robot-com": "Market-research site (nextmsc.com), not a manufacturer",
}

# Retail/aggregator company-name tokens (case-insensitive, word-boundary).
_RETAILER_NAME_RE = re.compile(
    r"\b(shop|store|outlet|marketplace|wholesale|reseller|distributor)\b", re.I)

# Nav/informational page names in common site languages.
_NAV_NOISE_RE = re.compile(
    r"^\s*("
    r"about( us)?|contact( us)?|faq|support|download(s)?|news|blog|career(s)?|"
    r"home|products?|services?|solutions?|partners?|privacy|terms|sitemap|"
    r"login|register|search|"
    r"à propos|nous contacter|accueil|produits|"
    r"über uns|kontakt|impressum|datenschutz|produkte|"
    r"chi siamo|contatti|prodotti|"
    r"sobre nosotros|contacto|productos|"
    r"会社概要|お問い合わせ|ニュース|製品情報?|事業内容|採用情報|"
    r"关于我们|联系我们|新闻中心|产品中心|解决方案|"
    r"회사소개|문의하기"
    r")\s*$", re.I)

# Products that are clearly not robots: materials, consumables, instruments.
_NON_ROBOT_PRODUCT_RE = re.compile(
    r"\b(tester|testing machine|test(er)? kit|resin|filament|flame retardant|"
    r"cartridge|toner|ink|adhesive|coating|lubricant|sealant|paint|"
    r"cable|connector|bearing|ballscrew|ball screw|gearbox|reducer|servo (motor|drive)|"
    r"^power supply|^dc power supply|battery pack|charger dock|spare parts?|accessor(y|ies)|"
    r"software license|subscription|warranty|training course|webinar)\b", re.I)


def heuristic_sweep(data: dict) -> tuple[list, list, dict]:
    dropped_cos, dropped_robs = [], []
    keep_cos = []
    for c in data["companies"]:
        slug, name = c["slug"], c["name"]
        if slug in COMPANY_CULL:
            dropped_cos.append(f"{name} — {COMPANY_CULL[slug]}")
        elif _RETAILER_NAME_RE.search(name) and "robot" not in (c.get("website") or ""):
            dropped_cos.append(f"{name} — retailer-pattern name")
        else:
            keep_cos.append(c)
    removed_slugs = {c["slug"] for c in data["companies"]} - {c["slug"] for c in keep_cos}

    keep_robs = []
    for r in data["robots"]:
        nm = (r.get("name") or "").strip()
        if r["company_slug"] in removed_slugs:
            dropped_robs.append(f"{nm} [{r['company_slug']}] — company culled")
        elif _NAV_NOISE_RE.match(nm):
            dropped_robs.append(f"{nm} [{r['company_slug']}] — nav noise")
        elif _NON_ROBOT_PRODUCT_RE.search(nm):
            dropped_robs.append(f"{nm} [{r['company_slug']}] — non-robot product")
        else:
            keep_robs.append(r)
    return keep_cos, keep_robs, {"companies": dropped_cos, "robots": dropped_robs}


def llm_rescreen(robots: list, dropped: dict, dry_run: bool) -> list:
    """Re-screen companies at/near the mining cap with Gemini."""
    try:
        from google import genai
    except ImportError:
        print("google-genai unavailable; skipping LLM rescreen")
        return robots
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY missing; skipping LLM rescreen")
        return robots
    client = genai.Client(api_key=api_key)

    by_co: dict[str, list] = {}
    for r in robots:
        by_co.setdefault(r["company_slug"], []).append(r)
    suspects = {s: rs for s, rs in by_co.items() if len(rs) >= CAP_SUSPECT}
    print(f"LLM rescreen: {len(suspects)} companies with >= {CAP_SUSPECT} robots")

    drop_keys: set[tuple[str, str]] = set()
    for slug, rs in suspects.items():
        names = [r["name"] for r in rs]
        prompt = (
            "You are cleaning a robot-product database. Company: "
            f"'{rs[0].get('company_name', slug)}'. Below is a list of product names "
            "mined from its website. Return STRICT JSON: "
            '{"keep": [...], "drop": [...]} where drop contains entries that are '
            "NOT actual robot/automation-machine products: navigation or page "
            "titles, news/blog/article titles, categories, services, components "
            "(motors, screws, grippers sold alone), consumables (resin, filament), "
            "test instruments, software-only items, or duplicates. Keep genuine "
            "robots, cobots, AGVs/AMRs, drones, exoskeletons, robotic machines "
            "and clear model names.\n\nNames:\n" + json.dumps(names, ensure_ascii=False)
        )
        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            verdict = json.loads(resp.text)
            drops = set(verdict.get("drop", []))
        except Exception as exc:
            print(f"  {slug}: LLM error {str(exc)[:80]} — kept as-is")
            continue
        for n in drops:
            drop_keys.add((slug, n))
        print(f"  {slug}: {len(rs)} -> {len(rs) - len(drops)} (dropped {len(drops)})")
        time.sleep(1.0)

    if dry_run:
        return robots
    kept = []
    for r in robots:
        if (r["company_slug"], r["name"]) in drop_keys:
            dropped["robots"].append(f"{r['name']} [{r['company_slug']}] — LLM rescreen (cap suspect)")
        else:
            kept.append(r)
    return kept


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-llm", action="store_true")
    args = ap.parse_args()
    load_research_env()

    data = json.loads(STAGED.read_text(encoding="utf-8"))
    n_c, n_r = len(data["companies"]), len(data["robots"])
    keep_cos, keep_robs, dropped = heuristic_sweep(data)
    print(f"heuristics: companies {n_c} -> {len(keep_cos)}, robots {n_r} -> {len(keep_robs)}")
    for line in dropped["companies"]:
        print("  CO-DROP:", line)
    for line in dropped["robots"][:40]:
        print("  ROB-DROP:", line)
    if len(dropped["robots"]) > 40:
        print(f"  ... and {len(dropped['robots']) - 40} more robot drops")

    if not args.skip_llm:
        keep_robs = llm_rescreen(keep_robs, dropped, args.dry_run)

    if args.dry_run:
        print("dry run — nothing written")
        return

    data["companies"] = keep_cos
    data["robots"] = keep_robs
    data["company_count"] = len(keep_cos)
    data["robot_count"] = len(keep_robs)
    data.setdefault("qa_dropped", {})["qa5"] = dropped
    STAGED.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"written: {STAGED} ({len(keep_cos)} companies, {len(keep_robs)} robots)")
    print("NEXT: run gap_sync_import_dirs.py then gap_summary_regen.py")


if __name__ == "__main__":
    main()
