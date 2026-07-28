"""Tile Ecovacs candidates into labelled contact sheets for visual QA.

House rule: LOOK at every hero before apply. One sheet per robot, each tile
labelled with its candidate index so picks can be referenced by number.

    python _ecovacs_contact_sheet.py --ids 1937,1939 --top 12
    python _ecovacs_contact_sheet.py --all --top 12
"""
from __future__ import annotations
import argparse, hashlib, io, json, sys
from pathlib import Path

from PIL import Image, ImageDraw

_D = Path(__file__).resolve().parent
sys.path.insert(0, str(_D))

CAND = _D / "staging" / "reports" / "ecovacs_candidates.json"
CACHE = _D / "staging" / "ecovacs_media_cache"
OUT = Path(r"C:\Users\tramk\AppData\Local\Temp\claude"
           r"\C--Github-Personal-robot-ai-geek"
           r"\83aaaf47-7682-4c7f-b152-0f961f4e2b97\scratchpad\ecovacs_sheets")
OUT.mkdir(parents=True, exist_ok=True)

TILE = 260
LABEL = 30
COLS = 4


def load(url: str) -> Image.Image | None:
    fp = CACHE / hashlib.md5(url.encode()).hexdigest()
    if not fp.exists():
        return None
    try:
        im = Image.open(io.BytesIO(fp.read_bytes()))
        if im.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", im.size, (245, 245, 245))
            im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[-1])
            im = bg
        return im.convert("RGB")
    except Exception:
        return None


def sheet(rid: str, entry: dict, top: int) -> Path | None:
    cands = entry["keep"][:top]
    if not cands:
        return None
    rows = (len(cands) + COLS - 1) // COLS
    W, H = COLS * TILE, rows * (TILE + LABEL) + LABEL
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(canvas)
    d.text((6, 6), f"{rid} {entry['label']}  ({len(cands)} candidates)", fill=(0, 0, 0))
    for i, c in enumerate(cands):
        im = load(c["url"])
        x = (i % COLS) * TILE
        y = (i // COLS) * (TILE + LABEL) + LABEL
        if im:
            im.thumbnail((TILE - 8, TILE - 8))
            canvas.paste(im, (x + 4 + (TILE - 8 - im.width) // 2,
                              y + 4 + (TILE - 8 - im.height) // 2))
        d.rectangle([x + 1, y + 1, x + TILE - 2, y + TILE - 2], outline=(200, 200, 200))
        name = c["url"].rsplit("/", 1)[-1].split("$")[-1][:30]
        flag = "*" if c.get("named_self") else " "
        d.text((x + 5, y + TILE), f"[{i}]{flag}{c['w']}x{c['h']}", fill=(0, 0, 0))
        d.text((x + 5, y + TILE + 13), name, fill=(90, 90, 90))
    p = OUT / f"sheet_{rid}.png"
    canvas.save(p)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()
    d = json.load(open(CAND, encoding="utf-8"))
    ids = sorted(d, key=int) if a.all else [i.strip() for i in (a.ids or "").split(",") if i.strip()]
    for rid in ids:
        p = sheet(rid, d[rid], a.top)
        print(f"{rid}: {p}" if p else f"{rid}: NO CANDIDATES")


if __name__ == "__main__":
    main()
