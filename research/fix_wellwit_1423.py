"""Full enrichment for Shenzhen Wellwit Robotics (company 1423) — 43 AMR/AGV robots.

Gaps: all lacked family_* and typed specs; 31 lacked a hero; names carried a
redundant "Wellwit Robotics" prefix. Sources: each model's own wellwit.com page
(clean, consistent spec tables — parsed in _wellwit_parse.py; og:image heroes
visually verified via a 43-cell contact sheet, all correct-product AMR renders).

Per robot: clean model name + family (W3/W5/W6/W8 AMR series, WMF-APR/WMF1000/
WMF-300 forklifts) + typed specs (payload/weight/L*W*H/speed km/h where the page
states them) + wheeled movement + Available + the verified og hero (PATCH image +
copy-media; existing galleries preserved). Features/description left as-is.

    cd scripts/research && export PYTHONIOENCODING=utf-8
    python fix_wellwit_1423.py            # dry-run (first 5)
    python fix_wellwit_1423.py --apply
"""
from __future__ import annotations
import argparse, json, os, re, time
import requests
from load_env import load_research_env
load_research_env()
from api_client import ResearchApiClient  # noqa: E402

WHEELED = [4]
AVAILABLE = 11
plan = json.load(open(os.path.join(os.environ["TEMP"], "wellwit_plan.json"), encoding="utf-8"))


def _admin_base() -> str:
    return os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/").replace("/api/v1", "")


def _headers() -> dict:
    s = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not s:
        raise RuntimeError("INTERNAL_API_SECRET missing")
    return {"X-Internal-Secret": s}


def copy_media(rid: int) -> str:
    r = requests.post(f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/?force=1",
                      headers=_headers(), timeout=240)
    return f"{r.status_code}"


def fam_name(fk: str) -> str:
    return {
        "wellwit:wmf-apr": "WMF-APR Pallet AMR", "wellwit:wmf1000": "WMF1000 Autonomous Forklift",
        "wellwit:wmf300": "WMF-300 Autonomous Forklift", "wellwit:w8": "W8 Series AMR",
        "wellwit:w6": "W6 Series AMR", "wellwit:w5": "W5 Series AMR", "wellwit:w3": "W3 Series AMR",
    }.get(fk, "")


def build_patch(x: dict) -> dict:
    specs = {k: v for k, v in x["specs"].items() if not k.startswith("_")}
    body = {
        "name": x["model"],
        "model_name": x["model"], "variant_code": x["model"], "variant_label": x["model"],
        "family_key": x["fk"], "family_name": fam_name(x["fk"]), "product_url_scope": "exact_variant",
        "movement_types": WHEELED, "availability_status": AVAILABLE,
        "image": x["og"], "s3_image": None,
    }
    body.update(specs)
    return body


def _bo(fn):
    for a in range(7):
        try:
            return fn()
        except Exception as e:
            if any(c in str(e) for c in ("429", "502", "503")):
                time.sleep(4 * (a + 1)); continue
            raise
    raise SystemExit("gave up")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    client = ResearchApiClient()

    items = plan if args.apply else plan[:5]
    for x in items:
        body = build_patch(x)
        print(f"{x['id']} {x['model']:16} fam={x['fk'].replace('wellwit:','')} "
              f"specs={ {k:v for k,v in x['specs'].items() if not k.startswith('_')} } hero={'Y' if x['og'] else '-'}")
        if not args.apply:
            continue
        _bo(lambda: client._patch(f"robots/robots/{x['id']}/", body))
        cm = copy_media(x["id"])
        print(f"     patched + copy-media {cm}")
    if not args.apply:
        print("\n(dry-run of first 5; --apply for all 43)")


if __name__ == "__main__":
    main()
