#!/usr/bin/env bash
set -euo pipefail

# Docker 安装脚本
# 在 Debian/Ubuntu 系统上安装 Docker Engine 和 Compose 插件
# 需要以 root 用户或 sudo 权限运行

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
if [[ "${EUID}" -ne 0 ]]; then
    log_error "此脚本必须以 root 用户身份运行"
    echo "使用方法: sudo $0"
    exit 1
fi

# 检测操作系统
detect_os() {
    if [[ ! -f /etc/os-release ]]; then
        log_error "无法检测操作系统信息（缺少 /etc/os-release 文件）"
        exit 1
    fi
    
    source /etc/os-release
    
    log_info "检测到操作系统: ${PRETTY_NAME:-${ID}} ${VERSION_ID:-}"
    
    case "${ID}" in
        ubuntu|debian)
            OS_TYPE="debian"
            PKG_MANAGER="apt-get"
            log_success "支持的 Debian 系列操作系统，继续安装"
            ;;
        centos|rhel|rocky|almalinux)
            OS_TYPE="rhel"
            PKG_MANAGER="yum"
            if command -v dnf >/dev/null 2>&1; then
                PKG_MANAGER="dnf"
            fi
            log_success "支持的 RHEL 系列操作系统，继续安装"
            ;;
        fedora)
            OS_TYPE="rhel"
            PKG_MANAGER="dnf"
            log_success "支持的 Fedora 系统，继续安装"
            ;;
        *)
            log_error "不支持的发行版: ${PRETTY_NAME:-${ID}}"
            log_error "此脚本支持 Ubuntu/Debian/CentOS/RHEL/Rocky/AlmaLinux/Fedora 系统"
            exit 1
            ;;
    esac
}

# 检查系统资源
check_system_resources() {
    log_info "检查系统资源..."
    
    # 检查磁盘空间 (至少需要 2GB)
    local available_space
    available_space=$(df / | awk 'NR==2 {print $4}')
    local required_space=2097152  # 2GB in KB
    
    if [[ $available_space -lt $required_space ]]; then
        log_error "磁盘空间不足！当前可用: $(($available_space / 1024))MB，需要至少: 2GB"
        exit 1
    fi
    
    # 检查内存 (建议至少 1GB)
    local total_mem
    total_mem=$(free -k | awk '/^Mem:/ {print $2}')
    local recommended_mem=1048576  # 1GB in KB
    
    if [[ $total_mem -lt $recommended_mem ]]; then
        log_warn "内存较少 ($(($total_mem / 1024))MB)，Docker 运行可能受影响，建议至少 1GB"
        read -p "是否继续安装？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "用户取消安装"
            exit 0
        fi
    fi
    
    log_success "系统资源检查通过"
}

# 检查是否已安装 Docker
check_existing_docker() {
    if command -v docker >/dev/null 2>&1; then
        local docker_version=$(docker --version 2>/dev/null || echo "未知版本")
        log_warn "检测到已安装的 Docker: $docker_version"
        echo
        read -p "是否继续重新安装？这将更新到最新版本 (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "用户取消安装"
            exit 0
        fi
    fi
}

# 安装 Docker - Debian/Ubuntu 系列
install_docker_debian() {
    log_info "移除旧版本 Docker 包（如果存在）..."
    apt-get remove -y docker docker-engine docker.io containerd runc >/dev/null 2>&1 || true

    log_info "更新包列表..."
    apt-get update -y

    log_info "安装必要的依赖包..."
    apt-get install -y ca-certificates curl gnupg lsb-release

    # 创建密钥目录
    install -m 0755 -d /etc/apt/keyrings

    # 下载并安装 Docker GPG 密钥（带重试机制）
    if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
        log_info "下载 Docker GPG 密钥..."
        local retry_count=0
        local max_retries=3
        
        while [[ $retry_count -lt $max_retries ]]; do
            if curl -fsSL "https://download.docker.com/linux/${ID}/gpg" | gpg --dearmor -o /etc/apt/keyrings/docker.gpg; then
                log_success "Docker GPG 密钥下载成功"
                break
            else
                retry_count=$((retry_count + 1))
                if [[ $retry_count -lt $max_retries ]]; then
                    log_warn "密钥下载失败，重试 ($retry_count/$max_retries)..."
                    sleep 3
                else
                    log_error "Docker GPG 密钥下载失败，已重试 $max_retries 次"
                    exit 1
                fi
            fi
        done
    else
        log_info "Docker GPG 密钥已存在，跳过下载"
    fi

    chmod a+r /etc/apt/keyrings/docker.gpg

    log_info "配置 Docker APT 仓库..."
    cat <<REPO >/etc/apt/sources.list.d/docker.list
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${ID} \
${VERSION_CODENAME} stable
REPO

    log_success "Docker 仓库配置完成"

    log_info "更新包列表..."
    apt-get update -y

    log_info "安装 Docker 软件包..."
    log_info "正在安装: docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
    if ! apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; then
        log_error "Docker 软件包安装失败"
        exit 1
    fi

    log_success "Docker 软件包安装完成"
}

# 安装 Docker - CentOS/RHEL 系列  
install_docker_rhel() {
    log_info "移除旧版本 Docker 包（如果存在）..."
    $PKG_MANAGER remove -y docker docker-client docker-client-latest docker-common docker-latest docker-latest-logrotate docker-logrotate docker-engine >/dev/null 2>&1 || true

    log_info "安装必要的依赖包..."
    $PKG_MANAGER install -y yum-utils device-mapper-persistent-data lvm2

    log_info "配置 Docker 仓库..."
    if [[ "$PKG_MANAGER" == "dnf" ]]; then
        dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    else
        yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    fi

    log_success "Docker 仓库配置完成"

    log_info "安装 Docker 软件包..."
    log_info "正在安装: docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
    if ! $PKG_MANAGER install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; then
        log_error "Docker 软件包安装失败"
        exit 1
    fi

    log_success "Docker 软件包安装完成"
}

detect_os
check_system_resources
check_existing_docker

# 根据操作系统选择安装方法
case "$OS_TYPE" in
    debian)
        install_docker_debian
        ;;
    rhel)
        install_docker_rhel
        ;;
    *)
        log_error "未知的操作系统类型: $OS_TYPE"
        exit 1
        ;;
esac

# 配置 Docker daemon
configure_docker_daemon() {
    log_info "配置 Docker daemon..."
    
    local docker_config="/etc/docker/daemon.json"
    
    # 创建 Docker 配置目录
    mkdir -p /etc/docker
    
    # 创建优化的 daemon 配置
    cat > "$docker_config" << 'EOF'
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
    }
}
EOF
    
    log_success "Docker daemon 配置完成"
}

configure_docker_daemon

log_info "启用并启动 Docker 服务..."
systemctl enable --now docker

# 验证 Docker 服务状态
if systemctl is-active --quiet docker; then
    log_success "Docker 服务运行正常"
else
    log_error "Docker 服务启动失败"
    exit 1
fi

# 用户组管理
setup_user_permissions() {
    local default_user="${SUDO_USER:-${LOGNAME:-}}"
    local user_added=false
    
    if [[ -n "${default_user}" && "${default_user}" != "root" ]]; then
        if id -u "${default_user}" >/dev/null 2>&1; then
            log_info "将用户 '$default_user' 添加到 docker 组..."
            usermod -aG docker "${default_user}"
            user_added=true
            log_success "用户 '$default_user' 已添加到 docker 组"
        else
            log_warn "用户 '$default_user' 不存在，跳过 docker 组权限设置"
        fi
    else
        log_warn "未检测到普通用户，跳过 docker 组权限设置"
    fi
    
    return 0
}

# 验证安装
verify_installation() {
    log_info "验证 Docker 安装..."
    
    # 等待 Docker 服务完全启动
    local retry_count=0
    while [[ $retry_count -lt 10 ]]; do
        if systemctl is-active --quiet docker && docker info >/dev/null 2>&1; then
            break
        fi
        sleep 2
        retry_count=$((retry_count + 1))
    done
    
    # 检查 Docker 版本
    if docker_version=$(docker --version 2>/dev/null); then
        log_success "Docker 版本: $docker_version"
    else
        log_error "Docker 命令验证失败"
        return 1
    fi
    
    # 检查 Docker Compose 版本
    if compose_version=$(docker compose version 2>/dev/null); then
        log_success "Docker Compose 版本: $compose_version"
    else
        log_error "Docker Compose 验证失败"
        return 1
    fi
    
    # 检查 Docker 系统信息
    if docker_info=$(docker system info --format "{{.ServerVersion}}" 2>/dev/null); then
        log_success "Docker Server 版本: $docker_info"
    else
        log_warn "无法获取 Docker 系统信息"
    fi
    
    # 测试 Docker 运行
    log_info "运行 Docker 测试容器..."
    if docker run --rm hello-world >/dev/null 2>&1; then
        log_success "✅ Docker 运行测试通过"
    else
        log_warn "⚠️  Docker 运行测试失败，可能需要重新登录"
        log_info "如果是权限问题，请运行: sudo usermod -aG docker \$USER"
    fi
    
    # 检查 Docker 存储驱动
    if storage_driver=$(docker info --format "{{.Driver}}" 2>/dev/null); then
        log_success "存储驱动: $storage_driver"
    fi
    
    # 检查 Cgroup 驱动
    if cgroup_driver=$(docker info --format "{{.CgroupDriver}}" 2>/dev/null); then
        log_success "Cgroup 驱动: $cgroup_driver"
    fi
}

setup_user_permissions
verify_installation

echo
log_success "=========================================="
log_success "🐳 Docker 安装完成！"
log_success "=========================================="

echo
log_info "📦 已安装的组件："
echo "  ✅ Docker Engine"
echo "  ✅ Docker CLI"
echo "  ✅ Containerd"
echo "  ✅ Docker Buildx 插件"
echo "  ✅ Docker Compose 插件"

echo
log_info "⚙️  配置优化："
echo "  ✅ 日志轮转配置 (最大 10MB × 3 文件)"
echo "  ✅ 存储驱动优化 (overlay2)"
echo "  ✅ Systemd Cgroup 驱动"
echo "  ✅ 容器存活恢复功能"

echo
log_info "🔧 系统信息："
echo "  🖥️  操作系统: ${PRETTY_NAME:-${ID}} ${VERSION_ID:-}"
echo "  📦 包管理器: $PKG_MANAGER"
echo "  🏃 服务状态: $(systemctl is-active docker)"

echo
log_info "🚀 下一步操作："
echo "  1. 验证安装: docker version && docker compose version"

default_user="${SUDO_USER:-${LOGNAME:-}}"
if [[ -n "${default_user}" && "${default_user}" != "root" ]]; then
    echo "  2. 重新登录用户 '$default_user' 以使 docker 组权限生效"
    echo "     或者运行: su - $default_user"
fi

echo "  3. 运行测试: docker run hello-world"
echo "  4. 查看系统信息: docker system info"
echo "  5. 管理 Docker: systemctl start|stop|restart docker"

echo
log_info "📁 重要文件位置："
echo "  🔧 配置文件: /etc/docker/daemon.json"
echo "  📋 服务日志: journalctl -u docker.service"
echo "  📂 数据目录: /var/lib/docker/"

log_info "🎉 Docker 服务已启动并设置为开机自启"
exit 0
