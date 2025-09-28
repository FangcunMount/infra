#!/usr/bin/env bash
set -euo pipefail

# =================================================================
# Docker 统一安装配置脚本
# =================================================================
# 功能：
# 1. Docker Engine 安装
# 2. Docker Compose 插件安装
# 3. 用户权限配置和测试
# 4. VPN 网络集成配置
# 5. 完整性验证和测试
# =================================================================
# 需要以 root 用户或 sudo 权限运行
# =================================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
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
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_step() {
    echo -e "${PURPLE}[STEP]${NC} $1"
}

log_test() {
    echo -e "${CYAN}[TEST]${NC} $1"
}

# =================================================================
# 错误处理和权限检查
# =================================================================

# 错误处理函数
handle_error() {
    local line_number=$1
    log_error "脚本在第 $line_number 行执行失败"
    log_info "Docker 安装过程中出现错误，请检查网络连接和系统状态"
    exit 1
}

# 设置错误陷阱
trap 'handle_error $LINENO' ERR

# 检查 root 权限
check_root_privileges() {
    if [[ "${EUID}" -ne 0 ]]; then
        log_error "此脚本必须以 root 用户身份运行"
        echo "使用方法: sudo $0"
        exit 1
    fi
}

# =================================================================
# 系统检测和环境准备
# =================================================================

# 检测操作系统
detect_os() {
    log_info "检测操作系统..."
    
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        OS_ID="$ID"
        OS_VERSION="$VERSION_ID"
        OS_CODENAME="${VERSION_CODENAME:-}"
        
        case "$OS_ID" in
            ubuntu|debian)
                log_success "检测到支持的操作系统: $PRETTY_NAME"
                ;;
            *)
                log_error "不支持的操作系统: $PRETTY_NAME"
                log_info "此脚本仅支持 Ubuntu 和 Debian 系统"
                exit 1
                ;;
        esac
    else
        log_error "无法识别操作系统"
        exit 1
    fi
}

# 系统要求检查
check_system_requirements() {
    log_step "检查系统要求..."
    
    # 检查架构
    local arch=$(uname -m)
    case "$arch" in
        x86_64|amd64)
            ARCH="amd64"
            log_success "架构: $arch (支持)"
            ;;
        aarch64|arm64)
            ARCH="arm64"
            log_success "架构: $arch (支持)"
            ;;
        *)
            log_error "不支持的架构: $arch"
            exit 1
            ;;
    esac
    
    # 检查内核版本
    local kernel_version=$(uname -r | cut -d. -f1,2)
    local kernel_major=$(echo $kernel_version | cut -d. -f1)
    local kernel_minor=$(echo $kernel_version | cut -d. -f2)
    
    if [[ $kernel_major -lt 3 ]] || [[ $kernel_major -eq 3 && $kernel_minor -lt 10 ]]; then
        log_error "内核版本过低: $kernel_version (要求 >= 3.10)"
        exit 1
    else
        log_success "内核版本: $kernel_version (符合要求)"
    fi
    
    # 检查内存
    local total_mem=$(free -m | awk '/^Mem:/ {print $2}')
    if [[ $total_mem -lt 512 ]]; then
        log_warn "内存较少 (${total_mem}MB)，Docker 运行可能受影响，建议至少 512MB"
    elif [[ $total_mem -lt 1024 ]]; then
        log_warn "内存较少 (${total_mem}MB)，Docker 运行可能受影响，建议至少 1GB"
    else
        log_success "内存: ${total_mem}MB (充足)"
    fi
    
    # 检查磁盘空间
    local disk_space=$(df -BG / | awk 'NR==2 {print $4}' | sed 's/G//')
    if [[ $disk_space -lt 10 ]]; then
        log_warn "磁盘空间较少 (${disk_space}GB)，建议至少 10GB"
    else
        log_success "磁盘空间: ${disk_space}GB (充足)"
    fi
}

# =================================================================
# Docker 安装检查和准备
# =================================================================

# 检查是否已安装 Docker
check_existing_docker() {
    log_step "检查现有 Docker 安装..."
    
    if command -v docker >/dev/null 2>&1; then
        local docker_version=$(docker --version 2>/dev/null || echo "未知版本")
        log_warn "检测到已安装的 Docker: $docker_version"
        
        echo
        read -p "是否要继续安装/更新 Docker? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "跳过 Docker 安装"
            return 1
        fi
        return 0
    else
        log_info "未检测到 Docker，准备安装"
        return 0
    fi
}

# 卸载旧版本
remove_old_docker() {
    log_step "清理旧版本 Docker..."
    
    local old_packages=(
        "docker.io" "docker-doc" "docker-compose" "docker-compose-v2"
        "podman-docker" "containerd" "runc" "docker-ce-cli"
        "docker-ce" "docker-buildx-plugin" "docker-compose-plugin"
    )
    
    for package in "${old_packages[@]}"; do
        if dpkg -l | grep -q "^ii.*$package "; then
            log_info "移除旧包: $package"
            apt-get remove -y "$package" 2>/dev/null || true
        fi
    done
    
    # 清理残留配置
    apt-get autoremove -y 2>/dev/null || true
    apt-get autoclean 2>/dev/null || true
    
    log_success "旧版本清理完成"
}

# =================================================================
# Docker 安装过程
# =================================================================

# 安装依赖包
install_dependencies() {
    log_step "安装依赖包..."
    
    # 更新包列表
    log_info "更新包列表..."
    apt-get update -y
    
    # 安装依赖
    local dependencies=(
        "apt-transport-https" "ca-certificates" "curl"
        "gnupg" "lsb-release" "software-properties-common"
    )
    
    log_info "安装依赖包..."
    apt-get install -y "${dependencies[@]}"
    
    log_success "依赖包安装完成"
}

# 添加 Docker GPG 密钥和仓库
add_docker_repository() {
    log_step "配置 Docker 官方仓库..."
    
    # 创建 keyrings 目录
    mkdir -p /etc/apt/keyrings
    
    # 删除旧密钥文件（如果存在）
    rm -f /etc/apt/keyrings/docker.gpg /usr/share/keyrings/docker-archive-keyring.gpg
    
    # 添加 Docker GPG 密钥
    log_info "添加 Docker GPG 密钥..."
    curl -fsSL https://download.docker.com/linux/$OS_ID/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    
    # 添加 Docker 仓库
    log_info "添加 Docker 仓库..."
    echo "deb [arch=$ARCH signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$OS_ID $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
    
    # 更新包列表
    apt-get update -y
    
    log_success "Docker 仓库配置完成"
}

# 安装 Docker Engine
install_docker_engine() {
    log_step "安装 Docker Engine..."
    
    # 安装 Docker 包
    log_info "安装 Docker CE, CLI 和插件..."
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # 验证安装
    if command -v docker >/dev/null 2>&1; then
        local version=$(docker --version)
        log_success "Docker 安装成功: $version"
    else
        log_error "Docker 安装失败"
        exit 1
    fi
    
    # 启动并启用 Docker 服务
    log_info "配置 Docker 服务..."
    systemctl start docker
    systemctl enable docker
    
    if systemctl is-active --quiet docker; then
        log_success "Docker 服务已启动并设为开机自启"
    else
        log_error "Docker 服务启动失败"
        exit 1
    fi
}

# =================================================================
# 用户权限配置
# =================================================================

# 配置 Docker 用户权限
configure_docker_users() {
    log_step "配置 Docker 用户权限..."
    
    # 确保 docker 组存在
    if ! getent group docker >/dev/null 2>&1; then
        log_info "创建 docker 用户组..."
        groupadd docker
    else
        log_info "docker 用户组已存在"
    fi
    
    # 目标用户列表
    local users_to_add=()
    
    # 添加 www 用户（如果存在）
    if id -u www >/dev/null 2>&1; then
        users_to_add+=("www")
    fi
    
    # 添加当前登录用户（非 root）
    if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
        users_to_add+=("$SUDO_USER")
    fi
    
    # 添加用户到 docker 组
    for user in "${users_to_add[@]}"; do
        if ! groups "$user" 2>/dev/null | grep -q docker; then
            log_info "将用户 $user 添加到 docker 组..."
            usermod -aG docker "$user"
            log_success "用户 $user 已添加到 docker 组"
        else
            log_info "用户 $user 已在 docker 组中"
        fi
    done
    
    if [[ ${#users_to_add[@]} -gt 0 ]]; then
        log_warn "注意: 用户需要重新登录后才能使用 Docker 命令（无需 sudo）"
    fi
}

# =================================================================
# VPN 网络配置
# =================================================================

# 配置 VPN 代理模式
configure_vpn_proxy_mode() {
    log_step "配置 VPN 代理模式..."
    
    # 检查 VPN 服务是否运行
    local vpn_running=false
    if systemctl is-active --quiet mihomo 2>/dev/null; then
        log_info "检测到 Mihomo VPN 服务正在运行"
        vpn_running=true
    elif pgrep -f "mihomo" >/dev/null 2>&1; then
        log_info "检测到 Mihomo 进程正在运行"
        vpn_running=true
    else
        log_warn "未检测到 VPN 服务，跳过 VPN 配置"
        return 0
    fi
    
    if [[ "$vpn_running" == true ]]; then
        # 检查 VPN 代理端口
        local http_proxy_port=7890
        local socks_proxy_port=7891
        local api_port=9090
        
        if netstat -tlnp 2>/dev/null | grep -q ":$http_proxy_port "; then
            log_success "HTTP 代理端口 $http_proxy_port 可用"
        else
            log_warn "HTTP 代理端口 $http_proxy_port 不可用"
            return 0
        fi
        
        # 配置 Docker daemon 代理
        log_info "配置 Docker daemon 代理..."
        
        # 创建 Docker 配置目录
        mkdir -p /etc/docker
        
        # 创建或更新 daemon.json
        local daemon_config='
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.nju.edu.cn"
  ]
}'
        echo "$daemon_config" > /etc/docker/daemon.json
        log_success "Docker daemon.json 配置已创建"
        
        # 配置 Docker 服务代理（systemd）
        log_info "配置 Docker 服务代理..."
        mkdir -p /etc/systemd/system/docker.service.d
        
        cat > /etc/systemd/system/docker.service.d/http-proxy.conf << EOF
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:$http_proxy_port"
Environment="HTTPS_PROXY=http://127.0.0.1:$http_proxy_port"
Environment="NO_PROXY=localhost,127.0.0.1,::1"
EOF
        log_success "Docker 服务代理配置已创建"
        
        # 重新加载 systemd 配置并重启 Docker
        log_info "重启 Docker 服务以应用代理配置..."
        systemctl daemon-reload
        systemctl restart docker
        
        # 等待 Docker 服务启动
        sleep 3
        
        if systemctl is-active --quiet docker; then
            log_success "Docker 服务重启成功"
        else
            log_error "Docker 服务重启失败"
            return 1
        fi
        
        # 配置"漏网之鱼"代理组（如果 API 可用）
        if curl -s "http://127.0.0.1:$api_port/proxies" >/dev/null 2>&1; then
            log_info "配置漏网之鱼代理组..."
            
            # 获取可用的代理节点
            local available_proxies=$(curl -s "http://127.0.0.1:$api_port/proxies" | jq -r '.proxies | keys[]' 2>/dev/null | grep -v "漏网之鱼\|DIRECT\|REJECT" | head -1 || echo "")
            
            if [[ -n "$available_proxies" ]]; then
                # 切换漏网之鱼到第一个可用代理
                if curl -s -X PUT "http://127.0.0.1:$api_port/proxies/%E6%BC%8F%E7%BD%91%E4%B9%8B%E9%B1%BC" \
                     -H "Content-Type: application/json" \
                     -d "{\"name\":\"$available_proxies\"}" >/dev/null 2>&1; then
                    log_success "漏网之鱼已配置为使用代理: $available_proxies"
                else
                    log_warn "无法配置漏网之鱼代理组"
                fi
            else
                log_warn "未找到可用的代理节点"
            fi
        else
            log_warn "Mihomo API 不可用，跳过代理组配置"
        fi
        
        log_success "✅ Docker 容器现在将自动使用 VPN 网络！"
    fi
}

# =================================================================
# Docker Hub 认证配置
# =================================================================

# 配置 Docker Hub 认证
configure_docker_hub_auth() {
    log_step "配置 Docker Hub 认证（可选）..."
    
    log_info "📋 Docker Hub 认证说明："
    echo "  • Docker Hub 对匿名用户有拉取速率限制 (100次/6小时)"
    echo "  • 注册用户有更高的限制 (200次/6小时)"
    echo "  • 如果您有 Docker Hub 账户，建议进行登录认证"
    echo "  • 这是可选步骤，可以稍后手动配置"
    echo
    
    read -p "是否现在配置 Docker Hub 登录认证？(y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "请输入 Docker Hub 认证信息："
        echo "  提示: 输入密码时不会显示字符，这是正常的安全行为"
        echo
        
        read -p "Docker Hub 用户名: " docker_username
        if [[ -n "$docker_username" ]]; then
            read -s -p "Docker Hub 密码: " docker_password
            echo
            
            if [[ -n "$docker_password" ]]; then
                log_info "尝试登录 Docker Hub..."
                if echo "$docker_password" | docker login -u "$docker_username" --password-stdin >/dev/null 2>&1; then
                    log_success "Docker Hub 登录成功！"
                else
                    log_error "Docker Hub 登录失败，请检查用户名和密码"
                fi
            else
                log_warn "密码为空，跳过登录"
            fi
        else
            log_warn "用户名为空，跳过登录"
        fi
    else
        log_info "跳过 Docker Hub 认证配置"
    fi
}

# =================================================================
# 测试和验证功能
# =================================================================

# 测试用户 Docker 权限
test_user_docker_permissions() {
    log_step "测试用户 Docker 权限..."
    
    # 检查 Docker 服务状态
    if ! systemctl is-active --quiet docker; then
        log_error "Docker 服务未运行"
        return 1
    fi
    
    log_success "Docker 服务运行正常"
    
    # 测试用户列表
    local test_users=("root")
    
    # 添加 www 用户（如果存在）
    if id -u www >/dev/null 2>&1; then
        test_users+=("www")
    fi
    
    # 添加当前登录用户（非 root）
    if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
        test_users+=("$SUDO_USER")
    fi
    
    # 测试每个用户的权限
    for user in "${test_users[@]}"; do
        echo "----------------------------------------"
        log_test "测试用户: $user"
        
        # 检查用户是否存在
        if ! id -u "$user" >/dev/null 2>&1; then
            log_warn "用户 $user 不存在，跳过测试"
            continue
        fi
        
        # 检查用户是否在 docker 组中
        if groups "$user" 2>/dev/null | grep -q docker; then
            log_success "✅ 用户 $user 在 docker 组中"
        else
            log_error "❌ 用户 $user 不在 docker 组中"
            continue
        fi
        
        # 测试 Docker 命令执行
        log_test "测试 Docker 命令执行..."
        
        if [[ "$user" == "root" ]]; then
            # 作为 root 直接执行
            if docker version >/dev/null 2>&1; then
                log_success "✅ root 用户可以执行 docker version"
            else
                log_error "❌ root 用户无法执行 docker version"
            fi
            
            if docker ps >/dev/null 2>&1; then
                log_success "✅ root 用户可以执行 docker ps"
            else
                log_error "❌ root 用户无法执行 docker ps"
            fi
        else
            # 切换到其他用户执行（需要新的组权限生效）
            log_info "注意: 用户 $user 需要重新登录后权限才能生效"
            
            # 尝试使用 newgrp 来临时启用新组权限
            if su - "$user" -c "newgrp docker << EOF
docker version >/dev/null 2>&1
EOF" 2>/dev/null; then
                log_success "✅ $user 用户可以执行 docker version"
            else
                log_warn "⚠️  $user 用户需要重新登录后才能使用 docker 命令"
            fi
        fi
    done
}

# 测试 Docker 基本功能
test_docker_basic_functionality() {
    log_step "测试 Docker 基本功能..."
    
    # 测试 Docker 信息
    log_test "测试 docker info..."
    if docker info >/dev/null 2>&1; then
        log_success "✅ docker info 正常"
    else
        log_error "❌ docker info 失败"
        return 1
    fi
    
    # 测试拉取镜像（增加超时和重试机制）
    log_test "测试镜像拉取 (hello-world)..."
    local pull_success=false
    
    # 尝试拉取镜像，增加超时时间
    if timeout 60 docker pull hello-world >/dev/null 2>&1; then
        log_success "✅ 镜像拉取成功"
        pull_success=true
    else
        log_warn "⚠️  首次镜像拉取失败，检查代理配置..."
        
        # 显示Docker代理配置信息
        if [[ -f /etc/systemd/system/docker.service.d/http-proxy.conf ]]; then
            log_info "Docker代理配置已启用"
        else
            log_warn "Docker代理配置未找到"
        fi
        
        # 再次尝试拉取
        log_test "重试镜像拉取..."
        if timeout 60 docker pull hello-world >/dev/null 2>&1; then
            log_success "✅ 镜像拉取成功（重试）"
            pull_success=true
        else
            log_error "❌ 镜像拉取失败"
            log_info "提示: 可能的原因："
            log_info "  1. 网络连接问题"
            log_info "  2. VPN代理配置问题"
            log_info "  3. Docker Hub访问限制"
            log_info "解决方法: 运行 ./docker-vpn-manager.sh test 检查网络状态"
            return 1
        fi
    fi
    
    if [[ "$pull_success" == true ]]; then
        # 测试运行容器
        log_test "测试容器运行..."
        if docker run --rm hello-world >/dev/null 2>&1; then
            log_success "✅ 容器运行成功"
        else
            log_error "❌ 容器运行失败"
            return 1
        fi
        
        # 清理测试镜像
        log_test "清理测试镜像..."
        docker rmi hello-world >/dev/null 2>&1 || true
    fi
    
    log_success "Docker 基本功能测试完成"
}

# 测试 Docker Compose
test_docker_compose() {
    log_step "测试 Docker Compose..."
    
    if docker compose version >/dev/null 2>&1; then
        local compose_version=$(docker compose version)
        log_success "✅ Docker Compose 可用: $compose_version"
        return 0
    else
        log_error "❌ Docker Compose 不可用"
        return 1
    fi
}

# 测试 VPN 网络连接
test_vpn_network() {
    log_step "测试 Docker VPN 网络连接..."
    
    # 检查 VPN 服务状态
    if ! systemctl is-active --quiet mihomo 2>/dev/null && ! pgrep -f "mihomo" >/dev/null 2>&1; then
        log_warn "VPN 服务未运行，跳过 Docker VPN 网络测试"
        return 0
    fi
    
    # 检查 VPN 代理端口
    local proxy_port=7890
    if ! netstat -tlnp 2>/dev/null | grep -q ":$proxy_port "; then
        log_warn "VPN 代理端口 $proxy_port 不可用，跳过 VPN 测试"
        return 0
    fi
    
    # 获取 Docker 网关地址
    local docker_gateway=$(docker network inspect bridge --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}' 2>/dev/null || echo "172.17.0.1")
    log_info "Docker 网关地址: $docker_gateway"
    
    log_test "测试 Docker 容器 VPN 代理连接..."
    
    # 测试直接连接（不使用代理）
    log_test "1. 测试容器直接连接..."
    local direct_ip=$(timeout 15 docker run --rm alpine/curl -s --connect-timeout 10 http://ipinfo.io/ip 2>/dev/null || echo "failed")
    
    if [[ "$direct_ip" != "failed" ]]; then
        log_info "容器直接连接 IP: $direct_ip"
    else
        log_warn "容器直接连接失败"
    fi
    
    # 测试通过代理连接
    log_test "2. 测试容器通过 VPN 代理连接..."
    local proxy_ip=$(timeout 15 docker run --rm alpine/curl -s --connect-timeout 10 --proxy "http://$docker_gateway:$proxy_port" http://ipinfo.io/ip 2>/dev/null || echo "failed")
    
    if [[ "$proxy_ip" != "failed" ]]; then
        log_success "✅ 容器 VPN 代理连接成功"
        log_info "容器 VPN 代理 IP: $proxy_ip"
        
        # 比较 IP 地址
        if [[ "$proxy_ip" != "$direct_ip" ]]; then
            log_success "🎉 Docker 容器可以通过 VPN 代理访问网络！"
            log_info "代理使用示例:"
            log_info "  # 方法 1: 环境变量（小写）"
            log_info "  docker run --rm -e http_proxy=http://$docker_gateway:$proxy_port alpine/curl http://ipinfo.io/ip"
            log_info "  # 方法 2: 显式代理参数"
            log_info "  docker run --rm alpine/curl --proxy http://$docker_gateway:$proxy_port http://ipinfo.io/ip"
        else
            log_warn "⚠️  代理 IP 与直连 IP 相同，可能代理未生效"
        fi
    else
        log_error "❌ Docker 容器无法通过 VPN 代理访问网络"
        log_info "可能原因:"
        log_info "  1. VPN 代理服务异常"
        log_info "  2. Docker 网络配置问题"
        log_info "  3. 代理端口不可访问"
        
        # 测试代理端口连通性
        log_test "3. 测试代理端口连通性..."
        if timeout 10 docker run --rm alpine sh -c "nc -zv $docker_gateway $proxy_port" 2>/dev/null; then
            log_info "代理端口连通性正常"
        else
            log_error "无法连接到代理端口 $docker_gateway:$proxy_port"
        fi
    fi
}

# =================================================================
# 主程序流程
# =================================================================

# 显示安装信息
show_installation_info() {
    echo "========================================"
    echo "🐳 Docker 统一安装配置脚本"
    echo "========================================"
    echo "功能包括:"
    echo "  • Docker Engine 安装"
    echo "  • Docker Compose 插件"
    echo "  • 用户权限配置"
    echo "  • VPN 网络集成"
    echo "  • 完整性测试验证"
    echo "========================================"
    echo
}

# 显示安装完成信息
show_completion_info() {
    echo
    echo "========================================"
    echo "🎉 Docker 安装配置完成！"
    echo "========================================"
    echo "安装的组件:"
    
    # Docker 版本信息
    if command -v docker >/dev/null 2>&1; then
        echo "  • $(docker --version)"
    fi
    
    # Docker Compose 版本信息
    if docker compose version >/dev/null 2>&1; then
        echo "  • $(docker compose version)"
    fi
    
    echo
    echo "基本用法:"
    echo "  • 查看 Docker 信息: docker info"
    echo "  • 查看运行容器: docker ps"
    echo "  • 查看所有镜像: docker images"
    echo "  • 运行容器: docker run [选项] <镜像>"
    echo
    
    # 用户权限提醒
    if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
        echo "⚠️  重要提醒:"
        echo "  • 用户 $SUDO_USER 需要重新登录后才能无需 sudo 使用 docker 命令"
        echo "  • 或者运行: newgrp docker"
        echo
    fi
    
    # VPN 配置信息
    if systemctl is-active --quiet mihomo 2>/dev/null || pgrep -f "mihomo" >/dev/null 2>&1; then
        echo "🌐 VPN 网络集成:"
        echo "  • VPN 代理已配置"
        echo "  • Docker 容器将自动使用 VPN 网络"
        echo "  • 管理 VPN: ./docker-vpn-manager.sh status"
        echo
    fi
    
    echo "日志和故障排除:"
    echo "  • Docker 服务日志: journalctl -u docker.service"
    echo "  • 重启 Docker: systemctl restart docker"
    echo "========================================"
}

# 显示帮助信息
show_help() {
    echo "Docker 统一安装配置脚本"
    echo
    echo "用法:"
    echo "  $0 [选项]"
    echo
    echo "选项:"
    echo "  --configure-vpn-only    仅配置 VPN 代理功能"
    echo "  --test-vpn-only         仅测试 VPN 代理功能"
    echo "  --help, -h              显示帮助信息"
    echo
    echo "示例:"
    echo "  $0                      完整安装 Docker 和配置"
    echo "  $0 --configure-vpn-only 仅配置 Docker VPN 代理"
    echo "  $0 --test-vpn-only      仅测试 Docker VPN 功能"
}

# 仅配置 VPN 代理
configure_vpn_only() {
    echo "========================================"
    echo "🌐 Docker VPN 代理配置"
    echo "========================================"
    
    # 基础检查
    check_root_privileges
    
    # 检查 Docker 是否已安装
    if ! command -v docker >/dev/null 2>&1; then
        log_error "Docker 未安装，请先运行完整安装脚本"
        exit 1
    fi
    
    # 配置 VPN 代理
    configure_vpn_proxy_mode
    
    # 测试 VPN 功能
    test_vpn_network
    
    log_success "🎉 Docker VPN 代理配置完成！"
}

# 仅测试 VPN 功能
test_vpn_only() {
    echo "========================================"
    echo "🧪 Docker VPN 功能测试"
    echo "========================================"
    
    # 基础检查
    check_root_privileges
    
    # 检查 Docker 是否已安装
    if ! command -v docker >/dev/null 2>&1; then
        log_error "Docker 未安装，请先运行完整安装脚本"
        exit 1
    fi
    
    # 测试 VPN 功能
    test_vpn_network
}

# 主函数
main() {
    # 解析命令行参数
    case "${1:-}" in
        --configure-vpn-only)
            configure_vpn_only
            exit 0
            ;;
        --test-vpn-only)
            test_vpn_only
            exit 0
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        "")
            # 无参数，执行完整安装
            ;;
        *)
            log_error "未知选项: $1"
            echo
            show_help
            exit 1
            ;;
    esac
    
    show_installation_info
    
    # 1. 环境检查
    check_root_privileges
    detect_os
    check_system_requirements
    
    # 2. Docker 安装检查
    if ! check_existing_docker; then
        log_info "跳过 Docker 安装步骤，继续配置检查..."
    else
        # 3. Docker 安装过程
        remove_old_docker
        install_dependencies
        add_docker_repository
        install_docker_engine
    fi
    
    # 4. 用户权限配置
    configure_docker_users
    
    # 5. VPN 网络配置
    configure_vpn_proxy_mode
    
    # 6. Docker Hub 认证（可选）
    configure_docker_hub_auth
    
    # 7. 测试和验证
    test_user_docker_permissions
    test_docker_basic_functionality
    test_docker_compose
    test_vpn_network
    
    # 8. 完成提示
    show_completion_info
}

# 脚本入口点
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi