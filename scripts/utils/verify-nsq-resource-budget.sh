#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ "$#" -ge 1 ]; then
  env_file="$1"
elif [ -r "${repo_root}/compose/env/prod/serverD.env" ]; then
  env_file="${repo_root}/compose/env/prod/serverD.env"
else
  env_file="${repo_root}/compose/env/prod/.env.example"
fi
compose_file="${2:-${repo_root}/components/nsq/docker-compose.yml}"

if [ ! -r "$env_file" ]; then
  echo "NSQ environment file is not readable: $env_file" >&2
  exit 1
fi
if [ ! -r "$compose_file" ]; then
  echo "NSQ compose file is not readable: $compose_file" >&2
  exit 1
fi

env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" "$env_file" | tail -n 1
}

memory_to_mib() {
  local raw="${1^^}"
  raw="${raw//IB/}"
  case "$raw" in
    *G) awk -v value="${raw%G}" 'BEGIN { printf "%.0f\n", value * 1024 }' ;;
    *M) awk -v value="${raw%M}" 'BEGIN { printf "%.0f\n", value }' ;;
    *) echo "Unsupported NSQD_MEMORY_LIMIT unit: $1" >&2; return 1 ;;
  esac
}

nsqd_memory="$(env_value NSQD_MEMORY_LIMIT)"
nsqd_cpus="$(env_value NSQD_CPUS)"
if [ -z "$nsqd_memory" ] || [ -z "$nsqd_cpus" ]; then
  echo "NSQD_MEMORY_LIMIT and NSQD_CPUS must both be configured in $env_file" >&2
  exit 1
fi

memory_mib="$(memory_to_mib "$nsqd_memory")"
if ! awk -v actual="$memory_mib" 'BEGIN { exit !(actual >= 512) }'; then
  echo "NSQD_MEMORY_LIMIT=$nsqd_memory is below the 512MiB production floor" >&2
  exit 1
fi
if ! awk -v actual="$nsqd_cpus" 'BEGIN { exit !(actual >= 1.0) }'; then
  echo "NSQD_CPUS=$nsqd_cpus is below the 1 CPU production floor" >&2
  exit 1
fi

if ! grep -Fq 'mem_limit: ${NSQD_MEMORY_LIMIT:-512M}' "$compose_file"; then
  echo "NSQ compose default memory budget must remain 512M" >&2
  exit 1
fi
if ! grep -Fq 'cpus: ${NSQD_CPUS:-1.00}' "$compose_file"; then
  echo "NSQ compose default CPU budget must remain 1.00" >&2
  exit 1
fi

echo "[OK] NSQD production resource floor: memory=${nsqd_memory} cpu=${nsqd_cpus}"
