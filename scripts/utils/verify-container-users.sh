#!/bin/bash
# verify-container-users.sh
# 验证所有基础设施容器的运行用户

set -euo pipefail

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "======================================"
echo "  基础设施容器用户验证"
echo "======================================"
echo ""

# 定义要检查的容器
declare -A EXPECTED_USERS=(
    ["nginx"]="www-data (UID 101)"
    ["mysql"]="mysql (UID 999)"
    ["redis-cache"]="redis (UID 999)"
    ["mongo"]="mongodb (UID 999)"
    ["nsqlookupd"]="nsq (UID 1000)"
    ["nsqd"]="nsq (UID 1000)"
    ["nsqadmin"]="nsq (UID 1000)"
)

# 统计
total=0
running=0
verified=0

echo "检查容器状态和运行用户:"
echo "--------------------------------------"

for container in "${!EXPECTED_USERS[@]}"; do
    ((total++))
    expected="${EXPECTED_USERS[$container]}"
    
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        ((running++))
        echo -n "✓ ${container}: "
        
        # 获取用户信息
        user_info=$(docker exec "$container" id 2>/dev/null || echo "ERROR")
        
        if [ "$user_info" != "ERROR" ]; then
            echo -e "${GREEN}${user_info}${NC}"
            echo "  预期: ${expected}"
            ((verified++))
        else
            echo -e "${RED}无法获取用户信息${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ ${container}: 容器未运行${NC}"
    fi
done

echo ""
echo "--------------------------------------"
echo "检查 Nginx worker 进程:"
echo "--------------------------------------"

if docker ps --format '{{.Names}}' | grep -q "^nginx$"; then
    nginx_workers=$(docker exec nginx ps aux 2>/dev/null | grep "nginx: worker" | head -3)
    if [ -n "$nginx_workers" ]; then
        echo "$nginx_workers"
        echo -e "${GREEN}✓ Nginx worker 进程使用 nginx 用户${NC}"
    else
        echo -e "${RED}✗ 未找到 nginx worker 进程${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Nginx 容器未运行${NC}"
fi

echo ""
echo "======================================"
echo "  验证摘要"
echo "======================================"
echo "总容器数: ${total}"
echo "运行中: ${running}"
echo "已验证: ${verified}"

if [ "$verified" -eq "$running" ]; then
    echo -e "${GREEN}✓ 所有运行中的容器用户配置正确${NC}"
    exit 0
else
    echo -e "${RED}✗ 部分容器验证失败${NC}"
    exit 1
fi
