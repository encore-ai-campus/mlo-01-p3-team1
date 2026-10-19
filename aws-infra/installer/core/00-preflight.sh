#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/lib/common.sh"
RUNTIME=${1:?Runtime JSON required}
require_root
[[ -f /etc/os-release ]] || fail 'Missing os-release'
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 && $(dpkg --print-architecture) == amd64 ]] || fail 'Ubuntu 24.04 amd64 is required for local and AWS'
[[ $(ps -p 1 -o comm=) == systemd ]] || fail 'systemd must be PID 1'
if [[ ${2:-} == --skip-peers ]]; then python3 "$CLUSTER_ROOT/lib/preflight.py" "$RUNTIME" --skip-peers
else python3 "$CLUSTER_ROOT/lib/preflight.py" "$RUNTIME"; fi
[[ $(timedatectl show -p NTPSynchronized --value) == yes ]] || fail 'NTP is not synchronized'
log 'Ubuntu preflight PASS; no network/hostname configuration was changed'
