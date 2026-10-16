#!/usr/bin/env python3
"""Vendor an explicit public source allowlist; never copy runtime/PKI/local network code."""
import argparse,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FILES=['versions.json','00-preflight.sh','01-common.sh','02-check-common.sh','10-kafka.sh',
       '20-spark.sh','25-connectors.sh','30-elasticsearch.sh','40-control.sh','90-health-check.sh',
       'cluster-bootstrap.sh','lib/common.sh','lib/config.py','lib/preflight.py','lib/state.py',
       'lib/render.py','lib/health.py','lib/connectors.py','lib/pki.py','examples/spark-smoke.py','examples/connector-smoke.py']
p=argparse.ArgumentParser();p.add_argument('--source',required=True);a=p.parse_args();source=Path(a.source).resolve()
manifest={}
for name in FILES:
 src=source/name
 if src.is_symlink() or not src.is_file():raise SystemExit('Missing/non-regular source: '+name)
 dest=ROOT/'core'/name;dest.parent.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(src,dest)
 manifest[name]=hashlib.sha256(src.read_bytes()).hexdigest()
# Explicit AWS-only changes are tracked outside the immutable source hashes.
path=ROOT/'core/lib/pki.py'
path.write_text(path.read_text().replace('Music cluster local CA','Music cluster AWS CA'))
path=ROOT/'core/20-spark.sh'
path.write_text(path.read_text().replace('elif [[ $phase == spark ]]; then','elif [[ $phase == spark-master || $phase == spark-worker ]]; then').replace('systemctl enable --now music-spark-master.service music-spark-worker.service', 'if [[ $phase == spark-master ]]; then\n        systemctl enable --now music-spark-master.service\n    else\n        [[ -f /var/lib/music-cluster/aws-state/$(get aws.generation)/spark-master-health.json ]] || fail "Verify all Masters before starting Workers"\n        systemctl enable --now music-spark-worker.service\n    fi'))
path=ROOT/'core/lib/preflight.py'
path.write_text(path.read_text().replace("shutil.disk_usage('/var').free", "shutil.disk_usage('/var/lib/music-cluster').free"))
path=ROOT/'core/cluster-bootstrap.sh'
path.write_text(path.read_text().replace('require_root\n', 'require_root\n[[ $(get env.ENVIRONMENT) == aws ]] || fail "AWS package rejects local environment"\npython3 "$CLUSTER_ROOT/../aws-identity.py" "$RUNTIME"\n',1))
(ROOT/'source-manifest.json').write_text(json.dumps({'source_files_sha256':manifest,
    'aws_patches':{'lib/pki.py':'AWS CA subject; new CA stored in private generation directory', '20-spark.sh':'Separate Master/Worker starts; health barrier marker required', 'lib/preflight.py':'Capacity measured on AWS mounted data volume', 'cluster-bootstrap.sh':'Reject local environment and check IMDSv2 identity even if called directly'}},indent=2)+'\n')
print('21 allowlisted source files copied. No source installer executed.')
