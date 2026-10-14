"""Fix Kivnon (company 1643): wrong images + Spanish text on all four rows.

ROOT CAUSE OF THE SPANISH TEXT
kivnon.com serves Spanish at the bare slug - `<html lang="es">` - and English at
`/en-uk/<slug>/`. All four rows were pointed at the bare slug, so description and
features were harvested in Spanish while `source_locale` still said "en". Every
row's features also opened with "Ir al contenido", which is simply the page's
"Skip to content" accessibility link. Fix: repoint each row at its `/en-uk/`
page and rewrite description + features from Kivnon's own English copy.

THE K32 IMAGE
K32 had exactly one photo, and it was its hero: a 1667x1667 square
"COMMITTED ecovadis Sustainability Rating JAN 2026" badge - a CSR certification
graphic, not a robot. Its real filename is
GREEN-ROBOTICS-AI-SOLUTIONS-SL_EV_Recognition.png (Green Robotics & AI Solutions
is Kivnon's legal entity) and it sits in the FOOTER of every page on the site.
The same badge had also attached itself to Gecko and K10. So K32 had no picture
of the robot at all.

Two other wrong images: an 800x450 render of the WHOLE Kivnon product line was
serving on both K10 and K11 as a stand-in for each specific model.

CAVEAT ON THE "SHARED = CHROME" RULE
Counting how many pages an image appears on usually separates chrome from
product shots (see [[project_kewei_queue_fix]]), but here it MISFIRES: Kivnon
puts a carousel of its whole range at the foot of every model page, so
k32-tractor-by-kivnon-ultra-.webp is "on 4 pages" yet is a genuine K32 photo.
On this site the FILENAME PREFIX is the reliable signal, not the page count.

EXCLUDED: files literally named ChatGPT-Image-21-may-2026-11_14_10.png and
ChatGPT-Image-26-jun-2026-11_29_53.png. Kivnon uses AI-generated marketing art
and these two announce it in the filename; they are not photographs of a robot.

A SPEC THAT IS WRONG ON THE VENDOR'S OWN SITE
The K32 page lists dimensions "1492 x 460 x 332 mm" - character for character
the same as the K10's, on a page whose own photos show an upright-column tugger
while the K10 is described as "ultra-low profile". One of them is copy-pasted.
K32 dimensions are therefore NOT stored; K10's are (332 mm matches its own
"ultra-low profile" claim) and K11's are distinct (2010 x 500 x 333) and kept.

`Robot.speed` is in km/h, so m/s figures are converted (3 -> 10.8, 1 -> 3.6,
0.7 -> 2.52).
"""
import sys
import time

from api_client import ResearchApiClient

APPLY = "--apply" in sys.argv
U = "https://www.kivnon.com/wp-content/uploads/"
EN = "https://www.kivnon.com/en-uk/"

FIX = {
    5797: {
        "slug": "kivnon-gecko",
        "photos": [U + "2026/02/Kivnon-Gecko.webp",
                   U + "2026/02/Hero-produto-kivnon.webp"],
        "description": (
            "The Kivnon Gecko is a case-handling shuttle that installs directly into existing "
            "standard shelving, with no floor tracks, structural reinforcement or other "
            "construction work. It moves at 3 m/s both horizontally and vertically, carries a rated "
            "load of 30 kg, and is available with 6, 9 or 12 metre masts. Power comes from a "
            "conductor rail rather than a swappable battery, so it runs continuously instead of "
            "stopping to recharge, and it connects natively to docking stations, conveyors, AGVs "
            "and AMRs. Safety is certified to EC regulations and TUV Rheinland functional-safety "
            "standards, implemented at Performance Level d."),
        "purpose": "Automated box and tote handling inside existing warehouse shelving.",
        "features": [
            "Non-invasive installation: works on standard shelving without floor tracks or special "
            "reinforcement.",
            "Rated load 30 kg.",
            "Speed 3 m/s in both horizontal and vertical motion.",
            "Available with 6-metre, 9-metre and 12-metre masts.",
            "Handles original cardboard boxes and plastic totes.",
            "Conductor-rail power supply gives continuous feeding, eliminating stops to recharge.",
            "Native connectivity with docking stations, conveyors, AGVs and AMRs.",
            "EC regulations and TUV Rheinland functional-safety certification.",
            "Performance Level d (PLd) safety systems for high-density environments.",
            "Multi-zone detection with standalone safety sensors and controlled access zones.",
            "Goods-to-person delivery, optimised for ergonomic operator picking.",
            "Suspended-rail system with low setup cost and easy maintenance.",
            "Kivnon Smart Controller: proprietary embedded industrial control, integrating the WMS "
            "with the company's ERP.",
            "IoT and Big Data integration for predictive service and real-time monitoring of masts, "
            "beams and rails.",
        ],
        "specs": {"payload_kg": 30.0, "speed": 10.8},
    },
    5799: {
        "slug": "k10-model",
        "photos": [U + "2026/02/k10-hero-one-way-scaled-1.webp",
                   U + "2026/02/k10-one-way-scaled-1.webp",
                   U + "2026/02/k10-model-kivnon-scaled.webp",
                   U + "2026/02/k10-one-way-sensor-scaled-1.webp",
                   U + "2026/02/mobile-10-scaled.webp"],
        "description": (
            "The Kivnon K10 is a one-way tow tractor AGV for heavy assembly-line logistics, rated "
            "to pull up to 5,000 kg. Its ultra-low 332 mm profile lets it drive underneath carts "
            "and work where taller vehicles cannot, freeing up aisle space, and magnetic guidance "
            "gives it repeatable stopping accuracy for handovers to operators and line robots. It "
            "couples to carts and logistics trains with a retractable pin, runs on an inline "
            "lithium battery trickle-charged through an onboard connector, and travels at up to "
            "1 m/s. Kivnon has been building the model for over 16 years."),
        "purpose": "Automated towing of heavy carts and logistics trains on industrial assembly lines.",
        "features": [
            "Towing capacity up to 5,000 kg.",
            "Ultra-low profile, 1,492 x 460 x 332 mm, allowing it to operate underneath carts.",
            "Maximum speed 1 m/s.",
            "Magnetic guidance for high stability and precise, repeatable stops.",
            "Retractable pin (PIN) coupling for carts and logistics trains.",
            "Inline lithium battery with trickle charging via an onboard charging connector.",
            "Safety system of 1 safety PLC, 1 safety scanner and 2 emergency stop buttons.",
            "Compatible with fleet management systems.",
            "Tow-tractor transport mode; it is a trailer model, not a direct-load model.",
            "In production for over 16 years.",
        ],
        "specs": {"length_mm": 1492.0, "width_mm": 460.0, "height_mm": 332.0, "speed": 3.6},
    },
    5800: {
        "slug": "k11-model",
        "photos": [U + "2026/02/k11-two-way-02-kivnon-atualizada-scaled-1.webp",
                   U + "2026/02/comprimidak_11-twoway-scaled-1.webp",
                   U + "2026/02/k11-model-kivnon-scaled.webp",
                   U + "2026/02/k11-mobile-scaled.webp"],
        "description": (
            "The Kivnon K11 is a bidirectional heavy-duty towing AMR that pulls up to 5,000 kg on a "
            "wheeled cart. Unlike one-way tuggers it reverses without needing a wide turning "
            "radius, so it works in narrow aisles and along long routes in both directions. It "
            "navigates either by magnetic guidance or by autonomous SLAM, which removes the need to "
            "lay magnetic tape, and it speaks VDA 5050 so a fleet integrates with existing "
            "management systems. At 2,010 x 500 x 333 mm it travels at up to 1 m/s and couples "
            "through a retractable pin."),
        "purpose": ("Automated bidirectional transport of heavy loads over long distances in "
                    "industrial intralogistics."),
        "features": [
            "Towing capacity up to 5,000 kg on a wheeled cart.",
            "Two-way movement: reverses without a wide turning radius, suiting narrow aisles.",
            "Magnetic guidance or autonomous SLAM navigation; SLAM removes the need for magnetic "
            "tape and plans routes around obstacles in real time.",
            "VDA 5050 protocol for integration with existing fleet management systems.",
            "Dimensions 2,010 x 500 x 333 mm.",
            "Maximum speed 1 m/s.",
            "Retractable pin (PIN) coupling.",
            "Inline lithium battery with trickle charging via an onboard charging connector.",
            "Safety: 1 laser scanner, 2 safety PLCs, 2 emergency stop buttons, front and rear "
            "displays, and status, error, battery and circuit monitoring.",
            "Intended for long-distance transport of large loads requiring bidirectional movement.",
        ],
        "specs": {"length_mm": 2010.0, "width_mm": 500.0, "height_mm": 333.0, "speed": 3.6},
    },
    5801: {
        "slug": "k32_model",
        "photos": [U + "2026/02/k32-tractor-by-kivnon-ultra-.webp",
                   U + "2026/02/kivnon-k32_-scaled-1.webp",
                   U + "2026/02/k32-kivnon-1-scaled.webp",
                   U + "2026/02/k32-kivnonm-_02-sensor-scaled-1.webp",
                   U + "2026/06/K32.png"],
        "description": (
            "The Kivnon K32 Tugger is a unidirectional tow tractor for intralogistics, rated to "
            "pull logistics trains of up to 2,000 kg between the warehouse and the production "
            "line. It navigates by magnetic guidance or by autonomous SLAM, so it can be deployed "
            "without laying physical infrastructure and can change route dynamically as demand "
            "shifts. Front and rear scanners stop the vehicle at any obstacle, and it couples to "
            "carts through a retractable pin or a rear manual coupling. It runs on a lithium "
            "battery trickle-charged through an onboard connector and travels at up to 0.7 m/s."),
        "purpose": "Automated towing of heavy carts and logistics trains in intralogistics operations.",
        "features": [
            "Towing capacity 2,000 kg, for logistics trains.",
            "Magnetic or autonomous SLAM navigation, deployable without physical infrastructure and "
            "able to change routes dynamically with plant demand.",
            "Dual-scanner safety system, front and rear, stopping the vehicle at any obstacle.",
            "Unidirectional travel.",
            "Maximum speed 0.7 m/s.",
            "Retractable pin (PIN) coupling or rear manual coupling.",
            "Lithium battery with trickle charging and an onboard charging connector.",
            "Fleet management connectivity over the VDA 5050 protocol.",
            "Precise stops with absolute accuracy.",
            "Intended for repetitive towing of heavy carts and kits, replacing manual hand trucks.",
        ],
        "specs": {"speed": 2.52},
    },
}

NOTE_COMMON = (
    "2026-08-23: url repointed from the SPANISH page (kivnon.com serves Spanish at the bare slug, "
    "<html lang=\"es\">) to the English one at /en-uk/. That mismatch is why description and "
    "features were in Spanish while source_locale said 'en', and why features opened with 'Ir al "
    "contenido' - the page's 'Skip to content' link. Both rewritten from Kivnon's own English copy, "
    "and the technical specification table on that page added."
)
NOTE_BADGE = (
    " IMAGE FIX: removed a 1667x1667 'COMMITTED ecovadis Sustainability Rating JAN 2026' badge - a "
    "CSR certification graphic, not a robot. Its real filename is "
    "GREEN-ROBOTICS-AI-SOLUTIONS-SL_EV_Recognition.png (Green Robotics & AI Solutions is Kivnon's "
    "legal entity) and it sits in the FOOTER of every page on the site, which is how it reached "
    "three separate robots."
)
NOTE_LINEUP = (
    " IMAGE FIX: removed an 800x450 render of Kivnon's WHOLE product line, which was standing in for "
    "this specific model on both K10 and K11."
)
NOTES = {
    5797: NOTE_COMMON + NOTE_BADGE + (
        " Only two Gecko photos are published on the site, so the gallery is small by necessity. "
        "Note that Kivnon's own English page leaves one sentence untranslated - 'eliminando paradas "
        "por carga de batería' - which is rendered here as 'eliminating stops to recharge'."),
    5799: NOTE_COMMON + NOTE_BADGE + NOTE_LINEUP,
    5800: NOTE_COMMON + NOTE_LINEUP,
    5801: NOTE_COMMON + NOTE_BADGE + (
        " This row's ONLY photo was that badge, so it had no picture of the robot at all; five real "
        "K32 photos added. SPEC WARNING: the K32 page lists dimensions '1492 x 460 x 332 mm', "
        "character for character the K10's figures, on a page whose photos show an upright-column "
        "tugger while the K10 is described as 'ultra-low profile'. One of the two is copy-pasted, so "
        "K32 dimensions are deliberately NOT stored. Towing capacity and speed are model-specific "
        "and are stored. Excluded two files named ChatGPT-Image-*.png: Kivnon uses AI-generated "
        "marketing art and those two say so in the filename."),
}


def show(c):
    for rid in sorted(FIX):
        d = c._get("robots/robots/%d/" % rid)
        ph = d.get("photos") or []
        hero = next((i for i, p in enumerate(ph) if p.get("is_primary")), None)
        desc = (d.get("description") or "")[:44]
        print("  %d %-18s conf=%-6s photos=%d hero=%-4s | %s" % (
            rid, (d.get("name") or "")[:18], d.get("verification_confidence"), len(ph),
            ("#%d" % hero) if hero is not None else "NONE", desc))


def main() -> int:
    c = ResearchApiClient()
    print("BEFORE:")
    show(c)
    if not APPLY:
        print("\nWould apply:")
        for rid, s in sorted(FIX.items()):
            print("  %d -> %s  photos=%d  specs=%s" % (
                rid, EN + s["slug"] + "/", len(s["photos"]), sorted(s["specs"])))
        print("\nDry run - pass --apply to write.")
        return 0

    for rid, s in sorted(FIX.items()):
        cur = c._get("robots/robots/%d/" % rid)
        url = EN + s["slug"] + "/"
        body = dict(s["specs"])
        body.update({
            "url": url,
            "product_url_scope": "exact_variant",
            "source_locale": "en",
            "description": s["description"],
            "purpose": s["purpose"],
            "features": "\n".join(s["features"]),
            "information_source_urls": [url],
            "notes": ((cur.get("notes") or "").strip() + "\n\n" + NOTES[rid]).strip(),
        })
        try:
            c._patch("robots/robots/%d/" % rid, body)
            print("  %d patched" % rid)
        except Exception as e:
            print("  %d patch FAILED: %s" % (rid, e))
        time.sleep(0.6)

    for rid, s in sorted(FIX.items()):
        cur = c._get("robots/robots/%d/" % rid)
        try:
            out = c.bulk_import_robots(
                [{"id": rid, "name": cur.get("name"), "company_slug": "kivnon",
                  "image": s["photos"][0],
                  "images": [{"url": u} for u in s["photos"]]}],
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
