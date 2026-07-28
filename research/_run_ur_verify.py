"""Run prod verify_content on Universal Robots (192) pending_review robots."""
from __future__ import annotations

import subprocess
import sys
import time

NS = "rag-server-prod"
BATCH = 8
COMPANY_ID = 192


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


def pending_ids(pod: str) -> list[int]:
    py = (
        "from robots.models import Robot; "
        f"ids=list(Robot.objects.filter(company_ref_id={COMPANY_ID},status='pending_review')"
        ".order_by('id').values_list('id', flat=True)); "
        "print(','.join(map(str, ids)))"
    )
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
        py,
    )
    for ln in reversed([x.strip() for x in out.splitlines() if x.strip()]):
        if all(p.isdigit() for p in ln.split(",") if p):
            return [int(x) for x in ln.split(",") if x.isdigit()]
    return []


def verify_batch(pod: str, ids: list[int]) -> None:
    idstr = ",".join(map(str, ids))
    print(f"\n=== FORCE VERIFY {ids[0]}..{ids[-1]} ({len(ids)}) on {pod} ===", flush=True)
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


def summarize(pod: str, ids: list[int]) -> None:
    idlist = ",".join(map(str, ids))
    py = (
        "from robots.models import Robot; "
        f"qs=Robot.objects.filter(id__in=[{idlist}]).order_by('id'); "
        "vals=list(qs.values_list('id','name','verification_confidence')); "
        "print('---SUMMARY---'); "
        "[print(f'{i}|{n}|{c}') for i,n,c in vals]; "
        "conf=[c for _,_,c in vals if c is not None]; "
        "print(f'count={len(vals)} with_conf={len(conf)} "
        "avg={round(sum(conf)/len(conf),1) if conf else None}')"
    )
    print(sh(
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
        py,
    ))


def main() -> int:
    pod = current_pod()
    ids = pending_ids(pod)
    print(f"pod={pod} pending={len(ids)}", flush=True)
    if not ids:
        print("no pending robots")
        return 0
    for i in range(0, len(ids), BATCH):
        batch = ids[i : i + BATCH]
        try:
            verify_batch(pod, batch)
        except SystemExit:
            pod = current_pod()
            print(f"retry batch on {pod}", flush=True)
            verify_batch(pod, batch)
        time.sleep(2)
    pod = current_pod()
    summarize(pod, ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
