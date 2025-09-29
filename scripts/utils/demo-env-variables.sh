#!/usr/bin/env bash
set -euo pipefail

# ==========================================
# Docker 环境变量机制演示脚本
# 验证 .env 文件中的变量不会写入镜像
# ==========================================

readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $*"; }

echo "========================================"
echo "Docker 环境变量机制演示"
echo "========================================"

# 1. 检查 MySQL 官方镜像中的环境变量
log_step "1. 检查 MySQL 官方镜像的原始环境变量"
echo
log_info "拉取 MySQL 镜像..."
docker pull mysql:8.0 >/dev/null 2>&1

log_info "查看 MySQL 镜像的原始环境变量:"
docker run --rm mysql:8.0 env | grep -E "^MYSQL_|^PATH=" | head -5 || true
echo

# 2. 查看镜像历史，确认没有我们的密码
log_step "2. 检查镜像构建历史（确认没有我们的配置）"
echo
log_info "MySQL 镜像的构建历史中不包含用户配置:"
docker history mysql:8.0 | grep -i mysql | head -3 || true
echo

# 3. 模拟我们的环境变量注入
log_step "3. 模拟运行时环境变量注入"
echo
log_info "创建临时 .env 文件..."
cat > /tmp/demo.env << 'EOF'
MYSQL_ROOT_PASSWORD=demo_secret_password_123
MYSQL_DATABASE=demo_database
MYSQL_USER=demo_user
MYSQL_PASSWORD=demo_user_password_456
EOF

log_info "使用环境变量启动 MySQL 容器（后台运行）..."
docker run -d \
  --name mysql-demo \
  --env-file /tmp/demo.env \
  mysql:8.0 >/dev/null 2>&1

# 等待容器启动
log_info "等待容器启动..."
sleep 5

# 4. 检查运行中容器的环境变量
log_step "4. 检查运行中容器的环境变量"
echo
log_info "容器运行时的环境变量（包含我们注入的配置）:"
docker exec mysql-demo env | grep -E "^MYSQL_" | head -5 || true
echo

# 5. 验证镜像本身没有改变
log_step "5. 验证原始镜像没有改变"
echo
log_info "重新检查原始镜像的环境变量（依然纯净）:"
docker run --rm mysql:8.0 env | grep -E "^MYSQL_" | head -3 || true
echo

# 6. 对比展示
log_step "6. 对比展示"
echo
log_success "✅ 验证结果:"
echo "   • 原始镜像: 不包含用户配置，保持纯净"
echo "   • 运行容器: 包含注入的环境变量配置"  
echo "   • 配置隔离: 同一镜像可用于不同环境"
echo

log_warn "🔍 关键点:"
echo "   • .env 文件的变量在 'docker-compose up' 时被读取"
echo "   • 这些变量作为环境变量传递给容器"
echo "   • 镜像本身永远不会包含这些配置"
echo "   • 这样可以实现 '一次构建，到处部署'"
echo

# 7. 清理
log_step "7. 清理演示资源"
log_info "停止并删除演示容器..."
docker stop mysql-demo >/dev/null 2>&1 || true
docker rm mysql-demo >/dev/null 2>&1 || true
rm -f /tmp/demo.env

log_success "演示完成！"
echo
echo "========================================"
echo "结论: compose/env 目录下的环境变量"
echo "     ❌ 不会写入 Docker 镜像"  
echo "     ✅ 仅在容器运行时注入"
echo "========================================"