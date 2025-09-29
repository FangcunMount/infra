#!/usr/bin/env bash
# Kafka 组件安装脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/install-components.sh"

main kafka "$@"