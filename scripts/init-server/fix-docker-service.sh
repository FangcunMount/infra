#!/bin/bash

# Docker 服务快速修复脚本
# 解决常见的 Docker 启动失败问题

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo "========================================"
echo "🔧 Docker 服务快速修复"
echo "========================================"

# 检查是否为 root 用户
if [[ "${EUID}" -ne 0 ]]; then
    log_error "此脚本必须以 root 用户身份运行"
    exit 1
fi

# 1. 停止 Docker 服务
log_info "步骤 1: 停止 Docker 服务..."
systemctl stop docker 2>/dev/null || true
systemctl stop docker.socket 2>/dev/null || true

# 杀死所有 Docker 进程
if pgrep dockerd >/dev/null 2>&1; then
    log_info "杀死残留的 dockerd 进程..."
    pkill dockerd || true
    sleep 2
fi

# 2. 备份并重置配置文件
log_info "步骤 2: 检查配置文件..."
if [[ -f /etc/docker/daemon.json ]]; then
    # 验证 JSON 语法
    if ! python3 -m json.tool /etc/docker/daemon.json >/dev/null 2>&1; then
        log_warn "发现配置文件 JSON 语法错误，进行修复..."
        cp /etc/docker/daemon.json "/etc/docker/daemon.json.backup.$(date +%Y%m%d_%H%M%S)"
        
        # 创建基本配置
        cat > /etc/docker/daemon.json << 'EOF'
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2"
}
EOF
        log_success "✅ 配置文件已修复"
    else
        log_success "✅ 配置文件语法正确"
    fi
else
    log_info "创建基本配置文件..."
    mkdir -p /etc/docker
    cat > /etc/docker/daemon.json << 'EOF'
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2"
}
EOF
fi

# 3. 检查并创建必要目录
log_info "步骤 3: 检查必要目录..."
if [[ ! -d /var/lib/docker ]]; then
    mkdir -p /var/lib/docker
    log_info "创建 Docker 数据目录"
fi

# 设置正确的权限
chown -R root:root /var/lib/docker 2>/dev/null || true
chmod 700 /var/lib/docker

# 4. 加载必要的内核模块
log_info "步骤 4: 加载内核模块..."
required_modules=("overlay" "br_netfilter")
for module in "${required_modules[@]}"; do
    if ! lsmod | grep -q "$module"; then
        log_info "加载内核模块: $module"
        modprobe "$module" 2>/dev/null || log_warn "无法加载模块 $module"
    fi
done

# 5. 重新加载 systemd 配置
log_info "步骤 5: 重新加载 systemd 配置..."
systemctl daemon-reload

# 6. 启动 containerd（如果需要）
if systemctl is-enabled containerd >/dev/null 2>&1; then
    log_info "启动 containerd 服务..."
    systemctl start containerd || log_warn "containerd 启动失败"
fi

# 7. 尝试启动 Docker 服务
log_info "步骤 6: 启动 Docker 服务..."
if systemctl start docker; then
    log_success "✅ Docker 服务启动成功"
    
    # 启用自动启动
    systemctl enable docker
    
    # 显示服务状态
    echo
    log_info "Docker 服务状态:"
    systemctl status docker --no-pager -l
    
    # 测试 Docker 功能
    echo
    log_info "测试 Docker 功能..."
    if docker version >/dev/null 2>&1; then
        log_success "✅ Docker 版本检查通过"
        docker --version
    else
        log_warn "⚠️  Docker 版本检查失败"
    fi
    
    if docker info >/dev/null 2>&1; then
        log_success "✅ Docker 信息获取成功"
    else
        log_warn "⚠️  Docker 信息获取失败"
    fi
    
    # 测试容器运行
    log_info "测试容器运行..."
    if timeout 30 docker run --rm hello-world >/dev/null 2>&1; then
        log_success "✅ hello-world 容器运行成功"
    else
        log_warn "⚠️  hello-world 容器运行失败，但服务已启动"
    fi
    
else
    log_error "❌ Docker 服务启动仍然失败"
    
    echo
    log_info "显示详细错误信息:"
    systemctl status docker --no-pager -l || true
    
    echo
    log_info "显示服务日志:"
    journalctl -xeu docker.service -n 20 --no-pager || true
    
    echo
    log_info "💡 进一步排查建议："
    echo "  1. 检查系统日志: dmesg | tail -20"
    echo "  2. 手动启动测试: dockerd --debug"
    echo "  3. 检查磁盘空间: df -h"
    echo "  4. 检查内存使用: free -h"
    echo "  5. 完全重置: systemctl stop docker && rm -rf /var/lib/docker && systemctl start docker"
    
    exit 1
fi

echo
echo "========================================"
log_success "🎉 Docker 服务修复完成！"
echo "========================================"

echo
log_info "📋 修复总结："
echo "  ✅ Docker 服务已启动"
echo "  ✅ 配置文件已验证"
echo "  ✅ 必要模块已加载"
echo "  ✅ 服务已启用自动启动"

echo
log_info "🚀 后续操作："
echo "  • 验证安装: docker version && docker info"
echo "  • 运行测试: docker run hello-world"
echo "  • 查看状态: systemctl status docker"
echo "  • 查看日志: journalctl -u docker.service"