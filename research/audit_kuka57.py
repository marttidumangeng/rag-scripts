"""Deep audit company 57 robots: fields + overlap vs 1396 + approximate quality flags."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient

OUT = _RESEARCH_DIR / "staging" / "reports" / "kuka57_audit.json"
MIN_DESC = 100


def _host(url: str) -> str:
    try:
        return (urlparse(url or "").hostname or "").lower()
    except Exception:
        return ""


def approx_flags(r: dict, company_host: str) -> list[str]:
    flags: list[str] = []
    url = (r.get("url") or "").strip()
    if not url:
        flags.append("missing_url")
    elif not url.startswith("http"):
        flags.append("malformed_url")
    else:
        h = _host(url)
        if company_host and h and not (h == company_host or h.endswith("." + company_host) or company_host.endswith(h.replace("www.", ""))):
            # same registrable: kuka.com
            if "kuka.com" not in h:
                flags.append("url_domain_mismatch")

    img = (r.get("image") or r.get("s3_image") or "").strip()
    photos = r.get("photos") or r.get("images") or []
    if not img and not photos:
        flags.append("missing_image")

    desc = (r.get("description") or "").strip()
    if not desc:
        flags.append("missing_description")
    elif len(desc) < MIN_DESC:
        flags.append("short_description")

    if not (r.get("features") or "").strip():
        flags.append("missing_features")
    if not (r.get("purpose") or "").strip():
        flags.append("missing_purpose")
    if r.get("release_year") is None:
        flags.append("missing_release_year")
    if not (r.get("availability_status") or r.get("availability_status_id")):
        flags.append("missing_availability")
    if not r.get("manufacturer_country") and not (r.get("manufacturer_countries") or []):
        flags.append("missing_manufacturer_country")
    if r.get("price_min") is None and r.get("price_max") is None and not (r.get("price_range") or "").strip():
        flags.append("missing_price")

    cats = r.get("categories") or []
    if not cats:
        flags.append("missing_category")
    uses = r.get("uses") or r.get("use_keys") or []
    inds = r.get("industries") or []
    mov = r.get("movement_types") or []
    if not uses and not inds and not mov:
        flags.append("missing_taxonomy")

    vids = r.get("videos") or r.get("video_urls") or []
    if not vids:
        flags.append("missing_video")

    # specs
    spec_keys = (
        "payload_kg",
        "reach_mm",
        "weight_kg",
        "dof",
        "repeatability_mm",
        "speed",
        "battery_capacity",
        "length_mm",
        "width_mm",
        "height_mm",
    )
    if all(r.get(k) in (None, "", []) for k in spec_keys):
        flags.append("missing_specs")

    return flags


def main() -> int:
    client = ResearchApiClient()
    robots57 = robots1396 = None
    for a in range(12):
        try:
            robots57 = client.list_robots_for_company(57)
            robots1396 = client.list_robots_for_company(1396)
            break
        except Exception as e:  # noqa: BLE001
            print(f"retry {a}: {e}")
            time.sleep(5)
    assert robots57 and robots1396

    # fetch detail for each 57 robot (list may omit fields)
    detailed = []
    for r in sorted(robots57, key=lambda x: int(x["id"])):
        rid = int(r["id"])
        try:
            full = client._get(f"robots/robots/{rid}/")
        except Exception as e:  # noqa: BLE001
            full = dict(r)
            full["_detail_err"] = str(e)
        detailed.append(full)
        time.sleep(0.05)

    names1396 = [(int(r["id"]), (r.get("name") or "").strip()) for r in robots1396]

    report = []
    for r in detailed:
        name = (r.get("name") or "").strip()
        flags = approx_flags(r, "kuka.com")
        # related 1396 robots
        related = []
        tokens = set(re.findall(r"[A-Za-z0-9]+", name.upper()))
        # drop generic
        tokens -= {"KUKA", "KR", "LBR", "THE", "AND"}
        for oid, oname in names1396:
            ou = oname.upper()
            # family placeholder match
            if name.upper() in ou or ou == name.upper():
                related.append({"id": oid, "name": oname, "how": "substring/exact"})
                continue
            # shared distinctive tokens
            ot = set(re.findall(r"[A-Za-z0-9]+", ou)) - {"KUKA", "KR", "LBR"}
            if tokens and tokens <= ot:
                related.append({"id": oid, "name": oname, "how": "token_subset"})
            elif tokens and len(tokens & ot) >= max(2, len(tokens) - 1) and any(
                t in ou for t in tokens if len(t) > 3
            ):
                related.append({"id": oid, "name": oname, "how": "fuzzy"})
        # cap related
        related = related[:12]
        # family-ish?
        is_family = bool(
            re.fullmatch(
                r"(KR|LBR)\s+[A-Za-z][A-Za-z0-9 ]+|KUKA\s+OmniMove|KMP\s+\d+[A-Za-z]*|KUKA\s+KR\s+\d+",
                name,
                re.I,
            )
        ) or name.upper() in {
            "KR AGILUS",
            "KR DELTA",
            "LBR IISY",
            "LBR IIWA",
            "KR CYBERTECH",
            "KR CYBERTECH NANO",
            "KR IONTEC",
            "KR QUANTEC",
            "KR FORTEC",
            "KR TITAN",
            "KUKA OMNIMOVE",
        }

        row = {
            "id": r.get("id"),
            "name": name,
            "url": r.get("url"),
            "status": r.get("status"),
            "flags": flags,
            "is_family_placeholder": is_family,
            "related_1396_sample": related,
            "related_count_est": len(related),
            "desc_len": len((r.get("description") or "").strip()),
            "feat_len": len((r.get("features") or "").strip()),
            "purpose": (r.get("purpose") or "")[:120],
            "image": (r.get("image") or r.get("s3_image") or "")[:100],
            "payload_kg": r.get("payload_kg"),
            "reach_mm": r.get("reach_mm"),
            "release_year": r.get("release_year"),
            "family_name": r.get("family_name"),
            "country": r.get("manufacturer_country"),
            "categories": r.get("categories"),
            "uses": r.get("uses") or r.get("use_keys"),
            "n_videos": len(r.get("videos") or r.get("video_urls") or []),
            "availability": r.get("availability_status") or r.get("availability_status_id"),
        }
        report.append(row)
        print(f"\n{row['id']} {name}")
        print(f"  flags={flags}")
        print(f"  family_ph={is_family} related≈{len(related)} url={ (r.get('url') or '')[:70]}")
        print(
            f"  desc={row['desc_len']} feat={row['feat_len']} img={bool(row['image'])} "
            f"y={row['release_year']} p={row['payload_kg']} vids={row['n_videos']} "
            f"country={row['country']} cats={bool(row['categories'])}"
        )
        if related[:5]:
            print("  related:", "; ".join(f"{x['id']}:{x['name']}" for x in related[:5]))

    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT}")

    # summary
    from collections import Counter

    ctr = Counter()
    for row in report:
        for f in row["flags"]:
            ctr[f] += 1
    print("flag counts:", dict(ctr.most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
