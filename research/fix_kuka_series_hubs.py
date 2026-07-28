"""Normalize the 15 merged family-placeholder robots as series hubs on company 1396.

Keep them pending_review — do not reject. Mark product_url_scope=family,
clear variant_code when the name is a series label, and prepend an actionable
hub note so queue reviewers know these are intentional series landing rows.

Usage:
  python fix_kuka_series_hubs.py            # dry-run
  python fix_kuka_series_hubs.py --apply
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

_RESEARCH_DIR = Path(__file__).resolve().parent
if str(_RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(_RESEARCH_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from load_env import load_research_env

load_research_env(local="--local" in sys.argv)

from api_client import ResearchApiClient

COMPANY_ID = 1396

# Former company-57 family placeholders kept as series hubs after merge.
HUBS: dict[int, dict[str, Any]] = {
    62: {
        "display_name": "KUKA KR 6",
        "family_name": "KR AGILUS",
        "family_key": "kuka:kr-agilus",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-agilus",
        "hub_role": "6 kg-class AGILUS series pointer (class label, not a single SKU)",
    },
    211: {
        "display_name": "KMP 3000P",
        "family_name": "KMP",
        "family_key": "kuka:kmp",
        "family_url": "https://www.kuka.com/en-us/products/amr-autonomous-mobile-robotics/mobile-platforms/kmp-3000p-omniMove",
        "hub_role": "KMP 3000P model page (unique vs older fleet; keep)",
        "is_exact_model": True,
    },
    213: {
        "display_name": "KUKA OmniMove",
        "family_name": "KUKA omniMove",
        "family_key": "kuka:omnimove",
        "family_url": "https://www.kuka.com/en-us/products/amr-autonomous-mobile-robotics/mobile-platforms",
        "hub_role": "omniMove family hub (see E375/E575 variant rows for specific platforms)",
    },
    342: {
        "display_name": "KMP 600",
        "family_name": "KMP",
        "family_key": "kuka:kmp",
        "family_url": "https://www.kuka.com/en-us/products/amr-autonomous-mobile-robotics/mobile-platforms/kmp-600p-diffdrive",
        "hub_role": "KMP 600 kg-class series hub (see KMP 600P/600W variant rows)",
    },
    2092: {
        "display_name": "KR AGILUS",
        "family_name": "KR AGILUS",
        "family_key": "kuka:kr-agilus",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-agilus",
        "hub_role": "KR AGILUS family series hub",
    },
    2097: {
        "display_name": "KR DELTA",
        "family_name": "KR DELTA",
        "family_key": "kuka:kr-delta",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-delta",
        "hub_role": "KR DELTA family series hub",
    },
    2102: {
        "display_name": "LBR iisy",
        "family_name": "LBR iisy",
        "family_key": "kuka:lbr-iisy",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/lbr-iisy",
        "hub_role": "LBR iisy family series hub",
    },
    2107: {
        "display_name": "LBR iiwa",
        "family_name": "LBR iiwa",
        "family_key": "kuka:lbr-iiwa",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/lbr-iiwa",
        "hub_role": "LBR iiwa family series hub",
    },
    2111: {
        "display_name": "KR CYBERTECH nano",
        "family_name": "KR CYBERTECH nano",
        "family_key": "kuka:kr-cybertech-nano",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-cybertech-nano",
        "hub_role": "KR CYBERTECH nano family series hub",
    },
    2114: {
        "display_name": "KR CYBERTECH",
        "family_name": "KR CYBERTECH",
        "family_key": "kuka:kr-cybertech",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-cybertech",
        "hub_role": "KR CYBERTECH family series hub",
    },
    2119: {
        "display_name": "KR IONTEC",
        "family_name": "KR IONTEC",
        "family_key": "kuka:kr-iontec",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-iontec",
        "hub_role": "KR IONTEC family series hub",
    },
    2122: {
        "display_name": "KR 470 PA",
        "family_name": "KR FORTEC PA",
        "family_key": "kuka:kr-fortec-pa",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-fortec-pa",
        "hub_role": "KR 470 PA / FORTEC PA series pointer (aligned to KR 470 R3200-2 PA OEM row)",
        "is_exact_model": True,
        "variant_code": "KR 470 R3200-2 PA",
    },
    2126: {
        "display_name": "KR QUANTEC",
        "family_name": "KR QUANTEC",
        "family_key": "kuka:kr-quantec",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-quantec",
        "hub_role": "KR QUANTEC family series hub",
    },
    2129: {
        "display_name": "KR FORTEC",
        "family_name": "KR FORTEC",
        "family_key": "kuka:kr-fortec",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-fortec",
        "hub_role": "KR FORTEC family series hub",
    },
    2132: {
        "display_name": "KR titan",
        "family_name": "KR 1000 titan",
        "family_key": "kuka:kr-1000-titan",
        "family_url": "https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/kr-1000-titan",
        "hub_role": "KR 1000 titan / KR titan family series hub",
    },
}

HUB_NOTE = (
    "[SERIES HUB — keep]\n"
    "Intentional family/series landing row after merge of company 57 → 1396.\n"
    "Role: {role}\n"
    "product_url_scope=family. Per-variant SKUs live as separate robot rows "
    "under the same family_key when published by KUKA.\n"
    "Do NOT reject as a duplicate of a variant unless a human confirms "
    "this hub is redundant.\n"
    "---"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    client = ResearchApiClient()
    robots = None
    for a in range(12):
        try:
            robots = {int(r["id"]): r for r in client.list_robots_for_company(COMPANY_ID)}
            break
        except Exception as e:  # noqa: BLE001
            print(f"retry {a}: {e}")
            time.sleep(5)
    if robots is None:
        return 1

    plan = []
    missing = []
    for rid, meta in sorted(HUBS.items()):
        r = robots.get(rid)
        if not r:
            missing.append(rid)
            continue
        note = HUB_NOTE.format(role=meta["hub_role"])
        notes = (r.get("notes") or "").strip()
        if "[SERIES HUB — keep]" not in notes:
            notes = (note + "\n" + notes).strip() if notes else note

        body: dict[str, Any] = {
            "source_locale": "en",
            "family_name": meta["family_name"],
            "family_key": meta["family_key"],
            "family_url": meta["family_url"],
            "url": meta["family_url"],
            "website_url": meta["family_url"],
            "product_url_scope": "family",
            "variant_label": meta["family_name"]
            if not meta.get("is_exact_model")
            else meta["display_name"],
            "notes": notes,
            "status": "pending_review",
        }
        if meta.get("is_exact_model"):
            body["variant_code"] = meta.get("variant_code") or meta["display_name"]
            body["model_name"] = meta.get("variant_code") or meta["display_name"]
        else:
            # Series label — no single SKU code
            body["variant_code"] = ""
            body["model_name"] = meta["display_name"]

        plan.append({"id": rid, "name": r.get("name"), "meta": meta, "body": body})

    print(f"hubs={len(plan)} missing={missing}")
    for p in plan:
        m = p["meta"]
        print(
            f"  {p['id']} {p['name']} → key={m['family_key']} "
            f"scope=family role={m['hub_role'][:50]}"
        )

    if not args.apply:
        print("DRY-RUN — pass --apply to write")
        return 0

    ok = fail = 0
    for p in plan:
        try:
            patched = client._patch(f"robots/robots/{p['id']}/", p["body"])
            print(
                f"ok {p['id']} key={patched.get('family_key')} "
                f"scope={patched.get('product_url_scope')} "
                f"status={patched.get('status')}"
            )
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {p['id']}: {exc}")
            fail += 1
        time.sleep(0.08)

    print(f"DONE ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
