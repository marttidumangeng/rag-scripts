"""Remediate KUKA depth imports (id>=5374): country, categories/uses, missing photos.

Stakeholder rule (2026-07-18): enrichment MUST clear:
  - No photo / invalid photos
  - No country
  - No categories/uses
Price/videos remain optional.

Usage:
  python remediate_kuka_required_fields.py            # dry-run
  python remediate_kuka_required_fields.py --apply --copy-media
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

import requests

from api_client import ResearchApiClient
from import_staging import resolve_created_by_id
from map_to_bulk_import import staging_dict_to_bulk_import_row

COMPANY_ID = 1396
COMPANY_SLUG = "kuka"
MIN_ID = 5374

# Visually verified OEM heroes (2026-07-18 remediation).
# Family share is accepted for KUKA (per-family renders, not per-variant).
K = "https://www.kuka.com/-/media/kuka-corporate/images"
FAMILY_IMAGE: dict[str, str] = {
    # Single-robot CTA — best available FORTEC hero
    "kr-fortec": (
        f"{K}/products/robots/cta-images/kr-fortec-360.png"
        "?rev=-1&w=767&hash=6E4AED83F1B96CF73A79A4A1B6386805"
    ),
    # Official FORTEC ultra CTA (two same-family robots)
    "kr-fortec-ultra": (
        f"{K}/products/robots/cta-images/kr-fortec-ultra.png"
        "?rev=-1&w=767&hash=0D6C590B351A21BD2868FFF3F131215F"
    ),
    # my.KUKA product picture — single arm close-up
    "kr-fortec-ultra-pa": (
        f"{K}/products/robots/kr-fortec/kr-fortec-ultra-pa/"
        "product-picture-mykuka-fortec-ultra-pa.png"
        "?rev=-1&w=767&hash=DFA07BE348804323773EEE2"
    ),
    # Official LBR iiwa CTA — single cobot close-up
    "lbr-iiwa": f"{K}/products/robots/cta-images/lbr-iiwa.png",
}

IMAGE_TODO_BLOCK = re.compile(
    r"\[IMAGE TO-DO[^\]]*\][\s\S]*?(?=---\n|\Z)",
    re.IGNORECASE,
)


def _admin_base() -> str:
    return (
        os.environ.get("IMPORT_SYNC_API_BASE_URL", "")
        .rstrip("/")
        .replace("/api/v1", "")
    )


def _secret() -> str:
    s = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if s:
        return s
    env = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip()
    return ""


def _copy_media(rid: int, secret: str) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
    try:
        r = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
        return "ok" if r.ok else f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return f"ERR {str(e)[:60]}"


def _taxonomy_body(name: str) -> dict[str, Any]:
    low = (name or "").lower()
    is_pa = " pa" in f" {low}" or low.endswith(" pa") or "pallet" in low
    is_cobot = "lbr" in low or "iisy" in low or "iiwa" in low

    if is_pa:
        uses = [25, 32]  # palletizing, material-handling
    elif is_cobot:
        uses = [21, 22]  # assembly, pick-and-place
    else:
        uses = [32, 46]  # material-handling, handling

    return {
        "manufacturer_country": "Germany",
        "manufacturer_countries": [7],
        "categories": ["Industrial-Robot"],
        "sub_category": 9,  # manufacturing-industrial
        "movement_types": [10],  # stationary
        "industries": [12, 26],  # manufacturing, automotive
        "uses": uses,
    }


def _strip_image_todo(notes: str) -> str:
    cleaned = IMAGE_TODO_BLOCK.sub("", notes or "").strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--ids", type=int, nargs="*")
    ap.add_argument("--created-by-id", type=int, default=0)
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = client.list_robots_for_company(COMPANY_ID)
            break
        except Exception as e:  # noqa: BLE001
            print(f"list retry {a}: {str(e)[:80]}", file=sys.stderr)
            time.sleep(5)
    if robots is None:
        print("ERROR: fetch failed", file=sys.stderr)
        return 1

    plan_path = _RESEARCH_DIR / "staging/reports/kuka_enrich_plan.json"
    family_by_id: dict[int, str] = {}
    if plan_path.is_file():
        for p in json.loads(plan_path.read_text(encoding="utf-8")):
            family_by_id[int(p["id"])] = p.get("family") or ""

    targets = [
        r
        for r in robots
        if int(r.get("id") or 0) >= MIN_ID
        and (not args.ids or int(r["id"]) in set(args.ids))
    ]
    targets.sort(key=lambda r: int(r["id"]))

    need_country = 0
    need_cat = 0
    need_use = 0
    need_img = 0
    for r in targets:
        rid = int(r["id"])
        if not (r.get("manufacturer_country") or (r.get("manufacturer_country_ref") or {}).get("id")):
            need_country += 1
        if not r.get("categories"):
            need_cat += 1
        if not r.get("uses"):
            need_use += 1
        img = (r.get("image") or r.get("s3_image") or "").strip()
        if not img:
            need_img += 1
            fam = family_by_id.get(rid, "")
            print(f"IMAGE GAP {rid} {r.get('name')} family={fam} -> {bool(FAMILY_IMAGE.get(fam))}")

    print(
        f"targets={len(targets)} need_country={need_country} "
        f"need_cat={need_cat} need_use={need_use} need_img={need_img}"
    )
    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0

    created_by = args.created_by_id or resolve_created_by_id()
    secret = _secret() if args.copy_media else ""
    ok = fail = 0
    media_ids: list[int] = []

    for r in targets:
        rid = int(r["id"])
        name = r.get("name") or ""
        body = _taxonomy_body(name)
        try:
            patched = client._patch(f"robots/robots/{rid}/", body)
            print(
                f"tax {rid}: country={patched.get('manufacturer_country') or (patched.get('manufacturer_country_ref') or {}).get('name')} "
                f"cats={patched.get('categories')} uses={[u.get('key') for u in (patched.get('uses') or [])]}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL tax {rid}: {exc}")
            fail += 1
            continue

        img = (r.get("image") or r.get("s3_image") or "").strip()
        fam = family_by_id.get(rid, "")
        render = FAMILY_IMAGE.get(fam) if not img else None
        if render:
            notes = _strip_image_todo(r.get("notes") or "")
            media_note = (
                f"[media] 2026-07-18 remediate: official KUKA {fam} family hero "
                f"(required-field fix; family share accepted). Source: {render.split('?')[0]}"
            )
            if notes:
                notes = media_note + "\n---\n" + notes
            else:
                notes = media_note

            row = staging_dict_to_bulk_import_row(
                {
                    "id": rid,
                    "name": name,
                    "company_slug": COMPANY_SLUG,
                    "image": render,
                    "images": [{"url": render}],
                    "source_locale": "en",
                    "research_notes": media_note,
                }
            )
            row["id"] = rid
            try:
                res = client.bulk_import_robots(
                    [row],
                    update_existing=True,
                    patch_existing=True,
                    replace_media=True,
                    status="pending_review",
                    skip_company_update=True,
                    created_by_id=created_by,
                )
                client._patch(f"robots/robots/{rid}/", {"notes": notes, "source_locale": "en"})
                print(f"  media {rid}: updated={res.get('updated_count')} err={res.get('error_count')}")
                media_ids.append(rid)
            except Exception as exc:  # noqa: BLE001
                print(f"  FAIL media {rid}: {exc}")
                fail += 1
                continue

        ok += 1
        time.sleep(0.08)

    if args.copy_media and secret and media_ids:
        print(f"\ncopy-media for {len(media_ids)} robots…")
        for rid in media_ids:
            status = _copy_media(rid, secret)
            print(f"  copy-media {rid}: {status}")
            if not status.startswith("ok"):
                fail += 1
            time.sleep(0.1)

    print(f"\nDONE ok={ok} fail={fail} media_attached={len(media_ids)}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
