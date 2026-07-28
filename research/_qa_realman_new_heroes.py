"""Download and hash-check heroes for new Realman variants."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_P = "https://www.realman-robotics.com/prop/products-images"
HEROES = {
    "eco63_std": f"{_P}/机械臂/ECO系列/ECO63/ECO63-标准版/前视图-标准版.png",
    "eco63_force": f"{_P}/机械臂/ECO系列/ECO63/ECO63-六维力版/前视图-6维力版.png",
    "rx71_std": f"{_P}/机械臂/RX系列/RX71-标准版/RX71-标准版.png",
}
OUT = Path("staging/realman_variants_qa")
OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}


def encode_url(url: str) -> str:
    p = urlsplit(url)
    segs = [quote(unquote(seg), safe="") for seg in p.path.split("/")]
    return urlunsplit((p.scheme, p.netloc, "/".join(segs), p.query, p.fragment))


def main() -> None:
    hashes = {}
    for key, url in HEROES.items():
        body = requests.get(encode_url(url), headers=UA, timeout=60).content
        assert body[:8].startswith(b"\x89PNG"), key
        md5 = hashlib.md5(body).hexdigest()
        hashes[key] = md5
        path = OUT / f"{key}_{md5[:12]}.png"
        path.write_bytes(body)
        print(key, len(body), md5, path.name)
    # uniqueness
    assert len(set(hashes.values())) == len(hashes), hashes
    print("all distinct OK")


if __name__ == "__main__":
    main()
