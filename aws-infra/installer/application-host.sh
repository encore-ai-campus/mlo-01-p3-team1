#!/usr/bin/env bash
# Base directories/TLS/database environment only; application code is deployed by the team.
set -Eeuo pipefail
umask 077
root=$(cd -- "$(dirname -- "$0")" && pwd)
source "$root/core/lib/common.sh"
RUNTIME=${1:?Runtime required}
require_root
python3 "$root/aws-identity.py" "$RUNTIME"
python3 "$root/init-disk.py" "$RUNTIME" --check-only
role=$(get node.role)
case "$role" in control|advertising) ;; *) fail 'Invalid application host role' ;; esac
user_create "$role"
tls_install "$role" "$role"
install -d -o "$role" -g "$role" -m 0750 "/opt/music-apps/$role"
python3 - "$root" "$RUNTIME" "$CONF/$role/database.env" "$role" <<'PY'
import json,os,pwd,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from database_config import client_environment
c=json.loads(Path(sys.argv[2]).read_text());content=client_environment(c)
p=Path(sys.argv[3]);user=pwd.getpwnam(sys.argv[4])
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o640)
with os.fdopen(fd,'w') as f:
    os.fchmod(f.fileno(),0o640);os.fchown(f.fileno(),user.pw_uid,user.pw_gid);f.write(content)
PY
log 'Application host directories/TLS/database environment prepared; application code and activation belong to the team'
