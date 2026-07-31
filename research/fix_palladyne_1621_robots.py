"""Fix Palladyne AI (company 1621) content-queue enrichment.

OEM: https://www.palladyneai.com
Sources: product PDPs under /products/ai-software/, /products/uas/, /products/components/.

Attribution (rule 15):
- Mini Harpy / HARPY / HAROP are IAI loitering munitions listed under Palladyne's
  IAI partnership nav — NOT Palladyne-made. Leave pending with notes; do NOT
  enrich as Palladyne products. Ask reviewer before reject/reassign.

Own products enriched (text + taxonomy + US country). Media:
- Fail-closed on Adobe stock / HUD / circuit-brain banners that are not the
  product (SwarmStrike, Gremlin-X, Brain X2) → imageless + IMAGE TO-DO notes.
- Software/platform pages keep OEM marketing heroes only when they are the
  official product-page banner (IQ, Pilot, SwarmOS, IntelliSwarm) — still
  imperfect for physical-robot rules; noted in run summary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row
from tag_suggest import TagCatalog

COMPANY_ID = 1621
COMPANY_SLUG = "palladyne-ai"
COMPANY_NAME = "Palladyne AI"
COMPANY_WEBSITE = "https://www.palladyneai.com"
US = "US"
US_COUNTRY_ID = 20

URL = {
    "iq": f"{COMPANY_WEBSITE}/products/ai-software/palladyne-iq-ai-robot/",
    "pilot": f"{COMPANY_WEBSITE}/products/ai-software/palladyne-pilot-ai-drones/",
    "swarmos": f"{COMPANY_WEBSITE}/products/ai-software/swarmos/",
    "swarmstrike": f"{COMPANY_WEBSITE}/products/uas/swarmstrike/",
    "gremlin": f"{COMPANY_WEBSITE}/products/uas/gremlin-x/",
    "brain": f"{COMPANY_WEBSITE}/products/components/brain/",
    "intelliswarm": f"{COMPANY_WEBSITE}/products/components/intelliswarm/",
    "mini_harpy": f"{COMPANY_WEBSITE}/products/iai/mini-harpy-ar-eo-loitering-munition/",
    "harpy": f"{COMPANY_WEBSITE}/products/iai/harpy-anit-radiation-loitering-munition/",
    "harop": f"{COMPANY_WEBSITE}/products/iai/harop-long-range-loitering-munition/",
}

IMG = {
    "iq": f"{COMPANY_WEBSITE}/wp-content/uploads/2025/01/robot-with-overlays-1-1024x301.png",
    "pilot": f"{COMPANY_WEBSITE}/wp-content/uploads/2025/11/palladyne_pilot-scaled.jpg",
    "swarmos": f"{COMPANY_WEBSITE}/wp-content/uploads/2025/11/swarmos_banner-scaled.jpg",
    "intelliswarm": f"{COMPANY_WEBSITE}/wp-content/uploads/2025/10/swarm-blog2.png",
}

TAGS_SW = "Industrial|Autonomous|Service Robot|Industrial Automation"
TAGS_UAS = "UAV|Drone|Aerial|Autonomous|Defense|Autonomous Flight"
TAGS_COMP = "UAV|Drone|Aerial|Autonomous|Defense"

_AVAIL_IDS = {
    "available": 11,
    "announced": 10,
    "discontinued": 4,
}

# IAI partner products — do not enrich in place; note for reviewer.
IAI_HOLD: dict[int, str] = {
    5675: "Mini Harpy",
    5672: "HARPY",
    5671: "HAROP",
}

IAI_NOTE = (
    "[ATTRIBUTION HOLD — IAI product on Palladyne partner pages]\n"
    "This SKU is an Israel Aerospace Industries (IAI) loitering munition listed "
    "under Palladyne AI's IAI Partnership product nav, not a Palladyne-designed "
    "platform. OEM copy cites IAI innovation / IAI systems.\n"
    "ACTION FOR TEAM: reject as wrong_company OR reassign to an IAI company "
    "record after confirming no better IAI-side duplicate exists. Do not publish "
    "under Palladyne AI as manufacturer.\n"
    "---\n"
)


def trigger_copy_media(robot_ids: list[int]) -> tuple[int, int]:
    secret = os.environ.get("INTERNAL_API_SECRET") or ""
    api = (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")
    if not secret:
        print("WARN: no INTERNAL_API_SECRET for copy-media", file=sys.stderr)
        return 0, len(robot_ids)
    ok = fail = 0
    for rid in robot_ids:
        url = f"{api}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(
                url, headers={"X-Internal-Secret": secret}, timeout=120
            )
            if resp.status_code < 300:
                ok += 1
                print(f"copy-media ok {rid}", flush=True)
            else:
                fail += 1
                print(f"copy-media fail {rid}: HTTP {resp.status_code}", flush=True)
        except Exception as exc:
            fail += 1
            print(f"copy-media fail {rid}: {exc}", flush=True)
        time.sleep(0.2)
    return ok, fail


def resolve_tags(catalog: TagCatalog, pipe: str) -> str:
    names = [n.strip() for n in pipe.split("|") if n.strip()]
    out: list[str] = []
    missing: list[str] = []
    for n in names:
        hit = catalog._by_name.get(n.lower())
        if hit:
            out.append(str(hit.get("name") or n))
        else:
            missing.append(n)
    if missing:
        print(f"WARN unresolved tags: {missing}", file=sys.stderr)
    return "|".join(out)


def image_todo(reason: str) -> str:
    return (
        "[IMAGE TO-DO — no hero, deliberate]\n"
        f"{reason}\n"
        "ACTION FOR TEAM: source a licensed model-specific product photo/render "
        "from Palladyne, or leave imageless until one exists.\n"
        "Do NOT substitute Adobe stock, HUD graphics, or sibling banners.\n"
        "---\n"
    )


ROBOT_FIXES: dict[int, dict[str, Any]] = {
    5676: {
        "name": "Palladyne IQ",
        "model_name": "Palladyne IQ",
        "variant_code": "IQ",
        "variant_label": "IQ",
        "url": URL["iq"],
        "family_key": "palladyne-ai:palladyne-iq",
        "family_name": "Palladyne IQ",
        "family_url": URL["iq"],
        "product_url_scope": "exact_variant",
        "image": IMG["iq"],
        "description": (
            "Palladyne IQ is closed-loop autonomy software that uses AI and machine "
            "learning to give industrial robots and cobots human-like reasoning. It "
            "lets robots perceive real-world variation and adapt dynamically so "
            "teams can automate unstructured tasks that rigid teach-pendant programs "
            "cannot handle."
        ),
        "purpose": (
            "Closed-loop AI autonomy for industrial robots and cobots\n"
            "Adaptive automation in unstructured environments\n"
            "Low-code / no-code robot task training\n"
            "Agile manufacturing, inspection, and surface preparation"
        ),
        "features": (
            "OEM Palladyne IQ page: closed-loop autonomy software for industrial "
            "robots and collaborative robots; AI/ML perception of environmental "
            "variation with continuous task adaptation; low-code/no-code training "
            "to cut costly programming; targets agile manufacturing, field repair, "
            "assembly-line quality inspection, and surface preparation. Software "
            "platform — no OEM payload/weight/dims (not a physical SKU)."
        ),
        "availability_status_key": "available",
        "movement_type_keys": "stationary",
        "industry_keys": "industrial|manufacturing|commercial",
        "use_keys": "general-automation|inspection",
        "category_slugs": "industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "tags": TAGS_SW,
        "manufacturer_country_code": US,
        "information_source_urls": [URL["iq"]],
        "notes_force": (
            "[AI Research] Palladyne IQ is autonomy software, not a physical robot. "
            "Hero kept as OEM product-page banner (robot-with-overlays). No typed "
            "mech specs — N/A for software. Trademarked name cleaned of mojibake."
        ),
        "source_note": URL["iq"],
        "programming_interface": (
            "Low-code / no-code training for robotic systems; closed-loop AI/ML "
            "autonomy stack (OEM public page)."
        ),
        "deployment_context": (
            "Industrial robots and cobots in unstructured or dynamically changing "
            "factory/field environments."
        ),
    },
    5677: {
        "name": "Palladyne Pilot",
        "model_name": "Palladyne Pilot",
        "variant_code": "Pilot",
        "variant_label": "Pilot",
        "url": URL["pilot"],
        "family_key": "palladyne-ai:palladyne-pilot",
        "family_name": "Palladyne Pilot",
        "family_url": URL["pilot"],
        "product_url_scope": "exact_variant",
        "image": IMG["pilot"],
        "description": (
            "Palladyne Pilot is a closed-loop AI software platform for tactical UAV "
            "missions. It enables networks of collaborating drones and multi-modal "
            "sensors to self-orchestrate for intelligence, surveillance, "
            "reconnaissance, and perimeter security with fewer operators."
        ),
        "purpose": (
            "Autonomous collaborative UAV mission software\n"
            "Intelligence, surveillance, and reconnaissance (ISR)\n"
            "Perimeter security drone coordination\n"
            "Tactical UAV detection, tracking, and control"
        ),
        "features": (
            "OEM Palladyne Pilot page: closed-loop autonomous detection, tracking, "
            "and control for mobile aerial machines; transforms UAVs into "
            "autonomously collaborating platforms; multi-modal sensor support "
            "(vision and external sensors); mission apps include intelligence, "
            "perimeter security, reconnaissance, and surveillance. Software "
            "platform — no airframe payload/weight published."
        ),
        "availability_status_key": "available",
        "movement_type_keys": "aerial|flying",
        "industry_keys": "defense|defence|military|commercial",
        "use_keys": "surveillance|reconnaissance",
        "category_slugs": "service-robots",
        "sub_category_slug": "military",
        "tags": TAGS_UAS,
        "manufacturer_country_code": US,
        "information_source_urls": [URL["pilot"]],
        "notes_force": (
            "[AI Research] Software platform for UAV autonomy. Hero is OEM "
            "product-page banner (firefighter + drones scene) — not a Pilot "
            "hardware SKU. Cleaned trademark mojibake from name."
        ),
        "source_note": URL["pilot"],
        "programming_interface": (
            "Palladyne Pilot AI Software Platform for collaborative UAV perception "
            "and closed-loop control."
        ),
        "deployment_context": "Tactical UAV / multi-drone ISR and security missions.",
    },
    5678: {
        "name": "SwarmOS",
        "model_name": "SwarmOS",
        "variant_code": "SwarmOS",
        "variant_label": "SwarmOS",
        "url": URL["swarmos"],
        "family_key": "palladyne-ai:swarmos",
        "family_name": "SwarmOS",
        "family_url": URL["swarmos"],
        "product_url_scope": "exact_variant",
        "image": IMG["swarmos"],
        "description": (
            "SwarmOS is Palladyne AI's patented swarming and autonomy software that "
            "lets heterogeneous drones, robots, and sensors collaborate as a "
            "self-organizing team. It shares compact feature-level insights across "
            "platforms for decentralized coordination in contested environments."
        ),
        "purpose": (
            "Heterogeneous autonomous swarm coordination\n"
            "Cross-platform drone and robot collaboration\n"
            "Decentralized multi-agent mission autonomy\n"
            "Tactical force-multiplier swarming"
        ),
        "features": (
            "OEM SwarmOS page: patented swarming/autonomy software for drones, "
            "robots, and sensors; feature-based decentralized communication; "
            "sensor-agnostic insight fusion (cameras, radar, RF); closed-loop "
            "feedback for dynamic role assignment and re-tasking; designed for "
            "GPS/comms-contested tactical warfare. Datasheet download offered on "
            "OEM page (not scraped). Software — no mech specs."
        ),
        "availability_status_key": "available",
        "movement_type_keys": "aerial|flying|hybrid",
        "industry_keys": "defense|defence|military",
        "use_keys": "surveillance|reconnaissance",
        "category_slugs": "service-robots",
        "sub_category_slug": "military",
        "tags": TAGS_UAS,
        "manufacturer_country_code": US,
        "information_source_urls": [URL["swarmos"]],
        "notes_force": (
            "[AI Research] SwarmOS is swarming software. OEM banner kept as hero. "
            "Cleaned trademark mojibake from name."
        ),
        "source_note": URL["swarmos"],
        "ecosystem_compatibility": (
            "Pairs with BRAIN X2 edge-AI flight module and IntelliSwarm integrated "
            "autonomy suite per OEM component pages."
        ),
    },
    5674: {
        "name": "IntelliSwarm",
        "model_name": "IntelliSwarm",
        "variant_code": "IntelliSwarm",
        "variant_label": "IntelliSwarm",
        "url": URL["intelliswarm"],
        "family_key": "palladyne-ai:intelliswarm",
        "family_name": "IntelliSwarm",
        "family_url": URL["intelliswarm"],
        "product_url_scope": "exact_variant",
        "image": IMG["intelliswarm"],
        "description": (
            "IntelliSwarm combines SwarmOS collaborative swarming software with the "
            "BRAIN X2 edge-AI flight module into an integrated plug-and-fight "
            "autonomy suite. It enables cross-platform UAVs to sense, decide, and "
            "act together even when communications are constrained."
        ),
        "purpose": (
            "Integrated UAV swarm autonomy suite\n"
            "Distributed multi-vehicle mission decisioning\n"
            "Plug-and-fight swarm deployment\n"
            "Contested-domain collaborative UAV operations"
        ),
        "features": (
            "OEM IntelliSwarm page: unites SwarmOS software + BRAIN X2 edge-AI "
            "hardware; distributed intelligence so each vehicle decides, not only "
            "follows; mission continuity with dynamic role reassignment; embedded "
            "discrimination/ethical autonomy logic; secure mesh sharing of mission "
            "context. Bundle/product suite — no single airframe payload published."
        ),
        "availability_status_key": "available",
        "movement_type_keys": "aerial|flying",
        "industry_keys": "defense|defence|military",
        "use_keys": "surveillance|reconnaissance",
        "category_slugs": "service-robots",
        "sub_category_slug": "military",
        "tags": TAGS_COMP,
        "manufacturer_country_code": US,
        "information_source_urls": [URL["intelliswarm"], URL["swarmos"], URL["brain"]],
        "notes_force": (
            "[AI Research] Integrated SwarmOS + BRAIN X2 suite. OEM swarm graphic "
            "kept as hero. Cleaned trademark mojibake."
        ),
        "source_note": URL["intelliswarm"],
        "ecosystem_compatibility": "Includes SwarmOS software and BRAIN X2 module.",
    },
    5679: {
        "name": "SwarmStrike",
        "model_name": "SwarmStrike",
        "variant_code": "SwarmStrike",
        "variant_label": "SwarmStrike",
        "url": URL["swarmstrike"],
        "family_key": "palladyne-ai:swarmstrike",
        "family_name": "SwarmStrike",
        "family_url": URL["swarmstrike"],
        "product_url_scope": "exact_variant",
        "image": "",
        "imageless": True,
        "description": (
            "SwarmStrike is a next-generation autonomous weapons platform under "
            "development by Palladyne AI. It is designed for mass, attritable "
            "precision-strike effects in GPS- and communications-denied "
            "environments, combining AI mission management with resilient "
            "navigation."
        ),
        "purpose": (
            "Autonomous precision-strike UAS (under development)\n"
            "Mass attritable munition deployment\n"
            "GPS-denied autonomous targeting\n"
            "Contested-battlespace strike coordination"
        ),
        "features": (
            "OEM SwarmStrike page: autonomous weapons platform currently under "
            "development; AI-driven autonomy via GuideTech BRAIN avionics "
            "(mission management, autonomous target recognition, in-flight "
            "coordination); ScavengerNav proprietary suite for GPS-denied "
            "navigation; positioned as affordable attritable mass vs legacy "
            "missiles. No public OEM weight/warhead/range numbers on page — "
            "typed columns left blank."
        ),
        "availability_status_key": "announced",
        "movement_type_keys": "aerial|flying",
        "industry_keys": "defense|defence|military",
        "use_keys": "surveillance|reconnaissance",
        "category_slugs": "service-robots",
        "sub_category_slug": "military",
        "tags": TAGS_UAS,
        "manufacturer_country_code": US,
        "information_source_urls": [URL["swarmstrike"]],
        "notes_force": image_todo(
            "OEM page hero is Adobe Stock conceptual missile/HUD graphic "
            "(AdobeStock_1526861541), not a SwarmStrike product photo. Visually "
            "rejected per media gates."
        )
        + "[AI Research] Under development. Availability set to Announced. "
        "Cleaned trademark mojibake. No OEM numeric specs on public page.",
        "source_note": URL["swarmstrike"],
    },
    5670: {
        "name": "Gremlin-X",
        "model_name": "Gremlin-X",
        "variant_code": "Gremlin-X",
        "variant_label": "Gremlin-X",
        "url": URL["gremlin"],
        "family_key": "palladyne-ai:gremlin-x",
        "family_name": "Gremlin-X",
        "family_url": URL["gremlin"],
        "product_url_scope": "exact_variant",
        "image": "",
        "imageless": True,
        "description": (
            "Gremlin-X is Palladyne AI's reusable mini-bomber UAS concept currently "
            "under development. It targets precision engagement in GPS- and "
            "communications-denied environments with a compact, low-cost, "
            "repeatable-mission architecture."
        ),
        "purpose": (
            "Reusable mini-bomber UAS (under development)\n"
            "Precision strike in GPS-denied environments\n"
            "Affordable repeatable aerial engagement\n"
            "Contested-domain embodied AI strike"
        ),
        "features": (
            "OEM Gremlin-X page: reusable mini-bomber under development; precision "
            "engagement for GPS/comms-denied domains; compact low-cost architecture "
            "with integrated AI/ML avionics for repeatable missions. Public page "
            "has no weight, payload, range, or endurance numbers — left blank."
        ),
        "availability_status_key": "announced",
        "movement_type_keys": "aerial|flying",
        "industry_keys": "defense|defence|military",
        "use_keys": "surveillance|reconnaissance",
        "category_slugs": "service-robots",
        "sub_category_slug": "military",
        "tags": TAGS_UAS,
        "manufacturer_country_code": US,
        "information_source_urls": [URL["gremlin"]],
        "notes_force": image_todo(
            "OEM page hero (banshee.png) is a conceptual HUD/wireframe collage, "
            "not a Gremlin-X airframe photo. Rejected per media gates."
        )
        + "[AI Research] Under development → Announced. Cleaned trademark "
        "mojibake. No OEM numeric specs on public page.",
        "source_note": URL["gremlin"],
    },
    5669: {
        "name": "Brain X2",
        "model_name": "BRAIN X2",
        "variant_code": "BRAIN X2",
        "variant_label": "BRAIN X2",
        "url": URL["brain"],
        "family_key": "palladyne-ai:brain-x2",
        "family_name": "BRAIN X2",
        "family_url": URL["brain"],
        "product_url_scope": "exact_variant",
        "image": "",
        "imageless": True,
        "description": (
            "BRAIN X2 is Palladyne AI's edge-AI flight computer for autonomous and "
            "semi-autonomous UAV platforms. It fuses high-performance avionics, "
            "AI/ML compute, and multi-sensor perception into a compact module for "
            "contested, GPS-denied, and communications-limited environments."
        ),
        "purpose": (
            "Edge-AI flight computer for UAV autonomy\n"
            "Multi-sensor perception and mission planning\n"
            "GPS-denied autonomous flight intelligence\n"
            "Scalable swarm edge compute"
        ),
        "features": (
            "OEM BRAIN X2 page: advanced flight computer / edge-AI system; fuses "
            "avionics, AI/ML compute, and multi-sensor perception; scalable "
            "real-time mission planning across platform networks; compact modular "
            "design for mass deployment; ethical-precision discrimination "
            "emphasis. Datasheet offered on OEM page. No public mass/size/power "
            "numbers extracted — left blank."
        ),
        "availability_status_key": "available",
        "movement_type_keys": "aerial|flying",
        "industry_keys": "defense|defence|military",
        "use_keys": "surveillance|reconnaissance",
        "category_slugs": "service-robots",
        "sub_category_slug": "military",
        "tags": TAGS_COMP,
        "manufacturer_country_code": US,
        "information_source_urls": [URL["brain"]],
        "notes_force": image_todo(
            "OEM hero (brainx2_hero-scaled.jpg) is a circuit-board brain graphic, "
            "not a photo of the BRAIN X2 module. Rejected per media gates."
        )
        + "[AI Research] Component / flight computer. Ecosystem: SwarmOS / "
        "IntelliSwarm. Datasheet not parsed in this pass.",
        "source_note": URL["brain"],
        "ecosystem_compatibility": (
            "Used with SwarmOS and IntelliSwarm per OEM component pages."
        ),
    },
}


def build_row(fix: dict[str, Any], *, tags: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "company_slug": COMPANY_SLUG,
        "company_name": COMPANY_NAME,
        "source_locale": "en",
    }
    skip = {
        "videos",
        "notes_force",
        "source_note",
        "images",
        "availability_status_key",
        "imageless",
    }
    for k, v in fix.items():
        if k in skip or v is None or v == "":
            continue
        row[k] = v
    row["tags"] = tags
    if fix.get("notes_force"):
        row["notes"] = fix["notes_force"]
    if fix.get("source_note"):
        row["research_notes"] = fix["source_note"]
    if fix.get("image"):
        row["images"] = [fix["image"]]
        row["image"] = fix["image"]
    elif fix.get("imageless"):
        row["image"] = ""
        row["images"] = []
    row["availability_status_key"] = fix.get("availability_status_key") or "available"
    return row


def patch_typed(client: ResearchApiClient, rid: int, fix: dict[str, Any]) -> None:
    body: dict[str, Any] = {}
    for k in (
        "family_key",
        "family_name",
        "family_url",
        "model_name",
        "variant_code",
        "variant_label",
        "product_url_scope",
        "purpose",
        "programming_interface",
        "deployment_context",
        "ecosystem_compatibility",
    ):
        if fix.get(k) not in (None, ""):
            body[k] = fix[k]
    avail_key = fix.get("availability_status_key")
    if avail_key:
        body["availability_status"] = _AVAIL_IDS.get(str(avail_key), avail_key)
    ok_keys: list[str] = []
    for k, v in body.items():
        try:
            client._patch(f"robots/robots/{rid}/", {k: v})
            ok_keys.append(k)
        except Exception as exc:
            print(f"  patch fail {rid}.{k}: {exc}", file=sys.stderr)
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "manufacturer_countries": [US_COUNTRY_ID],
                "manufacturer_country_ref": US_COUNTRY_ID,
            },
        )
        ok_keys.append("manufacturer_countries")
    except Exception as exc:
        print(f"  patch fail {rid}.manufacturer_countries: {exc}", file=sys.stderr)
    if ok_keys:
        print(f"  patched typed {rid}: {ok_keys}")


def hold_iai(client: ResearchApiClient) -> list[int]:
    held: list[int] = []
    for rid, name in IAI_HOLD.items():
        try:
            r = client._get(f"robots/robots/{rid}/")
        except Exception as exc:
            print(f"IAI hold read fail {rid}: {exc}", file=sys.stderr)
            continue
        existing = r.get("notes") or ""
        if "[ATTRIBUTION HOLD" in existing:
            print(f"IAI hold already set {rid} {name}")
            held.append(rid)
            continue
        notes = IAI_NOTE + existing
        try:
            client._patch(f"robots/robots/{rid}/", {"notes": notes})
            print(f"IAI hold noted {rid} {name}")
            held.append(rid)
        except Exception as exc:
            print(f"IAI hold fail {rid}: {exc}", file=sys.stderr)
    return held


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix Palladyne AI company 1621")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--verify-cdn", action="store_true")
    parser.add_argument("--mark-done", action="store_true")
    parser.add_argument("--hold-iai", action="store_true", help="Write attribution notes on IAI SKUs")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--only", type=int, nargs="*")
    args = parser.parse_args()

    client = ResearchApiClient()
    catalog = TagCatalog.load(client=client)
    all_robots = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    }

    targets: list[dict[str, Any]] = []
    for rid, fix in ROBOT_FIXES.items():
        if args.only and rid not in args.only:
            continue
        robot = all_robots.get(rid)
        if not robot:
            print(f"SKIP {rid}: not pending_review / not found")
            continue
        tags = resolve_tags(catalog, str(fix.get("tags") or ""))
        row = build_row(fix, tags=tags)
        if len(row.get("features") or "") < 40 or not row.get("family_key"):
            print(f"ERROR {rid}: incomplete", file=sys.stderr)
            return 1
        if not fix.get("imageless") and not row.get("image"):
            print(f"ERROR {rid}: missing image", file=sys.stderr)
            return 1
        targets.append({"id": rid, "name": row["name"], "row": row, "fix": fix})
        print(
            f"  {rid} {row['name']}: imageless={bool(fix.get('imageless'))} "
            f"avail={fix.get('availability_status_key')} fam={row.get('family_key')}"
        )

    preview = _RESEARCH_DIR / "staging" / "reports" / "palladyne-1621-fix-preview.json"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "id": t["id"],
                        "name": t["name"],
                        "imageless": bool(t["fix"].get("imageless")),
                        "url": t["row"].get("url"),
                        "availability": t["fix"].get("availability_status_key"),
                    }
                    for t in targets
                ],
                "iai_hold": IAI_HOLD,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    if not targets:
        print("ERROR: no targets", file=sys.stderr)
        return 1
    if not args.apply:
        print(
            f"Preview: {preview}. Re-run with "
            "--apply --copy-media --verify-cdn --hold-iai --mark-done"
        )
        return 0

    imported: list[int] = []
    for t in targets:
        rid, row, fix = t["id"], t["row"], t["fix"]
        bulk = staging_dict_to_bulk_import_row(row)
        bulk["id"] = rid
        bulk["name"] = fix["name"]
        bulk["status"] = "pending_review"
        # Imageless: still force replace_media so junk heroes are cleared.
        print(f"Importing {rid} {fix['name']}…", flush=True)
        result = client.bulk_import_robots(
            [bulk],
            update_existing=True,
            patch_existing=False,
            replace_media=True,
            replace_videos=True,
            status="pending_review",
            skip_company_update=True,
            created_by_id=resolve_created_by_id(args.created_by_id),
        )
        created = int(result.get("created_count") or 0)
        err = int(result.get("error_count") or 0)
        print(f"  bulk-import created={created} updated={result.get('updated_count')} err={err}")
        if created != 0 or err:
            print(f"ERROR {rid}: {result}", file=sys.stderr)
            return 1
        patch_typed(client, rid, fix)
        if fix.get("notes_force"):
            try:
                client._patch(f"robots/robots/{rid}/", {"notes": fix["notes_force"]})
            except Exception as exc:
                print(f"  notes fail {rid}: {exc}", file=sys.stderr)
        try:
            client._patch(
                f"robots/robots/{rid}/",
                {"status": "pending_review", "name": fix["name"]},
            )
        except Exception as exc:
            print(f"  status/name warn {rid}: {exc}", file=sys.stderr)
        imported.append(rid)

    held: list[int] = []
    if args.hold_iai:
        held = hold_iai(client)

    copy_ids = [t["id"] for t in targets if t["id"] in imported and not t["fix"].get("imageless")]
    if args.copy_media and copy_ids:
        ok, fail = trigger_copy_media(copy_ids)
        print(f"copy-media ok={ok} fail={fail}")
        for t in targets:
            if t["id"] in copy_ids:
                patch_typed(client, t["id"], t["fix"])

    if args.verify_cdn and copy_ids:
        subprocess.check_call(
            [sys.executable, str(_RESEARCH_DIR / "verify_cdn_images.py"),
             "--company-id", str(COMPANY_ID)],
            cwd=str(_RESEARCH_DIR),
        )

    # Do not mark-done while IAI holds remain pending reviewer decision —
    # only mark if user passed --mark-done explicitly after reviewing holds.
    if args.mark_done and imported:
        subprocess.check_call(
            [sys.executable, str(_RESEARCH_DIR / "triage_content_queue.py"),
             "--mark-done", str(COMPANY_ID)],
            cwd=str(_RESEARCH_DIR),
        )

    print(json.dumps({"imported": imported, "iai_held": held, "preview": str(preview)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
