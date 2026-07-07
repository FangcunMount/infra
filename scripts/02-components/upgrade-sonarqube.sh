#!/usr/bin/env bash
#
# SonarQube 升级脚本（仅重建 sonarqube 容器，保留 PostgreSQL 与数据卷）
#
# 用法：
#   bash scripts/02-components/upgrade-sonarqube.sh
#   SKIP_BACKUP=1 bash scripts/02-components/upgrade-sonarqube.sh
#

set -euo pipefail

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
ENV_FILE="${ENV_FILE:-$INFRA_ROOT/compose/env/prod/serverD.env}"
COMPOSE_DIR="$INFRA_ROOT/deploy/serverD"
COMPOSE_FILE="$COMPOSE_DIR/docker-compose.yml"
SONAR_COMPOSE="$INFRA_ROOT/components/sonarqube/docker-compose.yml"
BACKUP_ROOT="${SONAR_BACKUP_ROOT:-/data/backup/sonarqube}"
SKIP_BACKUP="${SKIP_BACKUP:-0}"
WAIT_TIMEOUT="${SONAR_UPGRADE_WAIT_TIMEOUT:-600}"
BACKUP_ONLY=0

for arg in "$@"; do
    case "$arg" in
        --backup-only) BACKUP_ONLY=1 ;;
    esac
done

if [[ ! -f "$ENV_FILE" ]]; then
    log_error "未找到环境变量文件: $ENV_FILE"
    exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
    log_error "未找到 compose 文件: $COMPOSE_FILE"
    exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

SONAR_DB_USER="${SONAR_DB_USER:-sonar}"
SONAR_DB_NAME="${SONAR_DB_NAME:-sonar}"
SONAR_ROOT_URL="${SONAR_ROOT_URL:-https://sonar.fangcunmount.cn}"
TARGET_IMAGE="$(awk '/^[[:space:]]*image:[[:space:]]*sonarqube:/ {print $2; exit}' "$SONAR_COMPOSE")"

if [[ -z "$TARGET_IMAGE" ]]; then
    log_error "无法从 $SONAR_COMPOSE 解析 SonarQube 镜像版本"
    exit 1
fi

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

current_image() {
    docker inspect sonarqube --format '{{.Config.Image}}' 2>/dev/null || true
}

wait_for_sonarqube() {
    local elapsed=0
    local interval=10

    log_step "等待 SonarQube 启动（最长 ${WAIT_TIMEOUT}s）..."
    while (( elapsed < WAIT_TIMEOUT )); do
        if docker exec sonarqube curl -sf http://127.0.0.1:9000/api/system/status >/dev/null 2>&1; then
            log_info "SonarQube API 已响应"
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
        echo "  ... 已等待 ${elapsed}s"
    done

    log_warn "等待超时，请手动检查日志: make sonarqube-logs"
    return 1
}

backup_database() {
    local backup_file="$BACKUP_ROOT/sonar_${DATE_FORMAT}.sql"

    mkdir -p "$BACKUP_ROOT"

    if ! docker ps --format '{{.Names}}' | grep -qx 'sonarqube-db'; then
        log_error "sonarqube-db 容器未运行，无法备份"
        exit 1
    fi

    log_step "备份 PostgreSQL 到 $backup_file"
    docker exec sonarqube-db pg_dump -U "$SONAR_DB_USER" "$SONAR_DB_NAME" > "$backup_file"
    log_info "数据库备份完成: $backup_file ($(du -h "$backup_file" | awk '{print $1}'))"
}

echo "=========================================="
echo "SonarQube 升级 - $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

CURRENT_IMAGE="$(current_image)"
DATE_FORMAT="$(date +"%Y%m%d_%H%M%S")"

echo ""
echo "目标镜像: $TARGET_IMAGE"
if [[ -n "$CURRENT_IMAGE" ]]; then
    echo "当前镜像: $CURRENT_IMAGE"
    if [[ "$CURRENT_IMAGE" == "$TARGET_IMAGE" ]]; then
        log_warn "当前运行版本与 compose 中目标版本相同，仍将执行 pull + recreate"
    fi
else
    log_warn "sonarqube 容器未运行，将按目标镜像启动"
fi
echo "Setup URL: ${SONAR_ROOT_URL%/}/setup"
echo ""

if [[ "$SKIP_BACKUP" != "1" ]]; then
    backup_database
else
    log_warn "已跳过数据库备份 (SKIP_BACKUP=1)"
fi

if [[ "$BACKUP_ONLY" -eq 1 ]]; then
    log_info "仅备份模式，已结束"
    exit 0
fi

log_step "拉取新镜像"
compose pull sonarqube

log_step "重建 sonarqube 容器（保留 sonarqube-db 与数据卷）"
compose up -d sonarqube

wait_for_sonarqube || true

echo ""
log_info "升级命令已执行完成"
echo ""
echo "下一步："
echo "  1. 打开 ${SONAR_ROOT_URL%/}/setup"
echo "  2. 若提示数据库迁移，点击 Upgrade 并等待完成"
echo "  3. 在 Administration → System → System Info 确认版本"
echo ""
echo "排查命令："
echo "  make sonarqube-status"
echo "  make sonarqube-logs"
