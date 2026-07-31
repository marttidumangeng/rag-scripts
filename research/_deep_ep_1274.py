"""Deep-parse one EP PDP + find clean product renders + brochure specs."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

URLS = {
    "es15": "https://ep-equipment.com/product/es15-15es/",
    "ept25": "https://ep-equipment.com/product/ept25-wa/",
    "ept20wa": "https://ep-equipment.com/product/ept20-20wa/",
    "jx0": "https://ep-equipment.com/product/jx0/",
    "rpl251": "https://ep-equipment.com/product/rpl251/",
    "rpl301": "https://ep-equipment.com/product/rpl301/",
    "qdd30s": "https://ep-equipment.com/product/qdd30s/",
    "epl154": "https://ep-equipment.com/product/epl154/",
    "epl185": "https://ep-equipment.com/product/epl185/",
    "kpl201": "https://ep-equipment.com/product/kpl201/",
    "esl122": "https://ep-equipment.com/product/esl122/",
    "ept20rap": "https://ep-equipment.com/product/ept20-rap/",
    "wpl202": "https://ep-equipment.com/product/wpl202/",
}

OUT = Path("staging/ep1274_heroes_png")
OUT.mkdir(parents=True, exist_ok=True)
RAW = Path("staging/ep1274_raw")
RAW.mkdir(parents=True, exist_ok=True)


def parse_specs_from_html(html: str) -> dict:
    """Prefer structured table / definition lists over flat regex."""
    specs = {}
    # table rows
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.I | re.S)
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.I | re.S)
        cells = [re.sub(r"<[^>]+>", " ", c) for c in cells]
        cells = [re.sub(r"\s+", " ", c).strip() for c in cells]
        if len(cells) < 2:
            continue
        label = cells[0].lower()
        vals = cells[1:]
        def num(s):
            m = re.search(r"(\d[\d,\.]*)", s.replace(" ", ""))
            return m.group(1).replace(",", "") if m else None

        if "load capacity" in label or "rated capacity" in label or label.strip() in {"q", "capacity"}:
            n = num(vals[0])
            if n:
                specs["payload_kg"] = float(n)
                specs["_payload_raw"] = vals
        elif "service weight" in label or ("weight" in label and "battery" not in label):
            n = num(vals[0])
            if n:
                specs["weight_kg"] = float(n)
                specs["_weight_raw"] = vals
        elif "lift height" in label or "lifting height" in label or "max. lift" in label:
            n = num(vals[0])
            if n:
                specs["lift_height_mm"] = float(n)
                specs["_lift_raw"] = vals
        elif "travel speed" in label or "driving speed" in label:
            n = num(vals[0])
            if n:
                specs["speed_kmh"] = float(n)
                specs["_speed_raw"] = vals
        elif "battery voltage" in label or label.strip() == "voltage":
            n = num(vals[0])
            if n:
                specs["voltage"] = int(float(n))
        elif "overall length" in label or label.startswith("length"):
            n = num(vals[0])
            if n:
                specs["length_mm"] = float(n)
        elif "overall width" in label or label.startswith("width"):
            n = num(vals[0])
            if n:
                specs["width_mm"] = float(n)
        elif "overall height" in label and "mast" not in label:
            n = num(vals[0])
            if n:
                specs["height_mm"] = float(n)
        elif "tow" in label and "capacity" in label:
            n = num(vals[0])
            if n:
                specs["towing_capacity_kg"] = float(n)
                specs["_tow_raw"] = vals
    return specs


def extract_features(html: str) -> list[str]:
    feats = []
    # common WP blocks
    for pat in [
        r'<li[^>]*class="[^"]*feature[^"]*"[^>]*>(.*?)</li>',
        r'<div[^>]*class="[^"]*feature[^"]*"[^>]*>(.*?)</div>',
    ]:
        for m in re.finditer(pat, html, re.I | re.S):
            t = re.sub(r"<[^>]+>", " ", m.group(1))
            t = re.sub(r"\s+", " ", t).strip()
            if 20 < len(t) < 300:
                feats.append(t)
    # h3/h4 + p pairs in highlights
    for m in re.finditer(
        r"<h[34][^>]*>(.*?)</h[34]>\s*<p[^>]*>(.*?)</p>", html, re.I | re.S
    ):
        title = re.sub(r"<[^>]+>", " ", m.group(1))
        body = re.sub(r"<[^>]+>", " ", m.group(2))
        title = re.sub(r"\s+", " ", title).strip()
        body = re.sub(r"\s+", " ", body).strip()
        if title and body and len(title) < 80:
            feats.append(f"{title}: {body}"[:280])
    # dedupe
    out = []
    seen = set()
    for f in feats:
        k = f.lower()[:60]
        if k in seen:
            continue
        seen.add(k)
        out.append(f)
    return out[:12]


def pick_clean_hero(html: str, key: str) -> dict | None:
    """Prefer square-ish product renders over 1800x600 lifestyle banners."""
    urls = []
    og = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html, re.I
    )
    if not og:
        og = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            html,
            re.I,
        )
    if og:
        urls.append(og.group(1))
    for u in re.findall(
        r'https?://cdn\.ep-portal\.net/products/[^"\'\s>]+\.(?:webp|jpg|png)', html, re.I
    ):
        if "thumbnail" in u.lower() or "-300w" in u.lower() or "-768w" in u.lower():
            continue
        urls.append(u)
    # unique preserve order
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)

    best = None
    for i, u in enumerate(uniq[:25]):
        try:
            r = requests.get(u, timeout=40, headers=HEADERS)
            if r.status_code != 200 or len(r.content) < 8000:
                continue
            data = r.content
            # save temp and check dims
            tmp = Path("staging/ep1274_heroes") / f"_probe_{key}_{i}.bin"
            tmp.write_bytes(data)
            im = Image.open(tmp)
            w, h = im.size
            ratio = w / max(h, 1)
            md5 = hashlib.md5(data).hexdigest()
            score = 0
            # prefer near-square or portrait product shots
            if 0.7 <= ratio <= 1.4:
                score += 50
            elif ratio > 2.2:  # banner
                score -= 40
            if w >= 600 and h >= 600:
                score += 20
            if "attr_5" in u:  # often og product
                score += 10
            if "attr_11" in u and ratio > 2:
                score -= 20
            info = {
                "url": u,
                "w": w,
                "h": h,
                "ratio": round(ratio, 2),
                "bytes": len(data),
                "md5": md5,
                "score": score,
            }
            print(f"  cand {key} {w}x{h} r={ratio:.2f} score={score} {u[-60:]}")
            if best is None or score > best["score"]:
                best = info
                best["data"] = data
                best["im"] = im.convert("RGB")
        except Exception as e:
            print(f"  skip {u[-40:]}: {e}")
    if best:
        png = OUT / f"best_{key}.png"
        best["im"].save(png)
        best["png"] = str(png)
        del best["im"]
        del best["data"]
        print(f"  BEST {key}: {best['w']}x{best['h']} score={best['score']} md5={best['md5']}")
    return best


def main() -> None:
    results = {}
    for key, url in URLS.items():
        print(f"\n=== {key} {url} ===")
        r = requests.get(url, timeout=60, headers=HEADERS)
        html = r.text
        (RAW / f"{key}.html").write_text(html, encoding="utf-8", errors="replace")
        specs = parse_specs_from_html(html)
        feats = extract_features(html)
        # also get description from og/desc
        desc = ""
        m = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', html, re.I
        )
        if m:
            desc = m.group(1)
        title = ""
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()
        hero = pick_clean_hero(html, key)
        print(f"  title={title[:80]}")
        print(f"  specs={ {k:v for k,v in specs.items() if not k.startswith('_')} }")
        print(f"  feats={len(feats)}")
        for f in feats[:5]:
            print(f"    - {f[:100]}")
        results[key] = {
            "url": url,
            "title": title,
            "desc": desc,
            "specs": specs,
            "features": feats,
            "hero": hero,
        }

    # Brochure text parse for discontinued
    bro_dir = Path("staging/ep1274_brochures")
    bro_specs = {}
    for txt in bro_dir.glob("*.txt"):
        text = txt.read_text(encoding="utf-8", errors="replace")
        # look for number patterns near capacity
        print(f"\n=== BROCHURE TEXT {txt.name} len={len(text)} ===")
        print(text[:1500])
        print("---")
        # try find kg numbers with context
        for m in re.finditer(r"(.{0,40})(\d{3,5})\s*kg(.{0,40})", text, re.I):
            print(f"  kgctx: {m.group(0).replace(chr(10),' ')[:120]}")
        bro_specs[txt.stem] = text[:5000]

    # EU2025 text mentions around ES20-WA
    eu = (bro_dir / "EU2025.txt").read_text(encoding="utf-8", errors="replace")
    for token in ["ES20", "ES12", "WPL", "HPL", "QDD", "EPT20-30", "RPL301", "RAP"]:
        idxs = [m.start() for m in re.finditer(re.escape(token), eu, re.I)]
        print(f"\nEU2025 token {token}: {len(idxs)} hits")
        for i in idxs[:3]:
            print(repr(eu[max(0, i - 40) : i + 80]))

    Path("staging/reports/_ep1274_deep.json").write_text(
        json.dumps(
            {
                "pages": {
                    k: {
                        **{kk: vv for kk, vv in v.items() if kk != "hero"},
                        "hero": {hk: hv for hk, hv in (v.get("hero") or {}).items()},
                    }
                    for k, v in results.items()
                }
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print("\nWrote _ep1274_deep.json")


if __name__ == "__main__":
    main()
