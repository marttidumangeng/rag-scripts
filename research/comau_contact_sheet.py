"""Build a labelled contact sheet of Comau image candidates for visual QA.

The house rules require a human/agent to LOOK at every hero before apply (no
drawings, no banners, no duplicates). Reviewing 40 heroes as 40 separate
downloads is slow; this tiles them into one labelled grid so a single look
catches drawings, banners and repeats.

    python comau_contact_sheet.py --mode proposed     # one tile per robot (chosen hero)
    python comau_contact_sheet.py --mode candidates --ids 1852,1856
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from comau_image_audit import CACHE, fetch

OUT_DIR = Path(
    r"C:\Users\tramk\AppData\Local\Temp\claude\C--Github-Personal-robot-ai-geek"
    r"\83aaaf47-7682-4c7f-b152-0f961f4e2b97\scratchpad"
)

TILE_W, TILE_H = 320, 150
LABEL_H = 26


def load(url: str) -> Image.Image | None:
    data, _ = fetch(url)
    if not data:
        return None
    try:
        import io
        im = Image.open(io.BytesIO(data)).convert("RGB")
        return im
    except Exception:
        return None


def build_sheet(items: list[tuple[str, str]], cols: int, dest: Path) -> None:
    """items: list of (label, url)."""
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * TILE_W, rows * (TILE_H + LABEL_H)), (250, 250, 250))
    draw = ImageDraw.Draw(sheet)
    for idx, (label, url) in enumerate(items):
        cx = (idx % cols) * TILE_W
        cy = (idx // cols) * (TILE_H + LABEL_H)
        im = load(url)
        if im is not None:
            im.thumbnail((TILE_W - 6, TILE_H - 6))
            sheet.paste(im, (cx + 3, cy + LABEL_H + 3))
        else:
            draw.rectangle([cx + 3, cy + LABEL_H + 3, cx + TILE_W - 3, cy + TILE_H], outline=(200, 0, 0))
            draw.text((cx + 8, cy + LABEL_H + 8), "FETCH FAIL", fill=(200, 0, 0))
        draw.rectangle([cx, cy, cx + TILE_W - 1, cy + LABEL_H - 1], fill=(30, 30, 30))
        draw.text((cx + 4, cy + 7), label[:52], fill=(255, 255, 255))
        draw.rectangle([cx, cy, cx + TILE_W - 1, cy + TILE_H + LABEL_H - 1], outline=(180, 180, 180))
    dest.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dest)
    print(f"wrote {dest} ({len(items)} tiles, {sheet.size[0]}x{sheet.size[1]})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", type=str, default="staging/reports/comau-hero-plan.json")
    ap.add_argument("--ids", type=str, default="")
    ap.add_argument("--mode", choices=["proposed", "candidates"], default="proposed")
    ap.add_argument("--out", type=str, default="")
    ap.add_argument("--cols", type=int, default=6)
    args = ap.parse_args()

    plan = json.loads((_RESEARCH_DIR / args.plan).read_text(encoding="utf-8"))
    items: list[tuple[str, str]] = []

    if args.mode == "proposed":
        for rid, p in plan.items():
            hero = p.get("hero")
            if hero:
                items.append((f"{rid} {p['name'][:18]}", hero))
    else:
        want = {x.strip() for x in args.ids.split(",") if x.strip()}
        for rid, p in plan.items():
            if want and rid not in want:
                continue
            for u in p.get("candidates", []):
                items.append((f"{rid} {u.rsplit('/', 1)[-1][:24]}", u))

    dest = Path(args.out) if args.out else (OUT_DIR / f"comau-sheet-{args.mode}.png")
    build_sheet(items, args.cols, dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
