#!/usr/bin/env bash
# Research VM: TWO independent smoke-gated loops as separate systemd services.
#
#   discovery.service   — company gap resolve -> greenfield discovery (+import)
#   enrichment.service  — queue enrichment -> queue remediation -> rejection loop
#
# SPLIT 2026-08-04. They ran sequentially in one loop while discovery was
# effectively broken (~3s/cycle); once the Playwright+catalogue fixes made
# discovery real (~85min/cycle) it sat serially in front of remediation and
# stretched every cycle to ~4h — remediation got ~5.5 time-capped passes/day
# against a 379-company backlog that discovery itself was growing. The old
# "sequential so the stages can't collide on the prod rate limit" rationale
# died when InternalKeyAwareUserThrottle deployed (2026-07-27): internal-key
# traffic no longer shares one throttle bucket. The two loops still share ONE
# Gemini spend ledger (state/gemini_spend.json, flock-serialized since the
# split), so the daily budget binds globally across both.
#
# The smoke test is a HARD GATE in each loop. Almost every failure mode in
# this pipeline is fail-open (grounded calls swallow exceptions into None,
# unserialized fields read as absent), so a broken run looks exactly like a
# quiet one. If the gate fails the loop backs off without touching prod.
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
  # the runner scripts at a previous version while the boot looked successful.
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

# ---------------------------------------------------------------------------
# Shared plumbing for both runners: env, secrets, ship(), stage(), gate().
# Sourced (not executed) by each runner AFTER it sets LOG + LOG_BASENAME.
# ---------------------------------------------------------------------------
cat > "$APP_DIR/pipeline_common.sh" <<'COMMON'
PROJECT="robotaigeek-core"
BUCKET="robotaigeek-core-enrichment"
APP_DIR="/opt/enrichment"
CODE_DIR="$APP_DIR/repo/scripts/research"
PY="$APP_DIR/venv/bin/python"

export IMPORT_SYNC_API_BASE_URL="https://ragadmin.robotaigeek.com/api/v1/"
export RESEARCH_CREATED_BY_ID="1"
export PYTHONIOENCODING="utf-8"
export RESEARCH_DISABLE_APIFY="1"
export RESEARCH_USE_PLAYWRIGHT="1"
export IMPORT_SYNC_API_KEY="$(gcloud secrets versions access latest --secret=rag-import-sync-api-key --project=$PROJECT)"
export INTERNAL_API_SECRET="$(gcloud secrets versions access latest --secret=internal-api-secret --project=$PROJECT)"
export GEMINI_API_KEY="$(gcloud secrets versions access latest --secret=rag-gemini-api-key --project=$PROJECT)"
export SERPER_API_KEY="$(gcloud secrets versions access latest --secret=rag-serper-api-key --project=$PROJECT)"
# Hard daily ceiling on paid Gemini calls (spend_guard.py). Counted in
# state/gemini_spend.json, which survives deploys AND restarts, and is
# flock-serialized because BOTH services charge the same ledger — the budget
# is global across discovery and enrichment, not per-service.
export GEMINI_DAILY_CALL_BUDGET="${GEMINI_DAILY_CALL_BUDGET:-2500}"

ship() { gcloud storage cp "$LOG" "gs://$BUCKET/logs/$LOG_BASENAME" >/dev/null 2>&1 || true; }

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
  # Ship after EVERY stage: Spot VM, preemption can stop it at any moment, and an
  # end-of-run-only upload means a preempted night leaves NO record at all.
  ship
  return 0   # one stage failing must never skip the rest
}

# Smoke gate + backoff. Returns nonzero when the cycle should be skipped.
gate() {
  echo "--- GATE: smoke test ---"
  if ! "$PY" -u smoke_test.py; then
    echo "!! SMOKE TEST FAILED — skipping this cycle without touching prod."
    echo "!! backing off ${GATE_BACKOFF:-1800}s"
    ship
    sleep "${GATE_BACKOFF:-1800}"
    return 1
  fi
  echo "--- gate passed ---"
  return 0
}

# Periodic uploader. Spot VM: it can vanish mid-stage with ~30s notice; shipping on
# a timer needs no shutdown hook and no systemd ordering, so it survives an abrupt
# stop; worst case is losing the last interval of output rather than everything.
start_shipper() {
  ( while true; do sleep "${SHIP_EVERY:-600}"; ship; done ) &
  SHIPPER_PID=$!
  trap 'kill "$SHIPPER_PID" 2>/dev/null' EXIT
}
COMMON

# ---------------------------------------------------------------------------
# Runner 1: discovery loop (company gap resolve -> greenfield discovery+import)
# ---------------------------------------------------------------------------
cat > "$APP_DIR/run_discovery.sh" <<'RUNNER'
#!/usr/bin/env bash
set -uo pipefail
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="/var/log/discovery-$TS.log"
LOG_BASENAME="discovery-$TS.log"
source /opt/enrichment/pipeline_common.sh
start_shipper
cd "$CODE_DIR"
{
  echo "=== discovery run $TS (cycle sleep ${DISCOVERY_SLEEP:-1800}s) ==="
CYCLE=0
while true; do
  CYCLE=$((CYCLE + 1))
  echo ""
  echo "############ DISCOVERY CYCLE $CYCLE  $(date -u +%FT%TZ) ############"
  gate || continue

  # Seed list is DATA, not code: it changes independently of the bundle, so it is
  # pulled per run rather than baked in.
  mkdir -p staging/reports
  gcloud storage cp "gs://$BUCKET/data/competitor_gap_companies.json" \
    staging/reports/competitor_gap_companies.json >/dev/null 2>&1 \
    && echo "seed list pulled" || echo "!! no seed list — discovery will find nothing"

  # Company-level gaps, fixed BEFORE discovery/enrichment because both inherit them:
  #  * no website -> the company is INVISIBLE to enrichment and every remedy
  #  * no country -> enrichment copies company.country onto each robot, so a blank
  #    here reproduces the error-severity "No country" flag on every robot it owns
  stage "company gap resolve (website + country)" "${T_WEBRESOLVE:-15m}" \
    "$PY" -u resolve_pending_company_gaps.py --apply --max-companies "${MAX_WEBSITE_RESOLVES:-12}"

  stage "discovery (greenfield)" "${T_DISCOVERY:-90m}" \
    "$PY" -u overnight_greenfield_import.py --max-companies "${MAX_NEW_COMPANIES:-6}" --created-by-id 1

  "$PY" -c "from spend_guard import status; print('GEMINI SPEND:', status())" || true
  echo "=== discovery cycle $CYCLE finished $(date -u +%FT%TZ) ==="
  ship
  f=staging/reports/greenfield-import-summary.json
  [ -f "$f" ] && gcloud storage cp "$f" \
    "gs://$BUCKET/logs/$(basename "$f" .json)-$TS-c$CYCLE.json" >/dev/null 2>&1

  # Discovery sleeps LONGER than enrichment on purpose: inflow already outruns
  # remediation (379-company backlog, growing), and every discovered robot is
  # downstream work. Slowing the tap while the sink drains is the point of the
  # split — not discovering faster.
  sleep "${DISCOVERY_SLEEP:-1800}"
done
} >>"$LOG" 2>&1
RUNNER
chmod +x "$APP_DIR/run_discovery.sh"

# ---------------------------------------------------------------------------
# Runner 2: enrichment loop (queue enrich -> queue remediation -> rejection loop)
# ---------------------------------------------------------------------------
cat > "$APP_DIR/run_enrich.sh" <<'RUNNER'
#!/usr/bin/env bash
set -uo pipefail
TS="$(date -u +%Y%m%d-%H%M%S)"
LOG="/var/log/enrich-$TS.log"
LOG_BASENAME="enrich-$TS.log"
source /opt/enrichment/pipeline_common.sh
start_shipper
cd "$CODE_DIR"
{
  echo "=== enrichment run $TS (cycle sleep ${CYCLE_SLEEP:-300}s) ==="
CYCLE=0
while true; do
  CYCLE=$((CYCLE + 1))
  echo ""
  echo "############ ENRICH CYCLE $CYCLE  $(date -u +%FT%TZ) ############"
  gate || continue

  mkdir -p staging/reports

  # FAST_COMPANY_IDS turns a long cycle into ~15min for iterating on the pipeline
  # itself. Companies run in parallel: each worker is fully isolated (own API
  # client) and Playwright's render calls self-serialize via
  # web_extract._PLAYWRIGHT_LOCK, so this is safe with RESEARCH_USE_PLAYWRIGHT=1.
  if [ -n "${FAST_COMPANY_IDS:-}" ]; then
    stage "enrichment (FAST: companies ${FAST_COMPANY_IDS})" "${T_ENRICH:-20m}" \
      "$PY" -u overnight_queue_enrich.py --workers "${MAX_ENRICH_WORKERS:-4}" --company-ids "$FAST_COMPANY_IDS"
  else
    stage "enrichment (gap-fill, oldest first)" "${T_ENRICH:-120m}" \
      "$PY" -u overnight_queue_enrich.py --workers "${MAX_ENRICH_WORKERS:-4}" --max-companies "${MAX_COMPANIES:-32}"
  fi

  # Flag-driven remedies for PENDING robots (vision photos, tags, family, purpose...).
  # Time-bound, not cap-bound: it hit the full 45m window EVERY cycle (rc=124) while
  # sharing a 4h sequential cycle with discovery. The service split exists largely
  # to give this stage more wall-clock — raised 45m -> 90m (2026-08-04) because the
  # enrichment loop no longer waits behind an ~85min discovery stage.
  stage "queue remediation (pending flags)" "${T_QREMEDY:-90m}" \
    "$PY" -u remedy_dryrun.py --queue --apply \
      --max-queue-companies "${MAX_REMEDY_COMPANIES:-18}" --max-robots "${MAX_REMEDY_ROBOTS:-12}" \
      --workers "${MAX_REMEDY_WORKERS:-6}"

  stage "rejection feedback loop" "${T_REJECT:-45m}" \
    "$PY" -u rejection_feedback_loop.py --max-robots "${MAX_REJECTED:-50}" --apply

  # Same-hour spend visibility: today's paid-call count against the budget, in
  # every cycle log. The $76-day was only caught by a human reading the bill.
  "$PY" -c "from spend_guard import status; print('GEMINI SPEND:', status())" || true

  echo "=== enrich cycle $CYCLE finished $(date -u +%FT%TZ) ==="
  ship
  # Reports are per-cycle so a later cycle never silently overwrites the evidence
  # from an earlier one.
  for f in staging/reports/overnight-queue-summary.json \
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
chmod +x "$APP_DIR/run_enrich.sh"

# NOTE: a systemd ExecStop hook was tried here and REMOVED — it never fired. With
# DefaultDependencies=no the stop action can run after network teardown, and gcloud
# needs the network, so it silently shipped nothing. Preemption safety is handled
# instead by the periodic uploader inside each runner.
systemctl disable --now nightly-shutdown.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/nightly-shutdown.service
# The pre-split single-loop service. Removed on every boot so an old unit file
# can never resurrect the sequential pipeline alongside the split ones.
systemctl disable --now nightly.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/nightly.service
rm -f "$APP_DIR/run_nightly.sh"

cat > /etc/systemd/system/discovery.service <<'UNIT'
[Unit]
Description=RobotAIGeek discovery loop (smoke-gated company gaps + greenfield discovery)
After=network-online.target
Wants=network-online.target

[Service]
# Type=simple + Restart=always: the runner is a LOOP. If it dies (crash, OOM, a
# stage killing the shell) systemd brings it back rather than leaving the VM up
# doing nothing — which would look identical to "running fine".
Type=simple
ExecStart=/opt/enrichment/run_discovery.sh
Restart=always
RestartSec=60
TimeoutStartSec=0
UNIT

cat > /etc/systemd/system/enrichment.service <<'UNIT'
[Unit]
Description=RobotAIGeek enrichment loop (smoke-gated queue enrich + remediation + rejection)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/enrichment/run_enrich.sh
Restart=always
RestartSec=60
TimeoutStartSec=0
UNIT
systemctl daemon-reload

AUTORUN="$(curl -s -H 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/instance/attributes/enrichment-autorun' 2>/dev/null || echo 0)"
echo "enrichment-autorun=$AUTORUN"
if [ "$AUTORUN" = "1" ]; then
  systemctl start --no-block discovery.service enrichment.service
else
  echo "--- autorun disabled; VM idle (manual/debug boot) ---"
fi
echo "=== startup done $(date -u +%FT%TZ) ==="
