"""
Crop transparent/white empty space from robotaigeek-logo.png.
Saves the result back to the same file (overwrites in-place).
"""

from pathlib import Path
import numpy as np
from PIL import Image

INPUT = Path(__file__).parent.parent / "reference" / "robotaigeek-logo.png"

# How far a channel must deviate from 255 to be treated as actual content.
WHITE_THRESHOLD = 20

# A row or column must contain at least this many content pixels to be treated
# as a real content row/column (ignores isolated anti-aliased edge artefacts).
MIN_CONTENT_PIXELS = 5

# Extra padding (in pixels) kept around the detected content box.
PADDING = 2


def get_crop_box(img: Image.Image):
    """Return the tight bounding box of non-background content.

    A pixel is background if:
      - alpha == 0 (transparent), OR
      - ALL RGB channels are within WHITE_THRESHOLD of 255 (near-white).

    Rows/columns with fewer than MIN_CONTENT_PIXELS are ignored so that
    isolated anti-aliasing artefacts at the image border don't expand the box.
    """
    arr = np.array(img.convert("RGBA"), dtype=np.int16)
    r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]

    transparent = a < 10  # treat very low / near-zero alpha as transparent
    near_white = (
        (255 - r <= WHITE_THRESHOLD) &
        (255 - g <= WHITE_THRESHOLD) &
        (255 - b <= WHITE_THRESHOLD)
    )
    content = ~(transparent | near_white)

    row_counts = np.sum(content, axis=1)   # content pixels per row
    col_counts = np.sum(content, axis=0)   # content pixels per column

    content_rows = row_counts >= MIN_CONTENT_PIXELS
    content_cols = col_counts >= MIN_CONTENT_PIXELS

    if not content_rows.any():
        return None

    h, w = arr.shape[:2]
    top    = max(0,  int(np.argmax(content_rows))              - PADDING)
    bottom = min(h,  h - int(np.argmax(content_rows[::-1]))   + PADDING)
    left   = max(0,  int(np.argmax(content_cols))              - PADDING)
    right  = min(w,  w - int(np.argmax(content_cols[::-1]))   + PADDING)

    return (left, top, right, bottom)


def main():
    img = Image.open(INPUT)
    print(f"Original size : {img.size[0]} x {img.size[1]}  mode={img.mode}")

    bbox = get_crop_box(img)
    if bbox is None:
        print("ERROR: Could not detect content — image may be entirely empty.")
        return

    print(f"Content bbox  : {bbox}")
    cropped = img.crop(bbox)
    print(f"Cropped size  : {cropped.size[0]} x {cropped.size[1]}")

    cropped.save(INPUT, format="PNG")
    print(f"Saved (in-place): {INPUT}")


if __name__ == "__main__":
    main()
