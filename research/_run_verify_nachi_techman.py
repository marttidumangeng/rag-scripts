"""Run prod verify_content over the 63 robots imported from the Nachi and
Techman structured catalogues (2026-08-03).

Two things this handles that a naive runner does not:

1. **Never hard-code a pod name.** The first attempt did, and the cluster
   deleted that pod mid-run (node churn, not OOM — no container restarts, no
   termination reason). The exec died with 137 and every subsequent batch then
   failed `NotFound` against a pod that no longer existed, so one transient
   event cost all 7 batches. The pod is now resolved fresh before each batch,
   and only a READY (2/2) pod is used.

2. **Retry a failed batch once.** verify_content is a paid Gemini path, so the
   goal is to avoid re-running work that already succeeded — but a batch killed
   by pod churn persisted nothing, so retrying it is correct and not
   double-spending. `--force` makes the retry idempotent either way.

Batch size 5 keeps each exec short, which is what survives churn.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

NS = "rag-server-prod"
SELECTOR = "app=robotaigeek,environment=prod"
BATCH = 5

# Techman 6901-6908, Nachi 6909-6963.
_env_ids = [int(x) for x in (os.environ.get("VERIFY_IDS") or "").split(",") if x.strip()]
IDS = _env_ids or list(range(6901, 6964))

ENV = {**os.environ, "CLOUDSDK_CORE_ACCOUNT": "martti@robotaigeek.com"}


def ready_pod() -> str | None:
    """Newest READY pod, or None. Unready pods are still booting and will
    refuse exec."""
    try:
        out = subprocess.run(
            ["kubectl", "get", "pods", "-n", NS, "-l", SELECTOR, "-o", "json"],
            capture_output=True, text=True, env=ENV, timeout=90,
        ).stdout
        data = json.loads(out)
    except (subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return None
    ready = [
        p["metadata"]["name"]
        for p in data.get("items", [])
        if p.get("status", {}).get("phase") == "Running"
        and all(c.get("ready") for c in p["status"].get("containerStatuses") or [])
    ]
    return ready[0] if ready else None


def run(ids: list[int], attempt: int = 1) -> bool:
    pod = ready_pod()
    if not pod:
        print("   no READY pod; waiting 20s", flush=True)
        time.sleep(20)
        pod = ready_pod()
        if not pod:
            print("   still no READY pod — skipping batch", flush=True)
            return False

    idstr = ",".join(map(str, ids))
    print(f"\n=== VERIFY {ids[0]}..{ids[-1]} ({len(ids)}) on {pod} "
          f"[attempt {attempt}] ===", flush=True)
    cmd = [
        "kubectl", "exec", "-n", NS, pod, "-c", "django-app", "--",
        "python", "manage.py", "verify_content",
        "--status", "pending_review",
        "--ids", idstr,
        "--force",
        "--delay", "0.5",
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", env=ENV)
    for line in p.stdout:
        line = line.rstrip()
        if line:
            print("   " + line, flush=True)
    p.wait()
    ok = p.returncode == 0
    print(f"=== exit {p.returncode} ===", flush=True)
    if not ok and attempt == 1:
        print("   retrying once on a freshly resolved pod", flush=True)
        time.sleep(10)
        return run(ids, attempt=2)
    return ok


def main() -> int:
    failed: list[tuple[int, int]] = []
    for i in range(0, len(IDS), BATCH):
        chunk = IDS[i:i + BATCH]
        if not run(chunk):
            failed.append((chunk[0], chunk[-1]))
    print(f"\nALL DONE — {len(IDS)} robots, {len(failed)} failed batch(es): {failed}",
          flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
