#!/usr/bin/env bash
#
# MongoDB 业务用户初始化脚本
# 用途：创建业务数据库用户，限制权限（最小权限原则）
#
# 用法：
#   1. 先启动 MongoDB 容器（确保 root 账户已创建）
#   2. 执行: bash scripts/components/init-mongo-users.sh
#

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 根据 ENV 参数选择环境配置文件
ENV="${ENV:-prod}"
if [[ "$ENV" == "prod" ]]; then
    ENV_FILE="$INFRA_ROOT/compose/env/prod/serverC.env"
elif [[ "$ENV" == "dev" ]]; then
    ENV_FILE="$INFRA_ROOT/compose/env/dev/.env"
else
    ENV_FILE="$INFRA_ROOT/compose/env/$ENV/.env"
fi

echo "=========================================="
echo "MongoDB 业务用户初始化"
echo "=========================================="

# 加载环境变量
if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "${RED}❌ 错误：未找到环境变量文件${NC}"
    echo "   期望路径: $ENV_FILE"
    exit 1
fi

source "$ENV_FILE"

# 检查必要的环境变量
if [[ -z "${MONGO_INITDB_ROOT_USERNAME:-}" ]] || [[ -z "${MONGO_INITDB_ROOT_PASSWORD:-}" ]]; then
    echo -e "${RED}❌ 错误：缺少 MONGO_INITDB_ROOT_USERNAME 或 MONGO_INITDB_ROOT_PASSWORD${NC}"
    exit 1
fi

# 提示输入业务用户信息
echo ""
echo -e "${YELLOW}📝 请输入业务用户信息：${NC}"
echo ""
read -p "数据库名称 [${MONGO_DATABASE:-infrastructure_prod}]: " DB_NAME
DB_NAME="${DB_NAME:-${MONGO_DATABASE:-infrastructure_prod}}"

read -p "业务用户名 [app_user]: " APP_USER
APP_USER="${APP_USER:-app_user}"

read -sp "业务用户密码（留空自动生成）: " APP_PASSWORD
echo ""

# 自动生成密码
if [[ -z "$APP_PASSWORD" ]]; then
    APP_PASSWORD=$(openssl rand -base64 16 | tr -d '/+=' | cut -c1-16)
    echo -e "${GREEN}✅ 自动生成密码: $APP_PASSWORD${NC}"
fi

read -p "用户角色 [readWrite/read/dbOwner, 默认 readWrite]: " APP_ROLE
APP_ROLE="${APP_ROLE:-readWrite}"

# 验证角色
if [[ ! "$APP_ROLE" =~ ^(read|readWrite|dbAdmin|dbOwner|userAdmin)$ ]]; then
    echo -e "${RED}❌ 错误：无效的角色 '$APP_ROLE'${NC}"
    echo "   支持的角色: read, readWrite, dbAdmin, dbOwner, userAdmin"
    exit 1
fi

echo ""
echo -e "${YELLOW}📋 配置摘要：${NC}"
echo "   数据库:   $DB_NAME"
echo "   用户名:   $APP_USER"
echo "   角色:     $APP_ROLE"
echo ""
read -p "确认创建用户？[y/N] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 已取消"
    exit 0
fi

# 执行创建用户命令
echo ""
echo -e "${YELLOW}🔧 正在创建用户...${NC}"

docker exec -i mongo mongosh \
    -u "$MONGO_INITDB_ROOT_USERNAME" \
    -p "$MONGO_INITDB_ROOT_PASSWORD" \
    --authenticationDatabase admin \
    --quiet <<EOF
use $DB_NAME;

// 检查用户是否已存在
var existingUser = db.getUser("$APP_USER");
if (existingUser) {
    print("⚠️  用户 '$APP_USER' 已存在，跳过创建");
    print("   如需修改密码，请使用: db.changeUserPassword('$APP_USER', 'newPassword')");
} else {
    // 创建用户
    db.createUser({
        user: "$APP_USER",
        pwd: "$APP_PASSWORD",
        roles: [
            { role: "$APP_ROLE", db: "$DB_NAME" }
        ]
    });
    print("✅ 用户 '$APP_USER' 创建成功");
}

// 显示用户信息
print("\n📊 用户信息：");
printjson(db.getUser("$APP_USER"));
EOF

if [[ $? -eq 0 ]]; then
    echo ""
    echo -e "${GREEN}=========================================="
    echo "✅ 用户创建成功！"
    echo "==========================================${NC}"
    echo ""
    echo "📝 连接信息："
    echo "   mongodb://$APP_USER:$APP_PASSWORD@localhost:${MONGO_PORT:-27017}/$DB_NAME?authSource=$DB_NAME"
    echo ""
    echo "🔐 建议："
    echo "   1. 将密码保存到密钥管理系统（如 1Password、Vault）"
    echo "   2. 应用程序通过环境变量读取连接字符串"
    echo "   3. 定期轮换密码（建议 90 天）"
    echo ""
    echo "📊 验证连接："
    echo "   docker exec -it mongo mongosh -u $APP_USER -p '$APP_PASSWORD' --authenticationDatabase $DB_NAME $DB_NAME"
    echo ""
else
    echo -e "${RED}❌ 用户创建失败，请检查 MongoDB 日志${NC}"
    echo "   docker logs mongo --tail 50"
    exit 1
fi
