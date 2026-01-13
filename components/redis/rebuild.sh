#!/bin/bash
# Redis 完全重建脚本
# 功能：停止容器、删除数据卷、清理宿主机数据、重新部署
#
# 用法:
#   ./rebuild.sh                         # 使用默认 prod 环境
#   ./rebuild.sh [env_file]              # 指定配置文件
#   ENV=dev ./rebuild.sh                 # 使用 dev 环境
#   ./rebuild.sh --clean-only            # 仅清理，不重建

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 确保脚本始终以脚本所在目录为基准
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 解析参数
CLEAN_ONLY=false
ENV_FILE=""

for arg in "$@"; do
    case $arg in
        --clean-only)
            CLEAN_ONLY=true
            shift
            ;;
        *)
            if [[ -z "$ENV_FILE" ]]; then
                ENV_FILE="$arg"
            fi
            ;;
    esac
done

# 根据 ENV 参数选择环境配置文件
if [[ -z "$ENV_FILE" ]]; then
    ENV="${ENV:-prod}"
    if [[ "$ENV" == "prod" ]]; then
        ENV_FILE="${SCRIPT_DIR}/../../compose/env/prod/serverA.env"
    elif [[ "$ENV" == "dev" ]]; then
        ENV_FILE="${SCRIPT_DIR}/../../compose/env/dev/.env"
    else
        ENV_FILE="${SCRIPT_DIR}/../../compose/env/$ENV/.env"
    fi
fi

echo -e "${BLUE}========================================${NC}"
if [[ "$CLEAN_ONLY" == true ]]; then
    echo -e "${BLUE}Redis 数据清理脚本${NC}"
else
    echo -e "${BLUE}Redis 完全重建脚本${NC}"
fi
echo -e "${BLUE}========================================${NC}"
echo ""

# 确认操作（如果通过 make 调用，已经确认过了）
if [[ -z "$REDIS_REBUILD_CONFIRMED" ]]; then
    echo -e "${RED}警告: 此操作将删除所有 Redis 数据！${NC}"
    echo -e "${YELLOW}包括:${NC}"
    echo "  - Redis 容器 (redis-cache)"
    echo "  - Docker 数据卷 (infra_redis_cache_data)"
    echo "  - 宿主机数据目录 (/data/redis)"
    echo "  - ACL 配置文件 (users.acl)"
    echo ""
    read -p "确认要继续吗？(yes/no): " confirm

    if [[ "$confirm" != "yes" ]]; then
        echo -e "${GREEN}操作已取消${NC}"
        exit 0
    fi
fi

echo ""
echo -e "${BLUE}[步骤 1/6] 停止并删除 Redis 容器${NC}"
cd "$(dirname "$0")"
if docker compose ps | grep -q redis; then
    docker compose stop redis-cache 2>/dev/null || true
    docker compose rm -f redis-cache 2>/dev/null || true
    echo -e "${GREEN}✓ 容器已停止并删除${NC}"
else
    echo -e "${YELLOW}✓ 容器不存在，跳过${NC}"
fi

echo ""
echo -e "${BLUE}[步骤 2/6] 删除 Docker 数据卷${NC}"
volumes=("infra_redis_cache_data")
for vol in "${volumes[@]}"; do
    if docker volume inspect "$vol" >/dev/null 2>&1; then
        docker volume rm "$vol"
        echo -e "${GREEN}✓ 已删除数据卷: $vol${NC}"
    else
        echo -e "${YELLOW}✓ 数据卷不存在: $vol${NC}"
    fi
done

echo ""
echo -e "${BLUE}[步骤 3/6] 清理宿主机数据目录${NC}"
data_dirs=(
    "/data/redis"
    "/data/logs/redis"
)

for dir in "${data_dirs[@]}"; do
    if [[ -d "$dir" ]]; then
        if [[ "$(id -u)" == "0" ]]; then
            # root 用户直接删除
            rm -rf "$dir"
            echo -e "${GREEN}✓ 已删除目录: $dir${NC}"
        else
            # 非 root 用户使用 sudo
            echo "需要 sudo 权限删除目录: $dir"
            sudo rm -rf "$dir"
            echo -e "${GREEN}✓ 已删除目录: $dir${NC}"
        fi
    else
        echo -e "${YELLOW}✓ 目录不存在: $dir${NC}"
    fi
done

echo ""
echo -e "${BLUE}[步骤 4/6] 删除 ACL 配置文件${NC}"
if [[ -e "users.acl" ]]; then
    rm -rf users.acl
    echo -e "${GREEN}✓ 已删除: users.acl${NC}"
else
    echo -e "${YELLOW}✓ users.acl 不存在${NC}"
fi

echo ""
echo -e "${BLUE}[步骤 5/6] 重新生成 ACL 配置${NC}"
# ENV_FILE 已在脚本开头解析，这里不需要重新赋值
if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "${RED}✗ 环境变量文件不存在: $ENV_FILE${NC}"
    exit 1
fi

# 创建空文件（防止 Docker 创建目录）
touch users.acl
echo -e "${GREEN}✓ 已创建空的 users.acl 文件${NC}"

# 生成 ACL 配置
if [[ -f "generate-acl.sh" ]]; then
    bash generate-acl.sh "$ENV_FILE"
    echo -e "${GREEN}✓ ACL 配置已生成${NC}"
else
    echo -e "${RED}✗ 找不到 generate-acl.sh 脚本${NC}"
    exit 1
fi

# 如果是仅清理模式，到这里就结束
if [[ "$CLEAN_ONLY" == true ]]; then
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}Redis 数据清理完成！${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo -e "${YELLOW}提示: 运行 'make redis-start' 或 'docker compose up -d' 启动 Redis${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}[步骤 6/6] 重新部署 Redis${NC}"
docker compose --env-file "$ENV_FILE" up -d redis-cache
echo -e "${GREEN}✓ Redis 容器已启动${NC}"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Redis 重建完成！${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "验证命令:"
echo "  docker ps | grep redis"
echo "  docker logs redis-cache"
echo ""
echo "测试 ACL 认证:"
ADMIN_PASS=$(grep "^REDIS_ADMIN_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2)
if [[ -n "$ADMIN_PASS" ]]; then
    echo "  docker exec redis-cache redis-cli --user admin --pass '$ADMIN_PASS' ping"
    echo "  docker exec redis-cache redis-cli --user admin --pass '$ADMIN_PASS' ACL LIST"
fi
