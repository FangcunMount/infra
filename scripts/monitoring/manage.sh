#!/usr/bin/env bash
set -euo pipefail

runtime="${MONITORING_RUNTIME:-$HOME/infra-monitoring}"
private="${MONITORING_PRIVATE_ROOT:-$HOME/.config/infra-monitoring}"
[[ "$(uname -s)" == Darwin ]] || { echo 'Run this target on the monitoring Mac mini.' >&2; exit 1; }
[[ -f "$private/runtime.env" ]] || { echo 'Monitoring runtime is not installed on this Mac.' >&2; exit 1; }
export PATH="/Applications/Docker.app/Contents/Resources/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
action="${1:-status}"
shift || true
compose=(docker compose --project-name macmini-monitoring --env-file "$private/runtime.env" -f "$runtime/docker-compose.yml")
case "$action" in
  up) "${compose[@]}" up -d --pull never "$@" ;;
  stop|restart|logs) "${compose[@]}" "$action" "$@" ;;
  status) "${compose[@]}" ps "$@" ;;
  targets) curl --fail --silent --show-error http://127.0.0.1:19090/api/v1/targets ;;
  discover) python3 "$runtime/discover.py" --config "$private/discovery.json" ;;
  *) echo "Unknown monitoring action: $action" >&2; exit 2 ;;
esac
