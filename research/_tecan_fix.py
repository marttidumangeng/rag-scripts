"""Tecan (company 1762): reject the D300e, rebuild the Freedom EVO row.

6388 TECAN D300e - REJECTED, NOT A ROBOT
Tecan's own page: it uses "HP's Direct Digital Dispensing technology" to provide
"picoliter to microliter non-contact dispensing of liquids directly into the
assay plate" through disposable Dispensehead cassettes. That is inkjet printing
of liquids. There is no manipulator, no gripper, no locomotion and nothing that
moves an object; its three photos are a closed benchtop box, a dose-response
curve, and two consumable cassettes. Same call as the Eddyfi NDT instruments and
the ADLINK/Orbbec component vendors ([[project_component_vendors]]).

6387 FREEDOM EVO - KEPT, IT REALLY IS A ROBOT
Tecan's own brochure (tecan.com/doc/freedom-evo-brochure-pdf-392956) is explicit:
"Seven types of robotic arm are available: Liquid displacement Liquid handling arm
(LiHa), Air displacement Liquid handling arm (Air LiHa), MultiChannel Arm (MCA)
96, MCA 384, standard or extended Z-axis Robotic Manipulator (RoMa) and Pick and
Place (PnP) arm." And on the RoMa: it "transports microplates and other labware
quickly and efficiently between worktable, peripheral devices and labware
storage". That is real material handling, not just fluid transfer.

BUT THE PRODUCT IS DISCONTINUED, and the row said `released`. The url it points
at is no longer a product page - it is an end-of-sale notice: "Sales of Freedom
EVO products has ended on December 31, 2025", "Orders of new EVO instruments and
related products are not possible anymore, starting from January 1, 2026", with
service and technical support continuing "until June 30, 2033". That end-of-sale
page is also why the row was so thin: its whole description was one line about
installed base and its features were a single marketing sentence.

WHY THE URL IS NOT CHANGED
It stays on lifesciences.tecan.com/freedom-evo-platform. That page is thin, but
it is the manufacturer's own current page for the product and it is the
authoritative source for the discontinuation, which is now a central fact about
the row. The technical claims below are cited to Tecan's own brochure, added as
an information source. Tecan's /doc/ brochure links serve an HTML download stub
rather than the PDF itself, so the brochure is a citation, not the row url.

release_year is deliberately left EMPTY. The page says only "more than 20 years
of trusted service", which is not a date - see [[project_release_year_citation_gate]].

Tags left ALONE despite looking like scraped codes (AR, HC, PL, UT, SP): the
?tags= filter is substring-based, so usage counts cannot confirm they are junk,
and deleting possibly-legitimate tags is not worth the risk. Flagged instead.
"""
import sys
import time

from api_client import ResearchApiClient

APPLY = "--apply" in sys.argv
PAGE = "https://lifesciences.tecan.com/freedom-evo-platform"
BROCHURE = "https://www.tecan.com/doc/freedom-evo-brochure-pdf-392956"

DESCRIPTION = (
    "The Freedom EVO is Tecan's modular laboratory automation platform: a benchtop gantry "
    "workstation that combines pipetting with genuine robotic material handling. Up to three arms "
    "mount on a single worktable, chosen from seven types - liquid-displacement (LiHa) and "
    "air-displacement (Air LiHa) pipetting arms, 96- and 384-channel MultiChannel Arms, a standard "
    "or extended Z-axis Robotic Manipulator (RoMa) that moves microplates and labware between the "
    "worktable, peripheral instruments and storage, and a Pick and Place arm for single tubes. The "
    "extended-range RoMa reaches below the worktable, so plate readers, washers and centrifuges can "
    "be built into the deck. Tecan shipped more than 5,000 systems across three worktable sizes - "
    "Freedom EVO 100, 150 and 200 - over more than twenty years. The series reached end of sale on "
    "31 December 2025, with Tecan hardware and software support continuing until 30 June 2033, and "
    "its lineage continues in the Fluent and Veya platforms."
)

FEATURES = [
    "Seven types of robotic arm available: liquid-displacement LiHa, air-displacement Air LiHa, "
    "MultiChannel Arm 96, MultiChannel Arm 384, standard or extended Z-axis Robotic Manipulator "
    "(RoMa), and Pick and Place (PnP).",
    "Up to three arms on one platform (up to two on the Freedom EVO 100); arms can be added or "
    "exchanged in the field.",
    "Robotic Manipulator (RoMa) arm transports microplates and other labware between the worktable, "
    "peripheral devices and labware storage; up to two RoMa arms for parallel logistics.",
    "Extended-range RoMa reaches below the worktable, allowing plate readers, washers, centrifuges "
    "and extra storage or incubation to be integrated.",
    "Pick and Place (PnP) arm gives fast, precise single-tube manipulation for tube weighing and "
    "compound dissolution.",
    "Two-, four- and eight-channel liquid displacement (LiHa) or four-/eight-channel air "
    "displacement (Air LiHa) pipetting, covering 0.5 to 5,000 ul.",
    "Up to two pipetting arms for 16 flexible channels, or 96-/384-channel parallel pipetting for "
    "whole-plate processing.",
    "Disposable tips from 10 ul to 5,000 ul; variable Y tip spacing for transfers across different "
    "labware.",
    "PosID automatic barcode reading of labware and carriers at any worktable position.",
    "Three worktable sizes: Freedom EVO 100, 150 and 200.",
    "Freedom EVOware control software combining pipetting, robotics and multi-device scheduling.",
    "More than 5,000 systems installed worldwide.",
    "End of sale 31 December 2025; Tecan service and technical support continue until 30 June 2033.",
]

NOTE_6387 = (
    "2026-08-23: kept as a robot and rebuilt. It qualifies on Tecan's own wording - the brochure "
    "(tecan.com/doc/freedom-evo-brochure-pdf-392956) states 'Seven types of robotic arm are "
    "available... standard or extended Z-axis Robotic Manipulator (RoMa) and Pick and Place (PnP) "
    "arm', and describes the RoMa as transporting 'microplates and other labware quickly and "
    "efficiently between worktable, peripheral devices and labware storage'. That is real material "
    "handling, which is what separates this row from its sibling 6388 (the D300e, rejected the same "
    "day as an inkjet dispenser with no manipulator). "
    "STATUS CORRECTED released -> DISCONTINUED: the row's url is no longer a product page but an "
    "end-of-sale notice - 'Sales of Freedom EVO products has ended on December 31, 2025', 'Orders of "
    "new EVO instruments and related products are not possible anymore, starting from January 1, "
    "2026', support 'until June 30, 2033'. China is the stated exception, supplied through 2026. "
    "Affected series: Freedom EVO, EVO NAE, EVOlyzer-2, EVOlyzer-3, EVO Clinical, EVO ELISA. "
    "That end-of-sale page is also why the row was so thin - its entire description was one line "
    "about installed base and features were a single marketing sentence; both rewritten from the "
    "brochure. url deliberately LEFT on the Tecan page: it is thin, but it is the manufacturer's own "
    "current page and the authority for the discontinuation. Tecan's /doc/ links serve an HTML "
    "download stub rather than the PDF, so the brochure is cited as a source, not used as the url. "
    "release_year left empty - the page says only 'more than 20 years of trusted service', which is "
    "not a date. Category 'Industrial-Robot' dropped as wrong for benchtop lab equipment. "
    "NOT TOUCHED: the tags include what look like scraped two-letter codes (AR, HC, PL, UT, SP) "
    "alongside spelled-out equivalents, but the ?tags= filter is substring-based so their usage "
    "counts cannot confirm it - worth a separate look rather than a blind delete."
)

REASON_6388 = (
    "Not a robot - a benchtop liquid-dispensing instrument. Tecan's own product page states it uses "
    "\"HP's Direct Digital Dispensing technology\" providing \"picoliter to microliter non-contact "
    "dispensing of liquids directly into the assay plate\" through disposable Dispensehead "
    "cassettes: this is inkjet printing of liquids. It has no manipulator, no gripper, no "
    "locomotion, and nothing that picks up or moves an object - the dispensing is non-contact by "
    "design. Its three photos are consistent with that: a closed benchtop box, a dose-response "
    "curve chart, and two consumable dispensehead cassettes, with no mechanism visible. Same "
    "judgement as the Eddyfi NDT instruments and the ADLINK/Orbbec component listings. Note this is "
    "a call about THIS product, not about Tecan: the company's Freedom EVO (robot 6387) is retained "
    "because Tecan's own brochure documents its Robotic Manipulator (RoMa) and Pick and Place arms "
    "physically transporting microplates and tubes. Rejected 2026-08-23."
)


def show(c):
    for rid in (6387, 6388):
        d = c._get("robots/robots/%d/" % rid)
        av = (d.get("availability_status") or {})
        print("  %d %-30s %-15s conf=%-6s avail=%-13s photos=%d" % (
            rid, (d.get("name") or "")[:30], d.get("status"), d.get("verification_confidence"),
            av.get("key") if isinstance(av, dict) else av, len(d.get("photos") or [])))


def main() -> int:
    c = ResearchApiClient()
    print("BEFORE:")
    show(c)
    if not APPLY:
        print("\nWould apply:")
        print("  6387: availability -> discontinued, description + %d features, "
              "categories -> research-robots|medical-robots, country CH, brochure source" % len(FEATURES))
        print("  6388: REJECT (not_real, escalate=True)")
        print("\nDry run - pass --apply to write.")
        return 0

    cur = c._get("robots/robots/6387/")
    body = {
        "availability_status_key": "discontinued",
        "description": DESCRIPTION,
        "purpose": ("Automated liquid handling with robotic transport of microplates and labware "
                    "for life-science and diagnostic laboratories."),
        "features": "\n".join(FEATURES),
        "manufacturer_country_code": "CH",
        "family_name": "Freedom EVO",
        "product_url_scope": "family",
        "information_source_urls": [PAGE, BROCHURE],
        "notes": ((cur.get("notes") or "").strip() + "\n\n" + NOTE_6387).strip(),
    }
    try:
        c._patch("robots/robots/6387/", body)
        print("  6387 patched")
    except Exception as e:
        print("  6387 patch FAILED: %s" % e)

    time.sleep(1)
    try:
        out = c.bulk_import_robots(
            [{"id": 6387, "name": cur.get("name"), "company_slug": "tecan",
              "category_slugs": "research-robots|medical-robots",
              "sub_category_slug": "research"}],
            update_existing=True, patch_existing=True,
            skip_company_update=True, created_by_id=1)
        print("  6387 categories:", {k: out.get(k) for k in ("updated_count", "error_count")},
              out.get("warnings") or "")
    except Exception as e:
        print("  6387 categories FAILED: %s" % e)

    time.sleep(1)
    try:
        c.reject_robot(6388, reason=REASON_6388, categories=["not_real"], escalate=True)
        print("  6388 rejected")
    except Exception as e:
        print("  6388 reject FAILED: %s" % e)

    time.sleep(3)
    print("\nAFTER:")
    show(c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
