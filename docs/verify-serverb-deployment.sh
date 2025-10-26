#!/usr/bin/env bash
# ServerB NSQ 部署验证脚本

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
echo "ServerB NSQ 部署验证"
echo "========================================="
echo ""

# 1. 验证 Swarm 状态
log_info "1. 验证 Swarm 集群状态..."
if docker info | grep -q "Swarm: active"; then
    log_success "Swarm 已激活"
    echo "   NodeID: $(docker info | grep 'NodeID:' | awk '{print $2}')"
    echo "   Is Manager: $(docker info | grep 'Is Manager:' | awk '{print $3}')"
else
    log_error "Swarm 未激活"
    exit 1
fi
echo ""

# 2. 检查网络状态
log_info "2. 检查网络状态..."
echo "   当前网络列表:"
docker network ls
echo ""

if docker network ls | grep -q infra-network; then
    log_success "infra-network 已存在"
else
    log_warn "infra-network 未显示（正常，会在启动服务时自动同步）"
fi
echo ""

# 3. 验证在 Manager 节点上查看
log_info "3. 在 ServerA (Manager) 上执行以查看完整信息:"
echo "   ${BLUE}docker node ls${NC}"
echo "   ${BLUE}docker network ls | grep infra-network${NC}"
echo ""

# 4. 准备部署
log_info "4. 准备部署 NSQ..."
echo "   确认以下事项:"
echo "   - [ ] 配置文件已更新 (TOML 格式已修复)"
echo "   - [ ] 环境变量文件存在: /opt/infra/compose/env/prod/.env"
echo "   - [ ] 防火墙端口已开放: 4150-4151, 4160-4161"
echo ""

log_info "5. 执行部署命令:"
echo "   ${BLUE}cd /opt/infra${NC}"
echo "   ${BLUE}make install-nsq${NC}"
echo ""

log_info "6. 部署后验证:"
echo "   ${BLUE}docker ps | grep nsq${NC}"
echo "   ${BLUE}docker network ls | grep infra-network${NC}  # 应该能看到了"
echo "   ${BLUE}docker network inspect infra-network${NC}  # 查看网络详情"
echo ""

log_info "提示: overlay 网络在 worker 节点上是惰性加载的"
echo "   - 网络在服务启动时会自动同步到 worker 节点"
echo "   - 这是 Docker Swarm 的正常行为"
echo ""
