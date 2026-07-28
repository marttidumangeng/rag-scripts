"""Assemble + upload + PATCH DAIHEN family-7 clean primaries; demote banners."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import boto3
import requests
from PIL import Image

_RESEARCH = Path(__file__).resolve().parent
ROOT = _RESEARCH.parent.parent
SERVER = ROOT / "robotaigeek-server"
sys.path.insert(0, str(_RESEARCH))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env
from api_client import ResearchApiClient

load_research_env()

OUT = Path("staging/reports/daihen_family7")
FINAL = OUT / "final"
FINAL.mkdir(parents=True, exist_ok=True)

CDN = "https://cdn.robotaigeek.com"
BUCKET = "cdn.robotaigeek.com"
PREFIX = "research-staging/daihen"

BANNER_V80 = "https://www.daihen-robot.com/assets/img/en/robot/items/mv_FD-V80_V100_V130.jpg"
BANNER_HEAVY = (
    "https://www.daihen-robot.com/assets/img/en/robot/items/"
    "mv_FD-V280L_V350_V400L_V600_V700.jpg"
)

# Verified sources (visual QA + labeled or official PDP)
SOURCES = {
    3051: {
        "name": "FD-V80",
        "src": OUT / "v80alt2_p0_i3_938x2517.jpg",
        "banner": BANNER_V80,
        "note": "MAP OTC PDF white-bg still, arm labeled FD-V80",
    },
    1903: {
        "name": "FD-V100",
        "src": OUT / "v80alt2_p0_i1_835x2652.jpg",
        "banner": BANNER_V80,
        "note": "MAP OTC PDF white-bg still, arm labeled FD-V100",
    },
    1904: {
        "name": "FD-V130",
        "src": OUT / "v80alt2_p0_i2_778x2652.jpg",
        "banner": BANNER_V80,
        "note": "MAP OTC PDF white-bg still, arm labeled FD-V130",
    },
    3054: {
        "name": "FD-V350",
        "src": OUT / "web2/0a1d69e041.jpg",
        "banner": BANNER_HEAVY,
        "note": "ATC Baltic FD-V350 dealer still (white bg; OTC co.id/Europe assets mislabeled V210)",
    },
    2472: {
        "name": "FD-V400L",
        "src": OUT / "otc_2472_0c5932919b_FD-V400L.png",
        "banner": BANNER_HEAVY,
        "note": "OTC product PNG, arm labeled FD-V400L",
    },
    1898: {
        "name": "FD-V600",
        "src": OUT / "otc_1898_b1dacb82a2_FD-V600_700.png",
        "banner": BANNER_HEAVY,
        "note": "OTC FD-V600/700 product still (assigned to V600)",
    },
    1899: {
        "name": "FD-V700",
        "src": OUT / "page5_imgs/i01_536x689.jpg",
        "banner": BANNER_HEAVY,
        "note": "EN catalog heavy page embed for V600/V700 slot (distinct bytes from V600 OTC)",
    },
}


def to_white_bg(im: Image.Image) -> Image.Image:
    """Composite near-black / mask artifacts onto white."""
    im = im.convert("RGBA")
    arr_mode = im
    # Simple: treat near-black pixels as transparent then paste on white
    pixels = arr_mode.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if r < 25 and g < 25 and b < 25:
                pixels[x, y] = (255, 255, 255, 255)
            elif r > 250 and g > 250 and b > 250 and (x < 5 or y < 5 or x > w - 6 or y > h - 6):
                # keep white
                pass
    bg = Image.new("RGB", im.size, (255, 255, 255))
    bg.paste(im, mask=im.split()[3])
    return bg


def build_finals() -> dict:
    plan = {}
    hashes: dict[str, int] = {}
    for rid, meta in SOURCES.items():
        src = meta["src"]
        assert src.is_file(), src
        im = Image.open(src).convert("RGB")
        if rid == 1899:
            # catalog cutout has black + white mask blocks — flatten to white
            im = to_white_bg(Image.open(src))
        # normalize tall portraits: optional max edge 1600
        max_edge = 1600
        if max(im.size) > max_edge:
            im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        dst = FINAL / f"{rid}-{meta['name']}-hero.jpg"
        im.save(dst, quality=92, optimize=True)
        md5 = hashlib.md5(dst.read_bytes()).hexdigest()
        if md5 in hashes:
            raise SystemExit(f"DUPLICATE HASH {md5} between {hashes[md5]} and {rid}")
        hashes[md5] = rid
        plan[rid] = {
            "id": rid,
            "name": meta["name"],
            "path": str(dst).replace("\\", "/"),
            "md5": md5,
            "banner": meta["banner"],
            "note": meta["note"],
            "size": list(im.size),
        }
        print(f"FINAL {rid} {meta['name']} {im.size} {md5[:12]} <- {src.name}")
    Path("staging/reports/daihen-family7-final.json").write_text(
        json.dumps({"plan": plan}, indent=2), encoding="utf-8"
    )
    return plan


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        if k.startswith("AWS_") or not str(os.environ.get(k) or "").strip():
            os.environ[k] = v


def s3_client():
    _load_dotenv(SERVER / ".env")
    os.environ["AWS_STORAGE_BUCKET_NAME"] = BUCKET
    region = os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1"
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def upload(s3, local: Path, key: str) -> str:
    body = local.read_bytes()
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=body,
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    url = f"{CDN}/{key}"
    for _ in range(10):
        r = requests.get(url, timeout=30)
        if r.status_code == 200 and r.content[:3] == b"\xff\xd8\xff":
            return url
        time.sleep(0.4)
    raise RuntimeError(f"CDN verify failed {url} {r.status_code}")


def apply(plan: dict) -> None:
    s3 = s3_client()
    client = ResearchApiClient()
    report = {"patched": [], "errors": []}
    for rid, row in plan.items():
        local = Path(row["path"])
        slug = row["name"].lower().replace(" ", "-")
        key = f"{PREFIX}/{rid}-{slug}-hero.jpg"
        try:
            crop_url = upload(s3, local, key)
            banner = row["banner"]
            payload = {"image": crop_url, "images": [crop_url, banner], "s3_image": None}
            client._patch(f"robots/robots/{rid}/", payload)
            client._patch(f"robots/robots/{rid}/", {"availability_status": 11})
            full = client._get(f"robots/robots/{rid}/")
            api_img = full.get("image") or ""
            print(f"PATCHED {rid} {row['name']} api_image={api_img[:80]}...")
            report["patched"].append(
                {
                    "id": rid,
                    "name": row["name"],
                    "image": crop_url,
                    "api_image": api_img,
                    "md5": row["md5"],
                    "note": row["note"],
                }
            )
            time.sleep(0.25)
        except Exception as e:
            print(f"ERROR {rid}: {e}")
            report["errors"].append({"id": rid, "error": str(e)})
    Path("staging/reports/daihen-family7-apply.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print("done", len(report["patched"]), "errors", len(report["errors"]))


def main() -> None:
    apply_flag = "--apply" in sys.argv
    plan = build_finals()
    if apply_flag:
        apply(plan)
    else:
        print("dry-run only; pass --apply to upload+patch")


if __name__ == "__main__":
    main()
