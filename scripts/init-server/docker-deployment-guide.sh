#!/bin/bash

# Docker 完整部署执行指南
# 这是一个逐步执行指南，帮助您完成 Docker 的完整安装和配置

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 日志函数
log_step() {
    echo -e "\n${CYAN}[STEP]${NC} $1"
    echo "========================================"
}

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
echo "🐳 Docker 完整部署执行指南"
echo "========================================"
echo "此脚本将引导您完成 Docker 的完整安装和配置"
echo "包括 VPN 集成、镜像加速器、用户权限等功能"
echo

# 检查是否为 root 用户
if [[ "${EUID}" -ne 0 ]]; then
    log_error "请以 root 用户身份运行此脚本"
    echo "使用方法: sudo bash $0"
    exit 1
fi

# 检查必要文件
log_step "1. 检查必要文件"
required_files=(
    "install-docker.sh"
    "fix-docker-service.sh"
    "diagnose-docker-failure.sh"
    "test-docker-users.sh"
    "verify-docker-install.sh"
)

missing_files=()
for file in "${required_files[@]}"; do
    if [[ -f "$file" ]]; then
        log_success "✅ $file 存在"
    else
        log_warn "⚠️  $file 缺失"
        missing_files+=("$file")
    fi
done

if [[ ${#missing_files[@]} -gt 0 ]]; then
    log_warn "部分文件缺失，但可以继续执行主要安装流程"
fi

echo

# 步骤 2: 系统环境检查
log_step "2. 系统环境检查"

log_info "检查操作系统..."
if [[ -f /etc/os-release ]]; then
    source /etc/os-release
    log_success "操作系统: ${PRETTY_NAME:-${ID}} ${VERSION_ID:-}"
else
    log_error "无法识别操作系统"
    exit 1
fi

log_info "检查系统资源..."
# 检查磁盘空间
available_space=$(df / | awk 'NR==2 {print $4}')
if [[ $available_space -gt 2097152 ]]; then  # 2GB
    log_success "磁盘空间充足: $(($available_space / 1024 / 1024))GB 可用"
else
    log_warn "磁盘空间较少: $(($available_space / 1024))MB 可用"
fi

# 检查内存
total_mem=$(free -m | awk '/^Mem:/ {print $2}')
log_info "系统内存: ${total_mem}MB"

echo

# 步骤 3: VPN 服务检查
log_step "3. VPN 服务检查"
if systemctl is-active --quiet mihomo 2>/dev/null; then
    log_success "✅ Mihomo VPN 服务运行正常"
    
    # 测试代理端口
    if nc -z 127.0.0.1 7890 >/dev/null 2>&1; then
        log_success "✅ HTTP 代理端口 7890 可用"
    else
        log_warn "⚠️  HTTP 代理端口 7890 不可用"
    fi
    
    if nc -z 127.0.0.1 7891 >/dev/null 2>&1; then
        log_success "✅ SOCKS5 代理端口 7891 可用"
    else
        log_warn "⚠️  SOCKS5 代理端口 7891 不可用"
    fi
else
    log_warn "⚠️  Mihomo VPN 服务未运行"
    log_info "Docker 将以直连模式安装"
fi

echo

# 步骤 4: Docker 安装
log_step "4. 执行 Docker 安装"

if [[ -f "install-docker.sh" ]]; then
    log_info "开始执行 Docker 安装脚本..."
    log_warn "注意: 如果询问是否配置 Docker Hub 认证，建议选择 'y' 并输入您的凭据"
    
    read -p "是否现在开始安装 Docker？(y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "执行命令: bash install-docker.sh"
        echo "----------------------------------------"
        
        # 实际执行安装脚本
        if bash install-docker.sh; then
            log_success "✅ Docker 安装脚本执行成功"
        else
            log_error "❌ Docker 安装脚本执行失败"
            
            # 自动尝试修复
            log_info "尝试自动修复..."
            if [[ -f "fix-docker-service.sh" ]]; then
                bash fix-docker-service.sh
            fi
            
            # 重新检查
            if systemctl is-active --quiet docker; then
                log_success "✅ 修复后 Docker 服务正常"
            else
                log_error "❌ Docker 服务仍然异常，需要手动排查"
                if [[ -f "diagnose-docker-failure.sh" ]]; then
                    log_info "运行诊断脚本..."
                    bash diagnose-docker-failure.sh
                fi
                exit 1
            fi
        fi
    else
        log_info "跳过 Docker 安装"
    fi
else
    log_error "install-docker.sh 文件不存在"
    exit 1
fi

echo

# 步骤 5: 验证安装
log_step "5. 验证 Docker 安装"

if [[ -f "verify-docker-install.sh" ]]; then
    log_info "运行 Docker 安装验证..."
    bash verify-docker-install.sh || true
else
    log_info "手动验证 Docker 安装..."
    
    # 基本验证
    if docker --version >/dev/null 2>&1; then
        log_success "✅ Docker 版本: $(docker --version)"
    else
        log_error "❌ Docker 命令不可用"
    fi
    
    if docker info >/dev/null 2>&1; then
        log_success "✅ Docker 服务正常"
    else
        log_error "❌ Docker 服务异常"
    fi
    
    # 测试容器运行
    log_info "测试容器运行..."
    if timeout 30 docker run --rm hello-world >/dev/null 2>&1; then
        log_success "✅ hello-world 容器运行成功"
    else
        log_warn "⚠️  hello-world 容器运行失败"
    fi
fi

echo

# 步骤 6: 用户权限测试
log_step "6. 用户权限测试"

if [[ -f "test-docker-users.sh" ]]; then
    log_info "运行用户权限测试..."
    bash test-docker-users.sh || true
else
    log_info "手动测试用户权限..."
    
    # 测试 root 用户
    if groups root | grep -q docker; then
        log_success "✅ root 用户在 docker 组中"
    else
        log_error "❌ root 用户不在 docker 组中"
    fi
    
    # 测试 www 用户
    if id -u www >/dev/null 2>&1; then
        if groups www | grep -q docker; then
            log_success "✅ www 用户在 docker 组中"
        else
            log_error "❌ www 用户不在 docker 组中"
        fi
    else
        log_info "www 用户不存在"
    fi
fi

echo

# 步骤 7: 配置总结
log_step "7. 配置总结"

log_info "📊 安装结果总结:"
echo

# Docker 服务状态
if systemctl is-active --quiet docker; then
    log_success "✅ Docker 服务: 运行正常"
else
    log_error "❌ Docker 服务: 异常"
fi

# VPN 集成状态
if systemctl is-active --quiet mihomo 2>/dev/null && [[ -f /etc/docker/daemon.json ]] && grep -q "proxies" /etc/docker/daemon.json 2>/dev/null; then
    log_success "✅ VPN 集成: 已启用"
else
    log_info "ℹ️  VPN 集成: 未启用或不可用"
fi

# 镜像加速器
if [[ -f /etc/docker/daemon.json ]] && grep -q "registry-mirrors" /etc/docker/daemon.json 2>/dev/null; then
    log_success "✅ 镜像加速器: 已配置"
else
    log_warn "⚠️  镜像加速器: 未配置"
fi

# Docker Hub 认证
if docker info 2>/dev/null | grep -q "Username:" || docker system info --format '{{.RegistryConfig.IndexConfigs}}' 2>/dev/null | grep -q "docker.io"; then
    log_success "✅ Docker Hub: 已登录"
else
    log_info "ℹ️  Docker Hub: 未登录"
fi

echo

# 步骤 8: 使用建议
log_step "8. 使用建议"

echo "🚀 常用命令:"
echo "  • 查看 Docker 版本: docker --version"
echo "  • 查看系统信息: docker info"
echo "  • 运行测试容器: docker run hello-world"
echo "  • 查看容器列表: docker ps -a"
echo "  • 查看镜像列表: docker images"

echo
echo "🔧 管理命令:"
echo "  • 启动 Docker: systemctl start docker"
echo "  • 停止 Docker: systemctl stop docker"
echo "  • 重启 Docker: systemctl restart docker"
echo "  • 查看状态: systemctl status docker"
echo "  • 查看日志: journalctl -u docker.service"

echo
echo "👥 用户切换:"
echo "  • 切换到 www 用户: su - www"
echo "  • 以 www 用户运行: su - www -c 'docker ps'"

if systemctl is-active --quiet mihomo 2>/dev/null; then
    echo
    echo "🌐 VPN 相关:"
    echo "  • VPN 强制命令: docker-vpn run <image>"
    echo "  • VPN Compose: docker-compose-vpn up"
    echo "  • 测试 VPN 网络: docker run --rm alpine/curl curl https://www.google.com"
fi

echo
echo "🔐 Docker Hub:"
echo "  • 登录 Docker Hub: docker login"
echo "  • 退出登录: docker logout"
echo "  • 查看登录状态: docker info | grep Username"

echo
log_success "🎉 Docker 部署完成！"
echo "如有问题，请查看相关日志或运行诊断脚本"