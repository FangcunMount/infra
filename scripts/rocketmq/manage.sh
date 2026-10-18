#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
action=${1:-status}
: "${ROCKETMQ_ENV_FILE:?explicit private env file required}"
compose=(docker compose --env-file "$ROCKETMQ_ENV_FILE" -f "$root/components/rocketmq/docker-compose.yml")
exec 9>"${ROCKETMQ_LOCK_FILE:-/tmp/infra-rocketmq.lock}"
if command -v flock >/dev/null; then flock -n 9 || { echo "RocketMQ operation already running" >&2; exit 1; }; fi
case "$action" in
  validate) "${compose[@]}" config --quiet ;;
  up)
    # Check explicit resource/release evidence before mutating a production stack.
    : "${ROCKETMQ_ACCEPTANCE_FILE:?validated acceptance receipt path required}"
    test -s "$ROCKETMQ_ACCEPTANCE_FILE"
    python3 "$root/scripts/rocketmq/validate_receipt.py" "$ROCKETMQ_ACCEPTANCE_FILE" "$ROCKETMQ_ENV_FILE"
    "${compose[@]}" config --quiet
    bash "$root/scripts/rocketmq/firewall.sh"
    "${compose[@]}" up -d --wait --wait-timeout 180 ;;
  stop) "${compose[@]}" stop --timeout 90 ;;
  status) "${compose[@]}" ps ;;
  logs) "${compose[@]}" logs --tail 100 ;;
  *) echo 'usage: manage.sh validate|up|stop|status|logs' >&2; exit 2 ;;
esac
