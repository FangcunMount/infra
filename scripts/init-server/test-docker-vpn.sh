#!/bin/bash

# Docker VPN 集成测试脚本
# 用于验证 Docker 是否正确配置了 VPN 网络环境

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
echo "🐳 Docker VPN 集成测试"
echo "========================================"

# 检查 Docker 是否安装
if ! command -v docker >/dev/null 2>&1; then
    log_error "Docker 未安装，请先运行 install-docker.sh 脚本"
    exit 1
fi

log_success "Docker 已安装: $(docker --version)"

# 检查 Docker 服务状态
if ! systemctl is-active --quiet docker; then
    log_error "Docker 服务未运行"
    exit 1
fi

log_success "Docker 服务运行正常"

# 检查 VPN 服务
if systemctl is-active --quiet mihomo 2>/dev/null; then
    log_success "Mihomo VPN 服务运行正常"
    VPN_AVAILABLE=true
else
    log_warn "Mihomo VPN 服务未运行"
    VPN_AVAILABLE=false
fi

# 检查 Docker daemon 配置
log_info "检查 Docker daemon 配置..."
if [[ -f /etc/docker/daemon.json ]]; then
    log_success "Docker daemon 配置文件存在"
    
    # 检查镜像加速器配置
    if grep -q "registry-mirrors" /etc/docker/daemon.json 2>/dev/null; then
        log_success "✅ Docker Hub 镜像加速器已配置"
        echo "镜像加速器:"
        grep -A 6 "registry-mirrors" /etc/docker/daemon.json | head -6
    else
        log_warn "Docker Hub 镜像加速器未配置"
    fi
    
    # 检查代理配置
    if grep -q "proxies" /etc/docker/daemon.json 2>/dev/null; then
        log_success "✅ Docker daemon 已配置代理设置"
        echo "代理配置预览:"
        grep -A 10 "proxies" /etc/docker/daemon.json | head -8
    else
        log_warn "Docker daemon 未配置代理设置"
    fi
else
    log_warn "Docker daemon 配置文件不存在"
fi

# 检查 systemd 代理配置
log_info "检查 Docker systemd 代理配置..."
if [[ -f /etc/systemd/system/docker.service.d/proxy.conf ]]; then
    log_success "✅ Docker systemd 代理配置存在"
    echo "代理环境变量:"
    cat /etc/systemd/system/docker.service.d/proxy.conf
else
    log_warn "Docker systemd 代理配置不存在"
fi

# 检查辅助脚本
log_info "检查 VPN 辅助脚本..."
if [[ -x /usr/local/bin/docker-vpn ]]; then
    log_success "✅ docker-vpn 辅助脚本可用"
else
    log_warn "docker-vpn 辅助脚本不可用"
fi

if [[ -x /usr/local/bin/docker-compose-vpn ]]; then
    log_success "✅ docker-compose-vpn 辅助脚本可用"
else
    log_warn "docker-compose-vpn 辅助脚本不可用"
fi

echo
echo "========================================"
echo "🌐 网络连接测试"
echo "========================================"

# 测试直连网络
log_info "测试直连网络 (不使用代理)..."
if timeout 15 docker run --rm --env http_proxy= --env https_proxy= alpine/curl:latest curl -s --connect-timeout 10 http://httpbin.org/ip >/dev/null 2>&1; then
    log_success "✅ 直连网络测试成功"
    
    # 获取直连 IP
    direct_ip=$(timeout 15 docker run --rm --env http_proxy= --env https_proxy= alpine/curl:latest curl -s --connect-timeout 10 http://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    echo "  直连出口 IP: $direct_ip"
else
    log_warn "直连网络测试失败"
fi

# 测试 VPN 网络
if [[ "$VPN_AVAILABLE" == true ]]; then
    log_info "测试 VPN 网络连接..."
    
    # 测试通过 VPN 访问 Google
    if timeout 30 docker run --rm alpine/curl:latest curl -s --connect-timeout 10 https://www.google.com >/dev/null 2>&1; then
        log_success "✅ VPN 网络连接测试成功 (Google 可访问)"
    else
        log_warn "VPN 网络连接测试失败 (Google 不可访问)"
    fi
    
    # 获取 VPN IP
    log_info "获取 VPN 出口 IP..."
    vpn_ip=$(timeout 15 docker run --rm alpine/curl:latest curl -s --connect-timeout 10 http://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    if [[ "$vpn_ip" != "unknown" ]]; then
        log_success "✅ VPN 出口 IP: $vpn_ip"
        
        # 比较 IP 地址
        if [[ "$direct_ip" != "$vpn_ip" && "$direct_ip" != "unknown" ]]; then
            log_success "✅ IP 地址已改变，Docker 容器正在使用 VPN 网络"
        else
            log_warn "⚠️  IP 地址未改变，可能未正确使用 VPN"
        fi
    else
        log_warn "无法获取 VPN 出口 IP"
    fi
else
    log_warn "VPN 服务未运行，跳过 VPN 网络测试"
fi

echo
echo "========================================"
echo "� Docker 镜像拉取测试"
echo "========================================"

# 测试镜像拉取速度
log_info "测试 Docker Hub 镜像拉取..."

# 删除测试镜像（如果存在）
docker rmi hello-world >/dev/null 2>&1 || true

# 测试镜像拉取
log_info "拉取测试镜像 hello-world..."
pull_start=$(date +%s)
if docker pull hello-world >/dev/null 2>&1; then
    pull_end=$(date +%s)
    pull_time=$((pull_end - pull_start))
    log_success "✅ 镜像拉取成功，耗时: ${pull_time}s"
    
    # 显示使用的镜像源信息
    log_info "检查镜像来源信息..."
    if docker image inspect hello-world --format '{{.RepoTags}}' >/dev/null 2>&1; then
        log_success "✅ 镜像验证通过"
    fi
else
    log_warn "⚠️  镜像拉取失败"
fi

# 测试镜像加速器效果
log_info "验证镜像加速器配置..."
if grep -q "registry-mirrors" /etc/docker/daemon.json 2>/dev/null; then
    mirror_count=$(grep -A 10 "registry-mirrors" /etc/docker/daemon.json | grep -c "https://" || echo "0")
    log_success "✅ 已配置 $mirror_count 个镜像加速器"
else
    log_warn "⚠️  未检测到镜像加速器配置"
fi

echo
echo "========================================"
echo "�🔧 使用建议"
echo "========================================"

if [[ "$VPN_AVAILABLE" == true ]]; then
    echo "✅ VPN 网络环境已配置，建议使用："
    echo "  • 正常使用: docker run <image>"
    echo "  • 强制 VPN: docker-vpn run <image>"
    echo "  • Compose: docker-compose-vpn up"
    echo "  • 测试连接: docker run --rm alpine/curl curl https://www.google.com"
else
    echo "⚠️  VPN 网络环境未配置："
    echo "  1. 先安装并启动 Mihomo VPN 服务"
    echo "  2. 重新运行 install-docker.sh 脚本"
    echo "  3. 或手动配置 Docker 代理设置"
fi

echo
log_info "测试完成！"