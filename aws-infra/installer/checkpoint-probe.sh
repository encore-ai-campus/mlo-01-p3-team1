#!/usr/bin/env bash
# Explicit synthetic probe only; never activates a business Driver or HA controller.
set -Eeuo pipefail
umask 077
root=$(cd -- "$(dirname -- "$0")" && pwd)
source "$root/core/lib/common.sh"
RUNTIME=${1:?Runtime required}
require_root; require_role spark
python3 "$root/aws-identity.py" "$RUNTIME"
python3 "$root/init-disk.py" "$RUNTIME" --check-only
python3 "$root/core/lib/health.py" "$RUNTIME" health
python3 - "$root" "$BASE/spark" <<'PY'
import json,sys
from pathlib import Path
root,home=map(Path,sys.argv[1:]);sys.path.insert(0,str(root/'core/lib'))
from connectors import validate_bundle
validate_bundle(root/'core/connectors',home,root/'connectors.lock.json')
if json.loads((home/'connectors.lock.json').read_text())!=json.loads((root/'connectors.lock.json').read_text()):
    raise SystemExit('Reviewed connector bundle must be installed before checkpoint probe')
PY
test_id=$(python3 -c 'import uuid; print(uuid.uuid4().hex)')
folder="$DATA/spark/probes/$test_id"
install -d -o spark -g spark -m 0700 "$DATA/spark/probes" "$folder"
python3 - "$RUNTIME" "$folder/runtime.json" "$root" "$folder" <<'PY'
import json,os,pwd,shutil,sys
from pathlib import Path
c=json.loads(Path(sys.argv[1]).read_text());user=pwd.getpwnam('spark')
runtime={'aws':c['aws'],'node':c['node'],'env':{k:c['env'][k] for k in ('ENVIRONMENT','AWS_REGION','S3_BUCKET','S3_CHECKPOINT_PREFIX')}}
p=Path(sys.argv[2]);p.write_text(json.dumps(runtime));p.chmod(0o600);os.chown(p,user.pw_uid,user.pw_gid)
for name in ('checkpoint_probe.py','integration_scope.py','aws-identity.py'):
    target=Path(sys.argv[4])/name;shutil.copyfile(Path(sys.argv[3])/name,target);target.chmod(0o600);os.chown(target,user.pw_uid,user.pw_gid)
PY
# One application core, bounded rows, existing authenticated/encrypted Spark
# settings. S3 uses the instance profiles already approved for this generation.
as_user spark env JAVA_HOME="$JAVA_HOME" SPARK_CONF_DIR="$CONF/spark" \
  "$BASE/spark/bin/spark-submit" --conf spark.cores.max=1 --conf spark.executor.cores=1 \
  --conf spark.sql.shuffle.partitions=3 --conf spark.ui.enabled=false \
  "$folder/checkpoint_probe.py" --runtime "$folder/runtime.json" --run-id "$test_id"
log 'Sequential S3 checkpoint restart probe finished; concurrent writer/Control fencing is a separate test'
