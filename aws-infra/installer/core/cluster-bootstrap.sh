#!/usr/bin/env bash
# Entry point executed on an existing Ubuntu guest, never on Windows/macOS.
set -Eeuo pipefail
source "$(dirname -- "$0")/lib/common.sh"
if [[ ${1:-} == --help ]]; then
    printf 'Ubuntu: sudo -n bash cluster-bootstrap.sh STAGE /absolute/runtime.json\n'
    exit 0
fi
[[ $# -ge 2 && $# -le 3 ]] || fail 'Expected STAGE and /absolute/runtime.json'
stage=$1
RUNTIME=$(readlink -f -- "$2")
[[ -f $RUNTIME ]] || fail 'Runtime file not found'
require_root
[[ $(get env.ENVIRONMENT) == aws ]] || fail "AWS package rejects local environment"
python3 "$CLUSTER_ROOT/../aws-identity.py" "$RUNTIME"
exec 9>/run/lock/music-cluster.lock
flock -n 9 || fail 'Another installer is running on this guest'
trap 'printf "[FAIL] Stage %s failed at line %s; inspect journalctl for the relevant music-* service.\n" "$stage" "$LINENO" >&2' ERR
# Every installation stage verifies OS/identity first. No normal VM is reinstalled.
if [[ ${3:-} == --preflight-verified ]]; then
    bash "$CLUSTER_ROOT/00-preflight.sh" "$RUNTIME" --skip-peers
elif [[ $# -eq 3 ]]; then fail 'Unknown guest option'
else bash "$CLUSTER_ROOT/00-preflight.sh" "$RUNTIME"; fi
if [[ $stage != preflight && $stage != common ]]; then
    [[ -f $DATA/state/identity.json ]] || fail 'Run common stage first'
    python3 "$CLUSTER_ROOT/lib/state.py" "$RUNTIME" identity "$DATA/state/identity.json"
fi
case "$stage" in
    preflight) ;;
    common) bash "$CLUSTER_ROOT/01-common.sh" "$RUNTIME" ;;
    check-common) bash "$CLUSTER_ROOT/02-check-common.sh" "$RUNTIME" ;;
    kafka) bash "$CLUSTER_ROOT/10-kafka.sh" "$RUNTIME" ;;
    zookeeper|spark) bash "$CLUSTER_ROOT/20-spark.sh" "$stage" "$RUNTIME" ;;
    es) bash "$CLUSTER_ROOT/30-elasticsearch.sh" "$RUNTIME" ;;
    control) bash "$CLUSTER_ROOT/40-control.sh" "$RUNTIME" ;;
    health|zookeeper-health|smoke|finalize-es|catalog) bash "$CLUSTER_ROOT/90-health-check.sh" "$stage" "$RUNTIME" ;;
    connectors) bash "$CLUSTER_ROOT/25-connectors.sh" "$RUNTIME" ;;
    pipeline|ha) fail 'Application/S3 integration and fencing are not configured; refusing activation' ;;
    *) fail 'Unknown guest stage' ;;
esac
