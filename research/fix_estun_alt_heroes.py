"""Patch Estun robots whose en.estun.com heroes are unreachable (addlink 502).

Uses reachable alternate heroes only:
- sibling CDN URLs already proven on prod (hash-rejected phone icons)
- www.estun.com /uploads/ when the asset matches the product form factor

Does NOT re-run auto media refresh.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env  # noqa: E402

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient  # noqa: E402
from import_staging import resolve_created_by_id  # noqa: E402
from map_to_bulk_import import staging_dict_to_bulk_import_row  # noqa: E402
from robot_auto_research import resolve_company_slug, slugify_robot_name  # noqa: E402

COMPANY_ID = 220
PHONE_HASH = "c7180ca80d3fb21d"  # known Estun footer phone icon on CDN
OWNED_CDN_HOSTS = ("cdn.robotaigeek.com", "robotaigeek.s3", "amazonaws.com")

# Direct reachable OEM URLs (www.estun.com /uploads/). Owned CDN siblings cannot be
# re-copied by prod copy-media (intentionally fail-closed), so never stage those.
CN_FAMILY_HEROES: dict[str, dict[str, str]] = {
    "ecr_pallet": {
        "url": "https://www.estun.com/uploads/20260109/74f3d1cc985c46bddc83bc858184637c.png",
        "source_page_url": "https://www.estun.com/mdjqr/254.html",
        "match_reason": "CN Estun palletizing series hero (iER60-2000-PL page); ECR is Co-Palletizer family.",
    },
    "er_articulated": {
        "url": "https://www.estun.com/uploads/20250903/1ee2b7172376d1bd128ba6139c7e9727.png",
        "source_page_url": "https://www.estun.com/gjjjqr/355.html",
        "match_reason": "CN Estun iER7-910-MI-C hero; articulated ER / ER-DB / MI family visual.",
    },
    "s_collab": {
        "url": "https://www.estun.com/uploads/20251101/ad5a130771e25561b3fc22f7868e4242.png",
        "source_page_url": "https://www.estun.com/xzjqr/381.html",
        "match_reason": "CN Estun S-Pro collaborative lineup hero.",
    },
}

SCARA_MAP_PATH = _RESEARCH_DIR / "staging" / "reports" / "estun_cn_scara_map.json"


def _is_owned_cdn(url: str) -> bool:
    low = (url or "").lower()
    return any(h in low for h in OWNED_CDN_HOSTS)


def _load_scara_map() -> dict[str, dict]:
    if not SCARA_MAP_PATH.is_file():
        return {}
    data = json.loads(SCARA_MAP_PATH.read_text(encoding="utf-8"))
    return data.get("scara") or {}


def _core_name(name: str) -> str:
    n = (name or "").strip()
    for prefix in (
        "Estun Collaborative Robot ",
        "Estun M-Series Mobile Manipulator ",
        "Estun ",
    ):
        if n.startswith(prefix):
            n = n[len(prefix) :]
    return n.strip().upper()


# CN PDP scrape sometimes glued nav models onto the wrong page hero.
_BAD_SCARA_IMAGE_URLS = {
    "https://www.estun.com/uploads/20260109/4c316236c4ddfa7ae7637e4e8494fce3.png",  # ER45 BD nav asset
}


def _match_scara_cn(name: str, scara_map: dict[str, dict]) -> dict | None:
    """Map SC/SR variant names onto CN SCARA PDP heroes."""
    core = _core_name(name)
    if not re.search(r"-(SC|SR)", core):
        return None
    # Normalize C/HI/UNO suffixes toward catalog keys
    candidates = [core]
    if core.endswith("-C"):
        candidates.append(core[:-2])
    if "-SC" in core:
        candidates.append(core.replace("-SC-C", "-SR"))
        candidates.append(core.replace("-SC", "-SR"))
    if core.endswith("-SR-C"):
        candidates.append(core.replace("-SR-C", "-SR"))
    # ER3-500 CN page scraped a wrong nav image — use ER3-400-SR
    if core.startswith("ER3-500"):
        candidates = ["ER3-400-SR", *candidates]
    # ER12-900 has no CN PDP — nearest ER10-800-SR
    if core.startswith("ER12-900"):
        candidates.append("ER10-800-SR")
    if core.startswith("ER20-800") and "HI" not in core:
        candidates.append("ER20-800-SR-HI")
    if core.startswith("ER20-1000") and "HI" not in core and "UNO" not in core:
        candidates.append("ER20-1000-SR-HI")
    for key in candidates:
        entry = scara_map.get(key)
        if not entry:
            continue
        if entry.get("image") in _BAD_SCARA_IMAGE_URLS:
            continue
        return {
            "url": entry["image"],
            "source_page_url": entry.get("page") or "https://www.estun.com/scara/",
            "match_reason": f"CN Estun SCARA PDP hero matched as {key}.",
        }
    # Fallback: ER10-700-SR family SCARA look
    fallback = scara_map.get("ER10-700-SR")
    if fallback and fallback.get("image") not in _BAD_SCARA_IMAGE_URLS:
        return {
            "url": fallback["image"],
            "source_page_url": fallback.get("page") or "https://www.estun.com/scara/",
            "match_reason": "CN Estun SCARA family hero (ER10-700-SR) fallback.",
        }
    return None


def _family_cn(name: str, family_key: str) -> dict | None:
    core = _core_name(name)
    fk = family_key or ""
    if fk == "estun:ecr" or core.startswith("ECR"):
        return CN_FAMILY_HEROES["ecr_pallet"]
    if fk == "estun:er-db" or core.startswith("ER-DB"):
        return CN_FAMILY_HEROES["er_articulated"]
    if fk in {"estun:collaborative", "estun:s-series"} or core.startswith("EMR") or core.startswith("S"):
        return CN_FAMILY_HEROES["s_collab"]
    if fk in {"estun:er", "estun:uno", "estun:m-series"}:
        return CN_FAMILY_HEROES["er_articulated"]
    return CN_FAMILY_HEROES["er_articulated"]

REPORT = _RESEARCH_DIR / "staging" / "reports" / "estun_alt_heroes_apply.json"


def _sha16(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]


def _validate_image(url: str, *, referer: str = "https://www.estun.com/") -> dict[str, Any]:
    if _is_owned_cdn(url):
        return {"ok": False, "reason": "owned_cdn_not_copyable"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": referer,
    }
    try:
        resp = requests.get(url, headers=headers, timeout=45)
    except requests.RequestException as exc:
        return {"ok": False, "reason": str(exc)[:120]}
    content = resp.content
    if resp.status_code != 200 or len(content) < 10_000:
        return {"ok": False, "reason": f"http={resp.status_code} bytes={len(content)}"}
    digest = _sha16(content)
    if digest == PHONE_HASH:
        return {"ok": False, "reason": "phone_icon_hash", "hash": digest}
    try:
        im = Image.open(BytesIO(content))
        w, h = im.size
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"not_image:{exc}"[:120]}
    if w * h < 40_000:
        return {"ok": False, "reason": f"tiny_canvas:{w}x{h}", "hash": digest}
    return {"ok": True, "hash": digest, "bytes": len(content), "w": w, "h": h, "url": url}


def _needs_alt(robot: dict) -> bool:
    """True when robot lacks s3_image (including owned-CDN hotlinks that cannot be recopy'd)."""
    if robot.get("s3_image"):
        return False
    image = (robot.get("image") or "").strip()
    if not image:
        return True
    if image.startswith("https://en.estun.com"):
        return True
    if _is_owned_cdn(image):
        return True
    return False


def build_plan(client: ResearchApiClient, company_id: int = COMPANY_ID) -> list[dict]:
    robots = list(client.list_robots_for_company(company_id))
    scara_map = _load_scara_map()
    validated_cn: dict[str, dict] = {}
    plan: list[dict] = []

    def resolve_cn(direct: dict) -> dict | None:
        url = direct["url"]
        if url in validated_cn:
            meta = validated_cn[url]
        else:
            meta = _validate_image(url)
            validated_cn[url] = meta
        if not meta.get("ok"):
            return None
        return {
            **meta,
            "source_page_url": direct["source_page_url"],
            "match_reason": direct["match_reason"],
            "media_class": "family_photo",
            "image_scope": "family",
            "source_tier": "official_family",
        }

    for robot in robots:
        if not _needs_alt(robot):
            continue
        name = robot["name"]
        fk = robot.get("family_key") or ""
        chosen: dict | None = None
        strategy = "NONE"

        scara = _match_scara_cn(name, scara_map)
        if scara:
            chosen = resolve_cn(scara)
            if chosen:
                strategy = "cn_scara"

        if not chosen:
            family = _family_cn(name, fk)
            if family:
                chosen = resolve_cn(family)
                if chosen:
                    strategy = f"cn_family:{fk or 'other'}"

        plan.append(
            {
                "id": robot["id"],
                "name": name,
                "family_key": fk,
                "old_image": robot.get("image") or "",
                "alt_image": (chosen or {}).get("url") or "",
                "strategy": strategy,
                "candidate": chosen,
            }
        )
    return plan


def stage_and_import(
    client: ResearchApiClient,
    plan: list[dict],
    *,
    force_overwrite: bool,
    replace_media: bool,
    created_by_id: int,
    dry_run: bool,
) -> dict:
    company = client.get_company(COMPANY_ID)
    slug = resolve_company_slug(str(company.get("name") or ""), company.get("slug"))
    staging_dir = _RESEARCH_DIR / "staging" / "robots" / slug / "_alt_heroes"
    staging_dir.mkdir(parents=True, exist_ok=True)
    robots_by_id = {r["id"]: r for r in client.list_robots_for_company(COMPANY_ID)}

    rows: list[dict] = []
    staged = 0
    for item in plan:
        cand = item.get("candidate")
        if not cand or not cand.get("url"):
            continue
        robot = robots_by_id.get(item["id"]) or {}
        data = {
            "id": item["id"],
            "name": item["name"],
            "company_slug": slug,
            "company_name": company.get("name") or "Estun Robotics",
            "model_name": robot.get("model_name") or item["name"],
            "description": (robot.get("description") or "").strip()
            or f"Estun industrial robot model {item['name']}.",
            "purpose": (robot.get("purpose") or "").strip(),
            "url": (robot.get("url") or "").strip() or "https://en.estun.com/",
            "image": cand["url"],
            "images": [
                {
                    "url": cand["url"],
                    "source_page_url": cand.get("source_page_url") or "",
                    "source_tier": cand.get("source_tier") or "official_family",
                    "source_publisher": "Estun",
                    "media_class": cand.get("media_class") or "family_photo",
                    "image_scope": cand.get("image_scope") or "family",
                    "rights_status": "review_required",
                    "match_reason": cand.get("match_reason") or "",
                }
            ],
            "family_key": robot.get("family_key") or item.get("family_key") or "",
            "family_name": robot.get("family_name") or "",
            "variant_code": robot.get("variant_code") or "",
            "product_url_scope": robot.get("product_url_scope") or "exact_variant",
            "sources": [{"url": cand.get("source_page_url") or "https://www.estun.com/", "type": "website"}],
            "research_notes": (
                f"Alternate hero patch 2026-07-15: {item['strategy']}. "
                "en.estun.com/static/upload images redirect to addlink CDN (502)."
            ),
            "manufacturer_country_code": "CN",
        }
        path = staging_dir / f"{slugify_robot_name(item['name'])}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        rows.append(staging_dict_to_bulk_import_row(data))
        staged += 1

    result: dict[str, Any] = {"staged": staged, "import": None}
    if dry_run or not rows:
        return result

    # Import in small batches to avoid gateway timeouts
    created_by = resolve_created_by_id(created_by_id)
    ok = fail = 0
    details = []
    batch_size = 5
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        try:
            resp = client.bulk_import_robots(
                batch,
                update_existing=True,
                patch_existing=not force_overwrite,
                status="pending_review",
                skip_company_update=True,
                created_by_id=created_by,
                replace_media=replace_media,
            )
            details.append(resp)
            if resp.get("ok") is False or resp.get("errors"):
                fail += 1
            else:
                ok += 1
        except Exception as exc:  # noqa: BLE001
            fail += 1
            details.append({"error": str(exc)})
        time.sleep(0.3)
    result["import"] = {"batches_ok": ok, "batches_fail": fail, "details": details}
    return result


def trigger_copy_media(robot_ids: list[int]) -> dict:
    import os

    api = os.environ.get("IMPORT_SYNC_API_BASE_URL", "").rstrip("/")
    admin = api.replace("/api/v1", "")
    secret = os.environ.get("INTERNAL_API_SECRET", "").strip()
    if not secret:
        env_file = _RESEARCH_DIR.parents[1] / "robotaigeek-server" / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("INTERNAL_API_SECRET="):
                    secret = line.split("=", 1)[1].strip()
                    break
    if not secret:
        return {"ok": False, "error": "INTERNAL_API_SECRET missing"}

    ok = fail = 0
    errors = []
    for rid in robot_ids:
        url = f"{admin}/admin/robots/robot/content-queue/api/robot/{rid}/copy-media/"
        try:
            resp = requests.post(url, headers={"X-Internal-Secret": secret}, timeout=120)
            if resp.ok:
                ok += 1
            else:
                fail += 1
                errors.append({"id": rid, "status": resp.status_code, "body": resp.text[:200]})
        except requests.RequestException as exc:
            fail += 1
            errors.append({"id": rid, "error": str(exc)})
        time.sleep(0.15)
    return {"ok": fail == 0, "copied_ok": ok, "copied_fail": fail, "errors": errors[:20]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch Estun alternate reachable heroes")
    parser.add_argument("--company-id", type=int, default=COMPANY_ID)
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply-import", action="store_true")
    parser.add_argument("--force-overwrite", action="store_true", default=True)
    parser.add_argument("--no-force-overwrite", action="store_true")
    parser.add_argument(
        "--replace-media",
        action="store_true",
        default=True,
        help="Wipe prior photos so broken en.estun.com heroes are replaced (default on).",
    )
    parser.add_argument("--no-replace-media", action="store_true")
    parser.add_argument("--copy-media", action="store_true")
    parser.add_argument("--created-by-id", type=int, default=1)
    args = parser.parse_args()

    force = False if args.no_force_overwrite else True
    replace = False if args.no_replace_media else True

    client = ResearchApiClient()
    plan = build_plan(client, args.company_id)
    with_alt = [p for p in plan if p.get("alt_image")]
    missing = [p["name"] for p in plan if not p.get("alt_image")]
    summary = {
        "targets": len(plan),
        "with_alt": len(with_alt),
        "missing": missing,
        "strategies": {},
    }
    for p in plan:
        key = (p.get("strategy") or "NONE").split(":")[0]
        summary["strategies"][key] = summary["strategies"].get(key, 0) + 1
    print(json.dumps(summary, indent=2))

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"summary": summary, "plan": plan}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {REPORT}")

    if not args.apply_import and not args.dry_run:
        print("Pass --dry-run or --apply-import")
        return 0

    imp = stage_and_import(
        client,
        plan,
        force_overwrite=force,
        replace_media=replace,
        created_by_id=args.created_by_id,
        dry_run=args.dry_run or not args.apply_import,
    )
    print(json.dumps({k: v for k, v in imp.items() if k != "import"}, indent=2))
    if imp.get("import"):
        print(json.dumps({
            "batches_ok": imp["import"]["batches_ok"],
            "batches_fail": imp["import"]["batches_fail"],
        }, indent=2))

    if args.copy_media and args.apply_import and not args.dry_run:
        ids = [p["id"] for p in with_alt]
        copy_result = trigger_copy_media(ids)
        print(json.dumps(copy_result, indent=2))
        REPORT.write_text(
            json.dumps(
                {"summary": summary, "plan": plan, "import": imp, "copy_media": copy_result},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return 0 if copy_result.get("ok") else 1
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
