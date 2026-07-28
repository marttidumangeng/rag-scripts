"""Re-import Estun catalog image URLs and force S3 recopy on prod (requires server deploy)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from import_staging import import_staging, resolve_created_by_id  # noqa: E402

COMPANY_SLUG = "estun-robotics"


def build_recopy_rows(staging_dir: Path) -> list[dict]:
    """Full staging records that have catalog hero images (passes validate_staging)."""
    rows: list[dict] = []
    for path in sorted(staging_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        image = (data.get("image") or "").strip()
        if not image:
            continue
        data["images"] = data.get("images") or [image]
        url = (data.get("url") or "").strip()
        if url:
            data["sources"] = [{"url": url, "type": "website"}]
        if not (data.get("description") or data.get("purpose")):
            data["purpose"] = data.get("name") or "Estun industrial robot"
        rows.append(data)
    return [r for r in rows if r.get("name")]


def main() -> int:
    parser = argparse.ArgumentParser(description="Recopy Estun images from catalog URLs")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=5)
    args = parser.parse_args()

    staging_dir = _RESEARCH_DIR / "staging" / "robots" / COMPANY_SLUG
    rows = build_recopy_rows(staging_dir)
    print(f"rows with images: {len(rows)}")

    if not args.apply:
        print(json.dumps({k: rows[0].get(k) for k in ("name", "url", "image")} if rows else {}, indent=2))
        return 0

    import tempfile
    from robot_auto_research import slugify_robot_name

    tmp = Path(tempfile.mkdtemp(prefix="estun-recopy-"))
    for row in rows:
        fname = slugify_robot_name(row["name"])
        (tmp / f"{fname}.json").write_text(json.dumps(row, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    result = import_staging(
        tmp,
        patch=False,
        force_overwrite=True,
        status="pending_review",
        dry_run=False,
        created_by_id=resolve_created_by_id(args.created_by_id),
        replace_media=True,
        batch_size=args.batch_size,
        skip_company_update=True,
    )
    print(json.dumps({
        "ok": result.get("ok"),
        "updated_count": result.get("updated_count"),
        "error_count": result.get("error_count"),
        "warnings": (result.get("warnings") or [])[:5],
    }, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
