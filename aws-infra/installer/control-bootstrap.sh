#!/usr/bin/env bash
# Dedicated opt-in package; never invokes foundation setup or starts a service.
set -Eeuo pipefail
umask 077
root=$(cd -- "$(dirname -- "$0")" && pwd)
[[ ${1:-} == control-fencing && $EUID -eq 0 ]] || { echo '[FAIL] Explicit Control fencing install stage/root required' >&2; exit 1; }
exec 8>/run/lock/music-aws-install.lock
flock -n 8 || { echo '[FAIL] Another AWS installer is active' >&2; exit 1; }
python3 "$root/aws-identity.py" "$root/runtime.json"
python3 "$root/init-disk.py" "$root/runtime.json" --check-only
bash "$root/control-fencing.sh" "$root/runtime.json"
