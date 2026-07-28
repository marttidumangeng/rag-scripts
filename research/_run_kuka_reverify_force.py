"""Force re-verify KUKA depth imports after URL/video/family fixes (batches of 10)."""
from __future__ import annotations

import subprocess
import sys
import time

NS = "rag-server-prod"
BATCH = 10
IDS = list(range(5374, 5511))


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
    print(f"pod={pod} total={len(IDS)}", flush=True)
    for i in range(0, len(IDS), BATCH):
        batch = IDS[i : i + BATCH]
        idstr = ",".join(map(str, batch))
        print(f"\n=== FORCE VERIFY {batch[0]}..{batch[-1]} ===", flush=True)
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
            # refresh pod and retry once
            pod = current_pod()
            print(f"retry on {pod}", flush=True)
            cmd[4] = pod
            p2 = subprocess.run(cmd)
            if p2.returncode != 0:
                return p2.returncode
        time.sleep(1)
        pod = current_pod()
    print("ALL DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
