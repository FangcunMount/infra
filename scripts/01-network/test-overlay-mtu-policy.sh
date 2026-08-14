#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

assert_contains() {
  local file="$1"
  local expected="$2"
  if ! grep -Fq -- "$expected" "$repo_root/$file"; then
    printf '[ERROR] %s must contain: %s\n' "$file" "$expected" >&2
    exit 1
  fi
}

assert_contains scripts/02-components/init-infrastructure.sh \
  'INFRA_NETWORK_MTU="${INFRA_NETWORK_MTU:-1280}"'
assert_contains scripts/01-network/swarm-manager.sh \
  'local mtu="${INFRA_NETWORK_MTU:-1280}"'
assert_contains scripts/01-network/app-network-manager.sh \
  'com.docker.network.driver.mtu=${INFRA_NETWORK_MTU:-1280}'
assert_contains components/networks/docker-compose.yml \
  'com.docker.network.driver.mtu: "1280"'
assert_contains Makefile 'INFRA_NETWORK_MTU ?= 1280'

if grep -RInE --exclude-dir=.git --exclude='*.dat' \
  'INFRA_NETWORK_MTU(:-|=)[^#]*1450|driver\.mtu[^#]*1450|MTU[^#`]*`1450`' \
  "$repo_root/scripts" "$repo_root/components/networks" "$repo_root/docs/network"; then
  printf '[ERROR] stale 1450 MTU policy remains in active network files\n' >&2
  exit 1
fi

bash -n "$repo_root/scripts/01-network/verify-overlay-mtu.sh"
bash -n "$repo_root/scripts/01-network/swarm-manager.sh"
bash -n "$repo_root/scripts/02-components/init-infrastructure.sh"

printf '[OK] overlay MTU policy: tailscale=1280 endpoint<=1230\n'
