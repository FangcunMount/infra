#!/usr/bin/env bash
# NSQ 集群连通性测试脚本
# 测试跨主机 NSQ 服务通信

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $*"; }

echo "=========================================="
echo "NSQ 集群连通性测试"
echo "=========================================="
echo ""

# 获取当前主机名
HOSTNAME=$(hostname)
log_info "当前主机: ${HOSTNAME}"
echo ""

# 1. 检查本地 NSQ 服务
log_step "1. 检查本地 NSQ 服务状态"
echo ""

if docker ps | grep -q nsqlookupd; then
    log_success "nsqlookupd 运行中"
    docker ps | grep nsqlookupd | awk '{print "   " $0}'
else
    log_warn "nsqlookupd 未运行"
fi

if docker ps | grep -q "nsqd"; then
    log_success "nsqd 运行中"
    docker ps | grep "nsqd" | grep -v nsqadmin | awk '{print "   " $0}'
else
    log_warn "nsqd 未运行"
fi

if docker ps | grep -q nsqadmin; then
    log_success "nsqadmin 运行中"
    docker ps | grep nsqadmin | awk '{print "   " $0}'
else
    log_warn "nsqadmin 未运行"
fi
echo ""

# 2. 检查 Swarm 网络
log_step "2. 检查 Swarm 集群和网络"
echo ""

if docker info 2>/dev/null | grep -q "Swarm: active"; then
    log_success "Swarm 已激活"
    
    # 获取节点角色
    if docker info 2>/dev/null | grep -q "Is Manager: true"; then
        echo "   角色: Manager"
        echo ""
        log_info "集群节点列表:"
        docker node ls | sed 's/^/   /'
    else
        echo "   角色: Worker"
    fi
else
    log_error "Swarm 未激活"
fi
echo ""

if docker network ls | grep -q infra-network; then
    log_success "infra-network 网络已同步"
    docker network ls | grep infra-network | sed 's/^/   /'
else
    log_error "infra-network 网络不存在"
fi
echo ""

# 3. 测试 nsqlookupd HTTP 接口
log_step "3. 测试 nsqlookupd HTTP 接口"
echo ""

NSQLOOKUPD_HTTP="http://localhost:4161"

if command -v curl >/dev/null 2>&1; then
    log_info "测试 ${NSQLOOKUPD_HTTP}/ping"
    if curl -s "${NSQLOOKUPD_HTTP}/ping" | grep -q "OK"; then
        log_success "nsqlookupd HTTP 接口正常"
    else
        log_error "nsqlookupd HTTP 接口异常"
    fi
    
    echo ""
    log_info "获取注册的 nsqd 节点列表:"
    if curl -s "${NSQLOOKUPD_HTTP}/nodes" 2>/dev/null | python3 -m json.tool 2>/dev/null; then
        :
    else
        curl -s "${NSQLOOKUPD_HTTP}/nodes"
    fi
else
    log_warn "curl 未安装，跳过 HTTP 测试"
fi
echo ""

# 4. 测试 nsqd HTTP 接口
log_step "4. 测试 nsqd HTTP 接口"
echo ""

NSQD_HTTP="http://localhost:4151"

if command -v curl >/dev/null 2>&1; then
    log_info "测试 ${NSQD_HTTP}/ping"
    if curl -s "${NSQD_HTTP}/ping" | grep -q "OK"; then
        log_success "nsqd HTTP 接口正常"
    else
        log_error "nsqd HTTP 接口异常"
    fi
    
    echo ""
    log_info "获取 nsqd 统计信息:"
    if curl -s "${NSQD_HTTP}/stats?format=json" 2>/dev/null | python3 -m json.tool 2>/dev/null | head -30; then
        echo "   ..."
    else
        curl -s "${NSQD_HTTP}/stats"
    fi
fi
echo ""

# 5. 测试容器间网络连通性
log_step "5. 测试容器间网络连通性"
echo ""

if docker ps | grep -q nsqd; then
    log_info "从 nsqd 容器 ping nsqlookupd"
    if docker exec nsqd wget --spider -q http://nsqlookupd:4161/ping 2>/dev/null; then
        log_success "nsqd → nsqlookupd 连通正常"
    else
        log_error "nsqd → nsqlookupd 连通失败"
    fi
    
    log_info "从 nsqadmin 容器访问 nsqlookupd"
    if docker exec nsqadmin wget --spider -q http://nsqlookupd:4161/ping 2>/dev/null; then
        log_success "nsqadmin → nsqlookupd 连通正常"
    else
        log_error "nsqadmin → nsqlookupd 连通失败"
    fi
fi
echo ""

# 6. 网络详情
log_step "6. 网络详细信息"
echo ""

log_info "infra-network 中的容器:"
docker network inspect infra-network 2>/dev/null | \
    grep -A 5 '"Containers"' | \
    grep '"Name"' | \
    sed 's/^/   /'
echo ""

log_info "infra-network Peers (Swarm 节点):"
docker network inspect infra-network 2>/dev/null | \
    grep -A 3 '"Peers"' | \
    sed 's/^/   /'
echo ""

# 7. 跨主机测试建议
log_step "7. 跨主机测试建议"
echo ""

log_info "在对端服务器上执行此脚本以验证双向连通性"
log_info "测试步骤:"
echo "   1. 在 ServerA 上执行: ./test-nsq-cluster.sh"
echo "   2. 在 ServerB 上执行: ./test-nsq-cluster.sh"
echo "   3. 对比两端的 'nsqlookupd 注册节点' 信息"
echo "   4. 对比两端的 'infra-network Peers' 信息"
echo ""

# 8. 功能测试
log_step "8. NSQ 功能测试 (可选)"
echo ""

log_info "创建测试主题和消息:"
echo "   # 发布消息"
echo "   curl -d 'hello world' 'http://localhost:4151/pub?topic=test'"
echo ""
echo "   # 创建 channel"
echo "   curl -X POST 'http://localhost:4151/channel/create?topic=test&channel=test_channel'"
echo ""
echo "   # 查看主题列表"
echo "   curl -s 'http://localhost:4161/topics' | python3 -m json.tool"
echo ""

log_success "测试完成！"
