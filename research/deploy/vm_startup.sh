#!/usr/bin/env bash
# Nightly research VM: smoke-gated discovery -> enrichment -> rejection loop.
#
# All three stages run HERE, sequentially, in pipeline order. Consolidating them onto
# one Spot VM is both cheaper than a separate Cloud Run Job (the box is already booting;
# Cloud Run bills per vCPU-second and would need its own ~1GB Playwright image) and
# safer: running sequentially on one host means discovery and enrichment CANNOT overlap
# on the shared prod API rate limit, which two staggered schedules could only approximate.
#
# The smoke test is a HARD GATE. Almost every failure mode in this pipeline is
# fail-open (grounded calls swallow exceptions into None, unserialized fields read as
# absent), so a broken run looks exactly like a quiet one: hours of work, zero
# changes, no error. If the gate fails we ship the log and power off without touching
# prod, because an unattended run that cannot tell "nothing to do" from "everything is
# broken" is worse than no run at all.
set -uo pipefail
exec > >(tee -a /var/log/enrichment-startup.log) 2>&1
echo "=== startup $(date -u +%FT%TZ) ==="

PROJECT="robotaigeek-core"
BUCKET="robotaigeek-core-enrichment"
APP_DIR="/opt/enrichment"
REPO_DIR="$APP_DIR/repo"
CODE_DIR="$REPO_DIR/scripts/research"

provision() {
  echo "--- provisioning ---"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y python3-venv python3-pip curl gnupg
  if ! command -v gcloud >/dev/null 2>&1; then
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
      > /etc/apt/sources.list.d/google-cloud-sdk.list
    curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
    apt-get update -y && apt-get install -y google-cloud-cli
  fi

  mkdir -p "$REPO_DIR"
  gcloud storage cp "gs://$BUCKET/code/repo-code.tar.gz" /tmp/repo-code.tar.gz
  tar xzf /tmp/repo-code.tar.gz -C "$REPO_DIR"

  python3 -m venv "$APP_DIR/venv"
  "$APP_DIR/venv/bin/pip" install --upgrade pip
  "$APP_DIR/venv/bin/pip" install -r "$CODE_DIR/requirements.txt"
  touch "$APP_DIR/.provisioned"
  echo "--- provisioning complete ---"
}

# Separate and self-checking on purpose. Bundling this inside provision() meant an
# already-provisioned VM skipped it entirely and silently ran without a browser —
# every JS-rendered catalogue would have returned nothing and looked like "no data".
# Each provisioning step must verify its OWN artefact, not trust one global flag.
ensure_playwright() {
  # NOT "$HOME": the GCE metadata script runner does not export HOME, and with
  # `set -u` that expansion ABORTS the whole startup script — which silently left
  # run_nightly.sh at a previous version while the boot looked successful.
  local pw_cache="${PLAYWRIGHT_BROWSERS_PATH:-${HOME:-/root}/.cache/ms-playwright}"
  if "$APP_DIR/venv/bin/python" -c "import playwright" >/dev/null 2>&1 \
     && ls -d "$pw_cache"/chromium-* >/dev/null 2>&1; then
    echo "--- playwright already present ($pw_cache) ---"
    return 0
  fi
  echo "--- installing playwright + chromium (~400MB, first boot only) ---"
  "$APP_DIR/venv/bin/pip" install -q playwright
  "$APP_DIR/venv/bin/playwright" install --with-deps chromium
  "$APP_DIR/venv/bin/python" -c "import playwright; print('playwright import OK')"
}

# Always refresh code, even when already provisioned — otherwise the VM silently
# keeps running whatever bundle it first booted with.
refresh_code() {
  echo "--- refreshing code bundle ---"
  gcloud storage cp "gs://$BUCKET/code/repo-code.tar.gz" /tmp/repo-code.tar.gz && \
    tar xzf /tmp/repo-code.tar.gz -C "$REPO_DIR" && echo "code refreshed"
  "$APP_DIR/venv/bin/pip" install -q -r "$CODE_DIR/requirements.txt" 2>&1 | tail -2
}

[ -f "$APP_DIR/.provisioned" ] || provision
refresh_code
ensure_playwright

cat > "$APP_DIR/run_nightly.sh" <<'RUNNER'
#!/usr/bin/env bash
set -uo pipefail
PROJECT="robotaigeek-core"
BUCKET="robotaigeek-core-enrichment"
APP_DIR="/opt/enrichment"
CODE_DIR="$APP_DIR/repo/scripts/research"
PY="$APP_DIR/venv/bin/python"
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="/var/log/nightly-$TS.log"

export IMPORT_SYNC_API_BASE_URL="https://ragadmin.robotaigeek.com/api/v1/"
export RESEARCH_CREATED_BY_ID="1"
export PYTHONIOENCODING="utf-8"
export RESEARCH_DISABLE_APIFY="1"
export RESEARCH_USE_PLAYWRIGHT="1"
export IMPORT_SYNC_API_KEY="$(gcloud secrets versions access latest --secret=rag-import-sync-api-key --project=$PROJECT)"
export INTERNAL_API_SECRET="$(gcloud secrets versions access latest --secret=internal-api-secret --project=$PROJECT)"
export GEMINI_API_KEY="$(gcloud secrets versions access latest --secret=rag-gemini-api-key --project=$PROJECT)"
export SERPER_API_KEY="$(gcloud secrets versions access latest --secret=rag-serper-api-key --project=$PROJECT)"

ship() { gcloud storage cp "$LOG" "gs://$BUCKET/logs/nightly-$TS.log" >/dev/null 2>&1 || true; }

# Periodic uploader. This VM is Spot: it can vanish mid-stage with ~30s notice, and
# the first supervised run proved the cost — preempted during enrichment, nothing
# ever reached GCS, so the night was unauditable. Shipping on a timer needs no
# shutdown hook and no systemd ordering, so it survives an abrupt stop; the worst
# case is losing the last interval of output rather than everything.
( while true; do sleep "${SHIP_EVERY:-600}"; ship; done ) &
SHIPPER_PID=$!
trap 'kill "$SHIPPER_PID" 2>/dev/null' EXIT

# Run one pipeline stage under a wall-clock limit. A hung stage must not starve the
# ones after it, and a stage cut short must SAY so — a truncated run that reports
# nothing looks exactly like a run with nothing to do, which is the failure mode this
# whole pipeline keeps producing.
stage() {
  local name="$1" limit="$2"; shift 2
  echo "--- $name (limit ${limit}) ---"
  local t0=$SECONDS
  timeout --signal=INT "$limit" "$@"
  local rc=$?
  if [ "$rc" -eq 124 ] || [ "$rc" -eq 130 ]; then
    echo "!! $name TIMED OUT after ${limit} — results are PARTIAL, not empty."
  fi
  echo "$name rc=$rc elapsed=$((SECONDS - t0))s"
  # Ship after EVERY stage, not just at the end. This is a Spot VM: preemption can
  # stop it at any moment, and an end-of-run-only upload means a preempted night
  # leaves NO record at all — which is exactly what happened on the first supervised
  # run (preempted mid-enrichment, GCS empty, hours of work invisible).
  ship
  return 0   # one stage failing must never skip the rest
}

cd "$CODE_DIR"
{
  echo "=== run $TS (continuous mode, cycle every ${CYCLE_SLEEP:-300}s) ==="

# TEST MODE: loop instead of one pass + poweroff. Faster feedback beats a tidy
# nightly window while the pipeline is still revealing bugs — a once-a-day run
# means a once-a-day lesson. Revert to a single pass (and restore `shutdown -h now`)
# once it runs clean, because continuous costs ~5x the compute and, more
# significantly, keeps spending Gemini/serper quota around the clock.
CYCLE=0
while true; do
  CYCLE=$((CYCLE + 1))
  echo ""
  echo "############ CYCLE $CYCLE  $(date -u +%FT%TZ) ############"

  echo "--- GATE: smoke test ---"
  if ! "$PY" -u smoke_test.py; then
    echo "!! SMOKE TEST FAILED — skipping this cycle without touching prod."
    # Back off hard rather than hammering a broken pipeline (or a throttled API)
    # every few minutes. A failing gate is usually environmental and needs a human.
    echo "!! backing off ${GATE_BACKOFF:-1800}s"
    ship
    sleep "${GATE_BACKOFF:-1800}"
    continue
  fi
  echo "--- gate passed ---"

  # Seed list is DATA, not code: it changes independently of the bundle, so it is
  # pulled per run rather than baked in.
  mkdir -p staging/reports
  gcloud storage cp "gs://$BUCKET/data/competitor_gap_companies.json" \
    staging/reports/competitor_gap_companies.json >/dev/null 2>&1 \
    && echo "seed list pulled" || echo "!! no seed list — discovery will find nothing"

  # Company-level gaps, fixed BEFORE enrichment because enrichment inherits them:
  #  * no website -> the company is INVISIBLE to enrichment and every remedy
  #    (60 companies / 345 pending robots parked that way, found 2026-07-29)
  #  * no country -> enrichment copies company.country onto each robot, so a blank
  #    here reproduces the error-severity "No country" flag on every robot it
  #    will ever own (232/806 companies, 351 pending robots, found 2026-07-31)
  # One pass covers both. Failures cool down a week in their own per-field ledger.
  stage "company gap resolve (website + country)" "${T_WEBRESOLVE:-15m}"     "$PY" -u resolve_pending_company_gaps.py --apply --max-companies "${MAX_WEBSITE_RESOLVES:-12}"

  # Order is the pipeline order: discovery creates pending_review robots, enrichment
  # fills them the SAME night, then the rejection loop reworks what reviewers bounced.
  # Sequential on one host is also why discovery and enrichment can no longer collide
  # on the shared prod rate limit.
  stage "discovery (greenfield)" "${T_DISCOVERY:-90m}" \
    "$PY" -u overnight_greenfield_import.py --max-companies "${MAX_NEW_COMPANIES:-6}" --created-by-id 1

  # FAST_COMPANY_IDS turns a ~2.5h cycle into ~15min for iterating on the pipeline
  # itself. It targets named companies, which ALSO skips the full pending scan —
  # ~7min of every cycle is spent paginating 1650 robots before any work starts, so
  # that scan, not the enrichment, is the thing making feedback slow.
  # Playwright's sync API is not thread-safe, hence --workers 1 while it is enabled.
  if [ -n "${FAST_COMPANY_IDS:-}" ]; then
    stage "enrichment (FAST: companies ${FAST_COMPANY_IDS})" "${T_ENRICH:-20m}" \
      "$PY" -u overnight_queue_enrich.py --workers 1 --company-ids "$FAST_COMPANY_IDS"
  else
    stage "enrichment (gap-fill, oldest first)" "${T_ENRICH:-120m}" \
      "$PY" -u overnight_queue_enrich.py --workers 1 --max-companies "${MAX_COMPANIES:-20}"
  fi

  # Flag-driven remedies for PENDING robots (vision photos, tags, family, purpose...).
  # Previously these ran only on REJECTED robots, so To Review sat full of fixable
  # warnings that gap-fill enrichment never saw. Ledgered via auto_fix_attempts.
  # Companies run in parallel (each robot belongs to exactly one company, so no two
  # workers ever touch the same robot); Playwright's render calls self-serialize via
  # web_extract._PLAYWRIGHT_LOCK, so this is safe even with RESEARCH_USE_PLAYWRIGHT=1.
  stage "queue remediation (pending flags)" "${T_QREMEDY:-45m}"     "$PY" -u remedy_dryrun.py --queue --apply       --max-queue-companies "${MAX_REMEDY_COMPANIES:-12}" --max-robots "${MAX_REMEDY_ROBOTS:-12}"       --workers "${MAX_REMEDY_WORKERS:-4}"

  stage "rejection feedback loop" "${T_REJECT:-45m}" \
    "$PY" -u rejection_feedback_loop.py --max-robots "${MAX_REJECTED:-50}" --apply

  echo "=== cycle $CYCLE finished $(date -u +%FT%TZ) ==="
  ship
  # Reports are per-cycle so a later cycle never silently overwrites the evidence
  # from an earlier one.
  for f in staging/reports/greenfield-import-summary.json \
           staging/reports/overnight-queue-summary.json \
           staging/reports/rejection-loop-report.json; do
    [ -f "$f" ] && gcloud storage cp "$f" \
      "gs://$BUCKET/logs/$(basename "$f" .json)-$TS-c$CYCLE.json" >/dev/null 2>&1
  done

  # Breather between cycles: gives prod's rate limiter room and stops a
  # zero-work cycle from spinning hot.
  sleep "${CYCLE_SLEEP:-300}"
done
} >>"$LOG" 2>&1
RUNNER
chmod +x "$APP_DIR/run_nightly.sh"

# NOTE: a systemd ExecStop hook was tried here and REMOVED — it never fired. With
# DefaultDependencies=no the stop action can run after network teardown, and gcloud
# needs the network, so it silently shipped nothing. Preemption safety is handled
# instead by a periodic uploader inside the runner (below), which depends on no
# shutdown ordering at all. Keeping a safety net that does not fire is worse than
# having none, because it buys false confidence.
systemctl disable --now nightly-shutdown.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/nightly-shutdown.service

cat > /etc/systemd/system/nightly.service <<'UNIT'
[Unit]
Description=RobotAIGeek continuous pipeline (smoke-gated discovery/enrichment/rejection)
After=network-online.target
Wants=network-online.target

[Service]
# Type=simple + Restart=always: the runner is now a LOOP, not a one-shot. If it
# dies (crash, OOM, a stage killing the shell) systemd brings it back rather than
# leaving the VM up doing nothing — which would look identical to "running fine".
Type=simple
ExecStart=/opt/enrichment/run_nightly.sh
Restart=always
RestartSec=60
TimeoutStartSec=0
UNIT
systemctl daemon-reload

AUTORUN="$(curl -s -H 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/instance/attributes/enrichment-autorun' 2>/dev/null || echo 0)"
echo "enrichment-autorun=$AUTORUN"
if [ "$AUTORUN" = "1" ]; then
  systemctl start --no-block nightly.service
else
  echo "--- autorun disabled; VM idle (manual/debug boot) ---"
fi
echo "=== startup done $(date -u +%FT%TZ) ==="
