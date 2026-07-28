#!/usr/bin/env python3
"""Audit Unitree pending_review robots (109) for quality flags + media."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import requests

sys.path.insert(0, ".")
sys.path.insert(0, str(Path(".").resolve().parents[1] / "robotaigeek-server"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from robots.quality import robot_quality_flags

IDS = [5362, 5355, 5353]
OUT = Path("staging/reports/unitree-109-pending-qa.json")
QA = Path("staging/unitree_pending_qa")
QA.mkdir(parents=True, exist_ok=True)


def ns(r: dict) -> SimpleNamespace:
    d = dict(r)
    # normalize nested
    return SimpleNamespace(**{k: v for k, v in d.items() if k.isidentifier()})


def main() -> int:
    c = ResearchApiClient()
    co = c._get("companies/109/")
    website = (co.get("website") or "").strip()
    rows = []
    for rid in IDS:
        r = c._get(f"robots/robots/{rid}/")
        photos = r.get("photos") or []
        vids = r.get("videos") or r.get("video_urls") or []
        n_photos = len(photos) if isinstance(photos, list) else 0
        n_vids = len(vids) if isinstance(vids, list) else 0
        # build object-like for quality
        obj = SimpleNamespace(
            id=r.get("id"),
            name=r.get("name"),
            description=r.get("description") or "",
            features=r.get("features") or "",
            purpose=r.get("purpose") or "",
            url=r.get("url") or "",
            image=r.get("image") or "",
            s3_image=r.get("s3_image") or "",
            payload_kg=r.get("payload_kg"),
            reach_mm=r.get("reach_mm"),
            weight_kg=r.get("weight_kg"),
            dof=r.get("dof"),
            release_year=r.get("release_year"),
            price_min=r.get("price_min"),
            price_max=r.get("price_max"),
            availability_status=r.get("availability_status"),
            manufacturer_country_ref=r.get("manufacturer_country_ref")
            or r.get("manufacturer_country"),
            manufacturer_countries=r.get("manufacturer_countries") or [],
            categories=r.get("categories") or r.get("category") or [],
            uses=r.get("uses") or [],
            industries=r.get("industries") or [],
            tags=r.get("tags") or [],
            notes=r.get("notes") or "",
            weight=r.get("weight"),
            width=r.get("width"),
            length=r.get("length"),
            height=r.get("height"),
            runtime=r.get("runtime"),
            battery_capacity=r.get("battery_capacity"),
            charging_time=r.get("charging_time"),
            voltage=r.get("voltage"),
            joint_torque=r.get("joint_torque"),
            torque_density=r.get("torque_density"),
            connectivity=r.get("connectivity"),
            sensors=r.get("sensors"),
            materials=r.get("materials"),
            charging_type=r.get("charging_type"),
            computation=r.get("computation"),
            actuation_mechanism=r.get("actuation_mechanism"),
            width_mm=r.get("width_mm"),
            length_mm=r.get("length_mm"),
            height_mm=r.get("height_mm"),
            speed=r.get("speed"),
            walking_speed=r.get("walking_speed"),
            runtime_minutes=r.get("runtime_minutes"),
            battery_wh=r.get("battery_wh"),
            charging_time_minutes=r.get("charging_time_minutes"),
            joint_torque_nm=r.get("joint_torque_nm"),
            torque_density_nm_per_kg=r.get("torque_density_nm_per_kg"),
            repeatability_mm=r.get("repeatability_mm"),
        )
        flags = robot_quality_flags(
            obj,
            company_website=website,
            active_photo_count=n_photos,
            active_video_count=n_vids,
        )
        hero = (r.get("s3_image") or r.get("image") or "").strip()
        magic = md5 = nbytes = None
        if hero:
            try:
                body = requests.get(hero, timeout=60).content
                nbytes = len(body)
                md5 = hashlib.md5(body).hexdigest()
                if body.startswith(b"\x89PNG"):
                    magic = "png"
                elif body.startswith(b"\xff\xd8"):
                    magic = "jpeg"
                elif body[:4] == b"RIFF" and body[8:12] == b"WEBP":
                    magic = "webp"
                elif len(body) > 12 and body[4:8] == b"ftyp":
                    magic = f"ftyp-{body[8:12]!r}"
                else:
                    magic = "other"
                (QA / f"{rid}_{md5[:12]}.{magic if magic in ('png','jpeg','webp') else 'bin'}").write_bytes(body)
            except Exception as e:
                magic = f"err:{e}"
        tags = r.get("tags") or []
        if isinstance(tags, list):
            tag_names = [t.get("name") if isinstance(t, dict) else t for t in tags]
        else:
            tag_names = tags
        entry = {
            "id": rid,
            "name": r.get("name"),
            "status": r.get("status"),
            "url": r.get("url"),
            "family_key": r.get("family_key"),
            "year": r.get("release_year"),
            "country": r.get("manufacturer_country_ref") or r.get("manufacturer_country"),
            "n_photos": n_photos,
            "n_videos": n_vids,
            "tags": tag_names,
            "features_len": len(r.get("features") or ""),
            "desc_len": len(r.get("description") or ""),
            "payload": r.get("payload_kg"),
            "weight": r.get("weight_kg"),
            "hero": hero[:100],
            "hero_md5": md5,
            "hero_bytes": nbytes,
            "hero_magic": magic,
            "flags": flags,
            "errors": [f for f in flags if f.get("severity") == "error"],
            "warns": [f for f in flags if f.get("severity") == "warn"],
            "notes": (r.get("notes") or "")[:300],
            "verification": r.get("verification"),
            "quality_flags_api": r.get("quality_flags"),
        }
        rows.append(entry)
        print(
            f"{rid} {r.get('name')}: err={[e['flag'] for e in entry['errors']]} "
            f"warn={[w['flag'] for w in entry['warns']]} hero={magic}/{nbytes}"
        )
        time.sleep(0.1)
    OUT.write_text(json.dumps({"pending": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
