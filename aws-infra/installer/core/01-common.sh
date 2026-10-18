#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/lib/common.sh"
RUNTIME=${1:?Runtime JSON required}
require_root
install -d -m 0755 "$BASE" "$CACHE"
install -d -m 0751 "$CONF" "$DATA"
install -d -m 0700 "$DATA/state"
python3 "$CLUSTER_ROOT/lib/state.py" "$RUNTIME" identity "$DATA/state/identity.json"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends openjdk-21-jdk-headless ca-certificates curl openssl python3 iproute2 procps util-linux xz-utils build-essential pkg-config libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev libncurses-dev libgdbm-dev uuid-dev
"$JAVA_HOME/bin/java" -version
version=$(get versions.python.version)
target="$BASE/python-$version"
if [[ -d $target ]]; then
    [[ -x $target/bin/python3.14 && -f $target/.music-install-checksum ]] || fail 'Partial/unmanaged Python installation'
    [[ $(cat "$target/.music-install-checksum") == "$(get versions.python.checksum)" ]] || fail 'Python artifact identity differs'
else
    download python
    build=$(mktemp -d "$CACHE/python-build.XXXXXXXX")
    tar --extract --file "$ARTIFACT" --directory "$build" --strip-components=1 --no-same-owner
    (
        cd -- "$build"
        ./configure --prefix="$target" --with-ensurepip=install
        make -j "$(nproc)"
        make altinstall
    )
    "$target/bin/python3.14" -c 'import ssl, sqlite3, bz2, lzma, ctypes; print("Python runtime module check PASS")'
    get versions.python.checksum > "$target/.music-install-checksum"
    chmod -R a+rX,go-w "$target"
    rm -rf -- "$build"
fi
[[ $($target/bin/python3.14 --version) == "Python $version" ]] || fail 'Python runtime version mismatch'
if [[ -e $BASE/python && ! -L $BASE/python ]]; then fail 'Unmanaged Python link path'; fi
if [[ -L $BASE/python && $(readlink "$BASE/python") != "$target" ]]; then fail 'Python version change requires a separate upgrade'; fi
ln -sfn -- "$target" "$BASE/python"
install -m 0600 "$RUNTIME" "$CONF/runtime.json"
dpkg-query -W -f='${Package} ${Version}\n' openjdk-21-jdk-headless > "$DATA/state/java-package.txt"
log 'Common runtime installed; Ubuntu system Python and networking were preserved'
