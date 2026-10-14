"""Fix Nanoflex Robotics (company 1934) — the images are people, not robots.

Across rows 7013/7014/7015 there were only SIX distinct images, and five of them
were shared between two or three of the rows:
  * four are corporate HEADSHOTS of Nanoflex staff (scraped from the homepage /
    about-us team section) — 7015's hero was one of them;
  * one is a "Falling Walls Foundation - I AM A GLOBAL CALL WINNER" award poster
    (scraped from the EIC-Accelerator funding post) — it was 7014's HERO;
  * exactly one is a real device image (the catheter/guidewire render on 7013).

Publishing identifiable people's faces as a robot's photos is the part that has to
go regardless of what else happens to these rows.

The three rows are also one product: all cite the same GlobeNewswire release, and
none points at a product page (about-us, a funding announcement, and the homepage).
Nanoflex publishes no model name — their own words are "Our Telerobotics
Intervention System", which is exactly row 7015's name, so 7015 is the keeper.
"""
import sys
import time

from api_client import ResearchApiClient

APPLY = "--apply" in sys.argv
CDN = "https://cdn.robotaigeek.com/robots/original/"

# The single genuine device image already on our CDN (7013's hero) plus the only
# real technology photo published on the site.
GOOD_RENDER = CDN + "robot-7013-endovascular-robotic-solutio-b7d8a514.png"
TECH_PHOTO = "https://nanoflexrobotics.com/wp-content/uploads/2024/04/Technology_Nanofelx.jpg"

# md5 -> what it actually is. All removed.
BAD = {
    "dcef550634": "headshot of a person",
    "bc3c429fb6": "headshot of a person",
    "b9dd6223bc": "headshot of a person",
    "85f6061a7a": "headshot of a person",
    "4854bcf295": "Falling Walls Foundation award poster",
}

KEEP = 7015
STRIP = (7013, 7014)

NOTE_KEEP = (
    "2026-08-23: media rebuilt. The row's four photos were all corporate HEADSHOTS of Nanoflex "
    "staff scraped from the homepage team section — the hero was a person's face. Replaced with "
    "the only two genuine device images that exist: the catheter/guidewire render (carried over "
    "from row 7013) and Technology_Nanofelx.jpg from /our-technology/. url moved from the site "
    "homepage to /our-technology/, the closest thing Nanoflex has to a product page — they publish "
    "no model name, and \"Telerobotics Intervention System\" is their own wording for it."
)
NOTE_STRIP = (
    "2026-08-23: all photos removed — they were corporate headshots of Nanoflex staff plus a "
    "Falling Walls Foundation award poster, none of them a robot. This row is also the same "
    "product as 7015 (Telerobotics Intervention System): all three Nanoflex rows cite the same "
    "GlobeNewswire release and none points at a product page. Left image-less pending a "
    "duplicate-rejection decision."
)


def main() -> int:
    c = ResearchApiClient()
    for rid in (KEEP,) + STRIP:
        r = c._get(f"robots/robots/{rid}/")
        if r.get("status") in ("approved", "published"):
            print(f"{rid}: LIVE, refusing")
            return 1
        print(f"{rid} {r.get('name')} ({r.get('status')}) photos={len(r.get('photos') or [])}")

    if not APPLY:
        print(f"\nWould give {KEEP} the 2 real images and strip all photos from {STRIP}.")
        print("Dry run — pass --apply to write.")
        return 0

    keep = c._get(f"robots/robots/{KEEP}/")
    c._patch(f"robots/robots/{KEEP}/", {
        "url": "https://nanoflexrobotics.com/our-technology/",
        "product_url_scope": "family",
        "notes": ((keep.get("notes") or "").strip() + "\n\n" + NOTE_KEEP).strip(),
    })
    out = c.bulk_import_robots(
        [{"id": KEEP, "name": keep.get("name"), "company_slug": "nanoflex-robotics",
          "image": GOOD_RENDER,
          "images": [{"url": GOOD_RENDER}, {"url": TECH_PHOTO}]}],
        update_existing=True, patch_existing=True, replace_media=True,
        skip_company_update=True, created_by_id=1)
    print(f"  {KEEP} media:", {k: out.get(k) for k in ("updated_count", "error_count")})

    for rid in STRIP:
        cur = c._get(f"robots/robots/{rid}/")
        c._patch(f"robots/robots/{rid}/", {
            "notes": ((cur.get("notes") or "").strip() + "\n\n" + NOTE_STRIP).strip()})
        # empty images + replace_media is the documented "intentional clear" path
        out = c.bulk_import_robots(
            [{"id": rid, "name": cur.get("name"), "company_slug": "nanoflex-robotics",
              "image": "", "images": []}],
            update_existing=True, patch_existing=True, replace_media=True,
            skip_company_update=True, created_by_id=1)
        print(f"  {rid} cleared:", {k: out.get(k) for k in ("updated_count", "error_count")})
        time.sleep(1)

    print("\n-- after --")
    for rid in (KEEP,) + STRIP:
        r = c._get(f"robots/robots/{rid}/")
        print(f"  {rid} {r.get('name')[:34]:34s} photos={len(r.get('photos') or []):2d} "
              f"hero={'yes' if r.get('image_url') else 'NO'} url={r.get('url')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
