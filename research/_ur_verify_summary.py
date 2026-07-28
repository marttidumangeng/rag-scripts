"""Print Universal Robots (192) verification summary from prod."""
from __future__ import annotations

import subprocess
import sys

NS = "rag-server-prod"
PY = r"""
from robots.models import Robot
qs = Robot.objects.filter(company_ref_id=192, status="pending_review").order_by("id")
rows = []
for r in qs:
    v = r.verification if isinstance(r.verification, dict) else {}
    flags = v.get("flags") or []
    if isinstance(flags, dict):
        flags = list(flags.keys())
    rows.append((r.id, r.verification_confidence, flags, r.name))
print("n", len(rows))
low = []
for i, c, f, n in rows:
    fl = ",".join(str(x) for x in list(f)[:5])
    print(f"{i}|{c}|{fl}|{n}")
    if c is None or float(c) < 80:
        low.append((i, c, n, fl))
conf = [float(c) for _, c, _, _ in rows if c is not None]
print(
    "with_conf",
    len(conf),
    "avg",
    round(sum(conf) / len(conf), 1) if conf else None,
    "min",
    min(conf) if conf else None,
)
print("below80", len(low))
for x in low:
    print(" LOW", x)
"""


def main() -> int:
    out = subprocess.check_output(
        [
            "kubectl",
            "get",
            "pods",
            "-n",
            NS,
            "--field-selector=status.phase=Running",
            "-o",
            "jsonpath={.items[*].metadata.name}",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    pod = next(
        p for p in out.split() if p.startswith("robotaigeek-prod-") and "mcp" not in p
    )
    r = subprocess.run(
        [
            "kubectl",
            "exec",
            "-n",
            NS,
            pod,
            "-c",
            "django-app",
            "--",
            "python",
            "manage.py",
            "shell",
            "-c",
            PY,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    sys.stdout.write(r.stdout)
    if r.returncode:
        sys.stderr.write(r.stderr)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
