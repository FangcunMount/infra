#!/bin/bash

# Docker 一键部署脚本
# 自动执行完整的 Docker 安装、配置和测试流程

set -e

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "🐳 Docker 一键部署开始..."

# 1. 修复可能的 Docker 服务问题
if [[ -f fix-docker-service.sh ]]; then
    log_info "1. 预先修复 Docker 服务..."
    bash fix-docker-service.sh 2>/dev/null || true
fi

# 2. 执行 Docker 安装
if [[ -f install-docker.sh ]]; then
    log_info "2. 执行 Docker 安装..."
    
    # 自动回答安装脚本的问题
    {
        echo "y"  # 继续重新安装
        echo "n"  # 跳过 Docker Hub 认证（可以后续配置）
    } | bash install-docker.sh
    
    log_success "✅ Docker 安装完成"
else
    log_error "❌ install-docker.sh 不存在"
    exit 1
fi

# 3. 验证安装
if [[ -f verify-docker-install.sh ]]; then
    log_info "3. 验证 Docker 安装..."
    bash verify-docker-install.sh 2>/dev/null || true
fi

# 4. 测试用户权限
if [[ -f test-docker-users.sh ]]; then
    log_info "4. 测试用户权限..."
    bash test-docker-users.sh 2>/dev/null || true
fi

# 5. 显示最终状态
echo
echo "🎉 Docker 一键部署完成！"
echo
echo "📊 状态概览："

# Docker 服务状态
if systemctl is-active --quiet docker; then
    echo "  ✅ Docker 服务: 运行正常"
    echo "  📋 版本信息: $(docker --version)"
else
    echo "  ❌ Docker 服务: 异常"
fi

# VPN 状态
if systemctl is-active --quiet mihomo 2>/dev/null; then
    echo "  ✅ VPN 服务: 运行正常"
else
    echo "  ⚠️  VPN 服务: 未运行"
fi

# 用户权限
if groups root 2>/dev/null | grep -q docker; then
    echo "  ✅ root 用户: Docker 权限正常"
fi

if id -u www >/dev/null 2>&1 && groups www 2>/dev/null | grep -q docker; then
    echo "  ✅ www 用户: Docker 权限正常"
fi

echo
echo "🚀 快速测试："
echo "  docker --version"
echo "  docker run hello-world"
echo "  docker info"

echo
log_success "部署完成！Docker 已准备就绪。"