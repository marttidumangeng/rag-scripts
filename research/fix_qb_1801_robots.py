"""Fix company 1801 (qb Robotics) content-queue errors/warnings.

Keepers: SoftHand Industry / Research / SoftHand2 Research.
Reject: mounting accessories (brackets, ISO flanges, Kinova adapter, clamp)
as wrong_category + escalated.
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
sys.path.insert(0, str(_RESEARCH_DIR))
from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

COMPANY_ID = 1801
IT = 10  # Italy
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

REJECT_IDS = [6513, 6514, 6515, 6516, 6517, 6518]
REJECT_REASON = (
    "wrong_category: qb Robotics accessory / mounting hardware (Bracket, "
    "ISO 9409 flange adapter, Kinova adapter, Robot Clamp) — not a robot or "
    "end-effector SKU. Catalog SoftHand products separately. Escalate — do "
    "not re-import as robots."
)

# Distinct OEM product photos only (no pisa campus banners, logos, cert badges,
# sibling/cross-brand shots). Verified visually 2026-08-02.
KEEPERS: dict[int, dict[str, Any]] = {
    6521: {
        "name": "qb SoftHand2 Research",
        "model_name": "qb SoftHand2 Research",
        "url": "https://qbrobotics.com/product/qb-softhand-2-research",
        "family_key": "qb-robotics:softhand2-research",
        "family_name": "SoftHand2 Research",
        "image": "https://qbrobotics.com/wp-content/uploads/2022/05/Posa1-1.jpg",
        "images": [
            "https://qbrobotics.com/wp-content/uploads/2022/05/Posa1-1.jpg",
            "https://qbrobotics.com/wp-content/uploads/2022/05/Cilieg_SH2R_w-1.jpg",
            "https://qbrobotics.com/wp-content/uploads/2022/05/egg_w.jpg",
            "https://qbrobotics.com/wp-content/uploads/2022/05/Pinch_mgn_wjpg.jpg",
        ],
        "purpose": (
            "Research grasping and in-hand manipulation\n"
            "Precision pinch of small objects\n"
            "Human-interaction and HRI testing\n"
            "Dexterous R&D on collaborative arms"
        ),
        "description": (
            "The qb SoftHand2 Research is the stronger, smarter evolution of "
            "qb SoftHand Research: an anthropomorphic soft robotic hand with "
            "19 dislocatable self-healing finger joints and two motor "
            "synergies. It performs precision and power grips plus in-hand "
            "manipulation without changing wrist orientation, and is aimed "
            "at R&D, testing, and human-interaction applications."
        ),
        "features": (
            "Anthropomorphic soft hand: 19 DOF, two synergies, two motors; "
            "dislocatable self-healing finger joints. Closure postures include "
            "precise pinch, in-hand manipulation, and pointing. Nominal "
            "payload 2 kg (pinch) / 3 kg (grasp); open-to-fist in ~1 s. "
            "Weight 0.94 kg. USB & RS485; motor position/current feedback; "
            "ROS & ROS2 compatible."
        ),
        "specs": {
            "payload_kg": 2.0,
            "weight_kg": 0.94,
            "dof": 19,
        },
        "tags": "Robotic Hand|Manipulation|Research|Collaborative|Soft Robotics|End Effector",
        "category_slugs": "end-effectors|research-robots",
        "sub_category_slug": "research",
        "movement_type_keys": "stationary|fixed",
        "industry_keys": "research|education|manufacturing",
        "use_keys": "pick-and-place|assembly|research",
    },
    6520: {
        "name": "qb SoftHand Research",
        "model_name": "qb SoftHand Research",
        "url": "https://qbrobotics.com/product/qb-softhand-research/",
        "family_key": "qb-robotics:softhand-research",
        "family_name": "SoftHand Research",
        "image": "https://qbrobotics.com/wp-content/uploads/2021/07/Stretta-mano-1.png",
        "images": [
            "https://qbrobotics.com/wp-content/uploads/2021/07/Stretta-mano-1.png",
            "https://qbrobotics.com/wp-content/uploads/2021/07/IMG_0059sf.png",
            "https://qbrobotics.com/wp-content/uploads/2021/07/IMG_1678.png",
            "https://qbrobotics.com/wp-content/uploads/2021/07/IMG_9483.jpg",
        ],
        "purpose": (
            "Research grasping and manipulation\n"
            "Adaptive object handling on cobots\n"
            "Humanoid and HRI experiments\n"
            "Education and soft-robotics demos"
        ),
        "description": (
            "The qb SoftHand Research is an anthropomorphic soft robotic hand "
            "with five fingers and 19 phalanges that reproduces human-like "
            "grasping via a single-motor, tendon-driven underactuated synergy. "
            "It adapts mechanically to varied object shapes without complex "
            "sensing, and is designed for collaborative robots, humanoids, "
            "and research labs."
        ),
        "features": (
            "5 human-like fingers; 19 anthropomorphic DOFs; one synergy, one "
            "motor; dislocatable self-healing finger joints. Replicates ~75% "
            "of human grasps via soft-robotics adaptation. Grasp force 62 N "
            "(pinch); nominal payload 1.1 kg (pinch). Weight 0.77 kg. ROS & "
            "ROS2 compatible; soft and safe for object/people interaction."
        ),
        "specs": {
            "payload_kg": 1.1,
            "weight_kg": 0.77,
            "dof": 19,
        },
        "tags": "Robotic Hand|Manipulation|Research|Collaborative|Soft Robotics|End Effector",
        "category_slugs": "end-effectors|research-robots",
        "sub_category_slug": "research",
        "movement_type_keys": "stationary|fixed",
        "industry_keys": "research|education|manufacturing",
        "use_keys": "pick-and-place|assembly|research",
    },
    6519: {
        "name": "qb SoftHand Industry",
        "model_name": "qb SoftHand Industry",
        "url": "https://qbrobotics.com/product/qb-softhand-industry/",
        "family_key": "qb-robotics:softhand-industry",
        "family_name": "SoftHand Industry",
        "image": "https://qbrobotics.com/wp-content/uploads/2021/07/SHI_original.jpg",
        "images": [
            "https://qbrobotics.com/wp-content/uploads/2021/07/SHI_original.jpg",
            "https://qbrobotics.com/wp-content/uploads/2021/07/qb-soft-hand-image-pick-04.jpg",
            "https://qbrobotics.com/wp-content/uploads/2021/07/softhand-industry-qbrobotics.jpg",
            "https://qbrobotics.com/wp-content/uploads/2021/07/IMG_3939.jpg",
        ],
        "purpose": (
            "Industrial adaptive grasping\n"
            "Food and delicate-object picking\n"
            "Bin picking and kitting\n"
            "Collaborative cell manipulation"
        ),
        "description": (
            "The qb SoftHand Industry is an anthropomorphic soft robotic hand "
            "for industrial and collaborative cells. A tendon-driven single "
            "motor opens and closes five fingers along the human first "
            "synergy for flexible, adaptable grasps. It is positioned as a "
            "plug-and-play end-effector for tasks that need human-like "
            "grasping under industrial safety standards "
            "(EN ISO 12100, ISO 10218, ISO/TS 15066)."
        ),
        "features": (
            "5 human-like fingers; 19 anthropomorphic DOFs; one synergy, one "
            "motor (tendon-driven). Power-grasp payload 2 kg; pinch-grasp "
            "payload 0.6 kg; weight 0.99 kg. ROS & ROS2 compatible. "
            "Industrial/collaborative normative compliance cited by OEM: "
            "ISO 12100, ISO/TS 15066, ISO 13849-1/-2, ISO 10218-1/-2, "
            "ISO 9409-1-50-4-M6, ISO/TR 20218-1."
        ),
        "specs": {
            "payload_kg": 2.0,
            "weight_kg": 0.99,
            "dof": 19,
        },
        "tags": "Robotic Hand|Manipulation|Industrial|Collaborative|Soft Robotics|End Effector|Pick-and-Place",
        "category_slugs": "end-effectors|collaborative-robots|industrial-robots",
        "sub_category_slug": "manufacturing-industrial",
        "movement_type_keys": "stationary|fixed",
        "industry_keys": "manufacturing|industrial|food",
        "use_keys": "pick-and-place|assembly|material-handling",
    },
}


def _admin_base() -> str:
    return (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")


def _internal_secret() -> str:
    secret = (
        os.environ.get("INTERNAL_API_SECRET")
        or os.environ.get("CONTENT_QUEUE_INTERNAL_SECRET")
        or ""
    ).strip()
    if secret:
        return secret
    for candidate in (
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env",
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env.local",
    ):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def reject_escalated(client: ResearchApiClient, rid: int) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Secret": _internal_secret(),
    }
    payload = {
        "rejection_reason": REJECT_REASON[:500],
        "rejection_categories": ["wrong_category"],
    }
    admin_msg = ""
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        admin_msg = f"admin {resp.status_code}"
    except requests.RequestException as exc:
        admin_msg = f"admin ERR {exc}"
    client._patch(
        f"robots/robots/{rid}/",
        {
            "status": "rejected",
            "rejection_reason": REJECT_REASON[:500],
            "rejection_categories": ["wrong_category"],
            "auto_fix_status": "escalated",
        },
    )
    return f"{admin_msg}; escalated"


def copy_media(rid: int) -> bool:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
    resp = requests.post(
        url, headers={"X-Internal-Secret": _internal_secret()}, timeout=180
    )
    print(f"copy-media {rid}: HTTP {resp.status_code} {resp.text[:160]}")
    return resp.status_code < 300


def md5_url(sess: requests.Session, url: str) -> tuple[str, int]:
    r = sess.get(url, timeout=60)
    r.raise_for_status()
    return hashlib.md5(r.content).hexdigest(), len(r.content)


def validate_media(cfg: dict[str, Any], used: set[str]) -> None:
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})
    hashes = []
    for u in cfg["images"]:
        h, n = md5_url(sess, u)
        if n < 8000:
            raise RuntimeError(f"too small {n} {u}")
        if h in used:
            raise RuntimeError(f"cross-robot hash reuse {h[:12]} {u}")
        if h in hashes:
            raise RuntimeError(f"within-gallery hash dup {h[:12]} {u}")
        hashes.append(h)
        print(f"  ok {n} {h[:12]} {u[-70:]}")
    used.update(hashes)


def apply_keeper(client: ResearchApiClient, rid: int, cfg: dict[str, Any]) -> dict[str, Any]:
    robot = client._get(f"robots/robots/{rid}/")
    notes = (robot.get("notes") or "").rstrip()
    notes += (
        "\n[AI Research] 2026-08-02: stripped shared pisa-campus banners; "
        "OEM SoftHand product photos only; features/specs from PDP; "
        "cleared junk Humanoid/Drone/AMR tags."
    )
    row = {
        "company_slug": "qb-robotics",
        "company_name": "Qb Robotics",
        "source_locale": "en",
        "name": cfg["name"],
        "model_name": cfg["model_name"],
        "url": cfg["url"],
        "description": cfg["description"],
        "purpose": cfg["purpose"],
        "features": cfg["features"],
        "image": cfg["image"],
        "images": cfg["images"],
        "information_source_urls": [cfg["url"]],
        "notes": notes,
        "manufacturer_country_code": "IT",
        "availability_status_key": "available",
        "family_key": cfg["family_key"],
        "family_name": cfg["family_name"],
        "family_url": cfg["url"],
        "product_url_scope": "exact_variant",
        "category_slugs": cfg["category_slugs"],
        "sub_category_slug": cfg["sub_category_slug"],
        "movement_type_keys": cfg["movement_type_keys"],
        "industry_keys": cfg["industry_keys"],
        "use_keys": cfg["use_keys"],
        "tags": cfg["tags"],
        **cfg["specs"],
    }
    bulk = staging_dict_to_bulk_import_row(row)
    bulk["id"] = rid
    bulk["status"] = "pending_review"
    result = client.bulk_import_robots(
        [bulk],
        update_existing=True,
        patch_existing=False,
        replace_media=True,
        replace_videos=False,
        status="pending_review",
        skip_company_update=True,
        created_by_id=resolve_created_by_id(1),
    )
    patch = {
        "status": "pending_review",
        "description": cfg["description"],
        "purpose": cfg["purpose"],
        "features": cfg["features"],
        "notes": notes,
        "manufacturer_countries": [IT],
        "manufacturer_country_ref": IT,
        "availability_status": 11,
        "family_key": cfg["family_key"],
        "family_name": cfg["family_name"],
        "family_url": cfg["url"],
        "product_url_scope": "exact_variant",
        "model_name": cfg["model_name"],
        "tags": [t.strip() for t in cfg["tags"].split("|")],
        **cfg["specs"],
    }
    client._patch(f"robots/robots/{rid}/", patch)
    if not copy_media(rid):
        time.sleep(2)
        copy_media(rid)
    # re-assert after copy-media
    client._patch(f"robots/robots/{rid}/", patch)
    full = client._get(f"robots/robots/{rid}/")
    flags = full.get("quality_flags") or []
    return {
        "id": rid,
        "name": full.get("name"),
        "updated": result.get("updated_count"),
        "errors_import": result.get("error_count"),
        "s3": full.get("s3_image") or full.get("image"),
        "photos_n": len(full.get("photos") or []),
        "features_len": len((full.get("features") or "").strip()),
        "hard": [
            f.get("flag")
            for f in flags
            if isinstance(f, dict) and f.get("severity") == "error"
        ],
        "warns": [
            f.get("flag")
            for f in flags
            if isinstance(f, dict) and f.get("severity") == "warn"
        ],
        "specs": {k: full.get(k) for k in ("payload_kg", "weight_kg", "dof")},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args()

    preview = {
        "reject": REJECT_IDS,
        "keepers": {
            str(k): {
                "name": v["name"],
                "image": v["image"],
                "images_n": len(v["images"]),
                "specs": v["specs"],
                "features": v["features"][:160] + "…",
            }
            for k, v in KEEPERS.items()
        },
    }
    out = _RESEARCH_DIR / "staging" / "reports" / "qb-1801-fix-preview.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(preview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(preview, indent=2, ensure_ascii=False))
    if not args.apply:
        print(f"Preview {out}. Re-run --apply")
        return 0

    client = ResearchApiClient()
    used_hashes: set[str] = set()
    print("Validating keeper media…")
    for rid, cfg in KEEPERS.items():
        print(f"#{rid} {cfg['name']}")
        validate_media(cfg, used_hashes)

    reject_results = {}
    for rid in REJECT_IDS:
        msg = reject_escalated(client, rid)
        reject_results[rid] = msg
        print(f"reject {rid}: {msg}")

    keeper_results = []
    for rid, cfg in KEEPERS.items():
        print(f"Enrich {rid} {cfg['name']}…", flush=True)
        keeper_results.append(apply_keeper(client, rid, cfg))

    ids = sorted(KEEPERS)
    subprocess.check_call(
        [sys.executable, str(_RESEARCH_DIR / "verify_cdn_images.py"), "--ids", *[str(i) for i in ids]],
        cwd=str(_RESEARCH_DIR),
    )

    summary = {"rejected": reject_results, "keepers": keeper_results}
    report = _RESEARCH_DIR / "staging" / "reports" / "qb-1801-fix-result.json"
    report.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    bad = [k for k in keeper_results if k.get("hard")]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
