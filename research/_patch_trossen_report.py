"""Patch trossen scrape-report: fix heroes, curate YouTube, clean specs/features."""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from scrape_trossen_heroes import (
    BASE,
    OUT_DIR,
    accept_youtube_title,
    download_hero,
    extract_og_image,
    extract_spec_table,
    fetch_page,
    model_match_tokens,
    wix_media_id,
)

REPORT = OUT_DIR / "scrape-report.json"

SOFTWARE_TITLE_RE = re.compile(
    r"(?i)\b(tutorial|guide|assembly|lerobot|colab|hugging face|mujoco|firmware|"
    r"configuration|driver|training and evaluation|data collection and playback|"
    r"mass data collection|cloud computing|action chunking|gravity compensation|"
    r"openpi|sdk|setup guide|getting started|walkthrough|update \| summary)\b",
)

JUNK_FEATURE_RE = re.compile(
    r"(?i)^(totl workstation|ranger mini|trossen ai \| aloha evolved|"
    r"research manipulator arms|optional accessories|pincherx 100 features|"
    r"widowx.*specifications|viperx.*specifications|aloha stationary specifications|"
    r".*technical drawing$|.*video series$|frame & accessories$|"
    r"computing capabilities depend)",
)

JUNK_SPEC_RE = re.compile(r"^Price: \$,|^Price: \$1$|^Span: \d+$|^Degrees of Freedom: 50g$")

SPEC_LINE_RE = re.compile(
    r"\b(payload|reach|weight|dof|degrees|span|repeatability|price)\b",
    re.I,
)

# Per-robot og:image overrides from manual verification (page-specific product hero).
CURATED_HERO: dict[int, str | None] = {
    5266: None,  # use og:image
    5267: None,
    5268: None,
    5269: None,
    5270: None,
    5271: None,
    5272: None,
    5273: None,
    5274: None,
}

ROBOT_SPEC_FILTER: dict[int, re.Pattern] = {
    5269: re.compile(r"50g|300mm|600mm|4.?dof|pincher", re.I),
    5270: re.compile(r"750g|750mm|1500mm|6.?dof|viperx.?300|viper.?x.?300", re.I),
    5272: re.compile(r"250g|650mm|1300mm|6.?dof|widowx.?250|widow.?x.?250", re.I),
    5273: re.compile(r"widowx.?ai|mobile ai", re.I),
}


def clean_specs(entry: dict) -> list[str]:
    specs = entry.get("specs") or []
    rid = entry["id"]
    name = entry["name"]
    out: list[str] = []
    seen: set[str] = set()
    filt = ROBOT_SPEC_FILTER.get(rid)
    for s in specs:
        if JUNK_SPEC_RE.search(s):
            continue
        if len(s) > 100:
            continue
        if filt and not filt.search(s) and SPEC_LINE_RE.search(s):
            continue
        if "Payload Capacity:" in s and "Reach:" in s:
            continue
        key = s.lower()
        if key not in seen:
            seen.add(key)
            out.append(s)
    # PincherX cited specs from page comparison row
    if rid == 5269:
        cited = [
            "Degrees of Freedom: 4",
            "Payload Capacity: 50g",
            "Reach: 300mm",
            "Span: 600mm",
            "Repeatability: 5mm",
        ]
        for c in cited:
            if c.lower() not in seen:
                out.insert(0, c)
    if rid == 5270:
        cited = [
            "Degrees of Freedom: 6",
            "Payload Capacity: 750g",
            "Reach: 750mm",
            "Span: 1500mm",
            "Repeatability: 1mm",
        ]
        for c in cited:
            if c.lower() not in seen:
                out.insert(0, c)
    if rid == 5272:
        cited = [
            "Degrees of Freedom: 6",
            "Payload Capacity: 250g",
            "Reach: 650mm",
            "Span: 1300mm",
        ]
        for c in cited:
            if c.lower() not in seen:
                out.insert(0, c)
    if rid == 5266 and not any("8,999" in x for x in out):
        out.insert(0, "Price: $8,999.95")
    if rid == 5268:
        prices = [s for s in specs if re.search(r"\$[\d,]+\.\d{2}", s)]
        for p in prices[:2]:
            if p not in out:
                out.append(p)
    return out[:12]


def clean_features(entry: dict) -> list[str]:
    feats = entry.get("features") or []
    out: list[str] = []
    seen: set[str] = set()
    for f in feats:
        if JUNK_FEATURE_RE.match(f.strip()):
            continue
        if len(f.strip()) < 20:
            continue
        key = f.lower()
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out[:8]


def rank_youtube(entry: dict) -> tuple[list[dict], list[dict]]:
    name = entry["name"]
    tokens = model_match_tokens(name)
    all_vids: list[dict] = []
    seen: set[str] = set()
    yt = entry.get("youtube") or {}
    for v in (yt.get("accepted") or []) + (yt.get("rejected") or []):
        url = v.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        all_vids.append(v)

    accepted: list[dict] = []
    rejected: list[dict] = []
    for v in all_vids:
        title = v.get("title") or ""
        desc = v.get("description") or ""
        ok, reason = accept_youtube_title(title, name, tokens, desc)
        if ok and SOFTWARE_TITLE_RE.search(title):
            rejected.append({**v, "reason": "software_only_reject"})
            continue
        if ok and "solo" in name.lower() and re.search(r"stationary|mobile hardware assembly", title, re.I):
            rejected.append({**v, "reason": "wrong_aloha_variant"})
            continue
        if ok and "stationary" in name.lower() and re.search(r"solo|mobile hardware assembly", title, re.I):
            rejected.append({**v, "reason": "wrong_aloha_variant"})
            continue
        if ok and name == "Mobile AI" and re.search(r"widowx ai \|", title, re.I):
            rejected.append({**v, "reason": "wrong_model_widowx"})
            continue
        if ok and "pincher" in name.lower() and not re.search(r"pincher|px100|px 100", title + desc, re.I):
            if not re.search(r"interbotix px100", title + desc, re.I):
                rejected.append({**v, "reason": "weak_model_match"})
                continue
        if ok:
            score = 0
            blob = f"{title} {desc}".lower()
            if any(t in blob.replace("-", "").replace(" ", "") for t in tokens if len(t) >= 4):
                score += 10
            if "in action" in blob or "payload test" in blob:
                score += 8
            if "assembly guide" in blob:
                score -= 5
            if "ad " in title.lower() or title.lower().endswith(" ad 2"):
                score += 3
            accepted.append({**v, "reason": v.get("reason", reason), "_score": score})
        else:
            rejected.append({**v, "reason": reason})

    accepted.sort(key=lambda x: -x.get("_score", 0))
    for v in accepted:
        v.pop("_score", None)
    return accepted[:3], rejected[:12]


def fix_hero(entry: dict, session: requests.Session, html: str | None) -> None:
    rid = entry["id"]
    curated = CURATED_HERO.get(rid)
    if curated:
        hero = curated
    elif html:
        hero = extract_og_image(html)
        if not hero:
            cands = [c for c in entry.get("hero_candidates") or [] if not c.startswith("https://static.wixstatic.com/media/11062b")]
            hero = cands[0] if cands else entry.get("hero")
    else:
        hero = entry.get("hero")
    if not hero:
        return
    entry["hero"] = hero
    dest = OUT_DIR / f"{rid}.jpg"
    if download_hero(session, hero, dest):
        entry["hero_file"] = str(dest.relative_to(BASE)).replace("\\", "/")


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({"User-Agent": "RobotAIGeek-ResearchAgent/1.0"})

    for entry in report["robots"]:
        rid = entry["id"]
        url = entry["url"]
        status, html, _ = fetch_page(session, url)
        if html:
            entry["specs"] = extract_spec_table(html)
        fix_hero(entry, session, html)
        entry["features"] = clean_features(entry)
        entry["specs"] = clean_specs(entry)
        acc, rej = rank_youtube(entry)
        entry["youtube"]["accepted"] = acc
        entry["youtube"]["rejected"] = rej
        entry["youtube_recommended"] = [v["url"] for v in acc]

        notes = [n for n in entry.get("notes", []) if not n.startswith("shared_hero")]
        entry["notes"] = notes

        recs: list[str] = []
        if len(acc) == 0:
            recs.append("attach_youtube_demo")
        if any("wrong_" in (v.get("reason") or "") for v in rej):
            recs.append("review_mistagged_videos_in_crm")
        if any("software_only" in (v.get("reason") or "") for v in rej):
            recs.append("remove_software_only_videos_from_crm")
        junk_feats = [f for f in entry.get("features") or [] if len(f) < 25]
        if junk_feats:
            recs.append("replace_short_nav_features")
        if not entry.get("specs"):
            recs.append("add_specs_if_cited_on_page")
        entry["crm_recommendations"] = recs or ["ok"]

    # shared hero detection after fix
    by_media: dict[str, list[int]] = {}
    for e in report["robots"]:
        mid = wix_media_id(e.get("hero") or "")
        if mid:
            by_media.setdefault(mid, []).append(e["id"])
    for mid, ids in by_media.items():
        if len(ids) > 1:
            for e in report["robots"]:
                if e["id"] in ids:
                    e.setdefault("notes", []).append(f"shared_hero_media_id={mid} with robot ids {ids}")
                    if "fix_shared_wrong_hero" not in e["crm_recommendations"]:
                        e["crm_recommendations"].insert(0, "fix_shared_wrong_hero")

    report["summary"]["shared_hero_groups"] = sum(
        1 for e in report["robots"] if any("shared_hero" in n for n in e.get("notes", []))
    )
    report["summary"]["with_youtube"] = sum(
        1 for e in report["robots"] if e.get("youtube", {}).get("accepted")
    )

    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Patched", REPORT)
    for e in report["robots"]:
        mid = wix_media_id(e.get("hero") or "") or "?"
        yt = len(e.get("youtube", {}).get("accepted") or [])
        print(e["id"], e["name"][:30], "hero", mid[:20], "yt", yt, "specs", len(e.get("specs") or []))


if __name__ == "__main__":
    main()
