#!/usr/bin/env bash
#
# 将 SonarQube 从 serverD 迁移到本机 Mac mini。
#
# 数据库使用 pg_dump/psql 逻辑迁移，可安全跨 amd64 -> arm64。
# Elasticsearch 索引卷不迁移，由 SonarQube 根据 PostgreSQL 自动重建。
#
# 用法：
#   SOURCE_SSH=deploy@82.157.204.239 make sonarqube-migrate-to-macmini
#
# 可选：
#   SOURCE_SSH_PORT=22
#   SOURCE_SONAR_CONTAINER=sonarqube
#   SOURCE_DB_CONTAINER=sonarqube-db
#   MIGRATION_BACKUP_ROOT=$HOME/infra-backups/sonarqube-migration
#

set -Eeuo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

SOURCE_SSH="${SOURCE_SSH:-}"
SOURCE_SSH_PORT="${SOURCE_SSH_PORT:-22}"
SOURCE_SONAR_CONTAINER="${SOURCE_SONAR_CONTAINER:-sonarqube}"
SOURCE_DB_CONTAINER="${SOURCE_DB_CONTAINER:-sonarqube-db}"
SOURCE_DOCKER="${SOURCE_DOCKER:-sudo -n docker}"

ENV_FILE="${ENV_FILE:-$INFRA_ROOT/compose/env/prod/mac-mini.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$INFRA_ROOT/deploy/mac-mini/docker-compose.yml}"
BACKUP_ROOT="${MIGRATION_BACKUP_ROOT:-$HOME/infra-backups/sonarqube-migration}"
WAIT_TIMEOUT="${SONAR_MIGRATION_WAIT_TIMEOUT:-900}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$BACKUP_ROOT/sonar_serverD_${STAMP}.sql"

if [[ -z "$SOURCE_SSH" ]]; then
    log_error "必须设置 SOURCE_SSH，例如 deploy@82.157.204.239"
    exit 1
fi

for command in docker ssh; do
    if ! command -v "$command" >/dev/null 2>&1; then
        log_error "本机缺少命令: $command"
        exit 1
    fi
done

if [[ ! -f "$ENV_FILE" ]]; then
    log_error "未找到 $ENV_FILE"
    echo "请先执行："
    echo "  cp compose/env/prod/mac-mini.env.example compose/env/prod/mac-mini.env"
    echo "并将 SONAR_DB_PASSWORD 设置为 serverD 当前实际密码。"
    exit 1
fi

read_env_var() {
    local key="$1"
    local line value
    line="$(grep -E "^${key}=" "$ENV_FILE" | tail -1 || true)"
    [[ -n "$line" ]] || return 1
    value="${line#*=}"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    printf '%s' "$value"
}

SONAR_DB_USER="$(read_env_var SONAR_DB_USER || echo sonar)"
SONAR_DB_NAME="$(read_env_var SONAR_DB_NAME || echo sonar)"
SONAR_DB_PASSWORD="$(read_env_var SONAR_DB_PASSWORD || true)"

if [[ -z "$SONAR_DB_PASSWORD" || "$SONAR_DB_PASSWORD" == change_me_* ]]; then
    log_error "mac-mini.env 中 SONAR_DB_PASSWORD 尚未设置"
    exit 1
fi

SSH=(ssh -p "$SOURCE_SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

SOURCE_STOPPED=0
MIGRATION_SUCCEEDED=0

rollback_source_on_failure() {
    local rc=$?
    if [[ "$MIGRATION_SUCCEEDED" -ne 1 && "$SOURCE_STOPPED" -eq 1 ]]; then
        log_warn "迁移未完成，正在重新启动 serverD SonarQube..."
        "${SSH[@]}" "$SOURCE_SSH" "$SOURCE_DOCKER start '$SOURCE_SONAR_CONTAINER' >/dev/null" || true
    fi
    exit "$rc"
}
trap rollback_source_on_failure EXIT

echo "============================================================"
echo "SonarQube 迁移：serverD -> Mac mini"
echo "============================================================"
echo "源端: $SOURCE_SSH ($SOURCE_SONAR_CONTAINER / $SOURCE_DB_CONTAINER)"
echo "源端 Docker 命令: $SOURCE_DOCKER"
echo "目标: 本机 Docker Desktop"
echo "备份: $BACKUP_FILE"
echo ""

log_step "检查源端容器"
"${SSH[@]}" "$SOURCE_SSH" \
    "$SOURCE_DOCKER inspect '$SOURCE_SONAR_CONTAINER' '$SOURCE_DB_CONTAINER' >/dev/null && $SOURCE_DOCKER ps --format '{{.Names}}' | grep -qx '$SOURCE_DB_CONTAINER'"

if docker ps -a --format '{{.Names}}' | grep -qx "$SOURCE_SONAR_CONTAINER"; then
    log_error "本机已存在 $SOURCE_SONAR_CONTAINER 容器；为防止覆盖，迁移中止"
    echo "如为测试容器，请先执行 make macmini-sonarqube-down。"
    exit 1
fi

log_step "确保本机 infra-network 存在"
docker network inspect infra-network >/dev/null 2>&1 \
    || docker network create --driver bridge infra-network >/dev/null

log_step "停止 serverD SonarQube 应用（数据库保持运行）"
"${SSH[@]}" "$SOURCE_SSH" "$SOURCE_DOCKER stop '$SOURCE_SONAR_CONTAINER' >/dev/null"
SOURCE_STOPPED=1

mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"

log_step "从 serverD 导出 PostgreSQL"
"${SSH[@]}" "$SOURCE_SSH" \
    "$SOURCE_DOCKER exec '$SOURCE_DB_CONTAINER' pg_dump \
      -U '$SONAR_DB_USER' \
      --clean --if-exists --no-owner --no-privileges \
      '$SONAR_DB_NAME'" >"$BACKUP_FILE"
chmod 600 "$BACKUP_FILE"

if [[ ! -s "$BACKUP_FILE" ]]; then
    log_error "数据库备份为空"
    exit 1
fi
log_info "数据库备份完成: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | awk '{print $1}'))"

log_step "启动 Mac mini PostgreSQL"
compose up -d sonarqube-init sonarqube-db

for _ in $(seq 1 30); do
    if docker exec "$SOURCE_DB_CONTAINER" pg_isready -U "$SONAR_DB_USER" -d "$SONAR_DB_NAME" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

if ! docker exec "$SOURCE_DB_CONTAINER" pg_isready -U "$SONAR_DB_USER" -d "$SONAR_DB_NAME" >/dev/null 2>&1; then
    log_error "Mac mini PostgreSQL 未就绪"
    exit 1
fi

log_step "清空目标数据库并恢复备份"
docker exec -e PGPASSWORD="$SONAR_DB_PASSWORD" "$SOURCE_DB_CONTAINER" \
    psql -v ON_ERROR_STOP=1 -U "$SONAR_DB_USER" -d "$SONAR_DB_NAME" \
    -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'

docker exec -i -e PGPASSWORD="$SONAR_DB_PASSWORD" "$SOURCE_DB_CONTAINER" \
    psql -v ON_ERROR_STOP=1 -U "$SONAR_DB_USER" -d "$SONAR_DB_NAME" \
    <"$BACKUP_FILE"

log_step "启动 Mac mini SonarQube"
compose up -d sonarqube

elapsed=0
interval=10
while (( elapsed < WAIT_TIMEOUT )); do
    if docker exec "$SOURCE_SONAR_CONTAINER" \
        curl -sf http://127.0.0.1:9000/api/system/status \
        | grep -q '"status":"UP"'; then
        MIGRATION_SUCCEEDED=1
        break
    fi
    sleep "$interval"
    elapsed=$((elapsed + interval))
    echo "  ... 已等待 ${elapsed}s"
done

if [[ "$MIGRATION_SUCCEEDED" -ne 1 ]]; then
    log_error "Mac mini SonarQube 未在 ${WAIT_TIMEOUT}s 内进入 UP"
    docker logs --tail 200 "$SOURCE_SONAR_CONTAINER" || true
    exit 1
fi

trap - EXIT

echo ""
log_info "Mac mini SonarQube 已恢复并进入 UP"
echo ""
echo "下一步（切流量）："
echo "  1. 在 serverA 更新 infra 仓库并执行 make sonarqube-nginx-deploy"
echo "  2. 从外部访问 https://sonar.fangcunmount.cn 验证项目、用户和历史数据"
echo "  3. 验证完成后，在 serverD 执行：docker stop $SOURCE_DB_CONTAINER"
echo ""
echo "回滚（切流量前或切回旧 Nginx 配置后）："
echo "  ssh -p $SOURCE_SSH_PORT $SOURCE_SSH '$SOURCE_DOCKER start $SOURCE_DB_CONTAINER $SOURCE_SONAR_CONTAINER'"
echo ""
echo "注意：旧 serverD 卷未删除，确认稳定运行一周后再人工清理。"
