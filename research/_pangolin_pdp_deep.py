"""Deep-scrape Pangolin PDPs for param tables + unique gallery uploads."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fix_pangolin_robots import HERO

SESS = requests.Session()
SESS.verify = False
SESS.headers["User-Agent"] = "Mozilla/5.0"
OUT = _RESEARCH_DIR / "staging" / "reports" / "pangolin-pdp-deep.json"
IMG = _RESEARCH_DIR / "staging" / "pangolin_pdp_extra"
IMG.mkdir(parents=True, exist_ok=True)

# known shared site assets (banner + list thumbs already assigned as primary)
BAN_HASHES = {
    "eee172ad753e9d623e64b52a8053981a",  # path token
}


def fetch(url: str) -> bytes:
    return SESS.get(url, timeout=45).content


def main() -> None:
    # load existing primary md5s from list thumbs report
    list_thumbs = json.loads(
        (_RESEARCH_DIR / "staging" / "reports" / "pangolin-list-thumbs.json").read_text(
            encoding="utf-8"
        )
    )
    primary_by_url: dict[str, set[str]] = {}
    all_primary_md5: set[str] = set()
    for p in list_thumbs["products"]:
        for m in p.get("thumb_meta") or []:
            if m.get("n_products") == 1 and m.get("md5"):
                primary_by_url.setdefault(p["url"], set()).add(m["md5"])
                all_primary_md5.add(m["md5"])

    report = {}
    for rid, cfg in sorted(HERO.items()):
        url = cfg["url"]
        html = SESS.get(url, timeout=45).text
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)

        # param-like lines
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        params = []
        for ln in lines:
            if re.search(
                r"(负载|载重|尺寸|重量|速度|续航|电池|充电|容量|货仓|舱|温度|爬坡|越障|导航)",
                ln,
            ) and len(ln) < 80:
                params.append(ln)

        uploads = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if "/public/uploads/images/" not in src:
                continue
            if "eee172ad" in src:
                continue
            if not src.startswith("http"):
                src = "https://www.alpha-robot.com.cn" + src
            uploads.append(src.split("?")[0])
        uploads = list(dict.fromkeys(uploads))

        extras = []
        for src in uploads[:25]:
            try:
                data = fetch(src)
            except Exception as e:
                continue
            if len(data) < 8000:
                continue
            if not (
                data[:8] == b"\x89PNG\r\n\x1a\n"
                or data[:2] == b"\xff\xd8"
                or data[:4] == b"RIFF"
            ):
                continue
            md5 = hashlib.md5(data).hexdigest()
            # skip if this is another robot's primary hero
            if md5 in all_primary_md5 and md5 not in primary_by_url.get(url, set()):
                continue
            fname = f"{rid}_{md5[:12]}_{Path(src).name}"
            (IMG / fname).write_bytes(data)
            extras.append({"url": src, "md5": md5, "bytes": len(data), "file": fname})

        report[str(rid)] = {
            "model": cfg["model"],
            "url": url,
            "params": params[:30],
            "n_uploads": len(uploads),
            "extras": extras[:12],
        }
        print(
            f"{rid} {cfg['model'][:22]:22s} params={len(params):2d} "
            f"uploads={len(uploads):2d} extras={len(extras):2d}"
        )
        for p in params[:6]:
            print(f"   · {p}")

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
