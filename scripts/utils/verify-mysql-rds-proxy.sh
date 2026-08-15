#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
env_file="${MYSQL_RDS_PROXY_ENV_FILE:-${repo_root}/compose/env/prod/serverA.env}"
compose_file="${repo_root}/deploy/serverA/docker-compose.yml"
template_file="${repo_root}/components/mysql-rds-proxy/nginx.conf.template"
candidate_config=$(mktemp)
trap 'rm -f "$candidate_config"' EXIT
umask 077

docker compose \
  --env-file "$env_file" \
  -f "$compose_file" \
  config --format json >"$candidate_config"

jq -e '
  .services["mysql-rds-proxy"] as $proxy |
  $proxy.image == "nginx:1.27" and
  $proxy.network_mode == null and
  ($proxy.ports == null) and
  $proxy.expose == ["3306"] and
  $proxy.networks.backend.aliases == ["mysql-rds-proxy"] and
  $proxy.environment.PROXY_BIND_PORT == "3306" and
  $proxy.healthcheck.test == ["CMD", "nginx", "-t"]
' "$candidate_config" >/dev/null

grep -Fq 'listen ${PROXY_BIND_PORT};' "$template_file"
grep -Fq 'server ${MYSQL_HOST}:${MYSQL_PORT}' "$template_file"
grep -Fq 'proxy_pass mysql_rds;' "$template_file"

echo '[OK] mysql-rds-proxy is internal-only and forwards to the configured RDS endpoint'
