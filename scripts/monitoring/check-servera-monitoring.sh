#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
formal="$root/deploy/serverA/monitoring"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -m 755 "$work/targets"
printf '[]\n' > "$work/targets/serverA.json"
printf '[]\n' > "$work/targets/serverD.json"

docker compose -f "$formal/compose.yml" config --format json > "$work/base.json"
docker compose -f "$formal/compose.yml" -f "$formal/history.override.yml" config --format json > "$work/history.json"
docker compose -f "$root/deploy/serverA/monitoring-route.yml" -f "$formal/route-network.override.yml" \
    config --format json > "$work/route.json"
# Compose 2.40 omits false create_host_path values from rendered bind objects.
jq -e --slurp '
    .[0] as $base | .[1] as $history | .[2] as $route |
    $base.services["servera-collector"] as $collector |
    $history.services["history-reader"] as $reader |
    $base.services["query-bridge"] as $bridge |
    {
      services: (($base.services | keys)==["query-bridge","servera-collector"] and
                 ($history.services | keys)==["history-reader","query-bridge","servera-collector"]),
      project: ($base.name=="qlume-servera-monitoring"),
      service_security: ([ $history.services[] | select(.read_only==true and .pull_policy=="never" and
          .platform=="linux/amd64" and (.ports // [] | length)==0) ] | length==3),
      networks: ($base.networks.backend.external and $base.networks.backend.name=="infra-network" and
          $base.networks.query.external and $base.networks.query.name=="qlume-servera-monitoring-query"),
      query_addresses: ($collector.networks.query.ipv4_address=="172.31.251.3" and
          $route.services["prometheus-route"].networks.query.ipv4_address=="172.31.251.2"),
      shared_namespace: ($bridge.network_mode=="service:servera-collector" and $reader.network_mode=="service:servera-collector"),
      listeners: (($collector.command | index("--web.listen-address=127.0.0.1:9090"))!=null and
          ($reader.command | index("--web.listen-address=127.0.0.1:19092"))!=null),
      history_retention: (($reader.command | index("--storage.tsdb.retention.time=30d"))!=null),
      rules_mounts: ([ $collector.volumes[] | select(.target=="/etc/prometheus/rules" or .target=="/etc/prometheus/servera-rules") |
          select(.type=="bind" and .read_only==true and (.bind | type)=="object" and
                 (.bind.create_host_path // false)==false) ] | length==2),
      distinct_volumes: ($history.volumes.data.external and $history.volumes["protected-history"].external and
          $history.volumes.data.name!=$history.volumes["protected-history"].name)
    } | with_entries(select(.value!=true)) |
    if length==0 then true else error("Compose checks failed: " + (keys | join(", "))) end
' "$work/base.json" "$work/history.json" "$work/route.json"
prom_image=$(jq -er '.services["servera-collector"].image' "$work/base.json")
# The production reference is an offline archive alias and is rendered above.
promtool_image=prom/prometheus:v2.54.1
if [[ -v SERVERA_MONITORING_PROMTOOL_IMAGE ]]; then
    promtool_image=$SERVERA_MONITORING_PROMTOOL_IMAGE
fi
test "$(docker run --rm --entrypoint /bin/promtool "$promtool_image" --version | head -1 | grep -c 'version 2.54.1')" -eq 1
case "$prom_image" in *'@sha256:'*) ;; *) exit 1 ;; esac
for config in prometheus.yml history/prometheus.yml history/history-prometheus.yml; do
    docker run --rm --network none --entrypoint /bin/promtool \
        -v "$formal/$config:/etc/prometheus/prometheus.yml:ro" \
        -v "$formal/rules:/etc/prometheus/servera-rules:ro" \
        -v "$root/components/prometheus/rules:/etc/prometheus/rules:ro" \
        -v "$work/targets:/etc/prometheus/targets:ro" \
        "$promtool_image" check config /etc/prometheus/prometheus.yml
done
docker run --rm --network none --entrypoint /bin/promtool \
    -v "$formal:/candidate:ro" --workdir /candidate/tests "$promtool_image" \
    test rules coverage.test.yml history-reader.test.yml

python3 -B "$root/scripts/monitoring/check-servera-history-overlap.py"
