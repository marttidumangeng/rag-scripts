"""Drive prod verify_content in batches of 10 (kubectl exec survives better that way)."""
from __future__ import annotations

import subprocess
import sys
import time

NS = "rag-server-prod"
BATCH = 10


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


def missing_ids(pod: str) -> list[int]:
    out = sh(
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
        "from robots.models import Robot; print(','.join(map(str, Robot.objects.filter(id__gte=5374,id__lte=5510,verification_confidence__isnull=True).order_by('id').values_list('id', flat=True))))",
    )
    # last non-empty line that looks like ids
    for ln in reversed([x.strip() for x in out.splitlines() if x.strip()]):
        if all(p.isdigit() for p in ln.split(",") if p):
            return [int(x) for x in ln.split(",") if x.isdigit()]
    return []


def verify_batch(pod: str, ids: list[int]) -> None:
    idstr = ",".join(map(str, ids))
    print(f"\n=== VERIFY {len(ids)}: {ids[0]}..{ids[-1]} on {pod} ===", flush=True)
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
        "--delay",
        "0.5",
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    assert p.stdout is not None
    for line in p.stdout:
        print(line, end="", flush=True)
    rc = p.wait()
    if rc != 0:
        raise SystemExit(rc)


def main() -> int:
    while True:
        pod = current_pod()
        miss = missing_ids(pod)
        print(f"pod={pod} remaining={len(miss)}", flush=True)
        if not miss:
            print("ALL DONE")
            return 0
        batch = miss[:BATCH]
        verify_batch(pod, batch)
        time.sleep(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
