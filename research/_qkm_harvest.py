"""Harvest official product images + specs for QKM Technologies (company 1946).

The 12 draft rows map 1:1 onto QKM's real catalogue:
  SCARA   /en/product/10.html -> AH3 AH6 AH10 AH20 HM3 HM8 PG6X
  Delta   /en/product/11.html -> AP3X AP8X AP15X AP25X
  Cobot   /en/product/13.html -> MS6MT

Only /upload/images/product/ and body /upload/images/ueditor/ images belong to the
model; everything else on the page is site chrome (/navigation/, /static/, /slides/,
/article/) and would cross-attribute across all 12 rows.
"""
import json
import re
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BASE = "https://www.qkmtech.com"

# robot_id -> (model, english product page)
CATALOG = {
    7045: ("AH3",   "/en/p/21.html"),
    7046: ("AH6",   "/en/p/25.html"),
    7047: ("AH10",  "/en/p/24.html"),   # was pointing at the Chinese /p/5.html
    7048: ("AH20",  "/en/p/26.html"),
    7049: ("HM3",   "/en/p/23.html"),
    7050: ("HM8",   "/en/p/22.html"),
    7051: ("PG6X",  "/en/p/60.html"),
    7052: ("AP3X",  "/en/p/27.html"),
    7053: ("AP8X",  "/en/p/28.html"),
    7054: ("AP15X", "/en/p/66.html"),
    7055: ("AP25X", "/en/p/67.html"),
    7056: ("MS6MT", "/en/p/37.html"),
}

FAMILY = {
    "AH":  ("QKM AH Series SCARA", "qkm:ah-scara"),
    "HM":  ("QKM HM Series High-Speed SCARA", "qkm:hm-scara"),
    "PG":  ("QKM PG Series SCARA", "qkm:pg-scara"),
    "AP":  ("QKM AP Series Delta", "qkm:ap-delta"),
    "MS":  ("QKM MS Series Co-robot", "qkm:ms-cobot"),
}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")


def family_for(model: str):
    for prefix, val in FAMILY.items():
        if model.startswith(prefix):
            return val
    return ("", "")


def harvest(model: str, path: str) -> dict:
    html_src = get(BASE + path)

    imgs, seen = [], set()
    # Product-gallery images, then body (ueditor) images — in document order.
    # Filenames may contain spaces ("PG6X 450X450px.png") AND CJK characters
    # ("AP15X-英文版线图.jpg"), so the character class must stop only at the
    # attribute quote, and the path needs full percent-encoding (a bare space or
    # CJK byte makes urllib raise UnicodeEncodeError rather than fetch).
    for m in re.findall(r'/upload/images/(?:product|ueditor)/[^"\']+?\.(?:png|jpg|jpeg)', html_src):
        url = BASE + urllib.parse.quote(m)
        if url not in seen:
            seen.add(url)
            imgs.append(url)

    # Spec table: QKM renders "Payload 3kg" style rows in the body text.
    text = re.sub(r"<script.*?</script>", " ", html_src, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    specs = {}
    # Real label set on QKM spec tables (checked against AH3/AP3X/AP15X/MS6MT):
    #   "Max. load 3 kg"            older pages
    #   "Payload(Max.) 15 kg"       newer AP15X/AP25X pages
    #   "Arm length J1+J2 400 mm"   SCARA   / "Arm length 962 mm" cobot
    #   "Max. range of motion Diameter 1600 mm"  delta — a working DIAMETER, so it
    #                               is deliberately NOT stored as reach_mm
    #   "Repeated positioning accuracy ± 0.01 mm"
    #   "Total weight 17 kg" / "Number of axes 4"
    pay = re.search(
        r"(?:Payload\s*(?:\(\s*Max\.?\s*\))?|Max\.?\s*load)\s*[:：]?\s*([\d.]+)\s*kg",
        text, re.I)
    if pay:
        specs["payload_kg"] = float(pay.group(1))

    reach = re.search(r"Arm\s*length(?:\s*J1\+J2)?\s*[:：]?\s*([\d.]+)\s*mm", text, re.I)
    if reach:
        specs["reach_mm"] = float(reach.group(1))
    else:
        dia = re.search(r"range\s*of\s*motion\s*Diameter\s*[:：]?\s*([\d.]+)\s*mm", text, re.I)
        if dia:
            specs["work_diameter_mm"] = float(dia.group(1))  # kept out of reach_mm

    rep = re.search(
        r"Repeat(?:ed\s*positioning\s*accuracy|ability)(?:\s*J1\+J2)?\s*[:：]?\s*±?\s*([\d.]+)\s*mm",
        text, re.I)
    if rep:
        specs["repeatability_mm"] = float(rep.group(1))

    wt = re.search(r"Total\s*weight\s*[:：]?\s*([\d.]+)\s*kg", text, re.I)
    if wt:
        specs["weight_kg"] = float(wt.group(1))

    dof = re.search(r"Number\s*of\s*axes\s*[:：]?\s*(\d+)", text, re.I)
    if dof:
        specs["dof"] = int(dof.group(1))

    ip = re.search(r"IP\s*[Pp]rotection\s*(?:grade|class)\s*[:：]?\s*(IP\s*\d{2})", text, re.I)
    if ip:
        specs["ip_rating"] = ip.group(1).replace(" ", "")

    # Full manufacturer model code, e.g. AH3-0400-0204-1700 / MS6MT-0900-3546.
    code = re.search(rf"\b({re.escape(model)}-[\d\-]+)\b", text)
    if code:
        specs["variant_code"] = code.group(1)

    fam_name, fam_key = family_for(model)
    return {
        "model": model,
        "url": BASE + path,
        "images": imgs,
        "specs": specs,
        "family_name": fam_name,
        "family_key": fam_key,
        "text_len": len(text),
    }


def main() -> int:
    out = {}
    for rid, (model, path) in CATALOG.items():
        try:
            rec = harvest(model, path)
        except Exception as exc:  # noqa: BLE001
            print(f"{rid} {model}: ERROR {exc}")
            continue
        out[rid] = rec
        print(f"{rid} {model:6s} imgs={len(rec['images']):2d} specs={rec['specs']} "
              f"family={rec['family_key']}")
        for i in rec["images"]:
            print("      ", i)

    dest = ("C:/Users/tramk/AppData/Local/Temp/claude/"
            "C--Github-Personal-robot-ai-geek/9cff51dd-ca8d-479a-8bd9-29d05105ebd3/"
            "scratchpad/qkm_harvest.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("\nsaved", dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
