#!/usr/bin/env bash
# Shared Ubuntu helpers. No eval, xtrace, or sourcing environment data.
set -Eeuo pipefail
umask 077
CLUSTER_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
BASE=/opt/music-cluster
CONF=/etc/music-cluster
DATA=/var/lib/music-cluster
CACHE=/var/cache/music-cluster
JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export JAVA_HOME
fail() { printf '[FAIL] %s\n' "$*" >&2; exit 1; }
log() { printf '[INFO] %s\n' "$*"; }
get() { python3 "$CLUSTER_ROOT/lib/config.py" get "$RUNTIME" "$1"; }
require_root() { [[ $EUID -eq 0 ]] || fail 'Run the Ubuntu installer with sudo -n.'; }
require_role() { python3 - "$RUNTIME" "$1" <<'PY'
import json, sys
if sys.argv[2] not in json.load(open(sys.argv[1]))['node']['roles']:
    raise SystemExit('Role is not assigned to this node')
PY
}
user_create() {
    if ! id "$1" >/dev/null 2>&1; then
        useradd --system --user-group --home-dir "$DATA/$1" --shell /usr/sbin/nologin "$1"
    fi
    install -d -o "$1" -g "$1" -m 0750 "$DATA/$1" "$CONF/$1"
}
as_user() { local user=$1; shift; runuser -u "$user" -- "$@"; }
verify_file() {
    python3 - "$1" "$2" "$3" <<'PY'
import hashlib, sys
h=hashlib.new(sys.argv[2])
with open(sys.argv[1], 'rb') as f:
    for b in iter(lambda:f.read(1024*1024), b''): h.update(b)
if h.hexdigest() != sys.argv[3].lower(): raise SystemExit('Artifact checksum mismatch')
PY
}
download() {
    local component=$1 url algorithm checksum archive source downloaded=0
    local sources=()
    url=$(get "versions.$component.url")
    algorithm=$(get "versions.$component.algorithm")
    checksum=$(get "versions.$component.checksum")
    archive="$CACHE/${url##*/}"
    install -d -m 0755 "$CACHE"
    if [[ ! -f $archive ]]; then
        # Prefer Apache's official CDN for versions still mirrored there.
        # Retain the pinned archive URL as fallback; both require the same hash.
        if [[ $url == https://archive.apache.org/dist/* ]]; then
            sources+=("https://dlcdn.apache.org/${url#https://archive.apache.org/dist/}")
        fi
        sources+=("$url")
        for source in "${sources[@]}"; do
            if curl --fail --location --proto '=https' --proto-redir '=https' --retry 3 --connect-timeout 15 --max-time 3600 "$source" -o "$archive.part"; then
                verify_file "$archive.part" "$algorithm" "$checksum"
                mv -- "$archive.part" "$archive"
                downloaded=1
                break
            fi
        done
        [[ $downloaded == 1 ]] || fail "Artifact download failed: $component"
    fi
    verify_file "$archive" "$algorithm" "$checksum"
    ARTIFACT=$archive
}
install_archive() {
    local component=$1 version target temp
    version=$(get "versions.$component.version")
    target="$BASE/$component-$version"
    if [[ -d $target ]]; then
        [[ -f $target/.music-install-checksum ]] || fail "Unmanaged/partial installation: $target"
        [[ $(cat "$target/.music-install-checksum") == "$(get "versions.$component.checksum")" ]] || fail 'Installed artifact identity differs'
    else
        download "$component"
        temp=$(mktemp -d "$BASE/.${component}.XXXXXXXX")
        # Verified upstream archives are trusted; never extract user-supplied archives.
        tar --extract --file "$ARTIFACT" --directory "$temp" --strip-components=1 --no-same-owner
        get "versions.$component.checksum" > "$temp/.music-install-checksum"
        chmod -R a+rX,go-w "$temp"
        mv -- "$temp" "$target"
    fi
    if [[ -e $BASE/$component && ! -L $BASE/$component ]]; then fail "Unmanaged path: $BASE/$component"; fi
    if [[ -L $BASE/$component && $(readlink "$BASE/$component") != "$target" ]]; then fail 'Version changes require a separate rolling upgrade'; fi
    ln -sfn -- "$target" "$BASE/$component"
}
publish_render() {
    local role=$1 user=$2 temp path relative destination service
    python3 "$CLUSTER_ROOT/lib/state.py" "$RUNTIME" secrets "$DATA/state/$role-secrets.json" "$role"
    temp=$(mktemp -d "$CACHE/render.XXXXXXXX")
    if [[ $role == elasticsearch && ! -f $DATA/state/es-initialized.json ]]; then
        python3 "$CLUSTER_ROOT/lib/render.py" "$RUNTIME" "$role" "$temp" --bootstrap-es
    else
        python3 "$CLUSTER_ROOT/lib/render.py" "$RUNTIME" "$role" "$temp"
    fi
    # Reject changes to active services before publishing any file.
    for path in "$temp"/units/*; do
        service=${path##*/}
        if systemctl is-active --quiet "$service"; then
            cmp -s "$path" "/etc/systemd/system/$service" || fail "Active unit changed: $service; stop/roll explicitly first"
            while IFS= read -r -d '' path; do
                relative=${path#"$temp/config/"}
                destination="$CONF/$role/$relative"
                cmp -s "$path" "$destination" || fail "Active configuration changed: $service; stop/roll explicitly first"
            done < <(find "$temp/config" -type f -print0)
        fi
    done
    while IFS= read -r -d '' path; do
        relative=${path#"$temp/config/"}
        install -d -o "$user" -g "$user" -m 0750 "$(dirname "$CONF/$role/$relative")"
        install -o "$user" -g "$user" -m 0640 "$path" "$CONF/$role/$relative"
    done < <(find "$temp/config" -type f -print0)
    for path in "$temp"/units/*; do install -o root -g root -m 0644 "$path" "/etc/systemd/system/${path##*/}"; done
    rm -rf -- "$temp"
    systemctl daemon-reload
}
tls_install() {
    local role=$1 user=$2 source="$CLUSTER_ROOT/pki"
    [[ -f $source/node.crt && -f $source/node.key && -f $source/ca.crt ]] || fail 'Prepare and supply node TLS material first'
    install -d -o "$user" -g "$user" -m 0750 "$CONF/$role/tls"
    local file
    for file in ca.crt node.crt node.key; do
        if [[ -f $CONF/$role/tls/$file ]]; then
            cmp -s "$source/$file" "$CONF/$role/tls/$file" || fail 'Certificate changes require an explicit rotation'
        else install -o "$user" -g "$user" -m 0640 "$source/$file" "$CONF/$role/tls/$file"; fi
    done
    if [[ $role == kafka || $role == spark || $role == zookeeper ]]; then
        get env.TLS_STORE_PASSWORD > "$CACHE/tls-password"
        if [[ ! -f $CONF/$role/tls/node.p12 ]]; then
            openssl pkcs12 -export -name node -inkey "$source/node.key" -in "$source/node.crt" -certfile "$source/ca.crt" -out "$CONF/$role/tls/node.p12" -passout "file:$CACHE/tls-password"
        fi
        if [[ ! -f $CONF/$role/tls/trust.p12 ]]; then
            "$JAVA_HOME/bin/keytool" -importcert -noprompt -alias cluster-ca -file "$source/ca.crt" -keystore "$CONF/$role/tls/trust.p12" -storetype PKCS12 -storepass:file "$CACHE/tls-password" >/dev/null
        fi
        chown "$user:$user" "$CONF/$role/tls/"*.p12
        chmod 0640 "$CONF/$role/tls/"*.p12
        if [[ $role == spark || $role == zookeeper ]]; then
            install -o "$user" -g "$user" -m 0640 "$CACHE/tls-password" "$CONF/$role/tls/store.password"
        fi
        rm -f -- "$CACHE/tls-password"
    fi
}
