#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/lib/common.sh"
RUNTIME=${1:?Runtime JSON required}
require_root; require_role kafka
user_create kafka
install_archive kafka
tls_install kafka kafka
publish_render kafka kafka
install -d -o kafka -g kafka -m 0750 "$DATA/kafka/data" "$DATA/kafka/metadata" "$DATA/kafka/log"
data_meta="$DATA/kafka/data/meta.properties"
quorum_meta="$DATA/kafka/metadata/meta.properties"
if [[ -f $data_meta || -f $quorum_meta ]]; then
    [[ -f $data_meta && -f $quorum_meta ]] || fail 'Partial Kafka format; inspect data before proceeding'
    python3 "$CLUSTER_ROOT/lib/state.py" "$RUNTIME" kafka "$data_meta"
    python3 "$CLUSTER_ROOT/lib/state.py" "$RUNTIME" kafka "$quorum_meta"
else
    [[ -z $(find "$DATA/kafka/data" "$DATA/kafka/metadata" -mindepth 1 -print -quit) ]] || fail 'Refusing to format non-empty Kafka directories'
    as_user kafka env JAVA_HOME="$JAVA_HOME" LOG_DIR="$DATA/kafka/log" "$BASE/kafka/bin/kafka-storage.sh" format --cluster-id "$(get env.KAFKA_CLUSTER_ID)" --config "$CONF/kafka/server.properties"
fi
systemctl enable --now music-kafka.service
log 'Kafka configured; quorum validation runs after all three nodes are installed'
