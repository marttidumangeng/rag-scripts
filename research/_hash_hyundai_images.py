"""Download and hash HDC static thumbs + FPD/HDC API heroes. Read-only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import requests

SITE = "https://hd-hyundairobotics.com"
API = "https://www.hd-hyundairobotics.com/api/v1"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{SITE}/en/biz/hdc",
}
OUT = Path(__file__).resolve().parent / "_hyundai_image_hash_report.json"


def unwrap(payload: dict) -> dict:
    if isinstance(payload, dict) and "resCd" in payload and "data" in payload:
        return payload.get("data") or {}
    return payload


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def fetch_url(url: str) -> tuple[int, int, str]:
    r = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=60)
    return r.status_code, len(r.content), sha_bytes(r.content)


report: dict = {"static_thumbs": {}, "api_products": [], "notes": []}

# Static HDC thumbs used by fix script
for name in ("thumb_prod_hdc_01.png", "thumb_prod_hdc_02.png", "thumb_prod_hdc_03.png"):
    url = f"{SITE}/resources/resource/images/thumb/{name}"
    try:
        status, size, digest = fetch_url(url)
        report["static_thumbs"][name] = {"url": url, "status": status, "bytes": size, "sha256_16": digest}
        print(f"STATIC {name}: status={status} bytes={size} sha={digest}")
    except Exception as e:
        report["static_thumbs"][name] = {"url": url, "error": str(e)}
        print(f"STATIC {name}: ERROR {e}")

# HDC API page 0
for prd_type, label in (("60010007", "HDC/cobot"), ("60010002", "FPD")):
    r = requests.get(
        f"{API}/product/page",
        params={"prdTypeCd": prd_type, "prdStateCd": "00010001", "page": 0, "size": 20},
        headers=HEADERS,
        timeout=60,
    )
    r.raise_for_status()
    data = unwrap(r.json())
    items = data.get("content") or []
    print(f"\nAPI {label} page0: total={data.get('totalElements')} got={len(items)}")
    for item in items:
        bd = item.get("bdContent") or {}
        atts = bd.get("attachments") or []
        att0 = atts[0] if atts else bd.get("bdcThumbFile1")
        link = (att0 or {}).get("fileDwLink") if isinstance(att0, dict) else None
        ori = (att0 or {}).get("fileOriNm") if isinstance(att0, dict) else None
        entry = {
            "type": label,
            "prdSeq": item.get("prdSeq"),
            "prdNm": (item.get("prdNm") or "").replace("\r", "").strip(),
            "fileOriNm": ori,
            "fileSeq": (att0 or {}).get("fileSeq") if isinstance(att0, dict) else None,
            "fileDwLink": link,
        }
        if link:
            try:
                status, size, digest = fetch_url(link)
                entry.update({"img_status": status, "img_bytes": size, "sha256_16": digest})
                print(f"  {entry['prdNm']}: ori={ori} bytes={size} sha={digest}")
            except Exception as e:
                entry["error"] = str(e)
                print(f"  {entry['prdNm']}: ERROR {e}")
        report["api_products"].append(entry)

# Compare static thumbs
thumbs = report["static_thumbs"]
if all("sha256_16" in thumbs[k] for k in ("thumb_prod_hdc_01.png", "thumb_prod_hdc_02.png")):
    same = thumbs["thumb_prod_hdc_01.png"]["sha256_16"] == thumbs["thumb_prod_hdc_02.png"]["sha256_16"]
    report["notes"].append(f"HDC25 vs HDC35 static thumbs identical bytes: {same}")
    print("\nHDC25 vs HDC35 static identical:", same)

# Compare API HDC images if present
hdc = [p for p in report["api_products"] if p["type"] == "HDC/cobot"]
by_name = {p["prdNm"]: p for p in hdc}
if "HDC25-18" in by_name and "HDC35-18" in by_name:
    a, b = by_name["HDC25-18"], by_name["HDC35-18"]
    same_api = a.get("sha256_16") and a.get("sha256_16") == b.get("sha256_16")
    report["notes"].append(
        f"HDC25 vs HDC35 API fileSeq distinct: {a.get('fileSeq') != b.get('fileSeq')}; "
        f"bytes identical: {same_api}; ori={a.get('fileOriNm')} vs {b.get('fileOriNm')}"
    )
    print("API HDC25 vs HDC35 identical bytes:", same_api)
    print("API fileSeq:", a.get("fileSeq"), b.get("fileSeq"))
    print("API ori:", a.get("fileOriNm"), b.get("fileOriNm"))

# FPD pairwise uniqueness
fpd = [p for p in report["api_products"] if p["type"] == "FPD" and p.get("sha256_16")]
digests = [p["sha256_16"] for p in fpd]
report["notes"].append(f"FPD distinct image hashes: {len(set(digests))}/{len(digests)}")
print(f"\nFPD distinct hashes: {len(set(digests))}/{len(digests)}")

OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("SAVED", OUT)
