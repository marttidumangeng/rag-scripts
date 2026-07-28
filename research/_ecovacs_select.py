"""Select per-model Ecovacs media candidates + build contact sheets for visual QA.

The hard problem here is CROSS-MODEL CONTAMINATION: every ECOVACS PDP embeds
"you may also like" sibling renders and accessory shots. Observed for real:
  * `id-t50-pro-omni-black-920x920.png` sits on the GOAT G1 *lawn mower* page
  * `id-x9-pro-omni-black-920x920.png` sits on the X5 PRO OMNI page
  * cleaning-solution / dust-bag / blade-kit accessory shots on 10 pages
So "biggest image on the page" or "the id-*-920x920 listing image" are both
wrong. A candidate is only kept when the filename does NOT name a *different*
model, and its bytes are unique to this page.

  python _ecovacs_select.py                 # write candidate JSON + contact sheets
"""
from __future__ import annotations
import io, json, re, sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

_D = Path(__file__).resolve().parent
sys.path.insert(0, str(_D))

RECON = _D / "staging" / "reports" / "ecovacs_media_recon.json"
CACHE = _D / "staging" / "ecovacs_media_cache"
SHEETS = Path(r"C:\Users\tramk\AppData\Local\Temp\claude"
              r"\C--Github-Personal-robot-ai-geek"
              r"\83aaaf47-7682-4c7f-b152-0f961f4e2b97\scratchpad\ecovacs_sheets")
SHEETS.mkdir(parents=True, exist_ok=True)
OUT = _D / "staging" / "reports" / "ecovacs_candidates.json"

# Global model vocabulary. Longest-first so X5PRO wins over X5.
# Each entry: canonical token -> regex fragment matched against the NORMALISED
# filename (alnum-uppercased, separators stripped).
VOCAB = [
    "T50MAXPROOMNI", "T50MAXPRO", "T50MAXOMNI", "T50PROOMNI", "T50SOMNI", "T50MAX",
    "T50PRO", "T50OMNI", "T50",
    "X11OMNICYCLONE", "X11PROOMNI", "X11",
    "X12OMNICYCLONE", "X12PROOMNI", "X12",
    "X8MAXPROOMNI", "X8PROOMNI", "X8OMNI", "X8",
    "X9PROOMNI", "X9",
    "X5PROOMNI", "X5OMNI", "X5HYBRID", "X5",
    "X2OMNI", "X2",
    "X1OMNI", "X1PLUS", "X1",
    "T80SOMNI", "T80OMNI", "T80",
    "T90PROOMNI", "T90OMNI", "T90",
    "T30PROOMNI", "T30OMNI", "T30SAI", "T30CPRO", "T30C", "T30E", "T30",
    "T20OMNI", "T20",
    "T10PLUS", "T10TURBO", "T10", "T9PLUS", "T9AIVI", "T9",
    "N20MAXPLUS", "N20PROPLUS", "N20PLUS", "N20PRO", "N20E", "N20",
    "N30PROOMNI", "N30PLUS", "N30PRO", "N30",
    "N8", "OZMO950",
    "W2PROOMNI", "W2SOMNI", "W2OMNI", "W2S", "W2", "W1PRO", "W1", "W3OMNI", "W3",
    "WINBOT920", "WINBOTMINI2", "WINBOTMINI",
    "GOATG1PLUS", "GOATG1800", "GOATG1", "G1PLUS", "G1800",
    "GOATA3000LIDARPRO", "GOATA3000LIDAR", "GOATA3000", "A3000LIDARPRO", "A3000",
    "GOATA2000LIDARPRO", "GOATA2000", "A2000",
    "GOATA1600", "A1600", "GOATO800", "O800", "GOATO600", "O600",
    "GOATO500", "O500", "GOATO1200", "O1200",
    "MINI2", "DEEBOTMINI",
    "AIRBOTZ1",
]

# robot id -> (accepted canonical tokens for THIS model, extra accept regexes)
# extra regexes cover Chinese internal codenames with no latin model token.
SELF: dict[int, tuple[list[str], list[str]]] = {
    1937: (["X5OMNI"], [r"玻尔标配_白色材质"]),            # 玻尔 = X5 internal codename, white
    2517: (["X5OMNI"], [r"玻尔标配_黑色材质"]),            # black colourway
    1939: (["X9PROOMNI", "X9"], []),
    1941: (["T50MAXPROOMNI", "T50MAXPRO", "T50MAX"], []),
    1943: (["T50OMNI"], []),
    1945: (["W2OMNI"], []),
    1947: (["W2S"], []),
    1949: (["W3OMNI", "W3"], []),
    1951: (["GOATA3000LIDAR", "GOATA3000", "A3000"], []),
    1954: (["GOATO800", "O800"], []),
    1955: (["T30PROOMNI"], []),
    1956: (["T30OMNI"], []),
    1957: (["X5PROOMNI"], []),
    1958: (["X2OMNI", "X2"], []),
    1959: (["N30PROOMNI"], []),
    1960: (["T20OMNI", "T20"], []),
    1961: (["W2PROOMNI"], []),
    1962: (["W1PRO"], []),
    1963: (["GOATG1"], []),
    2473: (["MINI2"], []),
    2474: (["N20PLUS"], []),
    2475: (["N30PLUS"], []),
    2476: (["T30C"], []),
    2477: (["T80OMNI", "T80"], []),
    2478: (["T90OMNI"], []),
    1965: (["AIRBOTZ1"], []),
    2518: (["T30C"], []),
}

# Dimension/spec/CAD art. Rule 9a: a drawing is NEVER a hero. We drop it outright
# rather than allow it as a gallery image — ECOVACS PDPs carry
# `us-w2s-dimension-920x920.png`, `US-WINBOT-W2-PRO-OMNI-Dimension-1280x1280.jpg`,
# `US-deebot-n20-plus_pro-plus-black-dimension-1280x1280.jpg`, and the Comau
# precedent (32 robots shipped with a dimension drawing as primary) is expensive.
DIAGRAM = ("dimension", "schematic", "cad", "exploded", "blueprint", "specsheet",
           "certific", "comparison", "compare", "qsg", "installation")

# Accessory / non-product tokens — never a hero, never a gallery image for a robot.
ACCESSORY = ("cleaningsolution", "dustbag", "moppingpad", "bladekit", "cleaningkit",
             "sidebrush", "buddykit", "filter", "brushcover", "mainbrush",
             "extensioncord", "cleaningpad", "gadgets", "warranty", "brandclaim",
             "stationdust", "solution", "accessoriesbundle", "accessories")


def norm(name: str) -> str:
    """Normalise a filename for model-token matching.

    CRITICAL: strip dimension tokens (920x920, 1280x1280, 2560x1440) FIRST.
    Otherwise `deebot-t90-black-920x920.png` normalises to `...920X920...`,
    whose substring `X9` makes the file look like it names the DEEBOT **X9** —
    a false positive that silently dropped every correctly-named T90/GOAT-G1
    listing image. Same trap for any `<n>x<n>` suffix.
    """
    s = re.sub(r"\d+\s*[xX]\s*\d+", " ", name)      # kill 920x920 / 2560x1440
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def tail(url: str) -> str:
    t = url.rsplit("/", 1)[-1]
    return t.split("$")[-1] if "$" in t else t


def foreign_models(fname: str, accept: list[str]) -> list[str]:
    """Canonical model tokens named in this filename that are NOT this model."""
    n = norm(fname)
    hits, consumed = [], []
    for tok in VOCAB:                       # VOCAB is longest-first
        if tok in n:
            # skip if this token is a substring of an already-matched longer token
            if any(tok in c for c in consumed):
                continue
            consumed.append(tok)
            # STRICT: the token must be an *exact* accepted token. A looser
            # "substring either way" test silently admitted sibling SKUs —
            # `id-winbot-w2s-omni-920x920.png` (WINBOT **W2S OMNI**, robot +
            # station) passed as WINBOT **W2S** because "W2S" is a substring of
            # "W2SOMNI". Same class of bug as T50 vs T50 MAX PRO OMNI. If a
            # shorter token really is the same product, list it in SELF.
            if tok not in accept:
                hits.append(tok)
    return hits


def main():
    d = json.load(open(RECON, encoding="utf-8"))
    by_hash = defaultdict(set)
    for rid, e in d.items():
        for im in e["images"]:
            by_hash[im["md5"]].add(rid)

    # --- who *claims* each image? ---------------------------------------
    # A cross-linked image is not automatically junk: ECOVACS puts a model's own
    # listing render on sibling pages as "you may also like". `N30-PRO-OMNI-
    # White.jpg` appears on both the N30 PRO OMNI page and the N20 PLUS page —
    # it depicts the N30 PRO OMNI and belongs to 1959 alone. So: a shared image
    # is kept ONLY by the one batch robot whose model it actually names. If zero
    # or >1 robots claim it (e.g. `DEEBOTT30CQSG.png`, claimed by both the T30C
    # white and black records), nobody gets it — that is the fail-closed side.
    def claims(rid: int, im: dict) -> bool:
        accept, extra = SELF.get(rid, ([], []))
        t = tail(im["url"])
        n = norm(t)
        if any(re.search(x, im["url"]) for x in extra):
            return True
        return bool(accept and any(a in n for a in accept)) and not foreign_models(t, accept)

    claimed_by: dict[str, list[int]] = {}
    for h, rids in by_hash.items():
        if len(rids) < 2:
            continue
        im = next(i for r in rids for i in d[r]["images"] if i["md5"] == h)
        claimed_by[h] = [int(r) for r in rids if claims(int(r), im)]

    out = {}
    for rid_s, e in sorted(d.items(), key=lambda x: int(x[0])):
        rid = int(rid_s)
        accept, extra = SELF.get(rid, ([], []))
        keep, dropped = [], []
        for im in e["images"]:
            t = tail(im["url"])
            n = norm(t)
            ar = im["w"] / im["h"] if im["h"] else 0
            reason = None
            if len(by_hash[im["md5"]]) > 1 and claimed_by.get(im["md5"]) != [rid]:
                owners = claimed_by.get(im["md5"]) or []
                reason = ("shared_across_models_uniquely_claimed_by_%s" % owners[0]
                          if len(owners) == 1 else
                          "shared_across_models_claimed_by_%s" % (owners or "none"))
            elif any(a in n.lower() or a in t.lower().replace("-", "").replace("_", "")
                     for a in ACCESSORY):
                reason = "accessory"
            elif any(g in n.lower() or g in t.lower().replace("-", "").replace("_", "")
                     for g in DIAGRAM):
                reason = "diagram_or_specsheet"
            elif ar >= 2.2 or ar <= 0.42:
                reason = f"banner_aspect_{ar:.1f}"
            elif im["bytes"] < 10_000:
                reason = "tiny"
            else:
                fm = foreign_models(t, accept)
                if fm:
                    reason = f"names_other_model:{','.join(fm)}"
            if reason:
                dropped.append({**im, "drop": reason})
                continue
            named_self = bool(accept and any(a in n for a in accept)) or \
                any(re.search(x, im["url"]) for x in extra)
            keep.append({**im, "named_self": named_self})
        keep.sort(key=lambda x: (not x["named_self"], -x["bytes"]))
        # WITHIN-robot dedupe by content hash: ECOVACS serves the same bytes
        # under several upload paths (e.g. two `id-x5-pro-omni-black-920x920.png`
        # uploads), so a URL-only gallery silently repeats one image.
        seen_h: set[str] = set()
        deduped = []
        for k in keep:
            if k["md5"] in seen_h:
                dropped.append({**k, "drop": "dup_within_robot"})
                continue
            seen_h.add(k["md5"])
            deduped.append(k)
        keep = deduped
        out[rid] = {"label": e["label"], "pdp": e["pdp"], "keep": keep, "dropped": dropped}
        ns = sum(1 for k in keep if k["named_self"])
        print(f"{rid} {e['label']:<24} keep={len(keep):<3} (named_self={ns:<2}) dropped={len(dropped)}")

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
