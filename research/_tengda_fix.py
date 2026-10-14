"""Fix Shandong Tengda (company 1751) — one real product, one news article.

6347 IS the product: its breadcrumb is `Index > HOT PRODUCTS > PV cleaning machine`.
6348 is NOT: its breadcrumb is `Index > NEWS CENTER`, its name is that article's
headline (note the trailing colon it was truncated at), and its "features" open
with the scraped breadcrumb and publish date — "Index > NEWS CENTER ... Update
time：2025-09-18".

Photo defects found by eye:
  6347 — a TENGDA company LOGO and a WhatsApp QR CODE among its six photos.
  6348 — the logo plus FOUR PHOTOS OF FORKLIFTS (CPD-18, CPD-25, a 1200 kg load
         test). Tengda is mainly a forklift/crane maker, so its news pages carry a
         related-products strip from a completely different product line.
  Only 6348's spec table is worth keeping; it is moved onto 6347.

6348's three videos are ALL other manufacturers': hyCleaner solarROBOT Pro
(HughCraneLimited), a Solavio Labs demo, and an unattributed clip. They leave with
the row.

Specs read off the spec-table image (2000x897, no text layer).
"""
import sys
import time

from api_client import ResearchApiClient

APPLY = "--apply" in sys.argv
U = "https://tengdaglobal.com/uploads/allimg/"

# 4 confirmed robot photos + the spec table lifted from 6348. Logo and QR dropped.
PHOTOS = [
    U + "20250306/1-250306152949495.jpg",   # full unit — hero
    U + "20250306/1-250306152940R5.png",    # brush assembly
    U + "20250313/1-25031314060R02.png",    # on a panel edge
    U + "20250306/1-2503061529444H.jpg",    # installed in frame
    "https://cdn.robotaigeek.com/robots/original/robot-6348-single-head-solar-panel-clea-0072e94d.jpg",
]

DESCRIPTION = (
    "A tracked, remote-controlled brush unit that drives itself along a photovoltaic array to clean "
    "it, in either washing or dry mode. It runs on a 24 V 28.6 Ah lithium pack for three to four "
    "hours at 200 W, crawls at 20 m/min and works panels pitched up to 30 degrees, in anything from "
    "-20 to 50 °C. At 35 kg and 150 mm tall it sits on the panels themselves, and comes in a "
    "1,100 mm or 1,300 mm cleaning width; the nylon-silk brush is 132 mm across."
)

FEATURES = "\n".join([
    "Remote-controlled operation.",
    "Track walking drive, stated as suitable for all terrains; travel speed 20 m/min.",
    "Cleaning width 1,100 mm (A) or 1,300 mm (B); 132 mm nylon-silk brush.",
    "Washing or dry cleaning modes.",
    "24 V DC, lithium battery 24 V / 28.6 Ah, 200 W rated total power.",
    "Working time 3-4 hours per charge.",
    "Works on arrays pitched up to 30 degrees.",
    "Operating temperature -20 to 50 °C.",
    "Equipment weight 35 kg; A model 950 x 1200 x 150 mm, B model 950 x 1400 x 150 mm.",
])

PATCH = {
    "name": "Tengda Single-Head Solar Panel Cleaning Robot",
    "model_name": "Single-Head Solar Panel Cleaning Robot",
    "description": DESCRIPTION,
    "purpose": "Automated brush cleaning of photovoltaic solar panel arrays.",
    "features": FEATURES,
    "weight_kg": 35.0,
    "length_mm": 1200.0, "width_mm": 950.0, "height_mm": 150.0,
    "speed": 1.2,                      # 20 m/min expressed in km/h (the field's unit)
    "runtime": "3-4 hours",            # left as text: the source says "3/4hours"
    "voltage": "24 V DC",
    "battery_capacity": "Lithium 24 V / 28.6 Ah",
    "environment": "Outdoor photovoltaic arrays; -20 to 50 °C, panel pitch up to 30 degrees.",
    "family_name": "Tengda PV Cleaning Machine",
    "family_key": "tengda:pv-cleaning",
    "variant_label": "1,100 mm (A) / 1,300 mm (B) cleaning width",
    "product_url_scope": "exact_variant",
    "availability_status_key": "released",
    "movement_type_keys_note": "tracked — stored as wheeled, no tracked key in the vocabulary",
    "tags": ["Solar Panel Cleaning", "Cleaning Robot", "Photovoltaic", "Remote Control",
             "Autonomous", "Maintenance"],
    "categories": ["cleaning-robots", "service-robots"],
}

NOTE_6347 = (
    "2026-08-23: renamed from the machine-translated 'Single-end robot' to Tengda's own English "
    "wording. Specs read off the spec-table image (2000x897, no text layer): remote control, 24 V DC, "
    "lithium 24 V/28.6 Ah, 3-4 h, 200 W, track walking, 20 m/min, cleaning width 1100/1300 mm, brush "
    "132 mm nylon silk, washing/dry, angle <=30 deg, -20~50 C, 35 kg, A 950x1200x150 / B 950x1400x150. "
    "Photos cleaned: dropped the TENGDA company LOGO and a WhatsApp QR CODE; kept the four real robot "
    "photos and added the spec table carried over from 6348. speed stored as 1.2 km/h = 20 m/min. "
    "Travel is TRACKED; movement_type is 'wheeled' only because the vocabulary has no tracked key."
)

REASON_6348 = (
    "News article, not a product. The page breadcrumb is 'Index > NEWS CENTER' (the real product page "
    "is aid=284, breadcrumb 'Index > HOT PRODUCTS > PV cleaning machine', already held as robot 6347). "
    "The row name is the article headline truncated at its colon, and its features begin with the "
    "scraped breadcrumb and publish date: 'Index > NEWS CENTER ... Update time：2025-09-18'. Four of "
    "its six photos were FORKLIFTS (CPD-18, CPD-25) from Tengda's unrelated product line and a fifth "
    "was the company logo; the spec table was moved to 6347. All three of its videos were other "
    "manufacturers' robots: hyCleaner solarROBOT Pro (HughCraneLimited), a Solavio Labs demo, and an "
    "unattributed clip. Rejected 2026-08-23 as a duplicate of 6347."
)


def main() -> int:
    c = ResearchApiClient()
    keep = c._get("robots/robots/6347/")
    drop = c._get("robots/robots/6348/")
    for r in (keep, drop):
        if r.get("status") in ("approved", "published"):
            print(f"{r['id']}: LIVE, refusing")
            return 1
    print(f"6347 {keep.get('name')} photos={len(keep.get('photos') or [])} -> {len(PHOTOS)}")
    print(f"6348 {drop.get('name')} photos={len(drop.get('photos') or [])} videos={len(drop.get('videos') or [])} -> reject")
    if not APPLY:
        print("\nDry run — pass --apply to write.")
        return 0

    body = {k: v for k, v in PATCH.items() if not k.endswith("_note")}
    body["notes"] = ((keep.get("notes") or "").strip() + "\n\n" + NOTE_6347).strip()
    c._patch("robots/robots/6347/", body)
    print("  6347 patched")

    time.sleep(1)
    out = c.bulk_import_robots(
        [{"id": 6347, "name": PATCH["name"], "company_slug": "shandong-tengda-heavy-industry-machinery",
          "image": PHOTOS[0], "images": [{"url": u} for u in PHOTOS],
          "movement_type_keys": "wheeled",
          "industry_keys": "energy|facilities|cleaning",
          "use_keys": "cleaning|maintenance" if False else "cleaning",
          "category_slugs": "cleaning-robots|service-robots",
          "sub_category_slug": "cleaning-facilities"}],
        update_existing=True, patch_existing=True, replace_media=True,
        skip_company_update=True, created_by_id=1)
    print("  6347 media:", {k: out.get(k) for k in ("updated_count", "error_count")}, out.get("warnings") or "")

    c.reject_robot(6348, reason=REASON_6348, categories=["duplicate"])
    print("  6348 rejected")

    time.sleep(2)
    for rid in (6347, 6348):
        r = c._get(f"robots/robots/{rid}/")
        print(f"  {rid} {r.get('name')[:44]:44s} {r.get('status'):14s} photos={len(r.get('photos') or [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
