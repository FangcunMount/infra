#!/usr/bin/env bash
#
# MongoDB 副本集 keyFile 准备脚本
# 用途：在启动 MongoDB 前为 "authorization + replica set" 场景准备本地 keyFile
#

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ENV="${ENV:-prod}"
if [[ "$ENV" == "prod" ]]; then
    ENV_FILE="$INFRA_ROOT/compose/env/prod/serverA.env"
elif [[ "$ENV" == "dev" ]]; then
    ENV_FILE="$INFRA_ROOT/compose/env/dev/.env"
else
    ENV_FILE="$INFRA_ROOT/compose/env/$ENV/.env"
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "${RED}❌ 错误：未找到环境变量文件${NC}"
    echo "   期望路径: $ENV_FILE"
    exit 1
fi

source "$ENV_FILE"

INFRA_DATA_ROOT="${INFRA_DATA_ROOT:-/data/infra}"
KEYFILE_DIR="${INFRA_DATA_ROOT}/mongo/config"
KEYFILE_PATH="${KEYFILE_DIR}/replset.key"

if [[ "${MONGO_REPLICA_SET_KEYFILE:-}" != "" ]]; then
    KEYFILE_PATH="${MONGO_REPLICA_SET_KEYFILE}"
    KEYFILE_DIR="$(dirname "$KEYFILE_PATH")"
fi

if [[ "$(id -u)" -eq 0 ]]; then
    SUDO=""
else
    SUDO="sudo"
fi

echo "=========================================="
echo "MongoDB 副本集 keyFile 准备"
echo "=========================================="

$SUDO mkdir -p "$KEYFILE_DIR"

if [[ ! -f "$KEYFILE_PATH" ]]; then
    echo -e "${YELLOW}🔐 未检测到 keyFile，开始生成...${NC}"
    TMP_FILE="$(mktemp)"
    openssl rand -base64 756 > "$TMP_FILE"
    $SUDO install -o 999 -g 999 -m 400 "$TMP_FILE" "$KEYFILE_PATH"
    rm -f "$TMP_FILE"
    echo -e "${GREEN}✅ 已生成 keyFile: $KEYFILE_PATH${NC}"
else
    echo -e "${YELLOW}ℹ️  检测到已有 keyFile，校正权限...${NC}"
    $SUDO chown 999:999 "$KEYFILE_PATH"
    $SUDO chmod 400 "$KEYFILE_PATH"
    echo -e "${GREEN}✅ keyFile 已就绪: $KEYFILE_PATH${NC}"
fi
