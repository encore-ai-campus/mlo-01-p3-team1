#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/lib/common.sh"
RUNTIME=${1:?Runtime JSON required}
require_root; require_role spark
[[ -f $BASE/spark/.music-install-checksum ]] || fail 'Install verified Spark first'
python3 "$CLUSTER_ROOT/lib/connectors.py" install --spark-home "$BASE/spark" --directory "$CLUSTER_ROOT/connectors"
