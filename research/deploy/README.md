# Continuous research VM

`vm_startup.sh` is the GCE **startup-script** for instance `discovery-bakeoff`
(`robotaigeek-core` / `asia-southeast1-b`). It is the whole pipeline orchestration —
smoke gate, stage order, per-stage timeouts, log shipping, the cycle loop — and it
lives here rather than only in instance metadata so it is reviewable and versioned.
It previously existed only in a temp directory; the sole other copy was the metadata
on the VM itself.

## Deploying

Two independent things ship, and confusing them wastes a cycle:

| What | How | When it takes effect |
|---|---|---|
| **Python pipeline** (`scripts/research/**`, `robotaigeek-server/robots/**`) | re-upload the tarball to `gs://robotaigeek-core-enrichment/code/repo-code.tar.gz` | next VM **boot** (the startup script re-pulls every boot) |
| **This orchestration script** | `gcloud compute instances add-metadata … --metadata-from-file startup-script=vm_startup.sh` | next boot, or `sudo google_metadata_script_runner startup` in place |

```bash
GC="--account martti@robotaigeek.com --project robotaigeek-core"

# 1. pipeline code
tar --exclude='scripts/research/.venv' --exclude='scripts/research/staging' \
    --exclude='scripts/research/docs' --exclude='scripts/research/state' \
    --exclude='**/__pycache__' --exclude='*.pyc' \
    -czf /tmp/repo-code.tar.gz scripts/research robotaigeek-server/robots
gcloud storage cp /tmp/repo-code.tar.gz \
  gs://robotaigeek-core-enrichment/code/repo-code.tar.gz $GC

# 2. this script
gcloud compute instances add-metadata discovery-bakeoff --zone asia-southeast1-b $GC \
  --metadata-from-file startup-script=scripts/research/deploy/vm_startup.sh
```

Verify a startup change actually landed — a failed startup script leaves the OLD
`run_nightly.sh` in place while the boot still looks successful:

```bash
sudo ls -la /opt/enrichment/run_nightly.sh   # mtime must be after your change
```

## Fast iteration

A normal cycle is ~2.5h, which is far too slow to debug the pipeline. Roughly 7min of
every cycle is spent **paginating 1650 pending robots** before any work begins — that
scan, not the enrichment, is what makes feedback slow.

`FAST_COMPANY_IDS` targets named companies, which skips the scan entirely:

```bash
sudo systemctl stop nightly.service
sudo nohup env \
  FAST_COMPANY_IDS=107,204 \
  MAX_NEW_COMPANIES=1 MAX_REJECTED=3 \
  T_DISCOVERY=10m T_ENRICH=15m T_REJECT=8m \
  CYCLE_SLEEP=60 SHIP_EVERY=120 \
  /opt/enrichment/run_nightly.sh > /tmp/fast.log 2>&1 &
```

Fastest of all: run the stages **locally** — no VM, no bundle upload, full tracebacks.
The VM only adds value for realistic scale and unattended duration.

```bash
cd scripts/research
python -u smoke_test.py                                   # ~20s, is the pipeline alive
python -u remedy_dryrun.py --company-id 107 --max-robots 3 # dry-run, writes nothing
python -u rejection_feedback_loop.py --max-robots 3        # dry-run by default
```

## Env knobs

| Var | Default | Purpose |
|---|---|---|
| `FAST_COMPANY_IDS` | *(unset)* | target companies; skips the full queue scan |
| `CYCLE_SLEEP` | 300 | pause between cycles |
| `GATE_BACKOFF` | 1800 | pause after a failed smoke gate |
| `MAX_NEW_COMPANIES` / `MAX_COMPANIES` / `MAX_REJECTED` | 3 / 8 / 25 | per-stage caps |
| `T_DISCOVERY` / `T_ENRICH` / `T_REJECT` | 90m / 120m / 45m | per-stage wall clocks |
| `SHIP_EVERY` | 600 | periodic log upload |
| `ENRICH_STALL_COOLDOWN_HOURS` | 168 | how long a no-progress robot is skipped |

## Operating notes

- **Test mode = continuous.** The runner loops; `Restart=always` brings it back if it
  dies. To return to nightly: restore `shutdown -h now`, set the unit to
  `Type=oneshot`, re-attach the `nightly-research-sched` policy.
- **The smoke gate is a hard gate.** Nearly every failure here is fail-open, so a
  broken run looks exactly like a quiet one. A failed gate skips the cycle without
  touching prod.
- **Artifacts** land in `gs://robotaigeek-core-enrichment/logs/` — one appended log
  plus per-cycle `*-c<N>.json` summaries.
