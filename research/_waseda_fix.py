"""Fix the four DRAFT Waseda rows (company 1979).

Scope note: 8 of the company's 14 rows are PUBLISHED and are deliberately not
touched (see the report — WABOT-1 and WABOT-2 cross-share a photo, and the
WAMOEBA-2R row carries a WAMOEBA-3 video). Only the drafts are edited here.

Common defects on the drafts: no photos at all, `url` pointing at the institute
HOMEPAGE rather than anything about the robot, and no family metadata even though
these robots form obvious lines (Hadaly-1/-2, the WF flutist series).
"""
import sys
import time

from api_client import ResearchApiClient

APPLY = "--apply" in sys.argv
WF3 = "http://www.takanishi.mech.waseda.ac.jp/top/research/music/flute/wf_3/"

FIX = {
    7078: {  # Humanoid Flute Robot WF3-RVIII
        "url": WF3 + "index.htm",
        "product_url_scope": "family",
        "family_name": "Waseda Flutist (WF)",
        "family_key": "waseda:wf-flutist",
        "variant_label": "WF-3 series, Refined VIII",
        "release_year": 1990,
        # Series-level images only. The page's WF3_R9_Front.jpg and
        # WF3_R9_with_Mr.Wakamatsu.jpg are the RIX generation — one refinement
        # LATER than this row's RVIII — so they are deliberately excluded.
        "images": [WF3 + "img/history2001.jpg",   # lineage strip of past WF robots
                   WF3 + "img/lip_part.jpg",      # labelled lip mechanism
                   WF3 + "img/lung1.jpg"],        # artificial lung hardware
        "note": ("2026-08-23: url moved off the institute HOMEPAGE "
                 "(humanoid.waseda.ac.jp/index.html, which it shared with row 7075 iSHA — hence "
                 "shared_url) to the Takanishi Lab WF-3 series page, which names WF-3RVIII in its "
                 "text. Photos added from that page, series-level only: the lineage strip of past WF "
                 "robots plus the lip and lung mechanisms. The page's front portraits are of WF3-RIX, "
                 "one refinement LATER than this model, and were deliberately not used. "
                 "release_year=1990 cited to the same page: 'The development of this robot was "
                 "started in 1990.'"),
    },
    7088: {  # Hadaly-1
        "url": "https://www.humanoid.waseda.ac.jp/booklet/booklet2000.html",
        "product_url_scope": "category",
        "family_name": "Hadaly",
        "family_key": "waseda:hadaly",
        "variant_label": "Hadaly-1",
        "release_year": 1995,
        "description": (
            "The navigation robot of Waseda University's Humanoid Project, built in 1995 as the first "
            "Hadaly and the starting point for the human-cooperative Hadaly-2 that followed in 1997. "
            "It sits in the institute's own timeline between the WABOT programme of the 1970s-80s and "
            "the WABIAN biped line, marking the shift from standalone anthropomorphic machines toward "
            "robots meant to move through and share space with people."),
        "features": "\n".join([
            "Navigation robot of the Waseda Humanoid Project.",
            "Built in 1995; the first of the Hadaly line.",
            "Direct predecessor of Hadaly-2 (1997), the human-cooperative robot.",
        ]),
        "note": ("2026-08-23: release_year=1995 cited to the institute's own Humanoid History "
                 "timeline on booklet2000.html — '1992 Humanoid Project / 1995 Hadaly-1 Navigation "
                 "robot / 1997 Hadaly-2 Human cooperative robot'. Description and features expanded "
                 "from the same source; the row previously read only 'Hadaly-1 is a navigation robot "
                 "developed by Waseda University in 1995 as part of the Humanoid Project.' with a "
                 "single feature line 'Navigation capabilities'. Family set so it groups with "
                 "Hadaly-2 (robot 7082). No photograph of Hadaly-1 is published on the institute "
                 "site, so the row stays image-less rather than borrow a Hadaly-2 picture."),
    },
    7075: {  # iSHA
        "product_url_scope": "category",
        "family_name": "Hadaly",
        "family_key": "waseda:hadaly",
        "note": ("2026-08-23: left on the institute homepage because no page specific to iSHA is "
                 "published — that is what scores url_content_mismatch (conf 55) and shared_url "
                 "(shared with row 7078). product_url_scope corrected to 'category' so the URL no "
                 "longer claims to be this robot's own page. Grouped with the Hadaly line: iSHA is "
                 "the institute's human-collaborative robot, the same research thread as Hadaly-2."),
    },
    7076: {  # Robisuke
        "product_url_scope": "category",
        "family_name": "Robisuke",
        "family_key": "waseda:robisuke",
        "note": ("2026-08-23: url is the institute's Japanese homepage (index-j.html); no page "
                 "specific to Robisuke is published — the Perceptual Computing Lab booklet page "
                 "covers the earlier ROBITA instead. product_url_scope corrected to 'category'. Its "
                 "one video is a third-party archive clip (Plastic Pals) that does name the robot."),
    },
}


def main() -> int:
    c = ResearchApiClient()
    for rid, spec in sorted(FIX.items()):
        cur = c._get(f"robots/robots/{rid}/")
        if cur.get("status") in ("approved", "published"):
            print(f"{rid}: PUBLISHED — refusing (drafts only)")
            continue
        print(f"{rid} {cur.get('name')} ({cur.get('status')}) photos={len(cur.get('photos') or [])}")
        if not APPLY:
            print(f"     would set: {sorted(k for k in spec if k not in ('note', 'images'))}"
                  f"{'  +%d photos' % len(spec['images']) if 'images' in spec else ''}")
            continue

        body = {k: v for k, v in spec.items() if k not in ("note", "images")}
        body["notes"] = ((cur.get("notes") or "").strip() + "\n\n" + spec["note"]).strip()
        c._patch(f"robots/robots/{rid}/", body)
        print("     patched")

        if "images" in spec:
            time.sleep(1)
            out = c.bulk_import_robots(
                [{"id": rid, "name": cur.get("name"), "company_slug": "waseda-university",
                  "image": spec["images"][0],
                  "images": [{"url": u} for u in spec["images"]]}],
                update_existing=True, patch_existing=True, replace_media=True,
                skip_company_update=True, created_by_id=1)
            print("     media:", {k: out.get(k) for k in ("updated_count", "error_count")})
        time.sleep(1)

    if not APPLY:
        print("\nDry run — pass --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
