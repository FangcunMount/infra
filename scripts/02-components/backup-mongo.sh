#!/usr/bin/env bash
#
# MongoDB 备份脚本（使用 mongodump）
# 用途：定时备份 MongoDB 数据到本地目录，结合 cron 实现自动备份
#
# 用法：
#   手动执行：bash scripts/02-components/backup-mongo.sh
#   指定环境：ENV=dev bash scripts/02-components/backup-mongo.sh
#   定时任务：0 2 * * * /path/to/infra/scripts/02-components/backup-mongo.sh >> /var/log/mongo-backup.log 2>&1
#

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 根据 ENV 参数选择环境配置文件
# ENV=prod (默认) -> serverC.env (MongoDB 部署在 serverC)
# ENV=dev -> dev/.env
ENV="${ENV:-prod}"
if [[ "$ENV" == "prod" ]]; then
    ENV_FILE="$INFRA_ROOT/compose/env/prod/serverC.env"
elif [[ "$ENV" == "dev" ]]; then
    ENV_FILE="$INFRA_ROOT/compose/env/dev/.env"
else
    ENV_FILE="$INFRA_ROOT/compose/env/$ENV/.env"
fi

# 备份配置
BACKUP_ROOT="/data/backup/mongo"
DATE_FORMAT=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_ROOT/backup_${DATE_FORMAT}.archive.gz"

# 从环境变量读取保留期，默认 7 天
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-7}

echo "=========================================="
echo "MongoDB 数据备份 - $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 加载环境变量
if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "${RED}❌ 错误：未找到环境变量文件: $ENV_FILE${NC}"
    exit 1
fi

source "$ENV_FILE"

# 检查必要变量
if [[ -z "${MONGO_INITDB_ROOT_USERNAME:-}" ]] || [[ -z "${MONGO_INITDB_ROOT_PASSWORD:-}" ]]; then
    echo -e "${RED}❌ 错误：缺少 MongoDB 认证信息${NC}"
    exit 1
fi

# 创建备份目录
mkdir -p "$BACKUP_ROOT"

# 检查 MongoDB 容器状态
if ! docker ps | grep -q "mongo"; then
    echo -e "${RED}❌ 错误：MongoDB 容器未运行${NC}"
    exit 1
fi

echo ""
echo "📦 开始备份..."
echo "   容器: mongo"
echo "   目标: $BACKUP_FILE"
echo "   保留期: $RETENTION_DAYS 天"
echo ""

# 执行 mongodump - 直接在容器内打包归档（减少临时 I/O）
START_TIME=$(date +%s)

docker exec mongo sh -c "
    mongodump \
        --username='$MONGO_INITDB_ROOT_USERNAME' \
        --password='$MONGO_INITDB_ROOT_PASSWORD' \
        --authenticationDatabase=admin \
        --archive \
        --gzip \
        --quiet > /tmp/backup_${DATE_FORMAT}.archive.gz
"

if [[ $? -ne 0 ]]; then
    echo -e "${RED}❌ mongodump 执行失败${NC}"
    exit 1
fi

# 从容器复制归档文件到宿主机（单个文件，速度更快）
docker cp "mongo:/tmp/backup_${DATE_FORMAT}.archive.gz" "$BACKUP_FILE"

# 清理容器内临时文件
docker exec mongo rm -f "/tmp/backup_${DATE_FORMAT}.archive.gz"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# 计算备份大小
BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)

echo ""
echo -e "${GREEN}✅ 备份完成！${NC}"
echo "   文件: $BACKUP_FILE"
echo "   大小: $BACKUP_SIZE"
echo "   耗时: ${DURATION}s"
echo ""

# 创建备份元数据
METADATA_FILE="${BACKUP_FILE}.info"
cat > "$METADATA_FILE" << EOF
备份时间: $(date '+%Y-%m-%d %H:%M:%S')
备份文件: $BACKUP_FILE
备份大小: $BACKUP_SIZE
备份耗时: ${DURATION}s
保留期限: $RETENTION_DAYS 天
MongoDB 版本: $(docker exec mongo mongod --version | head -n 1)
数据库列表: $(docker exec mongo mongosh -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --quiet --eval "db.adminCommand('listDatabases').databases.map(d => d.name).join(', ')")
EOF

# 清理旧备份（根据环境变量配置的保留期）
echo ""
echo "🧹 清理超过 $RETENTION_DAYS 天的旧备份..."
find "$BACKUP_ROOT" -maxdepth 1 -type f -name "backup_*.archive.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
find "$BACKUP_ROOT" -maxdepth 1 -type f -name "backup_*.archive.gz.info" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true

CURRENT_BACKUPS=$(find "$BACKUP_ROOT" -maxdepth 1 -type f -name "backup_*.archive.gz" | wc -l)
echo "   当前备份数量: $CURRENT_BACKUPS"
echo "   备份总大小: $(du -sh "$BACKUP_ROOT" | cut -f1)"

echo ""
echo "=========================================="
echo "✅ 备份任务完成"
echo "=========================================="
echo ""
echo "📝 恢复方法："
echo "   # 直接从归档恢复（推荐）"
echo "   docker exec -i mongo mongorestore \\"
echo "       --username=\$MONGO_INITDB_ROOT_USERNAME \\"
echo "       --password=\$MONGO_INITDB_ROOT_PASSWORD \\"
echo "       --authenticationDatabase=admin \\"
echo "       --archive=/path/to/backup_${DATE_FORMAT}.archive.gz \\"
echo "       --gzip \\"
echo "       --drop"
echo ""
echo "   # 或者从宿主机恢复"
echo "   docker exec -i mongo mongorestore \\"
echo "       --username=\$MONGO_INITDB_ROOT_USERNAME \\"
echo "       --password=\$MONGO_INITDB_ROOT_PASSWORD \\"
echo "       --authenticationDatabase=admin \\"
echo "       --archive \\"
echo "       --gzip < $BACKUP_FILE"
echo ""
echo "🔄 建议配置 cron 定时任务："
echo "   0 2 * * * $SCRIPT_DIR/backup-mongo.sh >> /var/log/mongo-backup.log 2>&1"
echo ""
