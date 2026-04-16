#!/usr/bin/env bash
#
# MongoDB 单节点副本集初始化脚本
# 用途：为已存在数据卷或首次启动后的 MongoDB 容器补齐 rs.initiate()
#
# 用法：
#   1. 先启动 MongoDB 容器
#   2. 执行: bash scripts/02-components/init-mongo-replica-set.sh
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

REPLICA_SET_NAME="rs0"
REPLICA_MEMBER_HOST="mongo:27017"

echo "=========================================="
echo "MongoDB 单节点副本集初始化"
echo "=========================================="

if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "${RED}❌ 错误：未找到环境变量文件${NC}"
    echo "   期望路径: $ENV_FILE"
    exit 1
fi

source "$ENV_FILE"

if [[ -z "${MONGO_INITDB_ROOT_USERNAME:-}" ]] || [[ -z "${MONGO_INITDB_ROOT_PASSWORD:-}" ]]; then
    echo -e "${RED}❌ 错误：缺少 MONGO_INITDB_ROOT_USERNAME 或 MONGO_INITDB_ROOT_PASSWORD${NC}"
    exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "mongo"; then
    echo -e "${RED}❌ 错误：MongoDB 容器未运行${NC}"
    echo "   请先执行: make mongo-start"
    exit 1
fi

echo ""
echo -e "${YELLOW}⏳ 等待 MongoDB 就绪...${NC}"
for _ in $(seq 1 30); do
    if docker exec mongo mongosh \
        -u "$MONGO_INITDB_ROOT_USERNAME" \
        -p "$MONGO_INITDB_ROOT_PASSWORD" \
        --authenticationDatabase admin \
        --quiet \
        --eval "db.adminCommand({ ping: 1 }).ok" 2>/dev/null | grep -q "1"; then
        break
    fi
    sleep 2
done

if ! docker exec mongo mongosh \
    -u "$MONGO_INITDB_ROOT_USERNAME" \
    -p "$MONGO_INITDB_ROOT_PASSWORD" \
    --authenticationDatabase admin \
    --quiet \
    --eval "db.adminCommand({ ping: 1 }).ok" 2>/dev/null | grep -q "1"; then
    echo -e "${RED}❌ 错误：MongoDB 未在预期时间内就绪${NC}"
    exit 1
fi

echo -e "${YELLOW}🔧 检查副本集状态...${NC}"

docker exec -i mongo mongosh \
    -u "$MONGO_INITDB_ROOT_USERNAME" \
    -p "$MONGO_INITDB_ROOT_PASSWORD" \
    --authenticationDatabase admin \
    --quiet <<EOF
const replSetName = "${REPLICA_SET_NAME}";
const memberHost = "${REPLICA_MEMBER_HOST}";

try {
  const status = rs.status();
  if (status.set === replSetName) {
    print("✅ 副本集已初始化: " + replSetName);
  } else {
    throw new Error("检测到副本集 '" + status.set + "'，与预期 '" + replSetName + "' 不一致");
  }
} catch (e) {
  if (e.codeName === "NotYetInitialized" || e.code === 94) {
    print("🚀 开始初始化副本集: " + replSetName);
    const result = rs.initiate({
      _id: replSetName,
      members: [
        { _id: 0, host: memberHost }
      ]
    });
    printjson(result);
  } else {
    throw e;
  }
}
EOF

echo -e "${YELLOW}⏳ 等待当前节点成为 PRIMARY...${NC}"
for _ in $(seq 1 30); do
    if docker exec mongo mongosh \
        -u "$MONGO_INITDB_ROOT_USERNAME" \
        -p "$MONGO_INITDB_ROOT_PASSWORD" \
        --authenticationDatabase admin \
        --quiet \
        --eval "const hello = db.hello(); print(hello.setName === '${REPLICA_SET_NAME}' && hello.isWritablePrimary ? 'PRIMARY' : 'WAITING')" 2>/dev/null | grep -q "PRIMARY"; then
        echo -e "${GREEN}✅ 单节点副本集已就绪：${REPLICA_SET_NAME}${NC}"
        echo "   成员地址: ${REPLICA_MEMBER_HOST}"
        echo "   建议连接串: mongodb://<user>:<password>@localhost:${MONGO_PORT:-27017}/<db>?authSource=<db>&replicaSet=${REPLICA_SET_NAME}&directConnection=true"
        exit 0
    fi
    sleep 2
done

echo -e "${RED}❌ 错误：副本集初始化后未在预期时间内成为 PRIMARY${NC}"
echo "   请执行: make mongo-rs-status"
exit 1
