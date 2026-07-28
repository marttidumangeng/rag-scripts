from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


DEFAULT_SIZE = 256
DEFAULT_SIZES = (32, 64, 128, 256)
DEFAULT_PADDING_RATIO = 0.02
DEFAULT_ALPHA_THRESHOLD = 8


def parse_sizes(value: str) -> tuple[int, ...]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("sizes must contain at least one integer")

    try:
        sizes = tuple(sorted({int(part) for part in parts}))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("sizes must be a comma-separated list of integers") from exc

    if any(size <= 0 for size in sizes):
        raise argparse.ArgumentTypeError("sizes must be positive integers")

    return sizes


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    default_input = script_dir / "influence_icon.png"
    default_output = script_dir / "optimized" / "influence_icon_coin.png"

    parser = argparse.ArgumentParser(
        description="Trim and resize the Influence coin icon for site use."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=default_input,
        help="Source image path. Defaults to scripts/influence_icon.png",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output,
        help="Output PNG path. Defaults to scripts/optimized/influence_icon_coin.png",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=DEFAULT_SIZE,
        help="Output square dimension in pixels. Defaults to 256.",
    )
    parser.add_argument(
        "--sizes",
        type=parse_sizes,
        default=DEFAULT_SIZES,
        help="Comma-separated icon sizes to generate. Defaults to 32,64,128,256.",
    )
    parser.add_argument(
        "--padding-ratio",
        type=float,
        default=DEFAULT_PADDING_RATIO,
        help="Transparent inset around the trimmed coin, expressed as a ratio of the output size.",
    )
    parser.add_argument(
        "--alpha-threshold",
        type=int,
        default=DEFAULT_ALPHA_THRESHOLD,
        help="Ignore pixels with alpha below this value when trimming. Defaults to 8.",
    )
    return parser.parse_args()


def get_trim_box(image: Image.Image, alpha_threshold: int = DEFAULT_ALPHA_THRESHOLD) -> tuple[int, int, int, int]:
    if not 0 <= alpha_threshold <= 255:
        raise ValueError("alpha_threshold must be between 0 and 255")

    alpha_channel = image.getchannel("A")
    thresholded_alpha = alpha_channel.point(
        lambda value: 255 if value >= alpha_threshold else 0
    )
    trim_box = thresholded_alpha.getbbox()
    if trim_box is None:
        raise ValueError("Could not detect non-transparent pixels to trim.")
    return trim_box


def optimize_icon(
    source_path: Path,
    output_path: Path,
    size: int,
    padding_ratio: float,
    alpha_threshold: int,
) -> Path:
    if size <= 0:
        raise ValueError("size must be a positive integer")
    if not 0 <= padding_ratio < 0.5:
        raise ValueError("padding_ratio must be between 0 and 0.5")

    source = Image.open(source_path).convert("RGBA")
    trim_box = get_trim_box(source, alpha_threshold=alpha_threshold)
    trimmed = source.crop(trim_box)

    inset = max(1, round(size * padding_ratio))
    inner_size = size - (inset * 2)
    if inner_size <= 0:
        raise ValueError("padding_ratio leaves no room for the icon")

    fitted = trimmed.copy()
    fitted.thumbnail((inner_size, inner_size), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - fitted.width) // 2, (size - fitted.height) // 2)
    canvas.paste(fitted, offset, fitted)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG", optimize=True)
    return output_path


def build_output_path(
    output_path: Path,
    size: int,
    generate_multiple: bool,
    primary_size: int,
) -> Path:
    if not generate_multiple:
        return output_path
    if size == primary_size:
        return output_path
    return output_path.with_name(f"{output_path.stem}_{size}{output_path.suffix}")


def optimize_icon_set(
    source_path: Path,
    output_path: Path,
    sizes: tuple[int, ...],
    padding_ratio: float,
    alpha_threshold: int,
) -> list[Path]:
    generate_multiple = len(sizes) > 1
    primary_size = max(sizes)
    return [
        optimize_icon(
            source_path,
            build_output_path(output_path, size, generate_multiple, primary_size),
            size,
            padding_ratio,
            alpha_threshold,
        )
        for size in sizes
    ]


def main() -> None:
    args = parse_args()
    sizes = args.sizes or (args.size,)
    if len(sizes) == 1 and args.size not in sizes:
        sizes = (args.size,)

    output_paths = optimize_icon_set(
        args.input,
        args.output,
        sizes,
        args.padding_ratio,
        args.alpha_threshold,
    )
    print("Saved optimized icon(s):")
    for output_path in output_paths:
        print(output_path)


if __name__ == "__main__":
    main()