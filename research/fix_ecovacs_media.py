"""MEDIA-ONLY repair for Ecovacs (company 32) — heroes + galleries.

Text/features/tags/specs on this company are already correct: this script sends
ONLY `image` + `images` and relies on `import_staging(patch=True,
replace_media=True)`, which replaces photos/s3_image and leaves every other
field untouched. It never uses force_overwrite (that would blank the curated
text work) and never touches published/approved records.

Picks are pinned by unique upload-timestamp prefix (e.g. `084932_8962`) rather
than by index, and every pick was visually confirmed on a contact sheet.

Fail-closed set: robots with no genuine, model-specific image get NO image and
instead receive an actionable `[IMAGE TO-DO]` note (see --notes).

    python fix_ecovacs_media.py                      # dry-run plan
    python fix_ecovacs_media.py --sheet              # proposed-hero contact sheet
    python fix_ecovacs_media.py --apply --copy-media
    python fix_ecovacs_media.py --notes --apply      # write imageless notes
    python fix_ecovacs_media.py --notes --apply --only 1939   # single-robot verify
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

_D = Path(__file__).resolve().parent
if str(_D) not in sys.path:
    sys.path.insert(0, str(_D))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from import_staging import import_staging, resolve_created_by_id
from robot_auto_research import slugify_robot_name

COMPANY_ID = 32
SKIP_STATUSES = {"published", "approved"}
CAND = _D / "staging" / "reports" / "ecovacs_candidates.json"

# robot id -> [hero, gallery...] pinned by unique filename substring.
PICKS: dict[int, list[str]] = {
    1937: ["084932_8962", "084945_5462", "084917_1373", "083120_3604", "070454_6842", "064352_1271"],
    1941: ["092317_5553", "092308_3602", "092248_1022", "092301_2298", "092348_9489", "092356_2783"],
    1943: ["074620_5410", "074613_8880", "074643_4439", "074605_9447", "090522_4723", "074632_1759"],
    # Hero is the W2 OMNI robot itself, not the robot+station render: the latter is
    # near-identical (same render, different crop) to WINBOT W2 PRO OMNI's listing
    # image on 1961. Byte-distinct, but two look-alike heroes read as a duplicate.
    1945: ["035411_5258", "035335_6891", "035519_8042", "035543_1126", "035432_3543", "033215_2965"],
    1947: ["084527_5477", "084558_4819", "084650_8785", "084701_1713", "084719_1852", "084807_3853"],
    1951: ["072902_2032", "033437_6632", "072211_5425", "031146_2241", "032212_8480"],
    1954: ["074345_4242", "074432_2784", "074423_1859", "074500_8721", "074453_3298"],
    1955: ["072403_8029", "073454_1298", "073441_7594", "072437_7069", "073415_1740", "072447_4020"],
    1956: ["032330_3077", "032505_2166", "032521_2299", "032351_1574", "032044_8075", "032404_5502"],
    1957: ["064153_5024", "070538_5833", "070555_2805", "070646_2557", "025103_8143", "024917_8324"],
    # Hero is the X2 robot in-frame, not `id-x2-omni-black-920x920.png`: that station
    # render is the same shot ECOVACS also uses for X5 PRO OMNI (1957), so leading with
    # it would give two models a visually identical hero. Kept as a gallery image.
    1958: ["073446_6736", "id-x2-omni-black-920x920", "072805_1994", "073053_7662", "073604_7487"],
    1959: ["091732_3998", "092033_5157", "054845_4512", "054838_4214", "054811_1209"],
    1960: ["114923_2406", "114905_8577", "114857_6495", "081419_2500", "114930_7429", "114917_3094"],
    1961: ["070559_4728", "031241_1282", "034542_5868", "034456_1254", "034549_2594"],
    1962: ["070929_7469", "005743_7538", "005804_4021", "020430_3504", "020210_1281", "020619_3028"],
    1963: ["074853_3756", "153734_1550", "153741_1732", "153758_6568", "153712_3125"],
    1965: ["091323_3487", "133440_5544", "133505_1001", "133406_2448", "133357_2643"],
    2474: ["072113_1292", "072034_1564", "071625_6610", "071701_7963", "080542_8661", "080024_5187"],
    2476: ["DEEBOTT30CWebpage-white-23", "DEEBOTT30CWebpage-white-13", "DEEBOTT30CWebpage-white-19",
           "DEEBOTT30CWebpage-white-04", "DEEBOTT30CWebpage-white-05"],
    2477: ["110641_6135", "110354_7349", "110619_4161", "110913_7683", "110849_3639", "110025_5018"],
    # T90 OMNI = WHITE colourway (the black assets belong to 4716). Sourced /de.
    2478: ["053947_3210", "032603_6985", "054551_3516", "054420_1926", "054249_6656", "053954_3141"],
    2517: ["085859_6650", "085925_7327", "085832_4537", "085724_2281", "090439_6460", "090623_4791"],
    2518: ["DEEBOTT30CWebpage-black-23", "DEEBOTT30CWebpage-black-13", "DEEBOTT30CWebpage-black-19",
           "DEEBOTT30CWebpage-black-04", "DEEBOTT30CWebpage-black-05"],
}

# Fail-closed: no genuine model-specific image exists. Each gets an actionable note.
# `why` = what we checked and what it served instead. `prev` = what we removed.
# `action` = what a human should do.
IMAGELESS: dict[int, dict[str, str]] = {
    1939: {
        "name": "ECOVACS DEEBOT X9 PRO OMNI",
        "why": "The only X9 PRO OMNI PDP ECOVACS publishes is the BLACK colourway "
               "(/global/deebot-robotic-vacuum-cleaner/deebot-x9-pro-omni-black; the generic "
               "/us/shop/deebot-x9-pro-omni serves the same black renders). X9 PRO OMNI appears "
               "to ship in black only, so every real image of this model is byte-identical to "
               "images already on robot 4715 'DEEBOT X9 PRO OMNI BLACK'.",
        "prev": "held a black DEEBOT+station render shared byte-identically across 12 vacuum records "
                "(X5/X9/T50/mini 2/N20/N30/T30C/T80/T90/X11/X12).",
        "action": "This is almost certainly a DUPLICATE RECORD of 4715 (DEEBOT X9 PRO OMNI BLACK) — "
                  "confirm and MERGE rather than sourcing images. If a distinct non-black X9 PRO OMNI "
                  "SKU does exist, source its own render and keep this record.",
    },
    1949: {
        "name": "ECOVACS WINBOT W3",
        "why": "The WINBOT W3 PDP (/global/winbot-window-cleaning-robot/winbot-w3) is titled "
               "'WINBOT W3 OMNI' and its images are byte-identical to images already on robot 4677 "
               "'WINBOT W3 OMNI'. There is no separate non-OMNI W3 product page.",
        "prev": "held a WINBOT render shared with W2 OMNI/W2S, plus a 2560x600 marketing banner.",
        "action": "Likely a DUPLICATE RECORD of 4677 (WINBOT W3 OMNI) — confirm and MERGE. Do not "
                  "re-source images until the identity question is settled.",
    },
    1952: {
        "name": "ECOVACS GOAT A2000",
        "why": "No 'GOAT A2000' SKU exists. ECOVACS publishes only 'GOAT A2000 LiDAR PRO' "
               "(/us/shop/goat-robotic-lawn-mower/goat-a2000-lidar-pro, a CES-2026 product) — a "
               "different model. Every /global, /us, /uk, /au, /de, /ca, /it, /fr slug for a bare "
               "A2000 returns 404, and Wayback has no capture of one.",
        "prev": "held a GOAT mower render shared with A3000 and O800, plus a family marketing banner.",
        "action": "Resolve the identity first: if this row means the A2000 LiDAR PRO, rename it (and "
                  "check it does not duplicate an existing record) — then its own PDP renders can be "
                  "used. If the SKU is bogus, delete the record. Do NOT borrow A3000/O800 imagery.",
    },
    1964: {
        "name": "ECOVACS GOAT G1 Plus",
        "why": "No 'GOAT G1 Plus' SKU exists. The G1 line is GOAT G1 (1600 m2), GOAT G1-800 and "
               "GOAT G1-2000. Every g1-plus slug 404s on every region, and a Wayback prefix scan of "
               "/global/goat-robotic-lawn-mower/ shows only GOAT-G1, goat-g1-2000 and goat-g1-800-grey "
               "— never a g1-plus.",
        "prev": "held a 2560x600 marketing banner used as the hero on 11 records (vacuums, mowers and "
                "the AIRBOT air purifier alike).",
        "action": "Resolve the identity: this is most likely GOAT G1-2000 or GOAT G1-800 under a wrong "
                  "name — rename to the real SKU and source that PDP's renders, or delete if bogus. "
                  "Robot 1963 already holds the genuine GOAT G1, so do not copy its images here.",
    },
    2475: {
        "name": "ECOVACS DEEBOT N30 PLUS",
        "why": "The N30 PLUS PDP (/global/deebot-robotic-vacuum-cleaner/deebot-n30-plus-white, titled "
               "'DEEBOT N30 PLUS WHITE-JP') has correct N30 PLUS body copy but every single one of its "
               "25 images is named for a DIFFERENT model — DEEBOTN20ePlus_White_*.jpg (DEEBOT N20e "
               "Plus). ECOVACS appears to have built the page with N20e Plus assets. Using them would "
               "ship another product's photos.",
        "prev": "held a black DEEBOT+station render shared byte-identically across 12 vacuum records.",
        "action": "Ask ECOVACS for genuine DEEBOT N30 PLUS imagery, or confirm whether N30 PLUS is a "
                  "JP rebadge of the N20e Plus (in which case the N20e assets are legitimate and this "
                  "can be filled). Do NOT ship the N20e Plus renders on the strength of the page alone.",
    },
    2479: {
        "name": "ECOVACS DEEBOT X11 OMNI",
        "why": "No 'DEEBOT X11 OMNI' SKU exists — the X11 line is X11 OmniCyclone and X11 PRO OMNI. "
               "Every deebot-x11-omni slug 404s on /global and /us.",
        "prev": "held a black DEEBOT+station render shared byte-identically across 12 vacuum records.",
        "action": "Almost certainly a DUPLICATE RECORD of 4681 (DEEBOT X11 OmniCyclone) — confirm and "
                  "MERGE, or rename to the real SKU. Do not copy 4681's images onto this record.",
    },
    2480: {
        "name": "ECOVACS DEEBOT X12 OMNI",
        "why": "No 'DEEBOT X12 OMNI' SKU exists — the X12 line is X12 OmniCyclone and X12 PRO OMNI. "
               "Every deebot-x12-omni slug 404s on /global and /us.",
        "prev": "held a black DEEBOT+station render shared byte-identically across 12 vacuum records.",
        "action": "Almost certainly a DUPLICATE RECORD of 4676 (DEEBOT X12 OmniCyclone) — confirm and "
                  "MERGE, or rename to the real SKU. Do not copy 4676's images onto this record.",
    },
    2473: {
        "name": "ECOVACS DEEBOT mini 2",
        "why": "Its only source PDP (/global/deebot-robotic-vacuum-cleaner/deebot-mini-2-white) is the "
               "same page robot 4720 'DEEBOT mini 2' was built from: 6 of its images are byte-identical "
               "to media already on 4720.",
        "prev": "held a black DEEBOT+station render shared byte-identically across 12 vacuum records.",
        "action": "DUPLICATE RECORD of 4720 (DEEBOT mini 2) — confirm and MERGE. 4720 already carries "
                  "the correct mini 2 media.",
    },
}

NOTE_TMPL = (
    "[IMAGE TO-DO — no hero, deliberate]\n"
    "{why}\n"
    "{prev_line}"
    "ACTION FOR TEAM: {action}\n"
    "Do NOT substitute a sibling render, a family banner, or marketing/diagram art.\n"
    "---\n"
)


def build_note(meta: dict[str, str]) -> str:
    prev = meta.get("prev")
    prev_line = f"Previously {prev}\n" if prev else ""
    return NOTE_TMPL.format(why=meta["why"], prev_line=prev_line, action=meta["action"])


def resolve(cands: list[dict], pick: str) -> dict:
    hits = [c for c in cands if pick in c["url"]]
    if len(hits) != 1:
        raise SystemExit(f"PICK '{pick}' matched {len(hits)} candidates (need exactly 1)")
    return hits[0]


def build_media() -> dict[int, list[dict]]:
    data = json.load(open(CAND, encoding="utf-8"))
    out: dict[int, list[dict]] = {}
    seen: dict[str, tuple[int, str]] = {}
    for rid, picks in PICKS.items():
        keep = data[str(rid)]["keep"]
        chosen = [resolve(keep, p) for p in picks]
        for c in chosen:
            if c["md5"] in seen:
                raise SystemExit(f"DUPLICATE bytes: robot {rid} {c['url']} == {seen[c['md5']]}")
            seen[c["md5"]] = (rid, c["url"])
        out[rid] = chosen
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-media", action="store_true")
    ap.add_argument("--notes", action="store_true", help="write [IMAGE TO-DO] notes on imageless robots")
    ap.add_argument("--only", type=str, default="")
    ap.add_argument("--created-by-id", type=int, default=1)
    ap.add_argument("--sheet", action="store_true")
    a = ap.parse_args()

    client = ResearchApiClient()
    live = {r["id"]: r for r in client.list_robots_for_company(COMPANY_ID)}
    only = {int(x) for x in a.only.split(",") if x.strip().isdigit()} if a.only.strip() else None

    if a.notes:
        return do_notes(client, live, only, a.apply)

    media = build_media()
    if a.sheet:
        return do_sheet(media, live)

    rows: dict[int, dict[str, Any]] = {}
    for rid, imgs in sorted(media.items()):
        if only and rid not in only:
            continue
        cur = live.get(rid)
        if cur is None:
            print(f"SKIP {rid}: not under company {COMPANY_ID}", file=sys.stderr)
            continue
        st = (cur.get("status") or "").lower()
        if st in SKIP_STATUSES or st != "pending_review":
            print(f"SKIP {rid} {cur.get('name')}: status={st}", file=sys.stderr)
            continue
        urls = [i["url"] for i in imgs]
        rows[rid] = {"id": rid, "name": cur["name"], "company": "Ecovacs Robotics",
                     "image": urls[0], "images": urls}
        print(f"{rid} {cur['name'][:38]:<38} imgs={len(urls)} hero={urls[0].rsplit('/',1)[-1][:44]}")

    if not a.apply:
        print(f"\nDry-run: {len(rows)} robots. Re-run with --apply --copy-media")
        return 0

    # Call bulk_import_robots directly rather than via import_staging(): the
    # client-side validator in validate_staging.py unconditionally demands
    # description + sources, and map_to_bulk_import would then emit
    # `information_source_urls` — which, combined with replace_media=True, DELETES
    # and recreates the curated RobotInformationSource rows (bulk_import_media.py
    # :200-213). Omitting that key entirely leaves sources untouched, which is what
    # a media-only pass must do. `company_name` is inert under skip_company_update.
    ok_all, done = True, []
    for rid, row in rows.items():
        res = client.bulk_import_robots(
            [row], update_existing=True, patch_existing=True, status="pending_review",
            skip_company_update=True, created_by_id=resolve_created_by_id(a.created_by_id),
            replace_media=True,
        )
        errs = res.get("errors") or []
        if errs or not res.get("updated_count"):
            ok_all = False
            print(f"IMPORT FAIL {rid}: updated={res.get('updated_count')} errors={errs}",
                  file=sys.stderr)
        else:
            done.append(rid)
            print(f"  imported {rid} updated={res.get('updated_count')} errors={len(errs)}")

    if a.copy_media:
        for rid in done:
            r = client.copy_media(rid) if hasattr(client, "copy_media") else _copy(client, rid)
            print(f"  copy-media {rid}: {r}")
    print(f"\n{len(done)}/{len(rows)} imported")
    return 0 if ok_all else 1


def _admin_base() -> tuple[str, str]:
    """(api_base, internal_secret) — same derivation as fix_ae_robots.py."""
    import os
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    env_file = _D.parents[1] / "robotaigeek-server" / ".env"
    if not secret and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                secret = line.split("=", 1)[1].strip()
    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")
    return api, secret


def _copy(client, rid: int):
    import requests
    base, secret = _admin_base()
    url = f"{base}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
    try:
        r = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=180)
        return f"HTTP {r.status_code} {r.text[:120]}"
    except Exception as e:
        return f"ERR {e}"


def do_notes(client, live, only, apply: bool) -> int:
    for rid, meta in sorted(IMAGELESS.items()):
        if only and rid not in only:
            continue
        cur = live.get(rid)
        if cur is None:
            print(f"SKIP {rid}: not found", file=sys.stderr)
            continue
        st = (cur.get("status") or "").lower()
        if st in SKIP_STATUSES:
            print(f"SKIP {rid}: status={st}", file=sys.stderr)
            continue
        existing = (cur.get("notes") or "").strip()
        note = build_note(meta)
        if existing.startswith("[IMAGE TO-DO"):
            print(f"  {rid} already noted — skip")
            continue
        merged = note + existing if existing else note.rstrip() + "\n"
        print(f"--- {rid} {cur['name']}\n{merged}")
        if apply:
            res = client._patch(f"robots/robots/{rid}/", {"notes": merged})
            got = (res.get("notes") or "")[:40].replace("\n", " ")
            print(f"  PATCHED {rid}: notes now starts '{got}...'")
    return 0


def do_sheet(media, live) -> int:
    import _ecovacs_contact_sheet as C
    entry = {"label": "PROPOSED HEROES (company 32)",
             "keep": [{**imgs[0], "named_self": True} for _, imgs in sorted(media.items())]}
    p = C.sheet("PROPOSED", entry, len(entry["keep"]))
    print(f"proposed heroes sheet: {p}")
    for i, (rid, imgs) in enumerate(sorted(media.items())):
        print(f"   [{i}] {rid} {live.get(rid, {}).get('name', '?')[:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
