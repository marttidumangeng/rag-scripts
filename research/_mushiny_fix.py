"""Fix the Mushiny rows (company 1850).

6680 3D Sorter Max — description was "3D Sorter Max intelligent Put Order Solution,
     Mushiny" (the name plus the company) and features were a two-line restatement of
     the name. One of its five photos, mini-sorter.jpg, shows a machine with
     "3D Sorter Mini" printed on its own body — a DIFFERENT Mushiny product — so it
     is dropped here via replace_media.
6681 4-Way Shuttle — description was "4-way shuttle solution", i.e. the name
     lowercased; features were empty; never AI-verified (confidence None).

Both rewritten from https://www.mushiny.com product pages. 6682 MIX Pro is
PUBLISHED and deliberately untouched (tools work draft/pending_review only).
"""
import sys
import time

from api_client import ResearchApiClient

APPLY = "--apply" in sys.argv

SORTER_PHOTOS = [
    "https://iprorwxhiqlkjl5q-static.micyjz.com/cloud/lmBpnKopjnSRolojlpmkjp/3D-Sorter-MAX-1920-1920.jpg",
    "https://iprorwxhiqlkjl5q-static.micyjz.com/cloud/lqBpnKopjnSRrlmnlilkjq/Sorterjiazutu.jpg",
    "https://iprorwxhiqlkjl5q-static.micyjz.com/cloud/liBpnKopjnSRilmrmirrjq/3D-Sorter-2024_3.png",
    "https://iprorwxhiqlkjl5q-static.micyjz.com/cloud/ljBpnKopjnSRilmrmiirjq/3D-Sorter-2024_5.jpg",
]

FIX = {
    6680: {
        "description": (
            "Put-to-wall sorting that stacks rebin locations vertically: the sorting carrier pitch "
            "is only 0.5 m (19.69 in), so a wall holds far more destinations in the same floor area. "
            "Rated for continuous throughput up to 10,000 pieces per hour, with sorting efficiency "
            "2-3 times and picking efficiency 3-5 times a manual line. Multiple feeding ports, a "
            "modular rebin wall whose sections can be swapped out, and direct integration with WMS, "
            "WCS, MES and ERP. Handles outbound multi-item orders and returns alike."
        ),
        "features": "\n".join([
            "Sorting carrier pitch of only 0.5 m (19.69 in), enabling ultra-dense vertical sorting.",
            "Continuous throughput of up to 10,000 pieces per hour.",
            "Sorting efficiency increased 2-3x and picking efficiency 3-5x versus manual handling.",
            "Flexible feeding method supporting multiple feed ports.",
            "Modular rebin wall with replaceable sections.",
            "Seamless connection to WMS, WCS, MES and ERP systems.",
            "Supports both forward and reverse (returns) logistics, including regional sorting.",
        ]),
        "purpose": "Automated put-to-wall order sorting and returns processing in warehouses.",
        "images": SORTER_PHOTOS,
        "note": (
            "2026-08-23: description and features rewritten from the product page — the previous "
            "description was the row's own name plus the company name (\"3D Sorter Max intelligent "
            "Put Order Solution, Mushiny\") and features restated the name. Photo mini-sorter.jpg "
            "removed: the machine in it carries \"3D Sorter Mini\" printed on its body, a different "
            "Mushiny product."
        ),
    },
    6681: {
        "description": (
            "A 125 mm-tall pallet shuttle that travels across aisles, zones and levels instead of "
            "being tied to a single lane, so one vehicle can serve a whole high-density block. "
            "Mushiny publishes 1.3-4x storage density, up to 50-300 percent space savings and "
            "2.5-5x better energy efficiency against conventional layouts. Drive is purely "
            "mechanical with no hydraulics to leak, the electrical architecture is modular and "
            "plug-and-play, and it carries onboard obstacle detection with multi-layer safety."
        ),
        "features": "\n".join([
            "Vehicle height of only 125 mm.",
            "Moves across aisles, zones and levels for high-density pallet storage and retrieval.",
            "Storage density increased 1.3-4x, with up to 50-300 percent space savings.",
            "2.5-5x higher energy efficiency and a claimed 40-90 percent cost reduction.",
            "Purely mechanical structure with zero oil leakage.",
            "Fully modular architecture with plug-and-play electrical modules.",
            "Intelligent obstacle detection with multi-layer safety protection.",
            "Deployed in manufacturing, 3PL, retail, e-commerce and cold chain.",
        ]),
        "purpose": "High-density automated pallet storage and retrieval across aisles, zones and levels.",
        "height_mm": 125.0,
        "note": (
            "2026-08-23: description and features rewritten from the product page — the previous "
            "description was the row's own name lowercased (\"4-way shuttle solution\") and features "
            "were empty."
        ),
    },
}


def main() -> int:
    c = ResearchApiClient()
    for rid, spec in sorted(FIX.items()):
        for attempt in range(8):
            try:
                cur = c._get(f"robots/robots/{rid}/")
                break
            except Exception:
                time.sleep(3 * (attempt + 1))
        else:
            print(f"{rid}: unreadable")
            continue

        if cur.get("status") in ("approved", "published"):
            print(f"{rid}: LIVE, refusing")
            continue

        print(f"{rid} {cur.get('name')}")
        print(f"   desc {len(cur.get('description') or '')} -> {len(spec['description'])} chars")
        print(f"   feat {len(cur.get('features') or '')} -> {len(spec['features'])} chars")
        if "images" in spec:
            print(f"   photos {len(cur.get('photos') or [])} -> {len(spec['images'])} (drops wrong-product shot)")
        if not APPLY:
            continue

        patch = {
            "description": spec["description"],
            "features": spec["features"],
            "purpose": spec["purpose"],
            "notes": ((cur.get("notes") or "").strip() + "\n\n" + spec["note"]).strip(),
        }
        if "height_mm" in spec:
            patch["height_mm"] = spec["height_mm"]
        # No `images` in this PATCH — the serializer would wipe the gallery.
        c._patch(f"robots/robots/{rid}/", patch)

        if "images" in spec:
            time.sleep(1)
            row = {
                "id": rid, "name": cur.get("name"), "company_slug": "mushiny",
                "image": spec["images"][0],
                "images": [{"url": u} for u in spec["images"]],
            }
            out = c.bulk_import_robots(
                [row], update_existing=True, patch_existing=True, replace_media=True,
                skip_company_update=True, created_by_id=1,
            )
            print("   media:", {k: out.get(k) for k in ("updated_count", "error_count")})
        time.sleep(1)

    if not APPLY:
        print("\nDry run — pass --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
