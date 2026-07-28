"""Probe Realman OEM prop URLs for missing variants."""
from __future__ import annotations

import re
import sys
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}


def encode_url(url: str) -> str:
    p = urlsplit(url)
    segs = [quote(unquote(seg), safe="") for seg in p.path.split("/")]
    path = "/".join(segs)
    return urlunsplit((p.scheme, p.netloc, path, p.query, p.fragment))


def main() -> None:
    pages = {
        "eco62": "https://www.realman-robotics.com/en/products/eco62.html",
        "eco63": "https://www.realman-robotics.com/en/products/eco63.html",
        "rx71": "https://www.realman-robotics.com/en/products/rx71.html",
        "rx75": "https://www.realman-robotics.com/en/products/rx75.html",
    }
    for slug, url in pages.items():
        html = requests.get(url, headers=UA, timeout=40).text
        props = sorted(set(re.findall(r"https?://[^\"'\s]+/prop/[^\"'\s]+", html)))
        print("====", slug, "props", len(props))
        for p in props:
            d = unquote(p)
            marks = []
            if "六维力" in d or "force" in d.lower():
                marks.append("FORCE")
            if "标准" in d or "standard" in d.lower():
                marks.append("STD")
            if "视觉" in d or "vision" in d.lower():
                marks.append("VIS")
            print(" ", ",".join(marks) or "-", d.split("/prop/")[-1][:120])

    # Candidate heroes to HEAD-check
    _PROP = "https://www.realman-robotics.com/prop/products-images"
    candidates = [
        f"{_PROP}/机械臂/ECO系列/ECO62/ECO62-六维力版/20240918-结构渲染.bip.669.png",
        f"{_PROP}/机械臂/ECO系列/ECO62/ECO62-六维力版/正视图-6维力版.png",
        f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-标准版/角度1-标准版.png",
        f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-六维力版/角度1-6维力版.png",
        f"{_PROP}/机械臂/ECO系列/ECO63/ECO63-六维力版/正视图-6维力版.png",
        f"{_PROP}/机械臂/RX系列/RX71/RX71-标准版/",
        f"{_PROP}/机械臂/RX系列/RX71-标准版/",
        f"{_PROP}/机械臂/RX系列/RX75-六维力版/",
        f"{_PROP}/机械臂/RX系列/RX75-标准版/2.185.png",
    ]
    print("\n==== HEAD checks (guessed paths) ====")
    for u in candidates:
        try:
            r = requests.head(encode_url(u), headers=UA, timeout=20, allow_redirects=True)
            print(r.status_code, unquote(u).split("/products-images/")[-1][:90])
        except requests.RequestException as e:
            print("ERR", e, u[:60])


if __name__ == "__main__":
    main()
