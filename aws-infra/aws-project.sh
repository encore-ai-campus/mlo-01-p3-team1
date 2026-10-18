#!/usr/bin/env bash
set -Eeuo pipefail
root=$(cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$root/bin/manage.py" "$@"
