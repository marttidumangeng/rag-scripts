"""Re-download Trossen heroes using page-specific media (not shared site OG)."""
from __future__ import annotations

import json
from pathlib import Path

import requests

from scrape_trossen_heroes import BASE, OUT_DIR, download_hero

REPORT = OUT_DIR / "scrape-report.json"

# Verified page-specific Wix media IDs (reject site-wide og cf083398 and nav 11062b).
HERO_MEDIA: dict[int, str] = {
    5266: "d3716d_1546c3eb4aef4d94b1b338d31153e43d",
    5267: "d3716d_6aa60d59cdd84e25943efabb8b0635aa",
    5268: "d3716d_090991aa9dbb47ebba899ac3531621e0",
    5269: "d3716d_142992415ec54ca8ba8bed02a1e1294e",
    5270: "d3716d_0eafddcd70e94c98ac67a8317615e27d",
    5271: "d3716d_2521e70fc40a460cbde6831166a349b2",
    5272: "d3716d_031418cc38d043228f47778e2c03cf0c",
    5273: "d3716d_414a7814471d463680e0c49edcd3ab2f",
    5274: "d3716d_7d9108b35b194e3c806cc260fcfd7268",
}

SHARED_OG = "d3716d_cf083398c1ab467495620daf4a9db20b"


def hero_url(media_id: str) -> str:
    mid = media_id.replace("~mv2.jpg", "").replace(".jpg", "")
    ext = ".jpg"
    if not mid.endswith("~mv2"):
        if mid.endswith(".jpg"):
            base = mid.split(".jpg")[0]
            return f"https://static.wixstatic.com/media/{base}~mv2.jpg/v1/fill/w_2500,h_1600,al_c,q_90/{base}~mv2.jpg"
    return f"https://static.wixstatic.com/media/{mid}~mv2{ext}/v1/fill/w_2500,h_1600,al_c,q_90/{mid}~mv2{ext}"


def main() -> None:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({"User-Agent": "RobotAIGeek-ResearchAgent/1.0"})

    for entry in report["robots"]:
        rid = entry["id"]
        mid = HERO_MEDIA.get(rid)
        if not mid:
            continue
        url = hero_url(mid)
        entry["hero"] = url
        dest = OUT_DIR / f"{rid}.jpg"
        ok = download_hero(session, url, dest)
        if ok:
            entry["hero_file"] = str(dest.relative_to(BASE)).replace("\\", "/")
            entry.setdefault("notes", [])
            entry["notes"] = [n for n in entry["notes"] if not n.startswith("shared_hero")]
        else:
            entry.setdefault("notes", []).append(f"hero_redownload_failed for {mid}")

    # Re-check shared heroes
    by_mid: dict[str, list[int]] = {}
    for e in report["robots"]:
        hero = e.get("hero") or ""
        for mid in HERO_MEDIA.values():
            if mid.split(".jpg")[0].replace("~mv2", "") in hero or mid in hero:
                by_mid.setdefault(mid, []).append(e["id"])
                break

    for e in report["robots"]:
        recs = [r for r in e.get("crm_recommendations", []) if r != "fix_shared_wrong_hero"]
        shared_note = any("shared_hero" in n for n in e.get("notes", []))
        if SHARED_OG in (e.get("hero") or ""):
            e.setdefault("notes", []).append(f"shared_site_og_hero={SHARED_OG}")
            recs.insert(0, "fix_shared_wrong_hero")
        elif shared_note:
            recs.insert(0, "fix_shared_wrong_hero")
        e["crm_recommendations"] = recs or ["ok"]

    report["summary"]["shared_hero_groups"] = sum(
        1 for e in report["robots"] if "fix_shared_wrong_hero" in e.get("crm_recommendations", [])
    )

    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Updated heroes")
    for e in report["robots"]:
        print(e["id"], e.get("hero_file"), e.get("crm_recommendations"))


if __name__ == "__main__":
    main()
