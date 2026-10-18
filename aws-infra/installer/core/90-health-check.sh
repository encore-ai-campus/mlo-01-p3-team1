#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/lib/common.sh"
action=${1:?health, zookeeper-health, smoke, finalize-es or catalog required}
RUNTIME=${2:?Runtime JSON required}
require_root
python3 "$CLUSTER_ROOT/lib/health.py" "$RUNTIME" "$action"
if [[ $action == smoke ]] && python3 - "$RUNTIME" <<'PY'
import json, sys
sys.exit(0 if 'spark' in json.load(open(sys.argv[1]))['node']['roles'] else 1)
PY
then
    install -o spark -g spark -m 0640 "$CLUSTER_ROOT/examples/spark-smoke.py" "$DATA/spark/spark-smoke.py"
    as_user spark env JAVA_HOME="$JAVA_HOME" SPARK_CONF_DIR="$CONF/spark" "$BASE/spark/bin/spark-submit" "$DATA/spark/spark-smoke.py"
fi
