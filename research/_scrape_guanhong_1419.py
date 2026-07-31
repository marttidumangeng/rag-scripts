"""Scrape Guanhong (1419) OEM PDPs and write enrichment staging data."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env()

from api_client import ResearchApiClient
from web_extract import WebFetcher, parse_page

COMPANY_ID = 1419
OUT = _RESEARCH_DIR / "staging" / "reports" / "guanhong-1419-scrape.json"

SPEC_RE = re.compile(
    r"Model:\s*(?P<model>SZGH[-–\w]+).*?"
    r"Payload:\s*(?P<payload>[\d.]+)\s*kg\.?\s*"
    r"Reach:\s*(?P<reach>[\d.]+)\s*mm\.?\s*"
    r"(?:Structure:\s*(?P<structure>[^N]+?)\s*)?"
    r"Number of axis:\s*(?P<dof>\d+)\s*(?:Axis)?\.?\s*"
    r"Repeatability:\s*[±+]?(?P<rep>[\d.]+)\s*mm\.?\s*"
    r"Weight:\s*(?P<weight>[\d.]+)\s*kg",
    re.I | re.S,
)

PROSE_RE = re.compile(
    r"Model:\s*(?P<model>SZGH[-–\w]+).*?"
    r"(?:load capacity|payload)\s+of\s+(?P<payload>[\d.]+)\s*kg.*?"
    r"(?:maximum reach|reach)\s+of\s+(?P<reach>[\d.]+)\s*mm",
    re.I | re.S,
)

DOF_FROM_NAME = re.compile(r"(\d+)\s*Axis", re.I)
MODEL_FROM_NAME = re.compile(r"(SZGH[-–][\w-]+)", re.I)

APP_RE = re.compile(r"Applications:\s*([^.<]+)", re.I)


def clean_name(raw: str, model: str) -> str:
    # Prefer model code as display name; keep series hint
    return model.replace("--", "-")


def family_from_model(model: str) -> tuple[str, str]:
    m = model.upper().replace("--", "-")
    if "SZGH-HZ" in m or m.startswith("SZGH-HZ"):
        return "guanhong:szgh-hz", "SZGH-HZ Welding"
    if re.search(r"SZGH-H\d", m):
        return "guanhong:szgh-h", "SZGH-H Welding"
    if re.search(r"SZGH-T\d", m):
        return "guanhong:szgh-t", "SZGH-T All-In-One"
    if re.search(r"SZGH-G\d", m):
        return "guanhong:szgh-g", "SZGH-G Palletizing"
    if re.search(r"SZGH-B\d", m):
        return "guanhong:szgh-b", "SZGH-B Palletizing"
    return "guanhong:szgh", "SZGH"


def pick_hero(images: list) -> str | None:
    urls = []
    for img in images or []:
        u = img.get("url") if isinstance(img, dict) else str(img)
        if not u:
            continue
        ul = u.lower()
        if any(x in ul for x in ("/s.png", "logo", "icon", "favicon", "captcha")):
            continue
        if "thefastimg.com" in ul or "szghrobot.com" in ul or "omo-oss" in ul:
            urls.append(u.split("?")[0] if "s.png" not in ul else u)
    # Prefer portal-saas cms product images
    scored = sorted(
        set(urls),
        key=lambda u: (
            0 if "cms/image" in u else 1,
            0 if u.endswith((".webp", ".jpg", ".jpeg", ".png")) else 1,
            -len(u),
        ),
    )
    return scored[0] if scored else None


def main() -> int:
    client = ResearchApiClient()
    fetcher = WebFetcher()
    robots = [
        r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    ]
    rows = []
    for r in robots:
        rid = int(r["id"])
        url = r.get("url") or ""
        print(f"Scraping {rid} {r.get('name')[:50]}…", flush=True)
        p = parse_page(fetcher, url, rendered=False) if url else None
        text = (p.text or "") if p else ""
        text_norm = text.replace("<br/>", " ").replace("<br>", " ")
        # Prefer model code from existing display name / URL (avoids related-product Model: hits)
        name_model_m = MODEL_FROM_NAME.search(r.get("name") or "") or MODEL_FROM_NAME.search(url)
        name_model = (
            name_model_m.group(1).replace("–", "-").replace("--", "-") if name_model_m else None
        )
        m = SPEC_RE.search(text_norm)
        prose = PROSE_RE.search(text_norm)
        # If compact specs exist for a different model than the name, prefer name model + page numbers
        apps = APP_RE.findall(text)
        apps_clean = []
        for a in apps:
            a = a.strip().rstrip(".")
            if a and a.lower() not in {x.lower() for x in apps_clean}:
                apps_clean.append(a)
        hero = pick_hero(p.images if p else [])

        payload = reach = dof = rep = weight = None
        model = name_model
        if m:
            spec_model = m.group("model").replace("–", "-").replace("--", "-")
            same = (
                not model
                or model.upper() == spec_model.upper()
                or model.upper().startswith(spec_model.upper())
                or spec_model.upper().startswith(model.upper().split("-B-")[0])
            )
            if same:
                model = model or spec_model
                # Prefer longer/more specific name model when both exist
                if name_model and len(name_model) >= len(spec_model):
                    model = name_model
                payload = float(m.group("payload"))
                reach = float(m.group("reach"))
                dof = int(m.group("dof"))
                rep = float(m.group("rep"))
                weight = float(m.group("weight"))
        if payload is None and prose:
            # Prose block may list wrong related Model:; still take load/reach from this PDP body
            if not model:
                model = prose.group("model").replace("–", "-").replace("--", "-")
            payload = float(prose.group("payload"))
            reach = float(prose.group("reach"))
        if dof is None:
            dof_m = DOF_FROM_NAME.search(r.get("name") or "") or DOF_FROM_NAME.search(text)
            dof = int(dof_m.group(1)) if dof_m else None
        if rep is None:
            rm = re.search(r"repeatability[:\s]*[±+]?([\d.]+)\s*mm", text, re.I)
            if rm:
                rep = float(rm.group(1))
        if weight is None:
            wm = re.search(r"(?<![a-z])weight[:\s]+([\d.]+)\s*kg", text, re.I)
            if wm:
                weight = float(wm.group(1))

        if not model or payload is None or reach is None:
            print(f"  WARN incomplete parse model={model} pay={payload} reach={reach}")
            rows.append(
                {
                    "id": rid,
                    "old_name": r.get("name"),
                    "url": url,
                    "parse_ok": False,
                    "image": hero or (r.get("s3_image") or r.get("image") or ""),
                    "text_snip": text[500:1200],
                }
            )
            continue
        fam_key, fam_name = family_from_model(model)
        purpose_lines = []
        for a in apps_clean[:6]:
            for part in re.split(r"[,;/]", a):
                part = part.strip()
                if part and part.lower() not in {x.lower() for x in purpose_lines}:
                    purpose_lines.append(part)
        if not purpose_lines:
            purpose_lines = ["Industrial articulated arm automation"]
        row = {
            "id": rid,
            "old_name": r.get("name"),
            "name": clean_name(r.get("name") or "", model),
            "model_name": model,
            "url": url,
            "parse_ok": True,
            "payload_kg": payload,
            "reach_mm": reach,
            "dof": dof,
            "repeatability_mm": rep,
            "weight_kg": weight,
            "family_key": fam_key,
            "family_name": fam_name,
            "family_url": url,
            "image": hero or (r.get("s3_image") or r.get("image") or ""),
            "applications": purpose_lines,
            "existing_image": r.get("s3_image") or r.get("image") or "",
        }
        print(
            f"  OK {model} pay={payload} reach={reach} dof={dof} "
            f"rep={rep} wt={weight} hero={bool(row['image'])}"
        )
        rows.append(row)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ok = sum(1 for x in rows if x.get("parse_ok"))
    print(f"Wrote {OUT}: {ok}/{len(rows)} parsed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
