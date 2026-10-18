#!/usr/bin/env bash
# Read-only completion check for the common runtime installed on an Ubuntu guest.
set -Eeuo pipefail
source "$(dirname -- "$0")/lib/common.sh"
RUNTIME=${1:?Runtime JSON required}
require_root
version=$(get versions.python.version)
target="$BASE/python-$version"
[[ -L $BASE/python && $(readlink "$BASE/python") == "$target" ]] || fail 'Common Python link is missing or differs'
[[ -x $target/bin/python3.14 && -f $target/.music-install-checksum ]] || fail 'Common Python installation is incomplete'
[[ $(cat "$target/.music-install-checksum") == "$(get versions.python.checksum)" ]] || fail 'Common Python artifact differs'
[[ $($target/bin/python3.14 --version) == "Python $version" ]] || fail 'Common Python version differs'
"$target/bin/python3.14" -c 'import ssl, sqlite3, bz2, lzma, ctypes; print("[PASS] Common Python runtime modules")'
[[ -x $JAVA_HOME/bin/java && -s $DATA/state/java-package.txt && -f $CONF/runtime.json ]] || fail 'Common Java/runtime completion files are missing'
java_info=$("$JAVA_HOME/bin/java" -XshowSettings:properties -version 2>&1)
[[ $java_info == *'java.specification.version = 21'* ]] || fail 'Common Java major version differs'
log "Common runtime verified: Java 21 / Python $version"
