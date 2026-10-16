#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "$0")/lib/common.sh"
phase=${1:?zookeeper or spark phase required}
RUNTIME=${2:?Runtime JSON required}
require_root; require_role spark
[[ -x $BASE/python/bin/python3.14 ]] || fail 'Run common runtime installation first'
if [[ $phase == zookeeper ]]; then
    user_create zookeeper
    install_archive zookeeper
    install -d -o zookeeper -g zookeeper -m 0750 "$DATA/zookeeper/data" "$DATA/zookeeper/log"
    zk_id=$(get node.zk_id)
    if [[ -f $DATA/zookeeper/data/myid ]]; then
        [[ $(cat "$DATA/zookeeper/data/myid") == "$zk_id" ]] || fail 'ZooKeeper myid differs; data was preserved'
    else
        [[ -z $(find "$DATA/zookeeper/data" -mindepth 1 -print -quit) ]] || fail 'Unmanaged ZooKeeper data exists'
        printf '%s\n' "$zk_id" > "$DATA/zookeeper/data/myid"
        chown zookeeper:zookeeper "$DATA/zookeeper/data/myid"
    fi
    tls_install zookeeper zookeeper
    publish_render zookeeper zookeeper
    systemctl enable --now music-zookeeper.service
elif [[ $phase == spark-master || $phase == spark-worker ]]; then
    user_create spark
    install_archive spark
    python3 - "$BASE/spark/jars" "$(get versions.spark.hadoop)" <<'PY'
from pathlib import Path
import sys
expected = 'hadoop-client-api-' + sys.argv[2] + '.jar'
if not (Path(sys.argv[1]) / expected).exists():
    raise SystemExit('Spark Hadoop distribution differs from pinned S3A version')
PY
    install -d -o spark -g spark -m 0750 "$DATA/spark/work" "$DATA/spark/local" "$DATA/spark/log"
    # Allow service-specific subdirectories without exposing sibling credentials.
    chmod 0751 "$CONF" "$DATA"
    tls_install spark spark
    publish_render spark spark
    if [[ $phase == spark-master ]]; then
        systemctl enable --now music-spark-master.service
    else
        [[ -f /var/lib/music-cluster/aws-state/$(get aws.generation)/spark-master-health.json ]] || fail "Verify all Masters before starting Workers"
        systemctl enable --now music-spark-worker.service
    fi
    log 'Spark Master/Worker configured; this does not activate Driver HA'
else fail 'Unknown Spark installation phase'; fi
