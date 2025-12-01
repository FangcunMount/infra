#!/bin/bash
# Redis 功能测试脚本
# 测试 Redis 容器状态、ACL 用户认证、基本功能
#
# 用法:
#   ./test-redis.sh                      # 使用默认 prod 环境
#   ./test-redis.sh [env_file]           # 指定配置文件
#   ENV=dev ./test-redis.sh              # 使用 dev 环境

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 测试统计
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# 确保脚本始终以脚本所在目录为基准
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 根据 ENV 参数或命令行参数选择环境配置文件
if [[ -n "${1:-}" ]]; then
    ENV_FILE="$1"
else
    ENV="${ENV:-prod}"
    if [[ "$ENV" == "prod" ]]; then
        ENV_FILE="${SCRIPT_DIR}/../../compose/env/prod/serverA.env"
    elif [[ "$ENV" == "dev" ]]; then
        ENV_FILE="${SCRIPT_DIR}/../../compose/env/dev/.env"
    else
        ENV_FILE="${SCRIPT_DIR}/../../compose/env/$ENV/.env"
    fi
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo -e "${RED}错误: 环境变量文件不存在: $ENV_FILE${NC}"
    exit 1
fi

# 加载环境变量
echo -e "${BLUE}加载环境变量: $ENV_FILE${NC}"
export $(grep "^REDIS.*PASSWORD=" "$ENV_FILE" | xargs)

# 测试函数
test_start() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo -n "  [$TOTAL_TESTS] $1 ... "
}

test_pass() {
    PASSED_TESTS=$((PASSED_TESTS + 1))
    echo -e "${GREEN}✓ PASS${NC}"
}

test_fail() {
    FAILED_TESTS=$((FAILED_TESTS + 1))
    echo -e "${RED}✗ FAIL${NC}"
    if [[ -n "${1:-}" ]]; then
        echo -e "      ${YELLOW}原因: $1${NC}"
    fi
}

test_skip() {
    echo -e "${YELLOW}⊘ SKIP${NC}"
    if [[ -n "${1:-}" ]]; then
        echo -e "      ${YELLOW}原因: $1${NC}"
    fi
}

# 执行 Redis 命令（带错误捕获）
redis_exec() {
    local instance="$1"
    local port="$2"
    local user="$3"
    local pass="$4"
    shift 4
    local cmd="$*"
    
    if [[ -z "$pass" ]]; then
        docker exec "$instance" redis-cli -p "$port" $cmd 2>&1
    else
        docker exec "$instance" redis-cli -p "$port" --user "$user" --pass "$pass" --no-auth-warning $cmd 2>&1
    fi
}

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}Redis 功能测试${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ============================================
# 1. 容器状态测试
# ============================================
echo -e "${BLUE}[1/7] 容器状态测试${NC}"

test_start "redis-cache 容器运行状态"
if docker ps --format '{{.Names}}' | grep -q '^redis-cache$'; then
    test_pass
else
    test_fail "容器未运行"
    echo -e "${RED}请先启动 Redis: make redis-start${NC}"
    exit 1
fi

test_start "redis-store 容器运行状态"
if docker ps --format '{{.Names}}' | grep -q '^redis-store$'; then
    test_pass
else
    test_fail "容器未运行"
    echo -e "${RED}请先启动 Redis: make redis-start${NC}"
    exit 1
fi

test_start "redis-cache 健康检查"
health=$(docker inspect redis-cache --format='{{.State.Health.Status}}' 2>/dev/null || echo "none")
if [[ "$health" == "healthy" ]]; then
    test_pass
elif [[ "$health" == "none" ]]; then
    test_skip "未配置健康检查"
else
    test_fail "状态: $health"
fi

test_start "redis-store 健康检查"
health=$(docker inspect redis-store --format='{{.State.Health.Status}}' 2>/dev/null || echo "none")
if [[ "$health" == "healthy" ]]; then
    test_pass
elif [[ "$health" == "none" ]]; then
    test_skip "未配置健康检查"
else
    test_fail "状态: $health"
fi

# ============================================
# 2. ACL 配置测试
# ============================================
echo ""
echo -e "${BLUE}[2/7] ACL 配置测试${NC}"

test_start "检查 ACL 文件存在"
if [[ -f "users.acl" ]]; then
    test_pass
else
    test_fail "users.acl 文件不存在"
fi

test_start "检查 ACL 文件不是目录"
if [[ ! -d "users.acl" ]]; then
    test_pass
else
    test_fail "users.acl 是目录而不是文件"
fi

test_start "检查 ACL 文件内容非空"
if [[ -s "users.acl" ]]; then
    test_pass
else
    test_fail "users.acl 文件为空"
fi

# ============================================
# 3. 默认用户禁用测试
# ============================================
echo ""
echo -e "${BLUE}[3/7] 默认用户禁用测试${NC}"

test_start "验证 default 用户已禁用 (cache)"
result=$(redis_exec "redis-cache" "6379" "" "" "PING" || true)
if echo "$result" | grep -q "NOAUTH\|Authentication required"; then
    test_pass
else
    test_fail "default 用户未禁用: $result"
fi

test_start "验证 default 用户已禁用 (store)"
result=$(redis_exec "redis-store" "6380" "" "" "PING" || true)
if echo "$result" | grep -q "NOAUTH\|Authentication required"; then
    test_pass
else
    test_fail "default 用户未禁用: $result"
fi

# ============================================
# 4. Admin 用户测试
# ============================================
echo ""
echo -e "${BLUE}[4/7] Admin 用户测试（完全权限）${NC}"

ADMIN_PASS="${REDIS_ADMIN_PASSWORD:-change_me_admin_pass}"

test_start "admin 用户认证 (cache)"
result=$(redis_exec "redis-cache" "6379" "admin" "$ADMIN_PASS" "PING" || true)
if echo "$result" | grep -q "PONG"; then
    test_pass
else
    test_fail "认证失败: $result"
fi

test_start "admin 用户认证 (store)"
result=$(redis_exec "redis-store" "6380" "admin" "$ADMIN_PASS" "PING" || true)
if echo "$result" | grep -q "PONG"; then
    test_pass
else
    test_fail "认证失败: $result"
fi

test_start "admin 用户写入数据 (cache)"
result=$(redis_exec "redis-cache" "6379" "admin" "$ADMIN_PASS" "SET test_admin_key test_value" || true)
if echo "$result" | grep -q "OK"; then
    test_pass
else
    test_fail "$result"
fi

test_start "admin 用户读取数据 (cache)"
result=$(redis_exec "redis-cache" "6379" "admin" "$ADMIN_PASS" "GET test_admin_key" || true)
if echo "$result" | grep -q "test_value"; then
    test_pass
else
    test_fail "$result"
fi

test_start "admin 用户执行 INFO 命令 (cache)"
result=$(redis_exec "redis-cache" "6379" "admin" "$ADMIN_PASS" "INFO server" || true)
if echo "$result" | grep -q "redis_version"; then
    test_pass
else
    test_fail "$result"
fi

test_start "admin 用户查看 ACL 列表 (cache)"
result=$(redis_exec "redis-cache" "6379" "admin" "$ADMIN_PASS" "ACL LIST" || true)
if echo "$result" | grep -q "user admin"; then
    test_pass
else
    test_fail "$result"
fi

# ============================================
# 5. App 用户测试
# ============================================
echo ""
echo -e "${BLUE}[5/7] App 用户测试（常规读写，排除危险命令）${NC}"

APP_PASS="${REDIS_APP_PASSWORD:-change_me_app_pass}"

test_start "app 用户认证 (cache)"
result=$(redis_exec "redis-cache" "6379" "app" "$APP_PASS" "PING" || true)
if echo "$result" | grep -q "PONG"; then
    test_pass
else
    test_fail "认证失败: $result"
fi

test_start "app 用户写入数据 (cache)"
result=$(redis_exec "redis-cache" "6379" "app" "$APP_PASS" "SET test_app_key app_value" || true)
if echo "$result" | grep -q "OK"; then
    test_pass
else
    test_fail "$result"
fi

test_start "app 用户读取数据 (cache)"
result=$(redis_exec "redis-cache" "6379" "app" "$APP_PASS" "GET test_app_key" || true)
if echo "$result" | grep -q "app_value"; then
    test_pass
else
    test_fail "$result"
fi

test_start "app 用户删除数据 (cache)"
result=$(redis_exec "redis-cache" "6379" "app" "$APP_PASS" "DEL test_app_key" || true)
if echo "$result" | grep -qE "^1$|OK"; then
    test_pass
else
    test_fail "$result"
fi

test_start "app 用户禁止执行 FLUSHALL (cache)"
result=$(redis_exec "redis-cache" "6379" "app" "$APP_PASS" "FLUSHALL" 2>&1 || true)
if echo "$result" | grep -q "NOPERM"; then
    test_pass
else
    test_fail "应该拒绝执行 FLUSHALL: $result"
fi

test_start "app 用户禁止执行 CONFIG (cache)"
result=$(redis_exec "redis-cache" "6379" "app" "$APP_PASS" "CONFIG GET maxmemory" 2>&1 || true)
if echo "$result" | grep -q "NOPERM"; then
    test_pass
else
    test_fail "应该拒绝执行 CONFIG: $result"
fi

test_start "app 用户禁止执行 KEYS (cache)"
result=$(redis_exec "redis-cache" "6379" "app" "$APP_PASS" "KEYS" "test:*" 2>&1 || true)
if echo "$result" | grep -q "NOPERM"; then
    test_pass
else
    test_fail "应该拒绝执行 KEYS: $result"
fi

# ============================================
# 6. Readonly 用户测试
# ============================================
echo ""
echo -e "${BLUE}[6/7] Readonly 用户测试（仅读取）${NC}"

READONLY_PASS="${REDIS_READONLY_PASSWORD:-change_me_readonly_pass}"

test_start "readonly 用户认证 (cache)"
result=$(redis_exec "redis-cache" "6379" "readonly" "$READONLY_PASS" "PING" || true)
if echo "$result" | grep -q "PONG"; then
    test_pass
else
    test_fail "认证失败: $result"
fi

# 先用 admin 创建测试数据
redis_exec "redis-cache" "6379" "admin" "$ADMIN_PASS" "SET test_readonly_key readonly_value" >/dev/null 2>&1

test_start "readonly 用户读取数据 (cache)"
result=$(redis_exec "redis-cache" "6379" "readonly" "$READONLY_PASS" "GET test_readonly_key" || true)
if echo "$result" | grep -q "readonly_value"; then
    test_pass
else
    test_fail "$result"
fi

test_start "readonly 用户禁止写入数据 (cache)"
result=$(redis_exec "redis-cache" "6379" "readonly" "$READONLY_PASS" "SET test_readonly_write fail" 2>&1 || true)
if echo "$result" | grep -q "NOPERM"; then
    test_pass
else
    test_fail "应该拒绝写入: $result"
fi

test_start "readonly 用户禁止删除数据 (cache)"
result=$(redis_exec "redis-cache" "6379" "readonly" "$READONLY_PASS" "DEL test_readonly_key" 2>&1 || true)
if echo "$result" | grep -q "NOPERM"; then
    test_pass
else
    test_fail "应该拒绝删除: $result"
fi

# ============================================
# 7. Monitor 用户测试
# ============================================
echo ""
echo -e "${BLUE}[7/7] Monitor 用户测试（仅监控查询）${NC}"

MONITOR_PASS="${REDIS_MONITOR_PASSWORD:-change_me_monitor_pass}"

test_start "monitor 用户认证 (cache)"
result=$(redis_exec "redis-cache" "6379" "monitor" "$MONITOR_PASS" "PING" || true)
if echo "$result" | grep -q "PONG"; then
    test_pass
else
    test_fail "认证失败: $result"
fi

test_start "monitor 用户执行 INFO (cache)"
result=$(redis_exec "redis-cache" "6379" "monitor" "$MONITOR_PASS" "INFO server" || true)
if echo "$result" | grep -q "redis_version"; then
    test_pass
else
    test_fail "$result"
fi

test_start "monitor 用户禁止写入数据 (cache)"
result=$(redis_exec "redis-cache" "6379" "monitor" "$MONITOR_PASS" "SET test_monitor_key value" 2>&1 || true)
if echo "$result" | grep -q "NOPERM"; then
    test_pass
else
    test_fail "应该拒绝写入: $result"
fi

test_start "monitor 用户禁止读取数据 (cache)"
result=$(redis_exec "redis-cache" "6379" "monitor" "$MONITOR_PASS" "GET test_admin_key" 2>&1 || true)
if echo "$result" | grep -q "NOPERM"; then
    test_pass
else
    test_fail "应该拒绝读取: $result"
fi

# ============================================
# 清理测试数据
# ============================================
echo ""
echo -e "${BLUE}清理测试数据...${NC}"
redis_exec "redis-cache" "6379" "admin" "$ADMIN_PASS" "DEL test_admin_key test_readonly_key" >/dev/null 2>&1 || true

# ============================================
# 测试总结
# ============================================
echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}测试总结${NC}"
echo -e "${CYAN}========================================${NC}"
echo -e "总测试数: ${TOTAL_TESTS}"
echo -e "${GREEN}通过: ${PASSED_TESTS}${NC}"
if [[ $FAILED_TESTS -gt 0 ]]; then
    echo -e "${RED}失败: ${FAILED_TESTS}${NC}"
else
    echo -e "${GREEN}失败: ${FAILED_TESTS}${NC}"
fi
echo ""

if [[ $FAILED_TESTS -eq 0 ]]; then
    echo -e "${GREEN}🎉 所有测试通过！Redis 配置正确。${NC}"
    exit 0
else
    echo -e "${RED}❌ 有 $FAILED_TESTS 个测试失败，请检查配置。${NC}"
    echo ""
    echo -e "${YELLOW}建议操作:${NC}"
    echo "  1. 查看容器日志: docker logs redis-cache"
    echo "  2. 检查 ACL 配置: cat users.acl"
    echo "  3. 重建 Redis: make redis-rebuild"
    exit 1
fi
