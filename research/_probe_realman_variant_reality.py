"""Deep-parse Realman PDPs for variant SKU reality vs marketing text."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
OUT = Path("staging/realman_variants_qa")
OUT.mkdir(parents=True, exist_ok=True)


def encode_url(url: str) -> str:
    p = urlsplit(url)
    segs = [quote(unquote(seg), safe="") for seg in p.path.split("/")]
    return urlunsplit((p.scheme, p.netloc, "/".join(segs), p.query, p.fragment))


def fetch(url: str) -> str:
    r = requests.get(encode_url(url) if any(ord(c) > 127 for c in url) else url, headers=UA, timeout=45)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def prop_urls(html: str, base: str) -> list[str]:
    found = set()
    for m in re.finditer(r"""(?:src|href|data-src)=["']([^"']*products-images[^"']+)["']""", html, re.I):
        found.add(urljoin(base, m.group(1)))
    for m in re.finditer(r"""(https?://[^"'\\\s]*products-images[^"'\\\s]+)""", html):
        found.add(m.group(1).rstrip("\\"))
    for m in re.finditer(r"""(/prop/products-images/[^"'\\\s]+)""", html):
        found.add(urljoin(base, m.group(1)))
    return sorted(found)


def head_ok(url: str) -> tuple[int, int, str]:
    try:
        r = requests.get(encode_url(url), headers=UA, timeout=40, stream=True)
        chunk = next(r.iter_content(2048), b"") or b""
        r.close()
        md5 = hashlib.md5(chunk).hexdigest()[:12] if chunk else ""
        return r.status_code, len(chunk), md5
    except requests.RequestException as e:
        return 0, 0, str(e)[:40]


def main() -> None:
    pages = [
        "eco62",
        "eco63",
        "rx71",
        "rx75",
    ]
    for slug in pages:
        url = f"https://www.realman-robotics.com/en/products/{slug}.html"
        html = fetch(url)
        props = prop_urls(html, url)
        print(f"\n==== {slug} prop assets {len(props)} ====")
        folders = set()
        for p in props:
            d = unquote(p)
            print(" ", d.split("/products-images/")[-1][:130])
            # folder token
            for tok in ("标准版", "六维力版", "视觉版", "带视觉"):
                if tok in d:
                    folders.add(tok)
        print(" folders:", sorted(folders))

        # Spec-ish lines mentioning Standard/Force/Vision
        for pat in (
            r".{0,40}Standard.{0,80}",
            r".{0,40}Six[- ]?Axis Force.{0,80}",
            r".{0,40}Vision.{0,80}",
            r".{0,40}Working [Rr]adius.{0,80}",
            r".{0,40}Payload.{0,80}",
            r".{0,40}Net [Ww]eight.{0,80}",
        ):
            hits = re.findall(pat, html)
            if hits:
                print(f"  sample {pat[10:25]}:", re.sub(r"\s+", " ", hits[0])[:120])

    # Known-good + explore force paths
    _P = "https://www.realman-robotics.com/prop/products-images"
    explore = [
        # ECO62 force guesses
        f"{_P}/机械臂/ECO系列/ECO62/ECO62-六维力版/20240918-结构渲染.bip.599.png",
        f"{_P}/机械臂/ECO系列/ECO62/ECO62-六维力版/20240918-结构渲染.bip.651.png",
        f"{_P}/机械臂/ECO系列/ECO62/ECO62-六维力版/20240918-结构渲染.bip.662.png",
        f"{_P}/机械臂/ECO系列/ECO62/ECO62-六维力版/20240918-结构渲染.bip.669.png",
        # ECO63
        f"{_P}/机械臂/ECO系列/ECO63/ECO63-标准版/角度1-标准版.png",
        f"{_P}/机械臂/ECO系列/ECO63/ECO63-标准版/角度3-标准版.png",
        f"{_P}/机械臂/ECO系列/ECO63/ECO63-六维力版/角度1-6维力版.png",
        f"{_P}/机械臂/ECO系列/ECO63/ECO63-六维力版/角度3-6维力版.png",
        f"{_P}/机械臂/ECO系列/ECO63/ECO63-六维力版/角度4-6维力版.png",
        f"{_P}/机械臂/ECO系列/ECO63/ECO63-六维力版/角度6-6维力版.png",
        # RX71
        f"{_P}/机械臂/RX系列/RX71-标准版/RX71-标准版.png",
        f"{_P}/机械臂/RX系列/RX71-六维力版/RX71-六维力版.png",
        f"{_P}/机械臂/RX系列/RX71-六维力版/RX71-标准版.png",
        # RX75 force
        f"{_P}/机械臂/RX系列/RX75-六维力版/2.185.png",
        f"{_P}/机械臂/RX系列/RX75-六维力版/RX75-六维力版.png",
        f"{_P}/机械臂/RX系列/RX75S-六维力版/RX75S-六维力版.png",
        f"{_P}/机械臂/RX系列/RX75-标准版/2.185.png",
        f"{_P}/机械臂/RX系列/RX75-视觉版/带视觉.png",
    ]
    print("\n==== explore HEAD/GET ====")
    for u in explore:
        code, n, h = head_ok(u)
        print(f"{code:3d} bytes~{n:5d} {h:12s} {unquote(u).split('/products-images/')[-1]}")


if __name__ == "__main__":
    main()
