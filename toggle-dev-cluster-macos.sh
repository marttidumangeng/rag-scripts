#!/usr/bin/env bash
set -euo pipefail

ACTION=""
MODE="workloads"
PROJECT_ID="robotaigeek-core"
CLUSTER_NAME="rag-cluster-dev"
REGION="asia-southeast1"
NAMESPACES=("default" "rag-web-dev")
DELETE_INGRESS="true"
FORCE="false"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE_FILE="$REPO_ROOT/tmp_ignore/dev-cluster-state-macos.tsv"

log_step() {
  echo "[dev-cluster-toggle] $*"
}

fail() {
  echo "[dev-cluster-toggle] ERROR: $*" >&2
  exit 1
}

ensure_tool() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    fail "Required tool '$name' is not installed or not in PATH."
  fi
}

usage() {
  cat <<'EOF'
Usage:
  ./scripts/toggle-dev-cluster-macos.sh <off|on|status> [options]

Options:
  --mode workloads|cluster         Default: workloads
  --project-id <id>                Default: robotaigeek-core
  --cluster-name <name>            Default: rag-cluster-dev
  --region <region>                Default: asia-southeast1
  --namespaces ns1,ns2             Default: default,rag-web-dev
  --state-file <path>              Default: tmp_ignore/dev-cluster-state-macos.tsv
  --no-delete-ingress              Keep ingress during off action
  --force                          Required for mode=cluster destructive actions
  -h, --help                       Show this help

Examples:
  ./scripts/toggle-dev-cluster-macos.sh off
  ./scripts/toggle-dev-cluster-macos.sh on
  ./scripts/toggle-dev-cluster-macos.sh status
EOF
}

parse_args() {
  if [[ $# -lt 1 ]]; then
    usage
    exit 1
  fi

  ACTION="$1"
  shift

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --mode)
        MODE="$2"
        shift 2
        ;;
      --project-id)
        PROJECT_ID="$2"
        shift 2
        ;;
      --cluster-name)
        CLUSTER_NAME="$2"
        shift 2
        ;;
      --region)
        REGION="$2"
        shift 2
        ;;
      --namespaces)
        IFS=',' read -r -a NAMESPACES <<< "$2"
        shift 2
        ;;
      --state-file)
        STATE_FILE="$2"
        shift 2
        ;;
      --no-delete-ingress)
        DELETE_INGRESS="false"
        shift
        ;;
      --force)
        FORCE="true"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        fail "Unknown option: $1"
        ;;
    esac
  done

  case "$ACTION" in
    off|on|status) ;;
    *) fail "Action must be one of: off, on, status" ;;
  esac

  case "$MODE" in
    workloads|cluster) ;;
    *) fail "Mode must be one of: workloads, cluster" ;;
  esac
}

ensure_cluster_credentials() {
  log_step "Ensuring kube credentials for $CLUSTER_NAME in $REGION"
  log_step "gcloud container clusters get-credentials $CLUSTER_NAME --region $REGION --project $PROJECT_ID"
  gcloud container clusters get-credentials "$CLUSTER_NAME" --region "$REGION" --project "$PROJECT_ID"
}

save_state() {
  mkdir -p "$(dirname "$STATE_FILE")"

  {
    echo "# projectId=$PROJECT_ID"
    echo "# clusterName=$CLUSTER_NAME"
    echo "# region=$REGION"
    echo "# savedAtUtc=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    for ns in "${NAMESPACES[@]}"; do
      kubectl get deployments -n "$ns" -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.replicas}{"\n"}{end}'
    done
  } > "$STATE_FILE"

  log_step "State saved to $STATE_FILE"
}

restore_replica_state() {
  local line ns name replicas

  if [[ ! -f "$STATE_FILE" ]]; then
    fail "State file not found: $STATE_FILE"
  fi

  while IFS= read -r line; do
    [[ -z "$line" || "${line:0:1}" == "#" ]] && continue

    IFS=$'\t' read -r ns name replicas <<< "$line"
    [[ -z "$ns" || -z "$name" ]] && continue
    [[ -z "$replicas" ]] && replicas="1"

    log_step "Restoring deployment $ns/$name replicas=$replicas"
    kubectl scale deployment "$name" -n "$ns" --replicas="$replicas" >/dev/null
  done < "$STATE_FILE"
}

restore_default_replica_state() {
  log_step "State file not found. Applying default dev replica counts."

  log_step "Restoring default deployment default/robotaigeek-dev replicas=1"
  kubectl scale deployment robotaigeek-dev -n default --replicas=1 >/dev/null

  log_step "Restoring default deployment default/robotaigeek-mcp-dev replicas=1"
  kubectl scale deployment robotaigeek-mcp-dev -n default --replicas=1 >/dev/null

  log_step "Restoring default deployment rag-web-dev/robotaigeek-web replicas=1"
  kubectl scale deployment robotaigeek-web -n rag-web-dev --replicas=1 >/dev/null
}

remove_hpas() {
  local ns hpa
  for ns in "${NAMESPACES[@]}"; do
    while IFS= read -r hpa; do
      [[ -z "$hpa" ]] && continue
      log_step "Deleting HPA $ns/$hpa"
      kubectl delete hpa "$hpa" -n "$ns" --ignore-not-found >/dev/null
    done < <(kubectl get hpa -n "$ns" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')
  done
}

delete_dev_ingresses() {
  local ns ingress
  for ns in "${NAMESPACES[@]}"; do
    while IFS= read -r ingress; do
      [[ -z "$ingress" ]] && continue
      log_step "Deleting ingress $ns/$ingress"
      kubectl delete ingress "$ingress" -n "$ns" --ignore-not-found --wait=false >/dev/null
    done < <(kubectl get ingress -n "$ns" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')
  done
}

apply_dev_hpa_manifest() {
  local hpa_path="$REPO_ROOT/robotaigeek-server/k8s/dev/hpa.yaml"
  if [[ -f "$hpa_path" ]]; then
    log_step "Applying HPA manifest: $hpa_path"
    kubectl apply -f "$hpa_path" >/dev/null
  else
    log_step "HPA manifest not found at $hpa_path (skipping)."
  fi
}

reset_failed_managed_certificates() {
  local ns cert_name cert_status

  for ns in default rag-web-dev; do
    while IFS=$'\t' read -r cert_name cert_status; do
      [[ -z "$cert_name" ]] && continue
      if [[ "$cert_status" == "ProvisioningFailedPermanently" ]]; then
        log_step "Recreating failed managed certificate $ns/$cert_name"
        kubectl delete managedcertificate "$cert_name" -n "$ns" --ignore-not-found >/dev/null
      fi
    done < <(kubectl get managedcertificate -n "$ns" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.certificateStatus}{"\n"}{end}' 2>/dev/null || true)
  done
}

apply_dev_ingress_manifests() {
  local path
  local ingress_paths=(
    "$REPO_ROOT/robotaigeek-server/k8s/dev/ingress.yaml"
    "$REPO_ROOT/robotaigeek-server/k8s/dev/mcp/mcp-ingress.yaml"
    "$REPO_ROOT/robotaigeek-web/k8s/dev/ingress.yaml"
  )

  reset_failed_managed_certificates

  for path in "${ingress_paths[@]}"; do
    if [[ -f "$path" ]]; then
      log_step "Applying ingress manifest: $path"
      kubectl apply -f "$path" >/dev/null
    fi
  done
}

verify_off_state() {
  local ns name replicas has_running="false" has_ingress="false" ingress_name

  for ns in "${NAMESPACES[@]}"; do
    while IFS=$'\t' read -r name replicas; do
      [[ -z "$name" ]] && continue
      if [[ -n "$replicas" && "$replicas" != "0" ]]; then
        has_running="true"
        log_step "WARNING: deployment still has replicas > 0: $ns/$name=$replicas"
      fi
    done < <(kubectl get deployments -n "$ns" -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.replicas}{"\n"}{end}')
  done

  if [[ "$has_running" == "false" ]]; then
    log_step "Verification passed: all target deployments are scaled to 0."
  fi

  if [[ "$DELETE_INGRESS" == "true" ]]; then
    for ns in "${NAMESPACES[@]}"; do
      while IFS= read -r ingress_name; do
        [[ -z "$ingress_name" ]] && continue
        has_ingress="true"
        log_step "WARNING: ingress still exists: $ns/$ingress_name"
      done < <(kubectl get ingress -n "$ns" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')
    done

    if [[ "$has_ingress" == "false" ]]; then
      log_step "Verification passed: target ingresses are removed."
    fi
  fi

  log_step "Note: public DNS/LB behavior can lag for a few minutes after changes."
}

print_status() {
  local ns
  log_step "Current status in cluster $CLUSTER_NAME"
  kubectl get nodes -o wide
  for ns in "${NAMESPACES[@]}"; do
    echo
    echo "Namespace: $ns"
    kubectl get deploy -n "$ns"
    kubectl get hpa -n "$ns"
    kubectl get ingress -n "$ns"
  done
}

handle_cluster_mode() {
  if [[ "$FORCE" != "true" ]]; then
    fail "Cluster mode is destructive/expensive. Re-run with --force to confirm."
  fi

  case "$ACTION" in
    off)
      log_step "Deleting cluster $CLUSTER_NAME in $REGION"
      gcloud container clusters delete "$CLUSTER_NAME" --region "$REGION" --project "$PROJECT_ID" --quiet
      ;;
    on)
      log_step "Creating Autopilot cluster $CLUSTER_NAME in $REGION"
      gcloud container clusters create-auto "$CLUSTER_NAME" --region "$REGION" --project "$PROJECT_ID" --release-channel regular
      log_step "Cluster created. Next: apply dev manifests and secrets before traffic cutover."
      ;;
    status)
      gcloud container clusters list --project "$PROJECT_ID" --filter="name=$CLUSTER_NAME"
      ;;
  esac
}

main() {
  parse_args "$@"

  ensure_tool gcloud
  ensure_tool kubectl

  if [[ "$MODE" == "cluster" ]]; then
    handle_cluster_mode
    exit 0
  fi

  ensure_cluster_credentials

  case "$ACTION" in
    off)
      save_state
      remove_hpas

      for ns in "${NAMESPACES[@]}"; do
        log_step "Scaling all deployments in $ns to 0"
        kubectl scale deployment --all -n "$ns" --replicas=0 >/dev/null
      done

      if [[ "$DELETE_INGRESS" == "true" ]]; then
        delete_dev_ingresses
      fi

      verify_off_state

      log_step "Dev workloads are now OFF."
      log_step "State file: $STATE_FILE"
      log_step "To restore: ./scripts/toggle-dev-cluster-macos.sh on"
      ;;
    on)
      if [[ -f "$STATE_FILE" ]]; then
        restore_replica_state
      else
        restore_default_replica_state
      fi

      apply_dev_hpa_manifest
      apply_dev_ingress_manifests

      log_step "Dev workloads are now ON."
      ;;
    status)
      print_status
      ;;
  esac
}

main "$@"
