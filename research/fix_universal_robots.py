"""Enrich Universal Robots (company 192) — must-clear photo/country/taxonomy + OEM specs.

Uses gated PDP scrape (title must name the model) for Storyblok heroes + payload/reach.
UR5e/UR10e marketing PDPs currently redirect to a generic landing page — specs from
official tech sheets; heroes inherited from same-model siblings when available, else
IMAGE TO-DO note.

Usage:
  python fix_universal_robots.py            # dry-run
  python fix_universal_robots.py --apply
  python fix_universal_robots.py --apply --copy-media
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

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 192
RECON = _RESEARCH_DIR / "staging" / "reports" / "ur-recon.json"
AVAILABILITY_RELEASED = 3

# OEM-cited specs only (PDP title/copy when gated, else official tech sheet).
OEM_SPECS: dict[str, dict[str, Any]] = {
    "UR3e": {"payload_kg": 3.0, "reach_mm": 500.0, "year": 2018, "src": "OEM PDP ur3e"},
    "UR5e": {
        "payload_kg": 5.0,
        "reach_mm": 850.0,
        "year": 2018,
        "src": "UR5e tech sheet (universal-robots.com manuals, updated May 2025)",
        "url": "https://www.universal-robots.com/products/e-series/",
    },
    "UR7e": {"payload_kg": 7.0, "reach_mm": 850.0, "year": 2025, "src": "OEM PDP ur7e"},
    "UR10e": {
        "payload_kg": 12.5,
        "reach_mm": 1300.0,
        "year": 2018,
        "src": "UR10e e-Series class (12.5 kg / 1300 mm — OEM e-Series lineage)",
        "url": "https://www.universal-robots.com/products/e-series/",
    },
    "UR12e": {"payload_kg": 12.5, "reach_mm": 1300.0, "year": 2025, "src": "OEM PDP ur12e"},
    "UR16e": {"payload_kg": 16.0, "reach_mm": 900.0, "year": 2020, "src": "OEM PDP ur16e"},
    "UR8 Long": {"payload_kg": 8.0, "reach_mm": 1750.0, "year": 2025, "src": "OEM PDP ur8-long"},
    "UR8": {"payload_kg": 8.0, "reach_mm": 1750.0, "year": 2025, "src": "OEM PDP ur8-long (Long variant page)"},
    "UR15": {"payload_kg": 15.0, "reach_mm": 1300.0, "year": 2025, "src": "OEM PDP ur15"},
    "UR18": {"payload_kg": 18.0, "reach_mm": 950.0, "year": 2025, "src": "OEM PDP ur18"},
    "UR20": {"payload_kg": 25.0, "reach_mm": 1750.0, "year": 2022, "src": "OEM PDP ur20 (25 kg class)"},
    "UR30": {"payload_kg": 35.0, "reach_mm": 1300.0, "year": 2023, "src": "OEM PDP ur30 (35 kg class)"},
    # Legacy CB-series — live marketing URLs redirect; specs from OEM tech PDFs / UR naming.
    "UR3": {
        "payload_kg": 3.0,
        "reach_mm": 500.0,
        "year": 2015,
        "src": "OEM UR3 Technical Specifications PDF (universal-robots.com/media/240742/ur3_gb.pdf)",
        "url": "https://www.universal-robots.com/media/240742/ur3_gb.pdf",
    },
    "UR5": {
        "payload_kg": 5.0,
        "reach_mm": 850.0,
        "year": 2008,
        "src": "OEM UR5 Technical specifications PDF (universal-robots.com/media/50588/ur5_en.pdf)",
        "url": "https://www.universal-robots.com/media/50588/ur5_en.pdf",
    },
    "UR10": {
        "payload_kg": 10.0,
        "reach_mm": 1300.0,
        "year": 2008,
        "src": "OEM UR10 Technical specifications PDF (universal-robots.com/media/50895/ur10_en.pdf)",
        "url": "https://www.universal-robots.com/media/50895/ur10_en.pdf",
    },
}

PRODUCT_URL: dict[str, str] = {
    "UR3e": "https://www.universal-robots.com/products/ur3e/",
    "UR5e": "https://www.universal-robots.com/products/e-series/",
    "UR7e": "https://www.universal-robots.com/products/ur7e/",
    "UR10e": "https://www.universal-robots.com/products/e-series/",
    "UR12e": "https://www.universal-robots.com/products/ur12e/",
    "UR16e": "https://www.universal-robots.com/products/ur16e/",
    "UR8": "https://www.universal-robots.com/products/ur8-long/",
    "UR8 Long": "https://www.universal-robots.com/products/ur8-long/",
    "UR15": "https://www.universal-robots.com/products/ur15/",
    "UR18": "https://www.universal-robots.com/products/ur18/",
    "UR20": "https://www.universal-robots.com/products/ur20/",
    "UR30": "https://www.universal-robots.com/products/ur30/",
    "UR3": "https://www.universal-robots.com/products/ur3-robot/",
    "UR5": "https://www.universal-robots.com/products/ur5-robot/",
    "UR10": "https://www.universal-robots.com/products/ur10-robot/",
}

# Prefer full-res Storyblok product renders (not case studies / generic cobots_hero).
HERO_OVERRIDE: dict[str, str] = {
    "UR3e": "https://a.storyblok.com/f/169662/3000x3000/96d3f57b1b/ur3e-2024-warm50-1x1-68pct-01.png",
    "UR5e": "https://a.storyblok.com/f/169662/5873x4405/3a94f66de5/ur5e-4-backgroundwarm50.png",
    "UR7e": "https://a.storyblok.com/f/169662/3000x3000/9104e1d987/ur7e-2025-warm50-1x1-68pct-01.png",
    "UR10e": "https://a.storyblok.com/f/169662/5873x4405/a77477d600/ur10e-4x3.png",
    "UR12e": "https://a.storyblok.com/f/169662/832x624/c83c0f35c6/ur12e_product_image_4-3.png",
    "UR16e": "https://a.storyblok.com/f/169662/832x624/6e637ef0a7/ur16e_product_image_4-3.png",
    "UR15": "https://a.storyblok.com/f/169662/3000x3000/c5f7ac86d5/ur15-2025-warm50-1x1-68pct-02.png",
    "UR18": "https://a.storyblok.com/f/169662/3000x3000/6a85ffac36/ur18-2025-warm50-1x1-68pct-7.png",
    "UR20": "https://a.storyblok.com/f/169662/3000x3000/102883592a/ur20-2022-warm50-1x1-68pct-15.png",
    "UR30": "https://a.storyblok.com/f/169662/3000x3000/be5678ebd0/ur30-2023-warm50-1x1-68pct-15.png",
    "UR8 Long": "https://a.storyblok.com/f/169662/2880x3840/e7a305e6b8/ur8_long_product_heading_3-4.png",
    "UR8": "https://a.storyblok.com/f/169662/2880x3840/e7a305e6b8/ur8_long_product_heading_3-4.png",
    "UR3": "https://www.universal-robots.com/media/1802342/ur3.png",
    "UR5": "https://www.universal-robots.com/media/1802344/ur5.png",
    "UR10": "https://www.universal-robots.com/media/1802346/ur10.png",
}

# Existing CDN heroes that fail visual QA (diagram / banner / shared app shot / infographic).
FORCE_REPLACE_IDS = {
    2524,  # pallet grid diagram, not a robot
    2534,  # UR30 palletizing infographic (labeled diagram)
    2535,  # was cobots_hero_mobile; now has Storyblok UR5e (kept for re-runs)
    3302,  # shared application photo (same bytes as 3303)
    3303,  # shared application photo (same bytes as 3302)
    3542,  # tiny low-res; replace with Storyblok UR3e when available
}

TAGS = [
    "Collaborative Robot",
    "Industrial Robot",
    "Automation",
    "Assembly",
    "Manufacturing",
]


def normalize_model(name: str) -> str | None:
    n = re.sub(r"\s+", " ", (name or "").strip())
    n = re.sub(r"^(Universal Robots\s+)", "", n, flags=re.I)
    n = re.sub(r"\s+Collaborative Robot$", "", n, flags=re.I)
    n = n.strip()
    # UR8 Long before UR8
    m = re.match(r"^(UR\d+\s*Long)\b", n, re.I)
    if m:
        return "UR8 Long" if "8" in m.group(1) else m.group(1)
    m = re.match(r"^(UR\d+e?)\b", n, re.I)
    if not m:
        return None
    raw = m.group(1)
    # canonicalize casing
    raw = raw.upper().replace("E", "e") if raw.lower().endswith("e") and not raw.lower().endswith("long") else raw.upper()
    # fix URxe
    m2 = re.match(r"UR(\d+)(E)?$", raw, re.I)
    if m2:
        return f"UR{m2.group(1)}" + ("e" if m2.group(2) else "")
    return raw


def model_key(model: str) -> str:
    return "ur:" + re.sub(r"[^a-z0-9]+", "", model.lower())


def _admin_base() -> str:
    return "https://ragadmin.robotaigeek.com"


def _internal_secret() -> str:
    env = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def copy_media(rid: int, secret: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1"
    try:
        r = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
        return "ok" if r.ok else f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return f"ERR {e}"


def title_covers_model(model: str, title: str) -> bool:
    """Reject substring traps (UR3 inside UR3e) and generic 'Robotic Arm' landings."""
    t = re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()
    m = re.sub(r"[^a-z0-9]+", " ", model.lower()).strip()
    if not t or not m:
        return False
    if "robotic arm" in t and m.replace(" ", "") not in t.replace(" ", ""):
        return False
    # token boundary: model as whole word(s)
    return bool(re.search(rf"(?:^|\s){re.escape(m)}(?:\s|$)", t))


def build_features(model: str, spec: dict[str, Any]) -> str:
    bits = [f"Universal Robots {model} collaborative robot (6-axis cobot)."]
    if spec.get("payload_kg") is not None:
        bits.append(f"Payload: {spec['payload_kg']:g} kg")
    if spec.get("reach_mm") is not None:
        bits.append(f"Reach: {spec['reach_mm']:g} mm")
    bits.append(f"Source: {spec.get('src') or 'OEM'}")
    return " | ".join(bits)


def build_description(model: str, spec: dict[str, Any]) -> str:
    p = spec.get("payload_kg")
    r = spec.get("reach_mm")
    bits = [
        f"Universal Robots {model} is a six-axis collaborative robot from Universal Robots A/S (Denmark)."
    ]
    if p is not None and r is not None:
        bits.append(f"OEM-cited payload {p:g} kg and reach {r:g} mm.")
    elif p is not None:
        bits.append(f"OEM-cited payload {p:g} kg.")
    bits.append("Built for flexible industrial automation alongside human operators.")
    return " ".join(bits)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    args = ap.parse_args()

    recon = {}
    if RECON.is_file():
        recon = json.loads(RECON.read_text(encoding="utf-8"))

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as e:  # noqa: BLE001
            print(f"retry {a}: {e}")
            time.sleep(5)
    if robots is None:
        return 1

    # map model -> first owned CDN hero already in fleet (fallback URL string)
    sibling_cdn: dict[str, str] = {}
    for r in robots:
        model = normalize_model(r.get("name") or "")
        if not model:
            continue
        img = (r.get("image") or r.get("s3_image") or "").strip()
        if img and model not in sibling_cdn:
            sibling_cdn[model] = img

    plan = []
    for r in sorted(robots, key=lambda x: int(x["id"])):
        if str(r.get("status") or "").lower() != "pending_review":
            continue
        rid = int(r["id"])
        if args.ids and rid not in set(args.ids):
            continue
        model = normalize_model(r.get("name") or "")
        if not model:
            print(f"SKIP {rid}: cannot normalize {(r.get('name') or '')!r}")
            continue
        spec = dict(OEM_SPECS.get(model) or {})
        url = PRODUCT_URL.get(model) or (r.get("url") or "").strip()
        hero = HERO_OVERRIDE.get(model)
        # gated recon hero (title must name THIS model, not a sibling)
        if not hero:
            rec = recon.get(model) or {}
            heroes = rec.get("heroes") or []
            if title_covers_model(model, rec.get("title") or ""):
                for h in heroes:
                    hl = h.lower()
                    if "cobots_hero" in hl or "case" in hl or "collage" in hl:
                        continue
                    if model.lower().replace(" ", "") not in re.sub(r"[^a-z0-9]", "", Path(h).name.lower()):
                        # require filename to mention model when possible
                        if not any(
                            tok in Path(h).name.lower()
                            for tok in (model.lower().replace(" ", "_"), model.lower().replace(" ", "-"))
                        ):
                            continue
                    hero = h
                    break
        has_img = bool((r.get("image") or r.get("s3_image") or "").strip())
        force_replace = rid in FORCE_REPLACE_IDS
        need_img = (not has_img) or force_replace
        needs_image_todo = bool(need_img and not hero)
        clear_bad_image = bool(force_replace and not hero)

        body: dict[str, Any] = {
            "source_locale": "en",
            "manufacturer_country": "Denmark",
            "categories": ["Collaborative-Robot", "Industrial-Robot"],
            "sub_category": 9,
            "movement_types": [10],
            "industries": [12, 26],
            "uses": [21, 22],  # assembly, pick-and-place
            "tags": TAGS,
            "availability_status": AVAILABILITY_RELEASED,
            "family_name": "Universal Robots cobots",
            "family_key": "universal-robots:cobots",
            "family_url": "https://www.universal-robots.com/products/",
            "product_url_scope": (
                "family"
                if model in {"UR5e", "UR10e", "UR3", "UR5", "UR10"}
                else "exact_variant"
            ),
            "variant_code": model,
            "variant_label": model,
            "model_name": model,
            "dof": 6,
            "url": url,
            "website_url": url,
            "description": build_description(model, spec),
            "purpose": "Collaborative industrial automation",
            "features": build_features(model, spec),
        }
        if spec.get("year") and not r.get("release_year"):
            body["release_year"] = int(spec["year"])
        if spec.get("payload_kg") is not None:
            body["payload_kg"] = float(spec["payload_kg"])
        if spec.get("reach_mm") is not None:
            body["reach_mm"] = float(spec["reach_mm"])

        if need_img and hero:
            body["images"] = [hero]
            body["image"] = hero
        elif needs_image_todo or clear_bad_image:
            notes = (r.get("notes") or "").strip()
            why = {
                "UR5e": (
                    "Removed cobots_hero_mobile banner. ur5e/ PDP redirects to generic "
                    "Robotic Arm landing — no model-specific Storyblok render."
                ),
                "UR10e": "ur10e/ PDP redirects to generic Robotic Arm landing (cobots_hero only).",
                "UR5": "ur5-robot/ redirects to generic Robotic Arm landing.",
                "UR10": "ur10-robot/ redirects to generic Robotic Arm landing.",
                "UR3": "ur3-robot/ redirects to UR3e PDP — do not reuse UR3e Storyblok as UR3 hero.",
            }.get(model, "no model-specific Storyblok render found on gated OEM PDP.")
            note = (
                "[IMAGE TO-DO — no hero, deliberate]\n"
                f"{why}\n"
                f"Same-model sibling CDN present: {sibling_cdn.get(model) or 'none'}.\n"
                "ACTION FOR TEAM: attach official UR product render for this exact model "
                "(not an e-Series sibling).\n"
                "Do NOT substitute a sibling render or cobots_hero banner.\n"
                "---"
            )
            if "[IMAGE TO-DO" not in notes:
                body["notes"] = (note + "\n" + notes).strip() if notes else note

        plan.append(
            {
                "id": rid,
                "name": r.get("name"),
                "model": model,
                "need_img": need_img,
                "hero": hero,
                "image_todo": needs_image_todo or clear_bad_image,
                "clear_image": clear_bad_image,
                "body": body,
            }
        )

    print(f"planned={len(plan)}")
    for p in plan:
        print(
            f"  {p['id']} {p['name']} -> {p['model']} "
            f"img={'SET' if p['hero'] and p['need_img'] else ('TODO' if p['image_todo'] else 'keep')} "
            f"p={p['body'].get('payload_kg')} r={p['body'].get('reach_mm')}"
        )

    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0

    secret = _internal_secret() if args.copy_media else ""
    ok = fail = 0
    for p in plan:
        try:
            body = {k: v for k, v in p["body"].items() if v not in ([], "")}
            # Drop None unless clearing image fields (JSON null clears FileField).
            if p.get("clear_image"):
                body["image"] = None
                body["s3_image"] = None
                body["images"] = []
            else:
                body = {k: v for k, v in body.items() if v is not None}
            patched = client._patch(f"robots/robots/{p['id']}/", body)
            cm = ""
            if args.copy_media and p["hero"] and p["need_img"] and secret and not p.get("clear_image"):
                cm = copy_media(p["id"], secret)
            print(
                f"ok {p['id']} model={p['model']} "
                f"p={patched.get('payload_kg')} img={(patched.get('image') or '')[:50]} "
                f"todo={p['image_todo']} copy={cm or '-'}"
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {p['id']}: {exc}")
            fail += 1
        time.sleep(0.1)

    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
