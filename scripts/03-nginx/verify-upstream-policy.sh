#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
config="${1:-${repo_root}/components/nginx/nginx.conf}"
expected='proxy_next_upstream error timeout http_502 http_504;'

if [ ! -r "$config" ]; then
  echo "Nginx config is not readable: $config" >&2
  exit 1
fi

active_policies="$({
  sed 's/[[:space:]]*#.*$//' "$config" |
    grep -E '^[[:space:]]*proxy_next_upstream[[:space:]]+' || true
})"

if [ "$(printf '%s\n' "$active_policies" | sed '/^$/d' | wc -l | tr -d '[:space:]')" -ne 1 ]; then
  echo "Expected exactly one global proxy_next_upstream policy in $config" >&2
  printf '%s\n' "$active_policies" >&2
  exit 1
fi

if ! grep -Fq "$expected" <<<"$active_policies"; then
  echo "Global proxy_next_upstream policy must be: $expected" >&2
  exit 1
fi

if grep -Fq 'http_503' <<<"$active_policies"; then
  echo "Global proxy_next_upstream policy must not eject upstreams on protective 503" >&2
  exit 1
fi

echo "[OK] Nginx global upstream policy preserves protective 503 responses"
