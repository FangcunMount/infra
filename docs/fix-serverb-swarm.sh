#!/usr/bin/env bash
# ServerB Swarm 集群修复脚本
# 用于将 ServerB 从独立 Swarm 迁移到 ServerA 的 Swarm 集群

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

echo "========================================="
echo "ServerB Swarm 集群修复脚本"
echo "========================================="

# 步骤 1: 停止所有 NSQ 容器
log_info "步骤 1: 停止 NSQ 容器..."
docker stop nsqd nsqadmin nsqlookupd 2>/dev/null || log_warn "部分容器已停止"
docker rm nsqd nsqadmin nsqlookupd 2>/dev/null || log_warn "部分容器已删除"

log_info "验证容器已停止..."
if docker ps -a | grep -q nsq; then
    log_error "NSQ 容器仍在运行，请手动停止"
    docker ps -a | grep nsq
    exit 1
fi
log_success "NSQ 容器已全部停止"

# 步骤 2: 离开当前 Swarm
log_info "步骤 2: 离开当前独立的 Swarm 集群..."
if docker info 2>/dev/null | grep -q "Swarm: active"; then
    log_warn "检测到活跃的 Swarm，正在离开..."
    docker swarm leave --force || {
        log_error "离开 Swarm 失败"
        exit 1
    }
    log_success "已离开 Swarm"
else
    log_info "当前未加入任何 Swarm"
fi

# 步骤 3: 清理 overlay 网络
log_info "步骤 3: 清理旧的 overlay 网络..."
if docker network ls | grep -q infra-network; then
    log_warn "检测到 infra-network，尝试删除..."
    docker network rm infra-network 2>/dev/null && log_success "网络已删除" || log_warn "网络删除失败（可能已自动清理）"
else
    log_info "未发现 infra-network"
fi

# 步骤 4: 验证状态
log_info "步骤 4: 验证当前状态..."
echo ""
echo "=== Docker 信息 ==="
docker info | grep -E "Swarm:|Server Version:" || true
echo ""
echo "=== 网络列表 ==="
docker network ls
echo ""

log_success "ServerB 清理完成！"
echo ""
echo "========================================="
echo "下一步操作："
echo "========================================="
echo ""
echo "1. 在 ServerA (shujie001) 上获取 join token："
echo "   ${BLUE}docker swarm join-token worker${NC}"
echo ""
echo "2. 复制输出的完整命令，然后在 ServerB 上执行："
echo "   ${BLUE}docker swarm join --token SWMTKN-1-xxxxx <ServerA-IP>:2377${NC}"
echo ""
echo "3. 验证加入成功："
echo "   ${BLUE}docker info | grep Swarm${NC}"
echo "   ${BLUE}docker network ls | grep infra-network${NC}"
echo ""
echo "4. 重新部署 NSQ："
echo "   ${BLUE}cd /opt/infra && make install-nsq${NC}"
echo ""
