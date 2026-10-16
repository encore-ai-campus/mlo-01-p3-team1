#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/core/lib/common.sh"
RUNTIME=${1:?Runtime required}
require_root; require_role control
[[ -x $BASE/python/bin/python3.14 ]] || fail 'Common stage required'
install_archive spark
bash "$CLUSTER_ROOT/40-control.sh" "$RUNTIME"
bash "$(dirname -- "$0")/application-host.sh" "$RUNTIME"
