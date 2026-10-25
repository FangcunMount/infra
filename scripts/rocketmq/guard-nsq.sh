#!/usr/bin/env bash
set -euo pipefail
# The generic component remains available only to development/isolated tests.
case "${1:-}" in
  prod|production)
    echo 'Production NSQ deployment is retired; use the reviewed RocketMQ release.' >&2
    exit 1
    ;;
esac
marker="${MESSAGING_PROVIDER_MARKER:-/data/infra/messaging-provider}"
if [ -f "$marker" ] && [ "$(cat "$marker")" = rocketmq ]; then
  echo 'NSQ is paused after RocketMQ cutover. Use the reviewed reconciliation/rollback procedure.' >&2
  exit 1
fi
