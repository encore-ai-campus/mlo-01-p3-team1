#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/lib/common.sh"
RUNTIME=${1:?Runtime JSON required}
require_root
if [[ $(get node.role) == control ]]; then require_role control; else require_role spark; fi
[[ -f $BASE/spark/.music-install-checksum ]] || fail 'Install verified Spark first'
# Adding classpath artifacts is allowed only while all three Masters can be
# observed and no application is active. Unreachable/ambiguous observations fail.
python3 - "$RUNTIME" <<'PY'
import json,sys
from urllib.request import urlopen
c=json.load(open(sys.argv[1]));values=[]
for n in c['inventory']['nodes']:
    if 'spark' in n['roles']:
        with urlopen('http://'+n['address']+':8080/json/',timeout=10) as response:values.append(json.load(response))
if len(values)!=3 or sorted(v['status'] for v in values)!=['ALIVE','STANDBY','STANDBY'] or any(not isinstance(v.get('activeapps'),list) or v['activeapps'] for v in values):
    raise SystemExit('No unique idle Spark cluster observed; connector installation blocked')
PY
python3 "$CLUSTER_ROOT/lib/connectors.py" install --spark-home "$BASE/spark" --directory "$CLUSTER_ROOT/connectors"
