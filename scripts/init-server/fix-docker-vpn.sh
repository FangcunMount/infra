#!/bin/bash

# Docker VPN 网络连接问题诊断和修复脚本

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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

log_step() {
    echo -e "\n${CYAN}[STEP]${NC} $1"
    echo "========================================"
}

echo "========================================"
echo "🔍 Docker VPN 网络问题诊断与修复"
echo "========================================"

# 检查是否为 root 用户
if [[ "${EUID}" -ne 0 ]]; then
    log_error "此脚本必须以 root 用户身份运行"
    exit 1
fi

log_step "1. 检查 VPN 服务状态"

# 检查 Mihomo VPN 服务
if systemctl is-active --quiet mihomo 2>/dev/null; then
    log_success "✅ Mihomo VPN 服务运行正常"
    
    # 检查代理端口
    if nc -z 127.0.0.1 7890 >/dev/null 2>&1; then
        log_success "✅ HTTP 代理端口 7890 可用"
    else
        log_error "❌ HTTP 代理端口 7890 不可用"
        log_info "检查 Mihomo 配置和端口绑定"
    fi
    
    if nc -z 127.0.0.1 7891 >/dev/null 2>&1; then
        log_success "✅ SOCKS5 代理端口 7891 可用"
    else
        log_warn "⚠️  SOCKS5 代理端口 7891 不可用"
    fi
else
    log_error "❌ Mihomo VPN 服务未运行"
    log_info "请先启动 VPN 服务: systemctl start mihomo"
    exit 1
fi

# 测试代理连接
log_info "测试代理连接..."
if curl -s --connect-timeout 10 --max-time 20 --proxy http://127.0.0.1:7890 https://www.google.com >/dev/null 2>&1; then
    log_success "✅ VPN 代理连接正常"
else
    log_error "❌ VPN 代理连接失败"
    log_info "请检查 VPN 配置和网络连接"
fi

log_step "2. 检查 Docker daemon 配置"

# 检查 Docker daemon 配置文件
if [[ -f /etc/docker/daemon.json ]]; then
    log_success "✅ Docker daemon 配置文件存在"
    
    # 显示当前配置
    log_info "当前 Docker daemon 配置:"
    cat /etc/docker/daemon.json | jq . 2>/dev/null || cat /etc/docker/daemon.json
    
    # 检查是否包含代理配置
    if grep -q "proxies" /etc/docker/daemon.json 2>/dev/null; then
        log_success "✅ Docker daemon 包含代理配置"
    else
        log_warn "⚠️  Docker daemon 未配置代理"
    fi
else
    log_error "❌ Docker daemon 配置文件不存在"
fi

log_step "3. 检查 Docker systemd 代理配置"

# 检查 systemd 代理配置
if [[ -f /etc/systemd/system/docker.service.d/proxy.conf ]]; then
    log_success "✅ Docker systemd 代理配置存在"
    log_info "systemd 代理配置:"
    cat /etc/systemd/system/docker.service.d/proxy.conf
else
    log_warn "⚠️  Docker systemd 代理配置不存在"
fi

log_step "4. 测试网络连接"

# 获取直连 IP
log_info "获取直连网络 IP..."
direct_ip=$(timeout 15 docker run --rm --env HTTP_PROXY= --env HTTPS_PROXY= --env http_proxy= --env https_proxy= alpine/curl:latest curl -s --connect-timeout 10 http://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4 || echo "failed")

if [[ "$direct_ip" != "failed" ]]; then
    log_success "✅ 直连 IP: $direct_ip"
else
    log_error "❌ 无法获取直连 IP"
fi

# 获取 VPN IP
log_info "获取 VPN 网络 IP..."
vpn_ip=$(timeout 30 docker run --rm alpine/curl:latest curl -s --connect-timeout 10 http://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4 || echo "failed")

if [[ "$vpn_ip" != "failed" ]]; then
    log_info "VPN 网络 IP: $vpn_ip"
    
    # 比较 IP 地址
    if [[ "$direct_ip" != "$vpn_ip" && "$direct_ip" != "failed" ]]; then
        log_success "✅ IP 地址不同，Docker 容器正在使用 VPN"
        echo "  直连 IP: $direct_ip"
        echo "  VPN IP: $vpn_ip"
    else
        log_error "❌ IP 地址相同或检测失败，Docker 容器未使用 VPN"
        echo "  直连 IP: $direct_ip"
        echo "  VPN IP: $vpn_ip"
    fi
else
    log_error "❌ 无法通过 VPN 获取 IP"
fi

log_step "5. 创建正确的 Docker VPN 配置"

# 备份现有配置
if [[ -f /etc/docker/daemon.json ]]; then
    cp /etc/docker/daemon.json /etc/docker/daemon.json.backup.$(date +%Y%m%d_%H%M%S)
    log_info "已备份现有配置"
fi

# 获取 Docker 网桥网关 IP
log_info "获取 Docker 网桥网关 IP..."
DOCKER_GATEWAY=$(docker network inspect bridge 2>/dev/null | grep '"Gateway"' | head -1 | sed 's/.*"Gateway": "\([^"]*\)".*/\1/' || echo "172.17.0.1")
log_info "Docker 网桥网关: $DOCKER_GATEWAY"

# 创建新的配置文件
log_info "创建优化的 Docker daemon 配置..."
cat > /etc/docker/daemon.json << EOF
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2",
    "exec-opts": ["native.cgroupdriver=systemd"],
    "live-restore": true,
    "userland-proxy": false,
    "experimental": false,
    "ipv6": false,
    "icc": true,
    "default-ulimits": {
        "nofile": {
            "Name": "nofile",
            "Hard": 64000,
            "Soft": 64000
        }
    },
    "registry-mirrors": [
        "https://docker.m.daocloud.io",
        "https://dockerproxy.com",
        "https://docker.mirrors.ustc.edu.cn",
        "https://docker.nju.edu.cn"
    ],
    "dns": ["8.8.8.8", "1.1.1.1"]
}
EOF

log_success "✅ Docker daemon 配置已更新"

# 创建或更新 systemd 代理配置
log_info "配置 Docker systemd 代理..."
mkdir -p /etc/systemd/system/docker.service.d

cat > /etc/systemd/system/docker.service.d/proxy.conf << 'EOF'
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
Environment="NO_PROXY=localhost,127.0.0.0/8,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
EOF

log_success "✅ Docker systemd 代理配置已更新"

log_step "6. 重启 Docker 服务"

log_info "重新加载 systemd 配置..."
systemctl daemon-reload

log_info "重启 Docker 服务..."
if systemctl restart docker; then
    log_success "✅ Docker 服务重启成功"
else
    log_error "❌ Docker 服务重启失败"
    exit 1
fi

# 等待服务完全启动
sleep 5

log_step "7. 配置容器 VPN 代理"

# 创建 Docker 代理配置脚本
log_info "创建 Docker VPN 代理脚本..."
cat > /usr/local/bin/docker-vpn << EOF
#!/bin/bash
# Docker VPN 代理封装脚本

# 获取 Docker 网桥网关 IP
DOCKER_GATEWAY=\$(docker network inspect bridge 2>/dev/null | grep '"Gateway"' | head -1 | sed 's/.*"Gateway": "\([^"]*\)".*/\1/' || echo "172.17.0.1")

# 设置代理环境变量
export HTTP_PROXY="http://\${DOCKER_GATEWAY}:7890"
export HTTPS_PROXY="http://\${DOCKER_GATEWAY}:7890"
export http_proxy="http://\${DOCKER_GATEWAY}:7890"
export https_proxy="http://\${DOCKER_GATEWAY}:7890"
export NO_PROXY="localhost,127.0.0.1,\${DOCKER_GATEWAY}"

# 运行 Docker 命令
docker "\$@"
EOF

chmod +x /usr/local/bin/docker-vpn
log_success "✅ 创建 Docker VPN 代理脚本"

# 创建 Docker Compose VPN 脚本
cat > /usr/local/bin/docker-compose-vpn << EOF
#!/bin/bash
# Docker Compose VPN 代理封装脚本

# 获取 Docker 网桥网关 IP
DOCKER_GATEWAY=\$(docker network inspect bridge 2>/dev/null | grep '"Gateway"' | head -1 | sed 's/.*"Gateway": "\([^"]*\)".*/\1/' || echo "172.17.0.1")

# 设置代理环境变量
export HTTP_PROXY="http://\${DOCKER_GATEWAY}:7890"
export HTTPS_PROXY="http://\${DOCKER_GATEWAY}:7890"
export http_proxy="http://\${DOCKER_GATEWAY}:7890"
export https_proxy="http://\${DOCKER_GATEWAY}:7890"
export NO_PROXY="localhost,127.0.0.1,\${DOCKER_GATEWAY}"

# 运行 Docker Compose 命令
docker compose "\$@"
EOF

chmod +x /usr/local/bin/docker-compose-vpn
log_success "✅ 创建 Docker Compose VPN 代理脚本"

log_step "8. 验证修复结果"

# 重新测试网络连接
log_info "重新测试网络连接..."

# 获取直连 IP
direct_ip_new=$(timeout 15 docker run --rm --env HTTP_PROXY= --env HTTPS_PROXY= --env http_proxy= --env https_proxy= alpine/curl:latest curl -s --connect-timeout 10 http://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4 || echo "failed")

# 使用 VPN 代理测试
vpn_ip_new=$(timeout 30 docker run --rm --env HTTP_PROXY="http://${DOCKER_GATEWAY}:7890" --env HTTPS_PROXY="http://${DOCKER_GATEWAY}:7890" alpine/curl:latest curl -s --connect-timeout 10 http://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4 || echo "failed")

if [[ "$direct_ip_new" != "failed" && "$vpn_ip_new" != "failed" ]]; then
    log_info "直连 IP: $direct_ip_new"
    log_info "VPN IP: $vpn_ip_new"
    
    if [[ "$direct_ip_new" != "$vpn_ip_new" ]]; then
        log_success "🎉 修复成功！Docker 容器现在可以使用 VPN 网络"
        echo "  直连 IP: $direct_ip_new"
        echo "  VPN IP: $vpn_ip_new"
    else
        log_warn "⚠️  IP 仍然相同，VPN 代理可能未生效"
    fi
else
    log_error "❌ 网络测试失败"
    log_info "直连测试: $direct_ip_new"
    log_info "VPN 测试: $vpn_ip_new"
fi

# 测试 Google 访问
log_info "测试 Google 访问..."
if timeout 30 docker run --rm --env HTTP_PROXY="http://${DOCKER_GATEWAY}:7890" --env HTTPS_PROXY="http://${DOCKER_GATEWAY}:7890" alpine/curl:latest curl -s --connect-timeout 10 https://www.google.com >/dev/null 2>&1; then
    log_success "✅ 可以通过 VPN 访问 Google"
else
    log_warn "⚠️  无法通过 VPN 访问 Google"
fi

log_step "9. 创建测试脚本"

# 创建便捷的测试脚本
cat > /usr/local/bin/test-docker-vpn << EOF
#!/bin/bash
echo "🔍 Docker VPN 网络测试"
echo "========================"

# 获取 Docker 网桥网关 IP
DOCKER_GATEWAY=\$(docker network inspect bridge 2>/dev/null | grep '"Gateway"' | head -1 | sed 's/.*"Gateway": "\([^"]*\)".*/\1/' || echo "172.17.0.1")

echo -n "直连 IP: "
docker run --rm --env HTTP_PROXY= --env HTTPS_PROXY= --env http_proxy= --env https_proxy= alpine/curl:latest curl -s --connect-timeout 5 http://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4 || echo "获取失败"

echo -n "VPN IP:  "
docker run --rm --env HTTP_PROXY="http://\${DOCKER_GATEWAY}:7890" --env HTTPS_PROXY="http://\${DOCKER_GATEWAY}:7890" alpine/curl:latest curl -s --connect-timeout 5 http://httpbin.org/ip 2>/dev/null | grep -o '"origin":"[^"]*"' | cut -d'"' -f4 || echo "获取失败"

echo -n "Google 访问: "
if docker run --rm --env HTTP_PROXY="http://\${DOCKER_GATEWAY}:7890" --env HTTPS_PROXY="http://\${DOCKER_GATEWAY}:7890" alpine/curl:latest curl -s --connect-timeout 5 https://www.google.com >/dev/null 2>&1; then
    echo "✅ 成功"
else
    echo "❌ 失败"
fi

echo
echo "💡 VPN 代理使用方法:"
echo "  • 使用 VPN: docker-vpn run --rm alpine/curl curl http://httpbin.org/ip"
echo "  • 直接连接: docker run --rm alpine/curl curl http://httpbin.org/ip"
echo "  • VPN Compose: docker-compose-vpn up"
EOF

chmod +x /usr/local/bin/test-docker-vpn
log_success "✅ 创建测试脚本: test-docker-vpn"

echo
log_success "🎉 Docker VPN 配置修复完成！"
echo
log_info "💡 使用建议:"
echo "  • 快速测试: test-docker-vpn"
echo "  • 使用 VPN: docker-vpn run --rm alpine/curl curl http://httpbin.org/ip"
echo "  • 直接连接: docker run --rm alpine/curl curl http://httpbin.org/ip"
echo "  • VPN Compose: docker-compose-vpn up"
echo "  • 查看配置: cat /etc/docker/daemon.json"
echo "  • 重启服务: systemctl restart docker"

if [[ "$direct_ip_new" != "$vpn_ip_new" && "$direct_ip_new" != "failed" && "$vpn_ip_new" != "failed" ]]; then
    echo
    log_success "✅ 配置成功！Docker 容器现在可以通过 VPN 网络访问互联网。"
    echo
    log_info "🔧 使用方法:"
    echo "  • 强制使用 VPN: docker-vpn run [容器参数]"
    echo "  • 强制直连: docker run [容器参数] (清空代理环境变量)"
    echo "  • 测试网络: test-docker-vpn"
else
    echo
    log_warn "⚠️  如果仍有问题，请检查："
    echo "  1. VPN 服务状态: systemctl status mihomo"
    echo "  2. 代理端口: nc -z 127.0.0.1 7890"
    echo "  3. Docker 网桥: docker network inspect bridge"
    echo "  4. 手动代理测试: curl --proxy http://127.0.0.1:7890 https://www.google.com"
    echo "  5. 容器网络测试: docker run --rm --env HTTP_PROXY=http://172.18.0.1:7890 alpine/curl curl http://httpbin.org/ip"
fi