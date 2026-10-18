#!/usr/bin/env bash
set -euo pipefail
marker="${MESSAGING_PROVIDER_MARKER:-/data/infra/messaging-provider}"
if [ -f "$marker" ] && [ "$(cat "$marker")" = rocketmq ]; then
  echo 'NSQ is paused after RocketMQ cutover. Use the reviewed reconciliation/rollback procedure.' >&2
  exit 1
fi
