"""Recon for Comau (company 245) pending_review robots.

Fetches each target PDP, parses the technical-specification table (label line
followed by value line), collects product/header images, and dumps JSON for
`fix_comau_robots.py` to consume. No writes to the DB.

    python comau_recon.py --ids 4165,4166        # explicit ids
    python comau_recon.py --all-pending          # every pending_review robot
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape
from pathlib import Path

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 245
BASE = "https://www.comau.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# Spec label -> canonical key. Values sit on the NEXT non-empty line.
# Comau uses two table dialects: NJ/PAL put the unit in the LABEL
# ("Maximum wrist payload (Kg)" -> "210"), while MyCo/Rebel/Racer put it in the
# VALUE ("Maximum wrist payload" -> "5 kg"). Both are handled.
SPEC_LABELS = {
    "number of axes": "axes",
    "axes": "axes",
    "degree of freedom": "dof",
    "robot type": "robot_type",
    "maximum wrist payload (kg)": "payload_kg",
    "maximum wrist payload": "payload_kg",
    "payload (kg)": "payload_kg",
    "payload": "payload_kg",
    "maximum payload (kg)": "payload_kg",
    "maximum payload": "payload_kg",
    "rated payload (kg)": "payload_kg",
    "additional load on forearm (kg)": "forearm_load_kg",
    "additional load on forearm": "forearm_load_kg",
    "maximum horizontal reach (mm)": "reach_mm",
    "maximum horizontal reach": "reach_mm",
    "horizontal reach (mm)": "reach_mm",
    "horizontal reach": "reach_mm",
    "horizontal reach (radius)": "reach_mm",
    "maximum reach (mm)": "reach_mm",
    "reach (mm)": "reach_mm",
    "vertical reach (z-stroke)": "vertical_reach_mm",
    "repeatability (mm)": "repeatability_mm",
    "repeatability": "repeatability_mm",
    "repeatability (x-y)": "repeatability_mm",
    "robot weight (kg)": "weight_kg",
    "robot weight": "weight_kg",
    "weight (kg)": "weight_kg",
    "protection class": "protection_class",
    "dust and water protection class": "protection_class",
    "available protection classes: ip class": "protection_class",
    "mounting position": "mounting_position",
    "tool speed": "tool_speed",
}

NUMERIC_KEYS = {
    "axes", "dof", "payload_kg", "forearm_load_kg", "reach_mm", "vertical_reach_mm",
    "weight_kg", "repeatability_mm",
}

# Site chrome / accessory banners that are never a product hero.
CHROME_TOKENS = (
    "logo", "favicon", "cropped-", "image-pop-up", "controls_header", "tech-pendant",
    "positioners", "external-axis", "slides", "comauflex", "welding-gun", "placeholder",
)


def clean_lines(html: str) -> list[str]:
    t = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    t = re.sub(r"<style[\s\S]*?</style>", " ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = unescape(t)
    out = []
    for ln in t.splitlines():
        ln = re.sub(r"[ \t]+", " ", ln).strip()
        if ln:
            out.append(ln)
    return out


# Units each numeric spec is allowed to carry. A value whose unit is not in the
# set is rejected rather than coerced -- this is what stops "Power consumption
# 350W" or a torque "35 Nm" from ever landing in weight/payload.
ALLOWED_UNITS: dict[str, set[str]] = {
    "payload_kg": {"", "kg"},
    "forearm_load_kg": {"", "kg"},
    "weight_kg": {"", "kg"},
    "reach_mm": {"", "mm", "m"},
    "vertical_reach_mm": {"", "mm", "m"},
    "repeatability_mm": {"", "mm"},
    "axes": {""},
    "dof": {""},
}


def _normalise_number(raw: str) -> str | None:
    """Comau mixes European separators: '1.300 mm' is 1300 (dot = thousands)
    while '2,5 m/s' is 2.5 (comma = decimal) and '0.02 mm' is 0.02 (dot =
    decimal). Resolve by shape, never by a blanket replace.
    """
    s = raw.strip()
    # dot/comma followed by exactly 3 digits, with a non-zero integer part -> thousands sep
    if re.fullmatch(r"\d{1,3}[.,]\d{3}", s) and not s.startswith("0"):
        return s.replace(".", "").replace(",", "")
    # comma as decimal separator ('2,5')
    if re.fullmatch(r"\d+,\d{1,2}", s):
        return s.replace(",", ".")
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return s
    return None


def _num(val: str, key: str) -> float | None:
    """Parse a spec value that may carry its unit ('5 kg', '±0.02mm', '1.300 mm').

    Rejects ranges/lists/degrees and any value whose unit doesn't belong to the
    field, so joint ranges and power figures can't masquerade as specs.
    """
    v = val.strip().replace("±", "").replace("+/-", "")
    v = re.sub(r"[“”\"']", "", v).strip()
    # Reject multi-value / range / degree strings outright.
    if re.search(r"[;/]|\bto\b|°|–|—|--", v):
        return None
    m = re.match(r"^~?\s*([\d.,]+)\s*([A-Za-z]+)?", v)
    if not m:
        return None
    norm = _normalise_number(m.group(1))
    if norm is None:
        return None
    try:
        num = float(norm)
    except ValueError:
        return None
    unit = (m.group(2) or "").lower()
    allowed = ALLOWED_UNITS.get(key)
    if allowed is not None and unit not in allowed:
        return None
    # Normalise reach to mm when the page states metres.
    if key in ("reach_mm", "vertical_reach_mm") and unit == "m" and num < 20:
        num *= 1000.0
    return num


def parse_specs(lines: list[str]) -> dict:
    specs: dict = {}
    for i, ln in enumerate(lines):
        key = SPEC_LABELS.get(ln.lower().strip())
        if not key or key in specs or i + 1 >= len(lines):
            continue
        val = lines[i + 1].strip()
        if key in NUMERIC_KEYS:
            num = _num(val, key)
            if num is not None:
                specs[key] = num
        else:
            specs[key] = val
    # Prefer an explicit "Degree of Freedom" over an "Axes" row when both exist.
    if specs.get("dof") and not specs.get("axes"):
        specs["axes"] = specs["dof"]
    return specs


def model_digits(name: str) -> str:
    """Digits that identify the model, e.g. 'NJ-210-3.1 SH' -> '21031'."""
    return re.sub(r"[^0-9]", "", name)


def parse_page(name: str, url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=45, allow_redirects=True)
    html = resp.text
    lines = clean_lines(html)

    og = re.search(r'property=["\']og:image["\'][^>]*content=["\']([^"\']+)', html) or \
        re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:image', html)
    og_img = unescape(og.group(1)) if og else ""

    ogd = re.search(r'property=["\']og:description["\'][^>]*content=["\']([^"\']+)', html)
    og_desc = unescape(ogd.group(1)).strip() if ogd else ""

    all_imgs = re.findall(
        r'(https?://[^"\'\s]+?/wp-content/uploads/[^"\'\s]+?\.(?:jpg|jpeg|png|webp))', html, re.I
    )
    renders: list[str] = []
    headers_imgs: list[str] = []
    for u in dict.fromkeys(all_imgs):
        low = u.lower()
        if any(x in low for x in CHROME_TOKENS):
            continue
        if re.search(r"-\d+x\d+\.(?:jpg|jpeg|png|webp)$", low):  # resized thumbs
            continue
        (headers_imgs if "_header" in low else renders).append(u)

    # Rank by shared model digits so sibling cross-nav renders sink.
    token = model_digits(name)

    def score(u: str) -> tuple:
        d = re.sub(r"[^0-9]", "", u.rsplit("/", 1)[-1])
        shared = 1 if token and len(token) >= 3 and token[:3] in d else 0
        return (-shared, len(u))

    renders.sort(key=score)
    headers_imgs.sort(key=score)

    paras = [
        ln for ln in lines
        if 50 <= len(ln) <= 400
        and "cookie" not in ln.lower()
        and "consent" not in ln.lower()
        and "©" not in ln
        and not ln.lower().startswith("http")
    ]

    specs = parse_specs(lines)
    return {
        "status": resp.status_code,
        "final_url": resp.url,
        "og_image": og_img,
        "og_desc": og_desc,
        "header_images": headers_imgs,
        "render_images": renders,
        "specs": specs,
        "spec_warnings": cross_check_specs(name, specs),
        "paras": paras[:8],
    }


def name_payload_reach(name: str) -> tuple[float | None, float | None]:
    """Comau encodes payload/reach in the model name:
    'NJ-210-3.1 SH' -> 210 kg / 3.1 m; 'MyCo-8-1.30' -> 8 kg / 1.30 m.
    'S-13' / 'Racer-5 SE' encode payload only.
    """
    m = re.search(r"-(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)", name)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.search(r"^[A-Za-z]+-(\d+(?:\.\d+)?)\b", name)
    if m:
        return float(m.group(1)), None
    return None, None


def cross_check_specs(name: str, specs: dict) -> list[str]:
    """Flag parsed specs that disagree with the model-name convention.

    A warning means 'do not trust this silently' -- the fixer refuses to import
    a flagged spec rather than shipping an invented number.
    """
    warns: list[str] = []
    n_pay, n_reach_m = name_payload_reach(name)
    pay = specs.get("payload_kg")
    if n_pay is not None and pay is not None:
        if abs(pay - n_pay) / max(n_pay, 1.0) > 0.2:
            warns.append(f"payload {pay} disagrees with name-implied {n_pay}")
    reach = specs.get("reach_mm")
    if n_reach_m is not None and reach is not None:
        expect = n_reach_m * 1000.0
        if abs(reach - expect) / max(expect, 1.0) > 0.15:
            warns.append(f"reach {reach} disagrees with name-implied {expect:.0f}")
    if reach is not None and reach < 100:
        warns.append(f"reach {reach} implausibly small (metre/thousands parse?)")
    w = specs.get("weight_kg")
    if w is not None and pay is not None and w < pay:
        warns.append(f"weight {w} < payload {pay} (suspect)")
    return warns


def main() -> int:
    ap = argparse.ArgumentParser(description="Recon Comau PDPs (company 245)")
    ap.add_argument("--ids", type=str, default="")
    ap.add_argument("--all-pending", action="store_true")
    ap.add_argument("--out", type=str, default="")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = client.list_robots_for_company(COMPANY_ID)
    pending = [r for r in robots if (r.get("status") or "") == "pending_review"]

    if args.ids.strip():
        want = {int(x) for x in args.ids.split(",") if x.strip().isdigit()}
        targets = [r for r in pending if int(r["id"]) in want]
    elif args.all_pending:
        targets = pending
    else:
        print("pass --ids or --all-pending", file=sys.stderr)
        return 2

    out: dict = {}
    for r in targets:
        rid = int(r["id"])
        name = r["name"]
        url = (r.get("url") or "").strip()
        if not url:
            print(f"SKIP {rid} {name}: no url")
            continue
        print(f"fetch {rid} {name} ...", flush=True)
        try:
            info = parse_page(name, url)
        except requests.RequestException as exc:
            print(f"  FAIL: {exc}")
            info = {"status": "error", "error": str(exc)}
        info["name"] = name
        info["url"] = url
        out[str(rid)] = info
        s = info.get("specs", {})
        print(
            f"  status={info.get('status')} payload={s.get('payload_kg')} reach={s.get('reach_mm')} "
            f"weight={s.get('weight_kg')} axes={s.get('axes')} renders={len(info.get('render_images', []))}"
        )

    dest = Path(args.out) if args.out else (_RESEARCH_DIR / "staging" / "reports" / "comau-recon.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {dest} ({len(out)} robots)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
