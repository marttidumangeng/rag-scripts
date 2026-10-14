"""Fix the 12 QKM Technologies draft rows (company 1946) so they can be reviewed.

What was wrong:
  * 7 of 12 had ZERO photos (missing_image, a pre-verify blocker) and 3 more were thin.
  * 7047 AH10 pointed at the Chinese page /p/5.html instead of the English /en/p/24.html.
  * All 12 carried missing_family despite being five obvious series.
  * No payload/reach/repeatability/weight/dof on any row.

Media goes through bulk_import patch mode (upsert by URL, additive) rather than a DRF
PATCH, because the serializer treats `images` as a wipe-and-replace of the gallery.

Taxonomy is echoed back on every row on purpose: bulk_import re-stamps quality_flags
from ROW-derived taxonomy counts, so a patch row that omits them makes the counts read
0 and fires a false "No categories/uses" chip.
"""
import json
import sys
import time

from api_client import ResearchApiClient

SP = ("C:/Users/tramk/AppData/Local/Temp/claude/"
      "C--Github-Personal-robot-ai-geek/9cff51dd-ca8d-479a-8bd9-29d05105ebd3/"
      "scratchpad/qkm_harvest.json")

APPLY = "--apply" in sys.argv


def main() -> int:
    harvest = json.load(open(SP, encoding="utf-8"))
    c = ResearchApiClient()

    rows = []
    for rid_s, rec in sorted(harvest.items(), key=lambda kv: int(kv[0])):
        rid = int(rid_s)
        for attempt in range(8):
            try:
                cur = c._get(f"robots/robots/{rid}/")
                break
            except Exception:
                time.sleep(3 * (attempt + 1))
        else:
            print(f"{rid}: could not read, skipping")
            continue

        if cur.get("status") in ("approved", "published"):
            print(f"{rid}: LIVE robot, refusing to touch")
            continue

        specs = rec["specs"]
        row = {
            "id": rid,
            "name": cur.get("name"),
            "company_slug": "qkm-technologies",
            "url": rec["url"],
            "image": rec["images"][0],
            "images": rec["images"],
            "family_name": rec["family_name"],
            "family_key": rec["family_key"],
            "family_url": rec["url"],
            "product_url_scope": "exact_variant",
            # Echoed so the flag re-stamp does not read taxonomy as 0.
            "category_slugs": "|".join(
                str(x).lower() for x in (cur.get("categories") or [])),
            "use_keys": "|".join(u["key"] for u in (cur.get("uses") or [])),
            "industry_keys": "|".join(i["key"] for i in (cur.get("industries") or [])),
            "movement_type_keys": "|".join(
                m["key"] for m in (cur.get("movement_types") or [])) or "stationary",
        }
        for key in ("payload_kg", "reach_mm", "repeatability_mm", "weight_kg",
                    "dof", "ip_rating", "variant_code"):
            if key in specs:
                row[key] = specs[key]
        rows.append((rid, rec["model"], cur, row))

    print(f"{len(rows)} rows prepared\n")
    for rid, model, cur, row in rows:
        url_change = "" if (cur.get("url") or "") == row["url"] else \
            f"  URL {cur.get('url')} -> {row['url']}"
        print(f"  {rid} {model:6s} photos {len(cur.get('photos') or []):2d} +{len(row['images'])} "
              f"| payload={row.get('payload_kg')} reach={row.get('reach_mm')} "
              f"dof={row.get('dof')} code={row.get('variant_code')}{url_change}")

    if not APPLY:
        print("\nDry run — pass --apply to write.")
        return 0

    payload = [r for _, _, _, r in rows]
    out = c.bulk_import_robots(
        payload, update_existing=True, patch_existing=True,
        skip_company_update=True, created_by_id=1,
    )
    print("\nbulk_import:", {k: out.get(k) for k in
                             ("created_count", "updated_count", "skipped_count", "error_count")})
    for w in (out.get("warnings") or [])[:10]:
        print("   warn:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
