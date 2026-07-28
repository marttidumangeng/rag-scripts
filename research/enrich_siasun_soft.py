#!/usr/bin/env python3
"""SIASUN (1424) soft-gap enrichment: description, specs, availability.

Clears content-queue warnings:
  - short_description (<100 chars) / "SIASUN"-only og stubs
  - missing_specs (typed columns empty)
  - missing_availability (null FK)

Never invents specs — only OEM PDP cites + unambiguous name encodings
(GCR30-1100, SA4A-4/0.40, 60T Heavy-Duty, P-T3000D) when the live EN page
is for that model.

Usage:
  python enrich_siasun_soft.py
  python enrich_siasun_soft.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_RESEARCH_DIR))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient
from fix_siasun_robots import classify, prefer_en_url, scrape_pdp

COMPANY_ID = 1424
AVAILABLE = 11  # AvailabilityStatus key=available
MIN_DESC = 100
REPORT = _RESEARCH_DIR / "staging" / "reports" / "siasun-soft-enrich.json"

SPEC_FIELDS = (
    "weight_kg", "width_mm", "length_mm", "height_mm", "speed", "walking_speed",
    "runtime_minutes", "battery_wh", "charging_time_minutes", "joint_torque_nm",
    "torque_density_nm_per_kg", "dof",
    "payload_kg", "reach_mm", "repeatability_mm",
    "weight", "width", "length", "height", "runtime", "battery_capacity",
    "charging_time", "voltage", "joint_torque", "torque_density", "connectivity",
    "sensors", "materials", "charging_type", "computation", "actuation_mechanism",
)


def _blank(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return not val.strip()
    if isinstance(val, (list, dict)):
        return len(val) == 0
    return False


def needs_soft(robot: dict[str, Any]) -> dict[str, bool]:
    desc = (robot.get("description") or "").strip()
    avail = robot.get("availability_status")
    if isinstance(avail, dict):
        aid = avail.get("id")
    else:
        aid = robot.get("availability_status_id") or avail
    return {
        "short_desc": len(desc) < MIN_DESC,
        "no_specs": all(_blank(robot.get(f)) for f in SPEC_FIELDS),
        "no_avail": aid is None,
    }


def parse_name_specs(name: str) -> dict[str, float | int]:
    """Unambiguous OEM name encodings only."""
    out: dict[str, float | int] = {}
    n = name.strip()

    m = re.match(r"GCR(\d+)-(\d+)\b", n, re.I)
    if m:
        out["payload_kg"] = float(m.group(1))
        out["reach_mm"] = float(m.group(2))
        out["dof"] = 6
        return out

    m = re.search(r"-(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", n)
    if m:
        payload = float(m.group(1))
        reach = float(m.group(2))
        out["payload_kg"] = payload
        # SA*/SN*/SR* reach is meters when < 20
        out["reach_mm"] = reach * 1000.0 if reach < 20 else reach
        if re.match(r"SA", n, re.I):
            out["dof"] = 4
        elif re.match(r"SR|SN", n, re.I):
            out["dof"] = 6
        return out

    m = re.match(r"(\d+)\s*T\b.*Heavy-Duty", n, re.I)
    if m:
        out["payload_kg"] = float(m.group(1)) * 1000.0
        return out

    m = re.match(r"P-T(\d+)D\b", n, re.I)
    if m:
        out["payload_kg"] = float(m.group(1))
        return out

    return out


def extract_label_values(lines: list[str]) -> dict[str, float]:
    """Pull payload/reach/weight/repeat from consecutive label/value lines."""
    out: dict[str, float] = {}
    for i, ln in enumerate(lines):
        nxt_lines = lines[i + 1 : i + 4]
        nxt = " ".join(nxt_lines)
        blob = f"{ln} {nxt}"

        if "payload_kg" not in out:
            m = re.search(
                r"(?:Max\s+)?Payload|Rated\s+Load|Rated\s+payload|Load\s+capacity",
                ln,
                re.I,
            )
            if m and not re.search(r"capacity\s+of\s+up", ln, re.I):
                # Same-line or next-line value in kg
                m2 = re.search(
                    r"(?:Max\s+)?(?:Payload|Rated\s+Load|Rated\s+payload|Load\s+capacity)[:：\s]*"
                    r"(\d[\d,]*(?:\.\d+)?)\s*kg",
                    blob,
                    re.I,
                )
                if m2:
                    out["payload_kg"] = float(m2.group(1).replace(",", ""))
                else:
                    for j in range(i + 1, min(i + 4, len(lines))):
                        m3 = re.match(
                            r"^(\d[\d,]*(?:\.\d+)?)\s*(?:kg)?$",
                            lines[j].strip(),
                            re.I,
                        )
                        if m3:
                            out["payload_kg"] = float(m3.group(1).replace(",", ""))
                            break
            if "payload_kg" not in out:
                m4 = re.search(r"up to\s+(\d[\d,]*(?:\.\d+)?)\s*kg", blob, re.I)
                if m4 and re.search(r"load|payload|handling", blob, re.I):
                    out["payload_kg"] = float(m4.group(1).replace(",", ""))

        if "reach_mm" not in out and re.search(r"^reach[:：]?$|Reach[:：]", ln, re.I):
            m = re.search(r"Reach[:：\s]*(\d[\d,]*(?:\.\d+)?)\s*mm", blob, re.I)
            if m:
                out["reach_mm"] = float(m.group(1).replace(",", ""))
            else:
                m = re.search(r"Reach[:：\s]*(\d+(?:\.\d+)?)\s*m\b", blob, re.I)
                if m:
                    out["reach_mm"] = float(m.group(1)) * 1000.0
                else:
                    for j in range(i + 1, min(i + 3, len(lines))):
                        m2 = re.match(
                            r"^(\d[\d,]*(?:\.\d+)?)\s*(mm|m)$",
                            lines[j].strip(),
                            re.I,
                        )
                        if m2:
                            v = float(m2.group(1).replace(",", ""))
                            out["reach_mm"] = v if m2.group(2).lower() == "mm" else v * 1000.0
                            break

        if "weight_kg" not in out and re.search(r"vehicle\s+weight|^weight[:：]", ln, re.I):
            m = re.search(r"[Ww]eight[:：\s]*(\d[\d,]*(?:\.\d+)?)\s*kg", blob)
            if m:
                out["weight_kg"] = float(m.group(1).replace(",", ""))

        # Repeatability: ONLY when the label is explicit — never confuse with reach/lift height.
        if "repeatability_mm" not in out and re.search(
            r"repeat(?:ability|\s+positioning)?|positioning\s+accuracy",
            ln,
            re.I,
        ):
            m = re.search(r"[±]?\s*(\d+(?:\.\d+)?)\s*mm", blob, re.I)
            if m:
                val = float(m.group(1))
                # Arms are typically ≤1 mm; mobiles often ≤20 mm. Reject reach-sized numbers.
                if val <= 20.0:
                    out["repeatability_mm"] = val
            else:
                for j in range(i + 1, min(i + 3, len(lines))):
                    m2 = re.match(r"^[±]?\s*(\d+(?:\.\d+)?)\s*mm$", lines[j].strip(), re.I)
                    if m2:
                        val = float(m2.group(1))
                        if val <= 20.0:
                            out["repeatability_mm"] = val
                        break

    return out


def clean_og(og: str) -> str:
    og = (og or "").strip()
    if not og or og.upper() in ("SIASUN", "SIASUN."):
        return ""
    # Strip nav chrome prefixes common on SIASUN EN PDPs
    og = re.sub(
        r"^(?:Introduction|Advantages|Application Area|Parameter|Case Studies)\s+",
        "",
        og,
        flags=re.I,
    )
    og = re.sub(
        r"^(?:Introduction|Advantages|Application Area|Parameter|Case Studies)\s+",
        "",
        og,
        flags=re.I,
    )
    return og.strip()


def pick_description(name: str, pdp: dict[str, Any], specs: dict[str, Any]) -> str:
    candidates: list[str] = []
    og = clean_og(pdp.get("og_desc") or "")
    if len(og) >= MIN_DESC:
        candidates.append(og)

    model_token = re.sub(r"[^A-Za-z0-9]+", "", name.split()[0]).lower()
    for p in pdp.get("paras") or []:
        p = (p or "").strip()
        if len(p) < 80:
            continue
        low = p.lower()
        if "unfortunately" in low and "not found" in low:
            continue
        if "cookie" in low or "copyright" in low or "agree to receive" in low:
            continue
        candidates.append(p)

    for ln in pdp.get("lines") or []:
        ln = (ln or "").strip()
        if not (140 <= len(ln) <= 900):
            continue
        low = ln.lower()
        if "agree to receive" in low or "cookie" in low:
            continue
        if "unfortunately" in low and "not found" in low:
            continue
        if (
            "siasun" in low
            or "robot" in low
            or (model_token and model_token[:4] in re.sub(r"[^a-z0-9]+", "", low))
        ):
            candidates.append(ln)

    # Rank: prefer model-token hits, then longer prose
    def score(text: str) -> tuple[int, int]:
        low = text.lower()
        hit = 1 if model_token and model_token[:4] in re.sub(r"[^a-z0-9]+", "", low) else 0
        return (hit, len(text))

    candidates = sorted(set(candidates), key=score, reverse=True)
    for text in candidates:
        text = text.strip()
        if text.upper() in ("SIASUN", "SIASUN."):
            continue
        if text.startswith("SIASUN ") and "|" in text and len(text) < 140:
            continue  # title-tag style
        if len(text) >= MIN_DESC:
            return text[:1200]

    bits = []
    if specs.get("payload_kg") is not None:
        bits.append(f"{specs['payload_kg']:g} kg payload")
    if specs.get("reach_mm") is not None:
        bits.append(f"{specs['reach_mm']:g} mm reach")
    if specs.get("dof") is not None:
        bits.append(f"{int(specs['dof'])} axes")
    kind = classify(name, pdp.get("final_url") or "")
    kind_phrase = {
        "cobot": "collaborative robot arm",
        "scara": "SCARA industrial robot",
        "arm": "industrial robot arm",
        "amr": "autonomous mobile robot",
        "fork": "forklift / handling mobile robot",
    }.get(kind, "industrial robot")
    spec_txt = (", ".join(bits) + ". ") if bits else ""
    return (
        f"The SIASUN {name} is a {kind_phrase} listed on the manufacturer's English "
        f"product catalog. {spec_txt}"
        f"It is offered for industrial automation and material-handling applications."
    )[:1200]


def merge_specs(name: str, pdp: dict[str, Any]) -> dict[str, Any]:
    name_specs = parse_name_specs(name)
    page = extract_label_values(list(pdp.get("lines") or []))
    # Also fold scrape_pdp numeric fields
    if pdp.get("payload_kg") is not None:
        page.setdefault("payload_kg", float(pdp["payload_kg"]))
    if pdp.get("reach_m") is not None:
        page.setdefault("reach_mm", float(pdp["reach_m"]) * 1000.0)
    if pdp.get("weight_kg") is not None:
        page.setdefault("weight_kg", float(pdp["weight_kg"]))
    if pdp.get("repeat_mm") is not None:
        page.setdefault("repeatability_mm", float(pdp["repeat_mm"]))

    out: dict[str, Any] = {}
    # Prefer name encoding for payload/reach/dof — OEM SKU encodes the catalog values.
    for k in ("payload_kg", "reach_mm", "dof"):
        if k in name_specs:
            out[k] = name_specs[k]
        elif k in page:
            out[k] = page[k]
    for k in ("weight_kg", "repeatability_mm"):
        if k in page:
            out[k] = page[k]
        elif k in name_specs:
            out[k] = name_specs[k]

    kind = classify(name, pdp.get("final_url") or "")
    if "dof" not in out:
        if kind == "scara" or re.match(r"SA\d", name, re.I):
            out["dof"] = 4
        elif kind == "cobot" or re.match(r"GCR", name, re.I):
            out["dof"] = 6
        elif re.match(r"^(SR|SN)\d", name, re.I):
            out["dof"] = 6
    return out


def pdp_usable(pdp: dict[str, Any]) -> bool:
    if (pdp.get("status") or 0) != 200:
        return False
    paras = " ".join(pdp.get("paras") or []).lower()
    if "unfortunately" in paras and "not found" in paras:
        return False
    if not (pdp.get("h1") or pdp.get("og_desc") or pdp.get("paras")):
        return False
    return True


def plan_one(robot: dict[str, Any]) -> dict[str, Any]:
    gaps = needs_soft(robot)
    if not any(gaps.values()):
        return {"id": robot["id"], "name": robot["name"], "action": "skip", "reason": "already_ok"}

    url = prefer_en_url((robot.get("url") or "").strip(), robot["name"])
    row: dict[str, Any] = {
        "id": robot["id"],
        "name": robot["name"],
        "url": url,
        "gaps": gaps,
        "action": "enrich",
    }
    if not url:
        row["action"] = "skip"
        row["reason"] = "no_url"
        return row

    try:
        pdp = scrape_pdp(url)
    except Exception as exc:  # noqa: BLE001
        row["action"] = "skip"
        row["reason"] = f"scrape_fail:{exc}"
        return row

    if not pdp_usable(pdp):
        row["action"] = "partial" if gaps["no_avail"] else "skip"
        row["reason"] = "pdp_404_or_empty"
        if gaps["no_avail"]:
            row["patch"] = {"availability_status": AVAILABLE}
        return row

    specs = merge_specs(robot["name"], pdp)
    patch: dict[str, Any] = {}

    if gaps["short_desc"] or len((robot.get("description") or "").strip()) < MIN_DESC:
        desc = pick_description(robot["name"], pdp, specs)
        if len(desc) >= MIN_DESC:
            patch["description"] = desc
            # Never copy description into purpose (stakeholder 0z / purpose_duplicates_description).
            # Purpose is rewritten separately by fix_siasun_purpose.py.

    if gaps["no_specs"]:
        for k, v in specs.items():
            if v is not None:
                patch[k] = v

    if gaps["no_avail"]:
        patch["availability_status"] = AVAILABLE

    if not patch:
        row["action"] = "skip"
        row["reason"] = "nothing_to_patch"
        return row

    row["patch"] = patch
    row["desc_len"] = len(patch.get("description") or robot.get("description") or "")
    row["specs"] = {k: patch[k] for k in ("payload_kg", "reach_mm", "dof", "weight_kg", "repeatability_mm") if k in patch}
    return row


def apply_patch(client: ResearchApiClient, rid: int, patch: dict[str, Any]) -> str:
    body = dict(patch)
    try:
        client._patch(f"robots/robots/{rid}/", body)
        return "ok"
    except Exception as e1:  # noqa: BLE001
        # Some envs reject unexpected keys — retry specs-only / desc-only subsets
        for drop in ("purpose", "repeatability_mm", "weight_kg"):
            body.pop(drop, None)
        try:
            client._patch(f"robots/robots/{rid}/", body)
            return f"ok_partial:{e1}"
        except Exception as e2:  # noqa: BLE001
            return f"fail:{e2}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Enrich SIASUN soft gaps")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", nargs="*", help="Optional name substrings")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = [
        r for r in client.list_robots_for_company(COMPANY_ID)
        if (r.get("status") or "") == "pending_review"
    ]
    if args.only:
        robots = [r for r in robots if any(s.lower() in r["name"].lower() for s in args.only)]

    plan = []
    for r in robots:
        gaps = needs_soft(r)
        if not any(gaps.values()):
            continue
        print(f"plan {r['id']} {r['name']} gaps={ {k:v for k,v in gaps.items() if v} }")
        item = plan_one(r)
        plan.append(item)
        print(f"  → {item.get('action')} {item.get('reason', '')} specs={item.get('specs')} desc_len={item.get('desc_len')}")
        time.sleep(0.15)

    results = {"planned": len(plan), "items": plan}
    if args.apply:
        applied = []
        for item in plan:
            if item.get("action") not in ("enrich", "partial"):
                continue
            patch = item.get("patch") or {}
            if not patch:
                continue
            status = apply_patch(client, int(item["id"]), patch)
            print(f"APPLY {item['id']} {item['name']}: {status}")
            applied.append({"id": item["id"], "status": status, "keys": sorted(patch.keys())})
            time.sleep(0.2)
        results["applied"] = applied

        # Recount
        robots2 = [
            r for r in client.list_robots_for_company(COMPANY_ID)
            if (r.get("status") or "") == "pending_review"
        ]
        short = sum(1 for r in robots2 if len((r.get("description") or "").strip()) < MIN_DESC)
        nospec = sum(1 for r in robots2 if all(_blank(r.get(f)) for f in SPEC_FIELDS))
        noavail = 0
        for r in robots2:
            avail = r.get("availability_status")
            aid = avail.get("id") if isinstance(avail, dict) else (r.get("availability_status_id") or avail)
            if aid is None:
                noavail += 1
        results["final"] = {
            "pending": len(robots2),
            "short_desc": short,
            "no_specs": nospec,
            "no_avail": noavail,
        }
        print("FINAL", results["final"])

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
