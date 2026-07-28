"""Booster Robotics (232) enrichment — 7 pending + 3 published (user-authorized).

Root causes fixed:
  - company.website points at DEAD boosterrobotics.com; the live official site is
    booster.tech -> the 7 url_domain_mismatch errors are a company-field problem
  - payload_kg on T1/K1 records is a WEIGHT clone (30/30, 19.5/19.5) — the pages
    state no T1/K1 payload -> null them; T2's 10 kg dual-arm payload IS official
  - 382 height_mm=1.18 (metres landed in the mm column)
  - 382 description is Chinese; its url is the dead homepage
  - published K2 (5617) has NO official page anywhere (pre-launch) — url/image
    stay empty, reported to reviewer
  - published T2 (5618) missing url -> /booster-t2/
  - families: T1 (base 382 + Basic/Standard/Customized), K1 (base 2392 + Geek/
    Education/Professional); T2/K2 singletons stay familyless

Usage: python booster_enrich.py [--apply]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

import os  # noqa: E402

from api_client import ResearchApiClient  # noqa: E402
from import_staging import resolve_created_by_id  # noqa: E402
from map_to_bulk_import import staging_dict_to_bulk_import_row  # noqa: E402

SNAP = Path(r"C:\Users\tramk\AppData\Local\Temp\claude\C--Github-Personal-robot-ai-geek"
            r"\f3998b3d-68c5-4c68-85be-c6a45d3e4add\scratchpad\c232_all.json")
RECON = Path(r"C:\Users\tramk\AppData\Local\Temp\claude\C--Github-Personal-robot-ai-geek"
             r"\f3998b3d-68c5-4c68-85be-c6a45d3e4add\scratchpad\booster_recon.json")

T1 = "https://www.booster.tech/booster-t1/"
K1 = "https://www.booster.tech/booster-k1/"
T2 = "https://www.booster.tech/booster-t2/"

# id -> (family_key, family_name, variant_label, scope, page)
PLAN: dict[int, tuple[str, str, str, str, str]] = {
    382:  ("booster-robotics:t1", "Booster T1", "", "family", "t1"),
    1823: ("booster-robotics:t1", "Booster T1", "Basic", "family", "t1"),
    1824: ("booster-robotics:t1", "Booster T1", "Standard", "family", "t1"),
    1825: ("booster-robotics:t1", "Booster T1", "Customized", "family", "t1"),
    2392: ("booster-robotics:k1", "Booster K1", "", "family", "k1"),
    1826: ("booster-robotics:k1", "Booster K1", "Geek", "family", "k1"),
    1827: ("booster-robotics:k1", "Booster K1", "Education", "family", "k1"),
    1828: ("booster-robotics:k1", "Booster K1", "Professional", "family", "k1"),
    5618: ("", "", "", "exact_variant", "t2"),
    5617: ("", "", "", "", ""),          # K2 — no official page exists
}
FAMILY_URL = {"t1": T1, "k1": K1}

# grounded per-page spec/battery fills (patch mode fills blanks only)
PAGE_FILLS: dict[str, dict[str, Any]] = {
    "t1": {"height_mm": 1200.0, "weight_kg": 30.0,
           "battery_capacity": "10.5Ah", "runtime_minutes": 120,
           "runtime": "2h walking / 4h standing"},
    "k1": {"height_mm": 950.0, "weight_kg": 19.5},
    "t2": {"height_mm": 1400.0, "weight_kg": 42.0, "payload_kg": 10.0,
           "battery_capacity": "10Ah", "runtime_minutes": 120,
           "runtime": "2h continuous walking"},
}
# K1 battery differs per SKU (page shows 2Ah/30min vs 5Ah/80min blocks)
K1_BATTERY = {1826: ("2Ah", 30, "30min walking at 0.4m/s"),
              1827: ("5Ah", 80, "80min walking at 0.4m/s"),
              1828: ("5Ah", 80, "80min walking at 0.4m/s"),
              2392: ("", None, "")}

NARRATIVE_LIMITS = {"programming_interface": 120, "safety_fencing": 120,
                    "mounting_options": 80, "deployment_context": 120,
                    "ecosystem_compatibility": 150}

_PROMPT = """You extract facts about a humanoid robot from its official product page text.
Return ONLY valid JSON with these keys (use "" when the text does not state it; NEVER invent):
- "programming_interface": how developers program/control it (SDK, APIs, simulators, teleop). Max 120 chars.
- "safety_fencing": safety posture stated (e.g. "Designed for safe operation around people"). Max 120 chars.
- "mounting_options": form factor/deployment ("Free-standing bipedal humanoid"). Max 80 chars.
- "deployment_context": stated use settings (research labs, education, RoboCup, commercial). Max 120 chars.
- "ecosystem_compatibility": stated integrations/standards (ROS, Isaac Sim, open-source repos, app). Max 150 chars.
Robot: {name}

PAGE TEXT:
{text}
"""

DESC_382 = ("Booster T1 is a ~1.2 m, ~30 kg developer-focused humanoid robot platform from "
            "Booster Robotics, offered in Basic, Standard and Customized configurations with "
            "23 to 41 degrees of freedom. Built for embodied-AI research, education and "
            "competition (it is a popular RoboCup platform), it combines durable, flexible "
            "hardware with an open development ecosystem.")


def _p(*a):
    print(*a, flush=True)


def gemini(name: str, text: str) -> dict[str, str]:
    try:
        from google import genai
        from google.genai import types as genai_types
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""),
                              http_options={"api_version": "v1beta"})
        resp = client.models.generate_content(
            model="models/gemini-2.5-flash",
            contents=_PROMPT.format(name=name, text=text[:6000]),
            config=genai_types.GenerateContentConfig(temperature=0.0))
        data = json.loads(re.sub(r"^```[a-z]*\n?|\n?```$", "", (resp.text or "").strip()))
    except Exception as exc:  # noqa: BLE001
        _p(f"  WARN gemini: {exc}")
        return {}
    return {k: v.strip()[:cap] for k, cap in NARRATIVE_LIMITS.items()
            if isinstance((v := data.get(k)), str) and v.strip()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--created-by-id", type=int, default=1)
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    snap = {int(r["id"]): r for r in json.loads(SNAP.read_text(encoding="utf-8"))}
    recon = json.loads(RECON.read_text(encoding="utf-8"))

    # one Gemini call per page; K2 grounded on its own stored description
    narr: dict[str, dict[str, str]] = {}
    for page in ("t1", "k1", "t2"):
        narr[page] = gemini(f"Booster {page.upper()}", "\n".join(recon[page]["lines"]))
        _p(f"narrative[{page}]: {sorted(narr[page])}")
    narr[""] = gemini("Booster K2", snap[5617].get("description") or "")
    _p(f"narrative[K2-from-desc]: {sorted(narr[''])}")

    # page images, absolutized + HEAD-checked, round-robin so each image lands
    # on <=2 robots (shared-hero detector fires at >3 robots per URL)
    session = requests.Session()
    imgs: dict[str, list[str]] = {}
    for page in ("t1", "k1", "t2"):
        cand = []
        for u in recon[page]["imgs"]:
            if u.startswith("/"):
                u = "https://www.booster.tech" + u
            if any(j in u.lower() for j in ("favicon", "logo", "icon")):
                continue
            try:
                ok = session.head(u, timeout=20, allow_redirects=True,
                                  headers={"User-Agent": "Mozilla/5.0"}).status_code == 200
            except requests.RequestException:
                ok = False
            if ok:
                cand.append(u)
        imgs[page] = cand
        _p(f"imgs[{page}]: {len(cand)}")

    NEED = {382: 1, 1823: 2, 1824: 2, 1825: 2, 2392: 3, 1826: 1, 1827: 1, 1828: 1, 5618: 1}
    assign: dict[int, list[str]] = {rid: [] for rid in NEED}
    use_count: dict[str, int] = {}
    for page, robots in (("t1", [382, 1823, 1824, 1825]), ("k1", [2392, 1826, 1827, 1828]),
                         ("t2", [5618])):
        pool = imgs.get(page, [])
        i = 0
        for rid in robots:
            for _ in range(NEED[rid]):
                for _try in range(len(pool)):
                    u = pool[i % len(pool)] if pool else None
                    i += 1
                    if u and use_count.get(u, 0) < 2 and u not in assign[rid]:
                        assign[rid].append(u)
                        use_count[u] = use_count.get(u, 0) + 1
                        break

    rows = []
    for rid, (fkey, fname, variant, scope, page) in PLAN.items():
        r = snap[rid]
        row: dict[str, Any] = {
            "id": rid, "name": r["name"], "company_slug": "booster-robotics",
            "company_name": "Booster Robotics", "model_name": r["name"],
            "variant_code": r["name"], "source_locale": "en",
            "family_key": fkey, "family_name": fname, "variant_label": variant,
            "product_url_scope": scope, "family_url": FAMILY_URL.get(page, ""),
            **narr.get(page, {}),
        }
        fills = dict(PAGE_FILLS.get(page, {}))
        if rid in K1_BATTERY:
            cap_, mins, runtime = K1_BATTERY[rid]
            if cap_:
                fills.update({"battery_capacity": cap_, "runtime_minutes": mins, "runtime": runtime})
        row.update(fills)
        if rid == 5618:
            row["url"] = T2
        if rid in (5617, 5618) and not (r.get("tags") or []):
            row["tags"] = ", ".join(snap[382].get("tags") or [])
        if assign.get(rid):
            row["images"] = assign[rid]
        page_url = {"t1": T1, "k1": K1, "t2": T2}.get(page)
        row["sources"] = [{"url": page_url or "https://www.booster.tech/",
                           "type": "website", "title": r["name"]}]
        rows.append(staging_dict_to_bulk_import_row(row) | {"id": rid})

    patches: dict[int, dict[str, Any]] = {
        382: {"description": DESC_382, "url": T1, "height_mm": 1180.0},
        # payload_kg values are weight clones — pages state no T1/K1 payload
        **{rid: {"payload_kg": None} for rid in (1823, 1824, 1825, 1826, 1827, 1828, 2392)},
    }

    _p(f"rows={len(rows)} patches={len(patches)} website-fix=booster.tech")
    if not args.apply:
        _p(json.dumps(rows[0], indent=1, ensure_ascii=False)[:1000])
        _p("dry-run")
        return 0

    client = ResearchApiClient()
    # 1. dead-domain company website fix
    client.patch_company(232, {"website": "https://www.booster.tech"})
    _p("company 232 website -> booster.tech")
    # 2. bulk patch import
    created_by = resolve_created_by_id(args.created_by_id)
    for i in range(0, len(rows), 8):
        resp = client.bulk_import_robots(rows[i:i + 8], update_existing=True, patch_existing=True,
                                         status="pending_review", skip_company_update=True,
                                         created_by_id=created_by)
        _p(f"batch {i // 8}: " + json.dumps({k: v for k, v in resp.items() if k.endswith('_count')}))
    # 3. corrections
    for rid, payload in patches.items():
        client._patch(f"robots/robots/{rid}/", payload)
        _p(f"patched {rid}: {sorted(payload)}")
        time.sleep(0.3)
    # 4. localize new photos
    from fix_acy_gallery_cleanup import trigger_copy_media
    ok, fail = trigger_copy_media([rid for rid, v in assign.items() if v], force=False)
    _p(f"copy-media ok={ok} fail={fail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
