#!/bin/bash

# Docker 用户权限测试脚本
# 测试 root、www 和当前用户的 Docker 访问权限

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
echo "👥 Docker 用户权限测试"
echo "========================================"

# 检查 Docker 服务状态
if ! systemctl is-active --quiet docker; then
    log_error "Docker 服务未运行"
    exit 1
fi

log_success "Docker 服务运行正常"
echo

# 测试用户列表
TEST_USERS=("root" "www")

# 获取当前用户
current_user=$(whoami)
if [[ "$current_user" != "root" && "$current_user" != "www" ]]; then
    TEST_USERS+=("$current_user")
fi

# 测试每个用户的权限
for user in "${TEST_USERS[@]}"; do
    echo "========================================"
    log_info "测试用户: $user"
    echo "========================================"
    
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
    log_info "测试 Docker 命令执行..."
    
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
        
        if docker images >/dev/null 2>&1; then
            log_success "✅ root 用户可以执行 docker images"
        else
            log_error "❌ root 用户无法执行 docker images"
        fi
    else
        # 切换到其他用户执行
        if su - "$user" -c "docker version >/dev/null 2>&1"; then
            log_success "✅ $user 用户可以执行 docker version"
        else
            log_error "❌ $user 用户无法执行 docker version"
        fi
        
        if su - "$user" -c "docker ps >/dev/null 2>&1"; then
            log_success "✅ $user 用户可以执行 docker ps"
        else
            log_error "❌ $user 用户无法执行 docker ps"
        fi
        
        if su - "$user" -c "docker images >/dev/null 2>&1"; then
            log_success "✅ $user 用户可以执行 docker images"
        else
            log_error "❌ $user 用户无法执行 docker images"
        fi
    fi
    
    # 测试容器运行（轻量级测试）
    log_info "测试容器运行..."
    if [[ "$user" == "root" ]]; then
        if timeout 30 docker run --rm hello-world >/dev/null 2>&1; then
            log_success "✅ root 用户可以运行容器"
        else
            log_warn "⚠️  root 用户容器运行测试失败"
        fi
    else
        if timeout 30 su - "$user" -c "docker run --rm hello-world >/dev/null 2>&1"; then
            log_success "✅ $user 用户可以运行容器"
        else
            log_warn "⚠️  $user 用户容器运行测试失败"
        fi
    fi
    
    echo
done

echo "========================================"
log_info "📊 权限配置总结"
echo "========================================"

# 显示 Docker 组成员
log_info "Docker 组成员:"
getent group docker | cut -d: -f4 | tr ',' '\n' | while read -r member; do
    if [[ -n "$member" ]]; then
        echo "  ✅ $member"
    fi
done

echo

# 显示用户家目录的 Docker 配置
log_info "用户 Docker 配置目录:"
for user in "${TEST_USERS[@]}"; do
    if id -u "$user" >/dev/null 2>&1; then
        if [[ "$user" == "root" ]]; then
            docker_dir="/root/.docker"
        else
            # 动态获取用户家目录
            user_home=$(getent passwd "$user" | cut -d: -f6)
            docker_dir="$user_home/.docker"
        fi
        
        if [[ -d "$docker_dir" ]]; then
            log_success "✅ $user: $docker_dir (存在)"
        else
            log_warn "⚠️  $user: $docker_dir (不存在)"
        fi
    fi
done

echo

# 使用建议
log_info "💡 使用建议:"
echo "  • 切换到 www 用户: su - www"
echo "  • 以 www 用户运行容器: su - www -c 'docker run hello-world'"
echo "  • 查看 Docker 信息: docker system info"
echo "  • 管理 Docker 服务: systemctl status docker"

echo
log_info "🔧 故障排除:"
echo "  • 如果权限问题，请重新登录用户"
echo "  • 检查用户组: groups <username>"
echo "  • 重新添加到 docker 组: usermod -aG docker <username>"
echo "  • 重启 Docker 服务: systemctl restart docker"

echo
log_info "测试完成！"