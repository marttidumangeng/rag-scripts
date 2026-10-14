"""Fix the wrong images on Verve Motion (company 1978).

WHAT WAS WRONG

7074's ONLY photo - and therefore its hero - was `Ahold-V2.png`, the corporate
logo of Ahold Delhaize. That is a CUSTOMER's logo, scraped off
vervemotion.com/customer-results/ (the row's own url), which is also where the
homepage's customer strip pulls Wegmans, Star Market, Shaw's and L3Harris from.
None of those are Verve products.

7073 carried `engineer.png` - a Verve engineer standing in a factory aisle in
business-casual clothes, wearing no exosuit at all. The filename says it
outright. It sits on /solutions/ illustrating the line "Engineered by our team
of scientists and athletic apparel designers", i.e. it is about the people, not
the product.

7073 also had NO primary photo set at all, so it had no hero.

A quieter one: `Floor-Ready-V1.png` is a 460x293 web thumbnail of the SafeLift
charging-locker scene. `Frame-180.png` is a different frame of that same scene
at 1920x1080 - 4x the resolution. Swapped.

HOW THE REAL PHOTOS WERE PICKED

SafeLift is visually unmistakable once you know the two markers: the RED
actuator cables running down the back, and the green-lit status pod on the
chest strap. Every image kept below shows at least one. Deliberately excluded:
the five customer logos; `v2_StockImage.jpg` (the filename is the confession);
`Team-bW.jpg` (company group photo); `About-Us-Cover-Image-V1.jpg` (a video
still of the co-founder); `Motion-Based-Insights-V2.png` (a tablet showing the
Verve Logic dashboard - that is the analytics product, not the robot).

DUPLICATE - NOT ACTED ON, FLAGGED FOR MARTTI

Verve Motion sells exactly one robot. Its own /solutions/ page describes a
"3-in-1 SafeLift solution" = the SafeLift exosuit (hardware) + Verve Logic
(cloud analytics) + Verve Care (a support service); only the first is a robot.
So 7073 "SafeLift exosuit" and 7074 "SafeLift exosuits" are the same product,
and 7074's description is about the COMPANY ("Since 2020, Verve Motion has
committed to...") rather than the machine. 7074 is the weaker row and should
probably be rejected as a duplicate of 7073 - but that is a bigger call than
"fix the wrong images", so it is left to Martti and recorded in the row's notes.
Its images are corrected either way so no wrong image is left in the queue.
"""
import sys
import time

from api_client import ResearchApiClient

APPLY = "--apply" in sys.argv
V = "https://vervemotion.com/wp-content/uploads/"
CDN = "https://cdn.robotaigeek.com/robots/original/"

# EVERY url here is on vervemotion.com. That is deliberate: `replace_media=True`
# re-ingests the whole gallery, and the server REFUSES TO RE-INGEST ITS OWN CDN -
# a payload mixing cdn.robotaigeek.com urls with vendor ones comes back
# `error_count: 1` with an empty error string and the media step silently does
# nothing (the robot record still reports `updated_count: 1`, so it looks like it
# worked). All eight urls return HTTP 200 individually; it is a server-side guard,
# not a broken link. Consequence: two photos already on 7073 could not be carried
# across a replace. Both were unattributed - localisation had wiped their source
# urls and neither is on vervemotion.com or its blog - so they are replaced with
# vendor photos of the same subjects, which are traceable and rights-checkable.
PHOTOS_7073 = [
    V + "2022/08/Walking-Box-2x.jpg",                   # HERO 1920x1060 two suited workers
    V + "2022/09/220708_VERVE_KNOTT_L2_293-2.jpg",      # 660x1424 back view, red actuators
    V + "2023/09/verve-human-powered-mobile.png",       # 745x1133 harness detail, lit status pod
    V + "2023/09/clipping-in.png",                      # 460x292 chest buckle + status LEDs
    V + "2024/02/Frame-180.png",                        # 1920x1080 SafeLift charging lockers
    V + "2022/08/220708_VERVE_KNOTT_L4_071-2.jpg",      # 660x1424 side view carrying a box
    V + "2024/02/Frame-177.jpg",                        # 1920x1080 lifting, cables under load
    V + "2023/12/power-and-protect-crop-desktop.jpeg",  # 1920x1080 suited worker, produce aisle
]

# From /customer-results/ - 7074's own source page - so provenance matches the row.
PHOTOS_7074 = [
    V + "2024/01/Customer-Results-Shift-Stories-V1-D.jpg",  # 1920x1080 suited worker on the floor
    V + "2024/01/Customer-Results-Shift-Stories-V1-M.png",  # 950x1424 back view, red actuators
    V + "2024/02/Frame-182.png",                            # 1248x1871 suited worker, pallet jack
]

# Specs are all stated verbatim on /solutions/ and the row was flagged missing_specs.
PATCH_7073 = {
    "features": "\n".join([
        "Offloads 40% of the weight from each lift with custom assistance.",
        "Up to 240 N of lift assistance force.",
        "Suits up in under 30 seconds for full-shift support.",
        "Fits 5'0\" - 6'6\" (XS - XXL) with 8 points of adjustment.",
        "100 Wh battery, rated to last a full shift plus overtime.",
        "Breathable, flexible, lightweight design intended to move with the wearer.",
        "Assistance is customisable per worker and per task.",
        "Designed for distribution centres, including tight aisles and electric pallet jacks.",
        "Deploys with dedicated locker storage, charging stations and support kiosks.",
        "Transmits lift and safety data to the Verve Logic cloud platform, separately from "
        "building networks so no IT integration is required.",
    ]),
    "family_name": "SafeLift",
    "family_key": "verve-motion:safelift",
    "product_url_scope": "exact_variant",
}

NOTE_7073 = (
    "2026-08-23 IMAGE FIX. Removed engineer.png - a Verve ENGINEER standing in a factory aisle in "
    "business-casual clothes, wearing no exosuit; it illustrates the /solutions/ line 'Engineered by "
    "our team of scientists and athletic apparel designers', so it is a photo of staff, not of the "
    "product. Replaced Floor-Ready-V1.png (460x293) with Frame-180.png (1920x1080), a different "
    "frame of the same SafeLift charging-locker scene at 4x the resolution. Set a HERO - the row had "
    "no primary photo at all. The gallery is now rebuilt entirely from vervemotion.com; every photo "
    "shows at least one of the two markers that identify this suit - the RED actuator cables down "
    "the back and the green-lit status pod on the chest strap. Two photos previously held here could "
    "not be carried across, because replacing a gallery re-ingests it and the server refuses to "
    "re-ingest its own CDN; both were unattributed (localisation had wiped their source urls and "
    "neither appears on vervemotion.com or its blog), so vendor photos of the same subjects were "
    "used instead - traceable and rights-checkable, which the originals were not. Also filled "
    "features from /solutions/, which states them verbatim (240 N assistance, 40% offload, 100 Wh, "
    "under 30 s to don, 5'0\"-6'6\" over 8 adjustment points)."
)

NOTE_7074 = (
    "2026-08-23 IMAGE FIX. The ONLY photo on this row, and therefore its hero, was Ahold-V2.png - "
    "the corporate logo of AHOLD DELHAIZE, a CUSTOMER of Verve Motion, scraped from this row's own "
    "source page /customer-results/. The same strip supplies Wegmans, Star Market, Shaw's and "
    "L3Harris logos; none are Verve products. Replaced with three real SafeLift photos from that "
    "same customer-results page. "
    "DUPLICATE - NEEDS A HUMAN DECISION: Verve Motion sells exactly one robot. Its /solutions/ page "
    "describes a '3-in-1 SafeLift solution' = the SafeLift exosuit (hardware) + Verve Logic (cloud "
    "analytics) + Verve Care (a support service), and only the first is a robot. This row is "
    "therefore the same product as robot 7073 'SafeLift exosuit', which is the stronger record. Note "
    "also that this row's description is about the COMPANY ('Since 2020, Verve Motion has committed "
    "to improving the lives of workers...') rather than about the machine. Recommend rejecting this "
    "row as a duplicate of 7073."
)


def show(c):
    for rid in (7073, 7074):
        d = c._get("robots/robots/%d/" % rid)
        ph = d.get("photos") or []
        hero = next((i for i, p in enumerate(ph) if p.get("is_primary")), None)
        print("  %d %-20s %-15s conf=%-6s photos=%d hero=%s" % (
            rid, (d.get("name") or "")[:20], d.get("status"),
            d.get("verification_confidence"), len(ph),
            "#%d" % hero if hero is not None else "NONE"))


def main() -> int:
    c = ResearchApiClient()
    print("BEFORE:")
    show(c)
    if not APPLY:
        print("\nWould apply:")
        print("  7073: photos 5 -> %d (drop engineer.png, swap Floor-Ready->Frame-180, set hero)"
              % len(PHOTOS_7073))
        print("  7073: + features/family/url_scope")
        print("  7074: photos 1 -> %d (drop the Ahold Delhaize customer logo)" % len(PHOTOS_7074))
        print("  7074: + duplicate-of-7073 note")
        print("\nDry run - pass --apply to write.")
        return 0

    for rid, note, extra in ((7073, NOTE_7073, PATCH_7073), (7074, NOTE_7074, {})):
        cur = c._get("robots/robots/%d/" % rid)
        body = dict(extra)
        body["notes"] = ((cur.get("notes") or "").strip() + "\n\n" + note).strip()
        try:
            c._patch("robots/robots/%d/" % rid, body)
            print("  %d patched" % rid)
        except Exception as e:
            print("  %d patch FAILED: %s" % (rid, e))
        time.sleep(0.6)

    for rid, urls in ((7073, PHOTOS_7073), (7074, PHOTOS_7074)):
        cur = c._get("robots/robots/%d/" % rid)
        try:
            out = c.bulk_import_robots(
                [{"id": rid, "name": cur.get("name"), "company_slug": "verve-motion",
                  "image": urls[0], "images": [{"url": u} for u in urls]}],
                update_existing=True, patch_existing=True, replace_media=True,
                skip_company_update=True, created_by_id=1)
            print("  %d media: %s %s" % (
                rid, {k: out.get(k) for k in ("updated_count", "error_count")},
                out.get("errors") or out.get("warnings") or ""))
        except Exception as e:
            print("  %d media FAILED: %s" % (rid, e))
        time.sleep(1)

    time.sleep(3)
    print("\nAFTER:")
    show(c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
