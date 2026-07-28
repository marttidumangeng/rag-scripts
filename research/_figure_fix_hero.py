"""Upload verified F.03 studio hero and PATCH Figure 03 (2502)."""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

import boto3
import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from api_client import ResearchApiClient
from load_env import load_research_env

load_research_env()

SERVER = Path(__file__).resolve().parents[2] / "robotaigeek-server"
BUCKET = "cdn.robotaigeek.com"
CDN = "https://cdn.robotaigeek.com"
KEY = "research-staging/figure/figure03-studio-hero.jpg"

SRC = Path("staging/tmp/figure-heroes/b6841d92dfe9.webp")
if not SRC.exists():
    cands = list(Path("staging/tmp/figure-heroes").glob("b6841d92dfe9.*"))
    SRC = next(p for p in cands if p.suffix.lower() in (".webp", ".jpg", ".png", ".bin"))

OUT = Path("staging/tmp/figure-heroes/figure03-studio-hero.jpg")
im = Image.open(SRC).convert("RGB")
im.save(OUT, quality=92, optimize=True)
print("local", OUT.stat().st_size, hashlib.md5(OUT.read_bytes()).hexdigest()[:12])


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        if k.startswith("AWS_") or not str(os.environ.get(k) or "").strip():
            os.environ[k] = v


_load_dotenv(SERVER / ".env")
s3 = boto3.client(
    "s3",
    region_name=os.environ.get("AWS_S3_REGION_NAME") or "ap-southeast-1",
    aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
)
s3.put_object(
    Bucket=BUCKET,
    Key=KEY,
    Body=OUT.read_bytes(),
    ContentType="image/jpeg",
    CacheControl="public, max-age=31536000",
)
url = f"{CDN}/{KEY}"
for _ in range(15):
    r = requests.get(url, timeout=30)
    if r.status_code == 200 and r.content[:3] == b"\xff\xd8\xff":
        print("CDN OK", url, len(r.content), hashlib.md5(r.content).hexdigest()[:12])
        break
    time.sleep(0.4)
else:
    raise SystemExit(f"CDN fail {url} {r.status_code}")

c = ResearchApiClient()
notes = (
    "[AI Research] Figure enrich 2026-07-20. Replaced wrong F.02-labeled CDN hero "
    "with OEM F.03 chest-labeled studio still (research-staging/figure/). "
    "US; Available; family figure:figure; typed specs from figure.ai/figure; "
    "release_year 2025 from Introducing Figure 03 (2025-10-09)."
)
body = {
    "image": url,
    "images": [url],
    "s3_image": None,
    "availability_status": 11,
    "weight_kg": 61,
    "height_mm": 1727,
    "payload_kg": 20,
    "speed": 4.32,
    "runtime_minutes": 300,
    "release_year": 2025,
    "family_key": "figure:figure",
    "family_name": "Figure",
    "family_url": "https://www.figure.ai/figure",
    "product_url_scope": "exact_variant",
    "manufacturer_countries": [20],
    "manufacturer_country_ref": 20,
    "notes": notes,
    "features": (
        "OEM figure.ai/figure + Introducing Figure 03 (2025-10-09): third-generation "
        "general-purpose humanoid for home and commercial work, redesigned for Helix "
        "VLA and high-volume BotQ manufacturing. Specs on product page: height 5'8\" "
        "(1727 mm), weight 61 kg, payload 20 kg, runtime 5 hr (300 min), speed 1.2 m/s "
        "(4.32 km/h), electric system. Soft textiles + multi-density foam for home "
        "safety; 9% less mass than Figure 02; actuators up to 2× faster with improved "
        "torque density. Hero: OEM studio still with F.03 chest label (replaced prior "
        "F.02 mislabel). Soft: no public MSRP."
    ),
}
r = c._patch("robots/robots/2502/", body)
print(
    "patched",
    r.get("id"),
    (r.get("image") or "")[:90],
    "year",
    r.get("release_year"),
    "w",
    r.get("weight_kg"),
    "payload",
    r.get("payload_kg"),
)
