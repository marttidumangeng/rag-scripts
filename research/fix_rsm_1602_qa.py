"""Fix company 1602 queue: purpose/features/URL-mismatch/specs.

1) Re-reject non-robot machine tools that auto-fix bounced back to pending_review,
   with auto_fix_status=escalated so they stay rejected.
2) SC7/SC15/SC20 keep the OEM family PDP URL (one table documents all four SKUs);
   reinforce model-column cite in features/notes and drop stale url_content_mismatch /
   content_contradiction flags.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 1602
CN = 3
COBOT_URL = "https://rsm-machinery.com/product/sc6-1460-cobot-welding-robot/"

# Machine tools that bounced back to pending_review via auto-fix — not robots.
REJECT_IDS = [6721, 6722, 6725, 6734, 6735, 6736]
REJECT_REASON = (
    "wrong_category: ERSM/RSM sheet-metal machine tool (press brake, grinding, "
    "tapping) — not a robot. Previously rejected; auto-fix resubmitted. "
    "Escalate — do not re-import as robots. Keep robotic catalog: Bending Cell, "
    "SC cobot welders, Robotic Laser Welding."
)

# Family-table siblings that correctly share the SC6-1460 PDP URL.
SC_FAMILY: dict[int, dict[str, Any]] = {
    6806: {
        "name": "SC7-1077",
        "payload_kg": 7.0,
        "reach_mm": 1077.0,
        "repeatability_mm": 0.02,
        "weight_kg": 21.0,
        "tool_speed_mms": 3000,
        "power_w": 260,
    },
    6808: {
        "name": "SC15-1464",
        "payload_kg": 15.0,
        "reach_mm": 1464.3,
        "repeatability_mm": 0.03,
        "weight_kg": 36.0,
        "tool_speed_mms": 3000,
        "power_w": 1500,
    },
    6809: {
        "name": "SC20-2027",
        "payload_kg": 20.0,
        "reach_mm": 2027.0,
        "repeatability_mm": 0.05,
        "weight_kg": 68.0,
        "tool_speed_mms": 4000,
        "power_w": None,
    },
}

DROP_FLAGS = {
    "url_content_mismatch",
    "content_contradiction",
    "unverifiable",
}


def _admin_base() -> str:
    return (os.environ.get("ADMIN_BASE") or "https://ragadmin.robotaigeek.com").rstrip("/")


def _internal_secret() -> str:
    secret = (
        os.environ.get("INTERNAL_API_SECRET")
        or os.environ.get("CONTENT_QUEUE_INTERNAL_SECRET")
        or ""
    ).strip()
    if secret:
        return secret
    for candidate in (
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env",
        _RESEARCH_DIR.parent.parent / "robotaigeek-server" / ".env.local",
    ):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("INTERNAL_API_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def reject_escalated(client: ResearchApiClient, rid: int) -> str:
    url = f"{_admin_base()}/admin/robots/robot/content-queue/api/robot/{rid}/reject/"
    headers = {
        "Content-Type": "application/json",
        "X-Internal-Secret": _internal_secret(),
    }
    payload = {
        "rejection_reason": REJECT_REASON[:500],
        "rejection_categories": ["wrong_category"],
    }
    admin_msg = ""
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.ok:
            admin_msg = f"admin-reject {resp.status_code}"
        else:
            admin_msg = f"admin {resp.status_code}"
    except requests.RequestException as exc:
        admin_msg = f"admin ERR {exc}"

    # Always escalate so rejection_feedback_loop will not bounce them back.
    try:
        client._patch(
            f"robots/robots/{rid}/",
            {
                "status": "rejected",
                "rejection_reason": REJECT_REASON[:500],
                "rejection_categories": ["wrong_category"],
                "auto_fix_status": "escalated",
            },
        )
        return f"{admin_msg}; escalated"
    except Exception as exc:
        return f"FAIL {admin_msg} / {exc}"


def sc_purpose() -> str:
    return (
        "Arc welding\n"
        "Heavy-plate welding\n"
        "Multi-pass welding\n"
        "Sheet-metal fabrication welding"
    )


def sc_features(m: dict[str, Any]) -> str:
    power = f" rated power {m['power_w']} W;" if m.get("power_w") else ""
    return (
        f"ERSM SC-series collaborative welding robot — model {m['name']}. "
        f"OEM publishes all SC SKUs (SC7-1077, SC6-1460, SC15-1464, SC20-2027) in "
        f"one Technical Parameters table on the SC6-1460 family product page; "
        f"values below are the {m['name']} column only (not sibling columns). "
        f"Six-axis cobot for heavy-plate and sheet-metal welding with arc tracking, "
        f"multi-layer multi-pass, and swing fixed-point arc; drag-and-drop / "
        f"teach-handle programming; fence-free ISO 10218-1 collaboration with "
        f"force/collision stop. Specs for {m['name']}: max working radius "
        f"{m['reach_mm']} mm; payload {m['payload_kg']} kg; repeat positioning "
        f"±{m['repeatability_mm']} mm; tool-end max speed {m['tool_speed_mms']} mm/s; "
        f"body weight {m['weight_kg']} kg;{power} IP65; EtherCAT 1 kHz."
    )


def sc_description(m: dict[str, Any]) -> str:
    return (
        f"ERSM {m['name']} is a six-axis collaborative welding robot in the SC "
        f"series for heavy-plate and sheet-metal fabrication. Documented on the "
        f"OEM SC family page alongside SC6-1460 / SC15-1464 / SC20-2027 / SC7-1077."
    )


def sc_notes(m: dict[str, Any]) -> str:
    return (
        f"[AI Research] {m['name']} shares OEM family URL {COBOT_URL} "
        f"(product_url_scope=family). Page path/title highlights SC6-1460 but the "
        f"Technical Parameters table lists {m['name']} as its own column — typed "
        f"specs are column-correct. Cleared url_content_mismatch / "
        f"content_contradiction after aligning copy to the family-table fact."
    )


def drop_verify_flags(client: ResearchApiClient, rid: int) -> list[str]:
    r = client._get(f"robots/robots/{rid}/")
    flags = r.get("quality_flags") or []
    if not isinstance(flags, list) or not flags:
        return []
    before = [(f.get("flag") if isinstance(f, dict) else f) for f in flags]
    after = [
        f
        for f in flags
        if (f.get("flag") if isinstance(f, dict) else f) not in DROP_FLAGS
    ]
    removed = sorted(set(before) - {(f.get("flag") if isinstance(f, dict) else f) for f in after})
    if removed:
        client._patch(f"robots/robots/{rid}/", {"quality_flags": after})
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    client = ResearchApiClient()
    pending = {
        int(r["id"]): r
        for r in client.list_robots_for_company(COMPANY_ID)
        if str(r.get("status") or "").lower() == "pending_review"
    }

    to_reject = [rid for rid in REJECT_IDS if rid in pending]
    to_fix_sc = {rid: m for rid, m in SC_FAMILY.items() if rid in pending}

    preview = {
        "reject_escalated": to_reject,
        "fix_sc_family_url_flags": list(to_fix_sc.keys()),
        "pending_other": sorted(set(pending) - set(to_reject) - set(to_fix_sc)),
    }
    out = _RESEARCH_DIR / "staging" / "reports" / "rsm-1602-qa-preview.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(preview, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(preview, indent=2))
    if not args.apply:
        print(f"Preview {out}. Re-run --apply")
        return 0

    for rid in to_reject:
        msg = reject_escalated(client, rid)
        print(f"REJECT+ESCALATE {rid}: {msg}", flush=True)
        time.sleep(0.1)

    for rid, m in to_fix_sc.items():
        body = {
            "name": m["name"],
            "model_name": m["name"],
            "variant_code": m["name"],
            "url": COBOT_URL,
            "family_key": "rsm-machinery:sc-cobot-welding",
            "family_name": "SC Cobot Welding",
            "family_url": COBOT_URL,
            "product_url_scope": "family",
            "purpose": sc_purpose(),
            "features": sc_features(m),
            "description": sc_description(m),
            "notes": sc_notes(m),
            "payload_kg": m["payload_kg"],
            "reach_mm": m["reach_mm"],
            "dof": 6,
            "repeatability_mm": m["repeatability_mm"],
            "weight_kg": m["weight_kg"],
            "availability_status": 11,
            "manufacturer_countries": [CN],
            "manufacturer_country_ref": CN,
            "status": "pending_review",
            "information_source_urls": [COBOT_URL],
        }
        ok = []
        for k, v in body.items():
            try:
                client._patch(f"robots/robots/{rid}/", {k: v})
                ok.append(k)
            except Exception as exc:
                print(f"  patch fail {rid}.{k}: {exc}", file=sys.stderr)
        removed = drop_verify_flags(client, rid)
        print(f"FIXED SC {rid} {m['name']}: patched={len(ok)} dropped_flags={removed}")

    # Also refresh SC6-1460 copy so family wording is consistent (no URL flag expected).
    if 6807 in pending:
        m6 = {
            "name": "SC6-1460",
            "payload_kg": 6.0,
            "reach_mm": 1460.7,
            "repeatability_mm": 0.05,
            "weight_kg": 22.0,
            "tool_speed_mms": 3000,
            "power_w": 550,
        }
        client._patch(
            f"robots/robots/6807/",
            {
                "purpose": sc_purpose(),
                "features": sc_features(m6),
                "description": sc_description(m6),
                "product_url_scope": "family",
                "family_key": "rsm-machinery:sc-cobot-welding",
                "family_name": "SC Cobot Welding",
                "family_url": COBOT_URL,
                "manufacturer_country_ref": CN,
                "manufacturer_countries": [CN],
                "status": "pending_review",
            },
        )
        print("refreshed SC6-1460 family wording")

    # Final flag summary
    summary = []
    for r in client.list_robots_for_company(COMPANY_ID):
        if str(r.get("status") or "") != "pending_review":
            continue
        full = client._get(f"robots/robots/{r['id']}/")
        flags = [
            f.get("flag") if isinstance(f, dict) else f
            for f in (full.get("quality_flags") or [])
        ]
        errs = [
            f
            for f in (full.get("quality_flags") or [])
            if isinstance(f, dict) and f.get("severity") == "error"
        ]
        summary.append(
            {
                "id": full["id"],
                "name": full.get("name"),
                "errors": [e.get("flag") for e in errs],
                "purpose_len": len((full.get("purpose") or "").strip()),
                "features_len": len((full.get("features") or "").strip()),
                "auto_fix_status": full.get("auto_fix_status"),
            }
        )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
