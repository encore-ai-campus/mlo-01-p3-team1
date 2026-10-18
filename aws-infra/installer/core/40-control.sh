#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/lib/common.sh"
RUNTIME=${1:?Runtime JSON required}
require_root; require_role control
[[ -x $BASE/python/bin/python3.14 && -x $BASE/spark/bin/spark-submit ]] || fail 'Python/Spark runtime required'
user_create control
if [[ ! -x $DATA/control/venv/bin/python ]]; then
    as_user control "$BASE/python/bin/python3.14" -m venv "$DATA/control/venv"
fi
log 'Control Python environment prepared. Web/Collector/Driver applications and HA are not activated.'
log 'ASGI server, locked app requirements, start/stop and fencing contracts belong to the team; application deployment is separate from infrastructure setup.'
