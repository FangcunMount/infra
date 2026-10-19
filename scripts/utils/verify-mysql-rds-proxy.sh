#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
node="${MYSQL_RDS_PROXY_NODE:-serverB}"
case "$node" in serverA|serverB) ;; *) echo 'MYSQL_RDS_PROXY_NODE must be serverA or serverB' >&2; exit 1 ;; esac
env_file="${MYSQL_RDS_PROXY_ENV_FILE:-${repo_root}/compose/env/prod/${node}.env}"
compose_file="${repo_root}/deploy/${node}/docker-compose.yml"
template_file="${repo_root}/components/mysql-rds-proxy/nginx.conf.template"
candidate_config=$(mktemp)
trap 'rm -f "$candidate_config"' EXIT
umask 077

profile_args=(--profile mysql-proxy-rollback)
docker compose \
  "${profile_args[@]}" \
  --env-file "$env_file" \
  -f "$compose_file" \
  config --no-env-resolution --format json >"$candidate_config"

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

echo "[OK] ${node} mysql-rds-proxy is internal-only and forwards to the configured RDS endpoint"
