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
| `MAX_NEW_COMPANIES` | 6 | discovery: new companies per cycle |
| `MAX_COMPANIES` | 20 | enrichment: companies per cycle (serial — see below) |
| `MAX_WEBSITE_RESOLVES` | 8 | website-resolve: companies per cycle |
| `MAX_REMEDY_COMPANIES` / `MAX_REMEDY_ROBOTS` | 12 / 12 | queue remediation: companies × robots/company per cycle |
| `MAX_REMEDY_WORKERS` | 4 | queue remediation: companies run in parallel (2026-07-30; see below) |
| `MAX_REJECTED` | 50 | rejection loop: robots per cycle |
| `T_DISCOVERY` / `T_ENRICH` / `T_QREMEDY` / `T_REJECT` | 90m / 120m / 45m / 45m | per-stage wall clocks |
| `SHIP_EVERY` | 600 | periodic log upload |
| `ENRICH_STALL_COOLDOWN_HOURS` | 168 | how long a no-progress robot is skipped |

### Parallelism: remediation vs. enrichment

Queue remediation (`remedy_dryrun.py --queue`) runs companies **in parallel**
(`--workers`, default 4) — each company gets its own API client and robots are
partitioned by company up front, so no two workers ever touch the same robot.
Playwright's sync API isn't thread-safe, but rather than disabling all
concurrency for that, `web_extract._PLAYWRIGHT_LOCK` serializes just the
render calls themselves — everything else (Tier-1 fetch, Gemini calls, DB
read/writes) stays parallel even with `RESEARCH_USE_PLAYWRIGHT=1`.

Enrichment (`overnight_queue_enrich.py`) still runs `--workers 1` — it was
built and deployed before the lock existed, and its own guard forces workers
back to 1 whenever `RESEARCH_USE_PLAYWRIGHT` is set regardless of what's
passed. It's a safe candidate for the same fix, just not done yet — do it as
its own change once remediation's concurrency has run for a few cycles in
prod, not bundled in.

## Operating notes

- **Test mode = continuous.** The runner loops; `Restart=always` brings it back if it
  dies. To return to nightly: restore `shutdown -h now`, set the unit to
  `Type=oneshot`, re-attach the `nightly-research-sched` policy.
- **The smoke gate is a hard gate.** Nearly every failure here is fail-open, so a
  broken run looks exactly like a quiet one. A failed gate skips the cycle without
  touching prod.
- **Artifacts** land in `gs://robotaigeek-core-enrichment/logs/` — one appended log
  plus per-cycle `*-c<N>.json` summaries.
