#!/bin/bash

# Docker 配置验证脚本
# 快速检查 Docker 安装和配置状态

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
echo "🔍 Docker 配置验证"
echo "========================================"

# 检查 Docker 服务状态
log_info "检查 Docker 服务状态..."
if systemctl is-active --quiet docker; then
    log_success "✅ Docker 服务运行正常"
else
    log_error "❌ Docker 服务未运行"
    exit 1
fi

# 检查 Docker 版本
log_info "检查 Docker 版本..."
docker_version=$(docker --version 2>/dev/null || echo "获取失败")
log_info "Docker 版本: $docker_version"

# 检查 Docker daemon 配置
log_info "检查 Docker daemon 配置..."
if [[ -f /etc/docker/daemon.json ]]; then
    log_success "✅ Docker daemon 配置文件存在"
    echo "配置文件内容:"
    cat /etc/docker/daemon.json | jq . 2>/dev/null || cat /etc/docker/daemon.json
else
    log_warn "⚠️  Docker daemon 配置文件不存在"
fi

echo

# 检查 systemd 代理配置
log_info "检查 Docker systemd 代理配置..."
if [[ -f /etc/systemd/system/docker.service.d/proxy.conf ]]; then
    log_success "✅ Docker systemd 代理配置存在"
    echo "代理配置:"
    cat /etc/systemd/system/docker.service.d/proxy.conf
else
    log_warn "⚠️  Docker systemd 代理配置不存在"
fi

echo

# 检查 VPN 服务
log_info "检查 VPN 服务状态..."
if systemctl is-active --quiet mihomo 2>/dev/null; then
    log_success "✅ Mihomo VPN 服务运行正常"
    
    # 测试代理端口
    if nc -z 127.0.0.1 7890 >/dev/null 2>&1; then
        log_success "✅ HTTP 代理端口 7890 可用"
    else
        log_warn "⚠️  HTTP 代理端口 7890 不可用"
    fi
else
    log_warn "⚠️  Mihomo VPN 服务未运行"
fi

echo

# 检查用户权限
log_info "检查用户权限..."
for user in root www; do
    if id -u "$user" >/dev/null 2>&1; then
        if groups "$user" | grep -q docker; then
            log_success "✅ $user 用户在 docker 组中"
        else
            log_error "❌ $user 用户不在 docker 组中"
        fi
    else
        log_warn "⚠️  $user 用户不存在"
    fi
done

echo

# 测试 Docker 基本功能
log_info "测试 Docker 基本功能..."

# 测试 docker info
if docker info >/dev/null 2>&1; then
    log_success "✅ docker info 命令正常"
else
    log_error "❌ docker info 命令失败"
fi

# 测试 docker version
if docker version >/dev/null 2>&1; then
    log_success "✅ docker version 命令正常"
else
    log_error "❌ docker version 命令失败"
fi

echo

# 测试简单容器运行
log_info "测试容器运行..."
if timeout 30 docker run --rm hello-world >/dev/null 2>&1; then
    log_success "✅ hello-world 容器运行成功"
else
    log_warn "⚠️  hello-world 容器运行失败"
    log_info "尝试拉取镜像..."
    if timeout 60 docker pull hello-world >/dev/null 2>&1; then
        log_success "✅ hello-world 镜像拉取成功"
        if timeout 30 docker run --rm hello-world >/dev/null 2>&1; then
            log_success "✅ hello-world 容器运行成功"
        else
            log_error "❌ hello-world 容器运行仍然失败"
        fi
    else
        log_error "❌ hello-world 镜像拉取失败"
    fi
fi

echo

# 测试网络连接
log_info "测试容器网络连接..."

# 测试直连
log_info "测试直连网络..."
if timeout 15 docker run --rm --env HTTP_PROXY= --env HTTPS_PROXY= alpine/curl:latest curl -s --connect-timeout 10 http://httpbin.org/ip >/dev/null 2>&1; then
    direct_ip=$(timeout 15 docker run --rm --env HTTP_PROXY= --env HTTPS_PROXY= alpine/curl:latest curl -s --connect-timeout 10 http://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    log_success "✅ 直连网络正常，IP: $direct_ip"
else
    log_warn "⚠️  直连网络测试失败"
fi

# 测试 VPN 网络
if systemctl is-active --quiet mihomo 2>/dev/null; then
    log_info "测试 VPN 网络..."
    if timeout 30 docker run --rm alpine/curl:latest curl -s --connect-timeout 10 http://httpbin.org/ip >/dev/null 2>&1; then
        vpn_ip=$(timeout 15 docker run --rm alpine/curl:latest curl -s --connect-timeout 10 http://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
        log_success "✅ VPN 网络正常，IP: $vpn_ip"
        
        # 比较 IP
        if [[ "$direct_ip" != "$vpn_ip" && "$direct_ip" != "unknown" && "$vpn_ip" != "unknown" ]]; then
            log_success "✅ 容器正在使用 VPN 网络（IP 已变化）"
        else
            log_warn "⚠️  容器可能未使用 VPN 网络（IP 未变化）"
        fi
    else
        log_warn "⚠️  VPN 网络测试失败"
    fi
fi

echo

log_info "✅ 验证完成！"

echo
log_info "💡 如果发现问题："
echo "  • 重启 Docker 服务: systemctl restart docker"
echo "  • 重新登录用户以刷新权限"
echo "  • 检查防火墙设置"
echo "  • 查看 Docker 日志: journalctl -u docker.service"