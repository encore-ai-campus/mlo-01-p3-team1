#!/usr/bin/env bash
# Ubuntu EC2 only. SSM delivers a node-scoped private package; never invoke on Mac/local VM.
set -Eeuo pipefail
umask 077
root=$(cd -- "$(dirname -- "$0")" && pwd)
stage=${1:?Explicit AWS stage required}
runtime="$root/runtime.json"
[[ $EUID -eq 0 ]] || { echo '[FAIL] EC2 root required' >&2; exit 1; }
exec 8>/run/lock/music-aws-install.lock
flock -n 8 || { echo '[FAIL] AWS installer already running' >&2; exit 1; }
# IMDSv2 identity check happens before formatting, mounting or invoking reused code.
python3 "$root/aws-identity.py" "$runtime"
generation=$(python3 "$root/core/lib/config.py" get "$runtime" aws.generation)
case "$stage" in
  init-empty-disk)
    [[ ${2:-} == "$generation" ]] || { echo '[FAIL] Explicit new generation token required' >&2; exit 1; }
    python3 "$root/init-disk.py" "$runtime"
    exit 0
    ;;
  application-host|postgresql|mongodb|database-health|preflight|common|check-common|kafka|zookeeper|es|control|connectors|health|smoke|finalize-es|catalog|zookeeper-health|spark-master|spark-master-health|spark-worker) ;;
  *) echo '[FAIL] Stage unavailable; application pipeline/HA activation belongs to team integration' >&2; exit 1 ;;
esac
mountpoint -q /var/lib/music-cluster || { echo '[FAIL] Explicit init-empty-disk stage is required first' >&2; exit 1; }
python3 "$root/init-disk.py" "$runtime" --check-only
state="/var/lib/music-cluster/aws-state/$generation"
install -d -m 0700 "$state"
# States indicate script completion only, never full service verification.
trap 'printf "[FAIL] AWS stage %s failed; inspect private SSM/service logs.\n" "$stage" >&2' ERR
role=$(python3 "$root/core/lib/config.py" get "$runtime" node.role)
if [[ $role == postgresql || $role == mongodb ]]; then
    case "$stage" in preflight|database-health|"$role") ;; *) echo '[FAIL] Invalid database stage' >&2; exit 1 ;; esac
    python3 "$root/database.py" "$runtime" "$stage"
elif [[ $stage == application-host || $role == advertising ]]; then
    case "$stage" in preflight) ;; application-host) bash "$root/application-host.sh" "$runtime" ;; *) echo '[FAIL] Invalid application host stage' >&2; exit 1 ;; esac
elif [[ $stage == spark-master-health ]]; then
    python3 "$root/spark-master-health.py" "$runtime"
elif [[ $stage == control ]]; then
    bash "$root/core/00-preflight.sh" "$runtime" --skip-peers
    bash "$root/control-tools.sh" "$runtime"
elif [[ $stage == spark-master || $stage == spark-worker ]]; then
    bash "$root/core/00-preflight.sh" "$runtime" --skip-peers
    python3 "$root/core/lib/state.py" "$runtime" identity /var/lib/music-cluster/state/identity.json
    bash "$root/core/20-spark.sh" "$stage" "$runtime"
else
    bash "$root/core/cluster-bootstrap.sh" "$stage" "$runtime" --preflight-verified
fi
python3 - "$runtime" "$state/$stage.json" <<'PY'
import datetime,json,os,sys
from pathlib import Path
c=json.loads(Path(sys.argv[1]).read_text())
d={'node':c['node']['name'],'generation':c['aws']['generation'],
   'completed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'service_validation':'separate'}
p=Path(sys.argv[2]);q=p.with_suffix('.tmp');q.write_text(json.dumps(d)+'\n');q.chmod(0o600);os.replace(q,p)
PY
echo "[PASS] AWS stage $stage completed; full pipeline/HA verification is separate."
