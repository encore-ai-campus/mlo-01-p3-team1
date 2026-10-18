#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/lib/common.sh"
RUNTIME=${1:?Runtime JSON required}
require_root; require_role es
user_create elasticsearch
install_archive elasticsearch
install -d -o elasticsearch -g elasticsearch -m 0750 "$DATA/elasticsearch/data" "$DATA/elasticsearch/log" "$CONF/elasticsearch/jvm.options.d"
tls_install elasticsearch elasticsearch
# These defaults belong to this exact upstream distribution.
for file in jvm.options log4j2.properties users users_roles; do
    if [[ ! -f $CONF/elasticsearch/$file ]]; then install -o elasticsearch -g elasticsearch -m 0640 "$BASE/elasticsearch/config/$file" "$CONF/elasticsearch/$file"; fi
done
publish_render elasticsearch elasticsearch
printf 'vm.max_map_count=1048576\n' > /etc/sysctl.d/90-music-elasticsearch.conf
sysctl -p /etc/sysctl.d/90-music-elasticsearch.conf
for pair in cluster_admin:superuser pipeline_writer:pipeline_writer; do
    name=${pair%%:*}; role=${pair##*:}
    if [[ ! -f $CONF/elasticsearch/users ]] || ! cut -d: -f1 "$CONF/elasticsearch/users" | grep -qx "$name"; then
        if [[ $name == cluster_admin ]]; then secret=$(get env.ES_ADMIN_PASSWORD); else secret=$(get env.ES_WRITER_PASSWORD); fi
        # Interactive password stdin prevents passwords appearing in process arguments.
        printf '%s\n%s\n' "$secret" "$secret" | as_user elasticsearch env -u JAVA_HOME ES_PATH_CONF="$CONF/elasticsearch" "$BASE/elasticsearch/bin/elasticsearch-users" useradd "$name" -r "$role"
        unset secret
    fi
done
chmod 0751 "$CONF" "$DATA"
systemctl enable --now music-elasticsearch.service
log 'Elasticsearch configured; initial-master setting is removed by finalize-es after cluster verification'
