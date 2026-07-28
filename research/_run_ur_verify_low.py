"""Re-verify UR5e/UR5/UR10 after pointing URLs at OEM tech PDFs."""
from __future__ import annotations

import subprocess
import sys

NS = "rag-server-prod"
IDS = [2535, 3544, 4883]


def sh(*args: str) -> str:
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        raise SystemExit(r.returncode)
    return r.stdout


def current_pod() -> str:
    out = sh(
        "kubectl",
        "get",
        "pods",
        "-n",
        NS,
        "--field-selector=status.phase=Running",
        "-o",
        "jsonpath={.items[*].metadata.name}",
    )
    for name in out.split():
        if name.startswith("robotaigeek-prod-") and "mcp" not in name:
            return name
    raise SystemExit("no running robotaigeek-prod pod found")


def main() -> int:
    pod = current_pod()
    idstr = ",".join(map(str, IDS))
    print(f"pod={pod} ids={IDS}", flush=True)
    cmd = [
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
        "verify_content",
        "--status",
        "pending_review",
        "--ids",
        idstr,
        "--force",
        "--delay",
        "0.5",
    ]
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert p.stdout is not None
    for line in p.stdout:
        print(line, end="", flush=True)
    return p.wait()


if __name__ == "__main__":
    raise SystemExit(main())
