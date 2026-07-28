"""Re-verify Universal Robots IDs that still lack verification_confidence."""
from __future__ import annotations

import subprocess
import sys
import time

NS = "rag-server-prod"
BATCH = 4
# First batch incomplete in prior run + known low scorers to re-check after URL note.
IDS = [2525, 2534, 2535, 3302, 3303, 3542, 3543]


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


def verify_batch(pod: str, ids: list[int]) -> None:
    idstr = ",".join(map(str, ids))
    print(f"\n=== FORCE VERIFY {ids} on {pod} ===", flush=True)
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
    rc = p.wait()
    if rc != 0:
        raise SystemExit(rc)


def main() -> int:
    pod = current_pod()
    print(f"pod={pod}", flush=True)
    for i in range(0, len(IDS), BATCH):
        batch = IDS[i : i + BATCH]
        try:
            verify_batch(pod, batch)
        except SystemExit:
            pod = current_pod()
            verify_batch(pod, batch)
        time.sleep(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
