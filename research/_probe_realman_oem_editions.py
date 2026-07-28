"""Inspect Realman OEM PDP edition folders (not page chrome)."""
from __future__ import annotations

import re
import sys
from urllib.parse import unquote

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

UA = {"User-Agent": "Mozilla/5.0 (compatible; RobotAIGeekResearch/1.0)"}
PAGES = [
    "eco62",
    "eco63",
    "eco65",
    "rm65",
    "rm75",
    "rml63",
    "rx71",
    "rx75",
    "realbot-01",
    "realbot-l2",
    "realbot-s2",
    "realbot-humanoid",
    "rmg24-gripper",
    "teleop-kit",
    "dual-arm-lift",
    "single-arm-lift",
    "four-steer-chassis",
    "dual-wheel-chassis",
    "whg-joint-modules",
    "whj-joint-modules",
    "whj-torque-joint-modules",
]


def main() -> None:
    for slug in PAGES:
        url = f"https://www.realman-robotics.com/en/products/{slug}.html"
        r = requests.get(url, headers=UA, timeout=40)
        html = r.text if r.ok else ""
        folders = sorted(set(re.findall(r"products-images/[^\"']+", html)))
        decoded = [unquote(f) for f in folders]
        editions = sorted(
            {
                m
                for f in decoded
                for m in re.findall(r"(标准版|六维力版|视觉版|带视觉)", f)
            }
        )
        title_m = re.search(r"<title>([^<]+)", html or "")
        title = title_m.group(1).strip() if title_m else "?"
        print(f"--- {slug} HTTP {r.status_code} title={title[:70]}")
        print("  path_editions", editions)
        # Spec table rows that look like variants
        if re.search(r"Six[- ]?Axis Force|六维力|Vision|视觉|Standard|标准", html, re.I):
            # pull nearby option labels if present
            opts = sorted(
                set(
                    re.findall(
                        r"(Standard|Six[- ]Axis Force|Vision|标准版|六维力版|视觉版)",
                        html,
                        re.I,
                    )
                )
            )
            print("  text_opts", opts[:12])
        for f in decoded[:10]:
            if any(
                k in f
                for k in (
                    "机械臂",
                    "移动",
                    "夹爪",
                    "关节",
                    "遥操作",
                    "人形",
                    "升降",
                    "底盘",
                )
            ):
                print(" ", f[:120])
        print("  folder_count", len(decoded))


if __name__ == "__main__":
    main()
