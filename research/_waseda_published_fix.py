"""Fix the PUBLISHED Waseda rows (company 1979) plus the image-less To Review rows.

Martti explicitly asked for the live rows this time, so the usual
"drafts and To Review only" rule is set aside for this run.

ATTRIBUTION EVIDENCE. Every original source URL was lost when the photos were
localised to the CDN, so attribution was rebuilt by hashing every image on
humanoid.waseda.ac.jp and matching md5s back to filenames and their captions:

  d9a38fe2d7 = booklet/photo/WABOT-1-1973s.jpg  captioned "WABOT-1"
  d4cabdd810 = booklet/photo/WABOT-2-1984s.jpg  captioned "WABOT-2 (1984)"
  4c6d2310d2 = booklet/photo/wabots.jpg         PLURAL - the kato_2 page-header
                                                montage of the whole project
  e7aa2f29ec = image/wabot-mini.jpg             the history.html masthead

The two defects that came out of that:
  * the wabots.jpg montage sat on WABOT-1 even though its content is dominated
    by WABOT-2 (hands on an organ keyboard, the seated player);
  * wabot-mini.jpg - a generic history-page masthead, not a WABOT-2 photo at
    all - was serving as WABOT-2's HERO, pushing its own labelled photo second.

A third defect, invisible until the filenames were recovered: every one of
these rows carries the site's 150 px THUMBNAIL. Dropping the "s" suffix yields
the full-size original of each, 3-4x larger (WABOT-1 450x677 at 361 KB against
150x226 at 49 KB). All photo sets below use the full-size files.

Subsystem photos are added only where Waseda's own text assigns them:
  kato_2: "WABOT-1 consisted of the WAM-4 (as its artificial hands) and the
           WL-5 (Its artificial legs)."
  kato_1: WAM-7 (1983) and WAM-8/WAM-7R/WAM-8L (1984) sit under the heading
           "Keyboard Playing Robot (1981~1989)" - i.e. WABOT-2's hands.
"""
import sys
import time

from api_client import ResearchApiClient

APPLY = "--apply" in sys.argv
P = "https://www.humanoid.waseda.ac.jp/booklet/photo/"

PHOTOS = {
    7080: [P + "WABOT-1-1973.jpg",      # hero - captioned "WABOT-1"
           P + "WAM-4_1972.jpg",        # its artificial hands, per kato_2
           P + "WL-5-1971.jpg"],        # its artificial legs, per kato_2
    7081: [P + "WABOT-2-1984.jpg",      # hero - captioned "WABOT-2 (1984)"
           P + "WAM-8-7R-8L_1984.jpg",  # keyboard-playing hands, 1984
           P + "WAM-7_1983.jpg",        # keyboard-playing hands, 1983
           P + "wabots.jpg"],           # project montage - organ-playing content
    7076: ["http://www.pcl.cs.waseda.ac.jp/wp-content/uploads/2015/07/image-robisuke.jpg"],
}

NOTES = {
    7080: ("2026-08-23 PUBLISHED-ROW FIX. Removed booklet/photo/wabots.jpg (md5 4c6d2310d2) - a "
           "PLURAL-named page-header montage of the whole WABOT project whose content is dominated "
           "by WABOT-2 (hands on an organ keyboard, the seated player). It stays on 7081 where it "
           "belongs. Replaced the remaining 150 px thumbnail with the full-size original "
           "(WABOT-1-1973.jpg, 450x677, vs 150x226) and added the two subsystems Waseda's own text "
           "assigns to this robot: 'WABOT-1 consisted of the WAM-4 (as its artificial hands) and the "
           "WL-5 (Its artificial legs)' (booklet/kato_2.html)."),
    7081: ("2026-08-23 PUBLISHED-ROW FIX. The HERO was image/wabot-mini.jpg (md5 e7aa2f29ec) - the "
           "masthead of history.html, a generic institute image and not a photograph of WABOT-2 - "
           "which pushed this robot's own labelled photo into second place. Removed; "
           "WABOT-2-1984.jpg is now the hero, at full size (450x626, replacing the 150x209 "
           "thumbnail). Added WAM-8/WAM-7R/WAM-8L (1984) and WAM-7 (1983), which booklet/kato_1.html "
           "files under the heading 'Keyboard Playing Robot (1981~1989)' - this robot's hands. Kept "
           "the wabots.jpg project montage here."),
    7076: ("2026-08-23: photo added. ROBISUKE is not pictured anywhere on the institute site; the "
           "robot is documented by its own lab, Prof. Kobayashi's Perceptual Computing Laboratory at "
           "pcl.cs.waseda.ac.jp, whose projects page covers SCHEMA / ROBISUKE / ROBITA. The image "
           "used is that site's image-robisuke.jpg, and the identification is not just the filename: "
           "the robot has ROBISUKE painted on the blue torso box. Two neighbouring images were "
           "rejected - schema_square.jpg is SCHEMA (the white/red round head, a different robot) and "
           "robot.png is a three-up strip mixing several of the lab's robots."),
    7075: ("2026-08-23 IMAGE SEARCH - NEGATIVE RESULT, recorded so nobody repeats it. iSHA has no "
           "published photograph. It appears exactly once on the whole institute site, in one "
           "sentence of index.html listing the four robots exhibited at ROBODEX 2002: 'WAMOEBA - "
           "2Ri, Anthropomorphic Flutist Robot WF3-RVIII, Human-like Head Robot WE-3RV, Human "
           "Collaborative Robot iSHA'. Checked: the whole humanoid.waseda.ac.jp crawl (40 pages), "
           "the booklet2000 lab chapters, and Wayback captures of index.html for 2002-06, 2002-12 "
           "and 2003-04 - the ROBODEX sentence is there in each, always without a picture. The row "
           "stays image-less rather than borrow another robot's photo."),
    7088: ("2026-08-23 IMAGE SEARCH - NEGATIVE RESULT. Hadaly-1 (1995) has no published photograph. "
           "The institute site pictures only the later Hadaly-2, and the one archived candidate, "
           "photo/hadaly4.gif, is from the 2001-2002 homepage where it sits beside wabian3.gif as "
           "the then-current pair - i.e. Hadaly-2, not this robot. It is also a different image from "
           "the one already on row 7082. Not borrowed. The row stays image-less."),
    7078: ("2026-08-23 CORRECTION to the earlier note on this row, which suggested rebadging it as "
           "the WF-3 series or as WF3-RIX. Do NOT do that. index.html names this exact designation "
           "as one of the four robots Waseda exhibited at ROBODEX 2002 - 'Anthropomorphic Flutist "
           "Robot WF3-RVIII' - so the model is real and is the institute's own wording. What is "
           "missing is only a dedicated page and a photograph of it; the Takanishi lab page "
           "documents the neighbouring RVII and RIX generations but skips this one."),
}

# 7085 WAMOEBA-2R - drop the WAMOEBA-3 clip, a later and different robot.
VIDEOS_7085 = [{"url": "https://www.youtube.com/watch?v=N2R5ix23OTo", "title": "WAMOEBA-2"}]
NOTE_7085 = ("2026-08-23 PUBLISHED-ROW FIX: removed the video titled 'WAMOEBA-3' "
             "(youtube BsRqwrjDPZo) - WAMOEBA-3 is a later and different robot from this row's "
             "WAMOEBA-2R. The remaining clip, 'WAMOEBA-2', is the right generation.")

# 7083 WABIAN - its three clips are all WABIAN-2 / WABIAN-2RIII while the row text
# is specific to WABIAN-RIII (1997). The row NAME is the line, so the honest fix is
# to make the row explicitly the line's RIII entry and say the line continued -
# not to delete three genuine Waseda videos.
PATCH_7083 = {
    "family_name": "WABIAN",
    "family_key": "waseda:wabian",
    "variant_label": "WABIAN-RIII",
}
NOTE_7083 = ("2026-08-23 PUBLISHED-ROW FIX: all three videos on this row are of WABIAN-2 / "
             "WABIAN-2RIII, a LATER generation than the WABIAN-RIII the row text describes. They "
             "are genuine Waseda footage of the same line, so rather than delete them the row is "
             "now explicitly family 'WABIAN', variant 'WABIAN-RIII', which puts the later-generation "
             "clips in scope. If the line is ever split into per-generation rows, these videos move "
             "to the WABIAN-2 row.")


def show(c, ids):
    for rid in ids:
        d = c._get("robots/robots/%d/" % rid)
        print("  %d %-28s %-13s conf=%s photos=%d videos=%d" % (
            rid, (d.get("name") or "")[:28], d.get("status"),
            d.get("verification_confidence"),
            len(d.get("photos") or []), len(d.get("videos") or [])))


def main() -> int:
    c = ResearchApiClient()
    ids = [7080, 7081, 7083, 7085, 7075, 7076, 7078, 7088]
    print("BEFORE:")
    show(c, ids)
    if not APPLY:
        print("\nWould apply:")
        for rid, ph in sorted(PHOTOS.items()):
            print("  %d: replace photos -> %d" % (rid, len(ph)))
        print("  7085: videos -> %d (drop WAMOEBA-3)" % len(VIDEOS_7085))
        print("  7083: %s" % PATCH_7083)
        print("  notes on %s" % sorted(NOTES))
        print("\nDry run - pass --apply to write.")
        return 0

    for rid, note in sorted(NOTES.items()):
        cur = c._get("robots/robots/%d/" % rid)
        body = {"notes": ((cur.get("notes") or "").strip() + "\n\n" + note).strip()}
        try:
            c._patch("robots/robots/%d/" % rid, body)
            print("  %d note ok" % rid)
        except Exception as e:
            print("  %d note FAILED: %s" % (rid, e))
        time.sleep(0.5)

    for rid, note, extra in ((7085, NOTE_7085, {"video_urls": VIDEOS_7085}),
                             (7083, NOTE_7083, PATCH_7083)):
        cur = c._get("robots/robots/%d/" % rid)
        body = dict(extra)
        body["notes"] = ((cur.get("notes") or "").strip() + "\n\n" + note).strip()
        try:
            c._patch("robots/robots/%d/" % rid, body)
            print("  %d patched ok" % rid)
        except Exception as e:
            print("  %d patch FAILED: %s" % (rid, e))
        time.sleep(0.5)

    for rid, urls in sorted(PHOTOS.items()):
        cur = c._get("robots/robots/%d/" % rid)
        try:
            out = c.bulk_import_robots(
                [{"id": rid, "name": cur.get("name"), "company_slug": "waseda-university",
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
    show(c, ids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
