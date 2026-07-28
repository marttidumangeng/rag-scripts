"""Audit quality ERROR/WARN flags for Pangolin 1413 via local quality.py + API fields."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.path.insert(0, str(_RESEARCH_DIR.parents[1] / "robotaigeek-server"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env()
from api_client import ResearchApiClient
from robots.quality import robot_quality_flags  # noqa: E402


def main() -> None:
    client = ResearchApiClient()
    co = client._get("companies/1413/")
    website = (co.get("website") or "").strip()
    print(f"company website={website!r}")

    robots = [
        r
        for r in client.list_robots_for_company(1413)
        if str(r.get("status") or "").lower() == "pending_review"
    ]
    # url share counts
    url_counts: Counter = Counter()
    for r in robots:
        full = client._get(f"robots/robots/{int(r['id'])}/")
        u = (full.get("url") or "").strip()
        if u:
            url_counts[u] += 1

    err_c: Counter = Counter()
    warn_c: Counter = Counter()
    rows = []
    for r in sorted(robots, key=lambda x: int(x["id"])):
        rid = int(r["id"])
        full = client._get(f"robots/robots/{rid}/")
        url = (full.get("url") or "").strip()
        img = (full.get("image") or full.get("s3_image") or "").strip()
        tags = full.get("tags")
        if isinstance(tags, list):
            tag_str = "|".join(
                (t.get("name") if isinstance(t, dict) else str(t)) for t in tags
            )
            n_tags = len(tags)
        else:
            tag_str = (tags or "").strip()
            n_tags = len([x for x in tag_str.split("|") if x.strip()]) if tag_str else 0

        cats = full.get("categories") or []
        uses = full.get("uses") or []
        moves = full.get("movement_types") or []
        inds = full.get("industries") or []
        vids = full.get("videos") or []
        photos = full.get("photos") or full.get("images") or []
        if isinstance(photos, list):
            n_photos = len(photos)
        else:
            n_photos = 1 if img else 0

        country = full.get("manufacturer_country")
        # quality.py checks manufacturer_country_ref_id — API may only expose name
        country_ref = full.get("manufacturer_country_ref") or full.get(
            "manufacturer_country_id"
        )
        avail = full.get("availability_status")
        avail_id = None
        if isinstance(avail, dict):
            avail_id = avail.get("id")
        elif isinstance(avail, int):
            avail_id = avail

        ns = SimpleNamespace(
            url=url,
            url_verified_at=full.get("url_verified_at"),
            image=img,
            s3_image=SimpleNamespace(name=img) if img and "cdn." in img else None,
            description=full.get("description") or "",
            purpose=full.get("purpose") or "",
            features=full.get("features") or "",
            source_locale=full.get("source_locale") or "en",
            release_year=full.get("release_year"),
            availability_status_id=avail_id,
            manufacturer_country_ref_id=1 if country else None,  # proxy: name present
            price_range=full.get("price_range"),
            price_min=full.get("price_min"),
            price_max=full.get("price_max"),
            tags=tag_str,
            n_tags=n_tags,
            n_categories=len(cats),
            n_movement_types=len(moves),
            n_industries=len(inds),
            n_uses=len(uses),
            weight_kg=full.get("weight_kg"),
            width_mm=full.get("width_mm"),
            length_mm=full.get("length_mm"),
            height_mm=full.get("height_mm"),
            speed=full.get("speed"),
            dof=full.get("dof"),
            payload_kg=full.get("payload_kg"),
            reach_mm=full.get("reach_mm"),
            weight=full.get("weight"),
            runtime=full.get("runtime"),
            battery_capacity=full.get("battery_capacity"),
            voltage=full.get("voltage"),
            sensors=full.get("sensors"),
            connectivity=full.get("connectivity"),
            materials=full.get("materials"),
        )
        # fill remaining SPEC blanks
        for f in (
            "walking_speed",
            "runtime_minutes",
            "battery_wh",
            "charging_time_minutes",
            "joint_torque_nm",
            "torque_density_nm_per_kg",
            "repeatability_mm",
            "width",
            "length",
            "height",
            "charging_time",
            "joint_torque",
            "torque_density",
            "charging_type",
            "computation",
            "actuation_mechanism",
        ):
            if not hasattr(ns, f):
                setattr(ns, f, full.get(f))

        flags = robot_quality_flags(
            ns,
            company_website=website,
            active_photo_count=max(n_photos, 1 if img else 0),
            active_video_count=len(vids) if isinstance(vids, list) else 0,
            url_shared_count=url_counts.get(url, 0),
        )
        errs = [f for f in flags if f["severity"] == "error"]
        warns = [f for f in flags if f["severity"] == "warn"]
        for f in errs:
            err_c[f["flag"]] += 1
        for f in warns:
            warn_c[f["flag"]] += 1
        if errs or warns:
            rows.append((rid, (full.get("name") or "")[:40], errs, warns))
            print(
                f"{rid} E={len(errs)} W={len(warns)} "
                f"err={[e['flag'] for e in errs]} "
                f"warn={[w['flag'] for w in warns]} "
                f"|{(full.get('name') or '')[:36]}"
            )

    print("\nERROR totals:", dict(err_c.most_common()))
    print("WARN totals:", dict(warn_c.most_common()))
    print(f"robots_with_errors={sum(1 for _,_,e,_ in rows if e)}/{len(robots)}")


if __name__ == "__main__":
    main()
