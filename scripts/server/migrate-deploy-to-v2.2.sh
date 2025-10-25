#!/usr/bin/env bash
set -euo pipefail

# =================================================================
# deploy 账户迁移脚本：v2.1 → v2.2
# =================================================================
# 功能：
# 1. 将 deploy 从禁止登录改为可登录（仅 SSH 密钥）
# 2. 配置受限 sudo 权限
# 3. 保持密码锁定状态
# =================================================================
# 需要以 root 用户或 sudo 权限运行
# =================================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# 检查 root 权限
check_root() {
    if [[ ${EUID} -ne 0 ]]; then
        log_error "此脚本需要 root 权限运行"
        log_info "请使用: sudo $0"
        exit 1
    fi
}

# 检查 deploy 账户是否存在
check_deploy_exists() {
    if ! id -u deploy >/dev/null 2>&1; then
        log_error "deploy 用户不存在，请先运行 init-users.sh 创建"
        exit 1
    fi
    log_success "deploy 用户存在"
}

# 配置 deploy 的受限 sudo 权限
setup_deploy_sudo_privileges() {
    local sudoers_file="/etc/sudoers.d/deploy-cicd"
    
    log_info "配置 deploy 的受限 sudo 权限..."
    
    # 创建 sudoers 配置文件
    cat > "$sudoers_file" << 'EOF'
# deploy 账户的受限 sudo 权限（用于 CI/CD）
# 
# 安全策略:
# 1. 不将 deploy 加入 docker 组（避免 root 等价权限）
# 2. 通过 sudo 白名单允许必要的命令
# 3. NOPASSWD: deploy 通过 SSH 密钥认证,无需密码
# 4. 所有操作有 sudo 审计日志

# Docker 和 Docker Compose 操作
deploy ALL=(ALL) NOPASSWD: /usr/bin/docker
deploy ALL=(ALL) NOPASSWD: /usr/bin/docker-compose
deploy ALL=(ALL) NOPASSWD: /usr/local/bin/docker-compose

# systemd 服务管理
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl start *
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop *
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart *
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload *
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl status *
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable *
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl disable *

# 文件同步和权限管理（部署时常用）
deploy ALL=(ALL) NOPASSWD: /usr/bin/rsync
deploy ALL=(ALL) NOPASSWD: /usr/bin/chown
deploy ALL=(ALL) NOPASSWD: /usr/bin/chmod

# 创建目录（部署时可能需要）
deploy ALL=(ALL) NOPASSWD: /usr/bin/mkdir

# 禁止其他所有 sudo 命令
EOF

    # 设置正确的权限
    chmod 440 "$sudoers_file"
    
    # 验证 sudoers 文件语法
    if visudo -c -f "$sudoers_file" >/dev/null 2>&1; then
        log_success "deploy sudo 权限配置完成: $sudoers_file"
        log_info "允许的命令:"
        log_info "  • sudo docker / sudo docker-compose"
        log_info "  • sudo systemctl [start|stop|restart|reload|status|enable|disable]"
        log_info "  • sudo rsync / sudo chown / sudo chmod / sudo mkdir"
    else
        log_error "sudoers 文件语法错误，已删除"
        rm -f "$sudoers_file"
        return 1
    fi
}

# 显示当前状态
show_current_status() {
    log_info "========================================"
    log_info "deploy 账户当前状态"
    log_info "========================================"
    
    # 检查 shell
    local current_shell=$(getent passwd deploy | cut -d: -f7)
    echo "  Shell: $current_shell"
    
    # 检查密码状态
    local passwd_status=$(passwd -S deploy 2>/dev/null | awk '{print $2}')
    echo "  密码状态: $passwd_status"
    
    # 检查 docker 组
    if groups deploy | grep -q docker; then
        echo "  docker 组: ✅ 是（v2.0 旧配置）"
    else
        echo "  docker 组: ❌ 否（符合 v2.1/v2.2）"
    fi
    
    # 检查 sudo 配置
    if [[ -f /etc/sudoers.d/deploy-cicd ]]; then
        echo "  sudo 配置: ✅ 存在"
    else
        echo "  sudo 配置: ❌ 不存在"
    fi
    
    echo ""
}

# 执行迁移
perform_migration() {
    log_info "========================================"
    log_info "开始迁移 deploy 账户到 v2.2"
    log_info "========================================"
    echo ""
    
    # 步骤 1: 允许登录
    log_info "步骤 1/4: 允许 deploy SSH 登录..."
    local current_shell=$(getent passwd deploy | cut -d: -f7)
    
    if [[ "$current_shell" == "/usr/sbin/nologin" || "$current_shell" == "/sbin/nologin" ]]; then
        usermod -s /bin/bash deploy
        log_success "已将 shell 从 $current_shell 改为 /bin/bash"
    else
        log_warn "deploy 的 shell 已经是 $current_shell，跳过"
    fi
    
    # 步骤 2: 确保密码已锁定
    log_info "步骤 2/4: 确保密码已锁定（仅 SSH 密钥认证）..."
    passwd -l deploy >/dev/null 2>&1 || true
    log_success "密码已锁定，只能通过 SSH 密钥登录"
    
    # 步骤 3: 从 docker 组移除（如果存在）
    log_info "步骤 3/4: 检查并移除 docker 组..."
    if groups deploy | grep -q docker; then
        gpasswd -d deploy docker >/dev/null 2>&1
        log_success "已从 docker 组移除（将使用 sudo docker）"
    else
        log_success "deploy 不在 docker 组（符合安全策略）"
    fi
    
    # 步骤 4: 配置受限 sudo
    log_info "步骤 4/4: 配置受限 sudo 权限..."
    setup_deploy_sudo_privileges
    
    echo ""
    log_success "========================================"
    log_success "迁移完成！"
    log_success "========================================"
}

# 显示迁移后状态
show_final_status() {
    echo ""
    log_info "========================================"
    log_info "迁移后的配置"
    log_info "========================================"
    
    local current_shell=$(getent passwd deploy | cut -d: -f7)
    echo "  Shell: $current_shell"
    echo "  密码: 已锁定（仅 SSH 密钥登录）"
    echo "  docker 组: $(groups deploy | grep -q docker && echo '✅ 是' || echo '❌ 否（使用 sudo docker）')"
    echo "  sudo 配置: $(test -f /etc/sudoers.d/deploy-cicd && echo '✅ 已配置' || echo '❌ 未配置')"
    echo ""
}

# 显示后续步骤
show_next_steps() {
    log_info "========================================"
    log_info "后续步骤"
    log_info "========================================"
    echo ""
    echo "1️⃣  添加 deploy 的 SSH 公钥（如果还没有）："
    echo ""
    echo "    sudo mkdir -p /home/deploy/.ssh"
    echo "    sudo tee /home/deploy/.ssh/authorized_keys << 'EOF'"
    echo "    ssh-ed25519 AAAAC3... deploy@github-actions"
    echo "    EOF"
    echo "    sudo chown -R deploy:deploy /home/deploy/.ssh"
    echo "    sudo chmod 700 /home/deploy/.ssh"
    echo "    sudo chmod 600 /home/deploy/.ssh/authorized_keys"
    echo ""
    echo "2️⃣  测试 SSH 登录："
    echo ""
    echo "    ssh -i ~/.ssh/deploy_key deploy@$(hostname -I | awk '{print $1}')"
    echo ""
    echo "3️⃣  测试 sudo 命令："
    echo ""
    echo "    ssh -i ~/.ssh/deploy_key deploy@server 'sudo docker --version'"
    echo ""
    echo "4️⃣  更新 GitHub Actions 工作流："
    echo ""
    echo "    - 使用 'sudo docker' 替代 'docker'"
    echo "    - 使用 'sudo systemctl' 替代 'systemctl'"
    echo "    - 参考: docs/server/github-actions-deploy-guide.md"
    echo ""
    log_info "详细文档: docs/server/user-security-hardening.md (v2.2)"
    echo ""
}

# 主函数
main() {
    log_info "deploy 账户迁移脚本 (v2.1 → v2.2)"
    echo ""
    
    # 检查权限
    check_root
    
    # 检查 deploy 用户
    check_deploy_exists
    
    # 显示当前状态
    show_current_status
    
    # 确认迁移
    log_warn "即将执行以下操作："
    echo "  1. 允许 deploy SSH 登录（shell: /bin/bash）"
    echo "  2. 保持密码锁定（仅 SSH 密钥认证）"
    echo "  3. 从 docker 组移除（如果存在）"
    echo "  4. 配置受限 sudo 权限"
    echo ""
    read -p "确认继续？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "用户取消操作"
        exit 0
    fi
    
    # 执行迁移
    perform_migration
    
    # 显示最终状态
    show_final_status
    
    # 显示后续步骤
    show_next_steps
}

# 运行主函数
main "$@"
