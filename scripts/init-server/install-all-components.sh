#!/usr/bin/env bash
# 安装所有组件的快捷脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/install-components.sh"

main all "$@"