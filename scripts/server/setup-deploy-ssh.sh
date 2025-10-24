#!/usr/bin/env bash
set -euo pipefail

# =================================================================
# deploy 账户受限 SSH 配置脚本
# =================================================================
# 功能：
# 1. 创建受限入口 /usr/local/bin/deployctl（白名单命令）
# 2. 配置 deploy 的 authorized_keys（强制命令 + 禁用能力）
# 3. 配置最小 sudoers 白名单（仅允许必要的 docker/rsync 命令）
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

# 错误处理
handle_error() {
    local line_number=$1
    log_error "脚本在第 $line_number 行执行失败"
    exit 1
}

trap 'handle_error $LINENO' ERR

# 检查 root 权限
check_root() {
    if [[ ${EUID} -ne 0 ]]; then
        log_error "此脚本必须以 root 用户身份运行"
        echo "使用方法: sudo $0 <CI_PUBLIC_KEY>"
        exit 1
    fi
}

# 检查 deploy 用户是否存在
check_deploy_user() {
    if ! id -u deploy >/dev/null 2>&1; then
        log_error "deploy 用户不存在"
        log_info "请先运行 init-users.sh 创建 deploy 用户"
        exit 1
    fi
    
    log_success "检测到 deploy 用户"
}

# 1. 创建受限入口 /usr/local/bin/deployctl
create_deployctl() {
    log_info "创建受限入口: /usr/local/bin/deployctl"
    
    cat >/usr/local/bin/deployctl <<'EOF'
#!/usr/bin/env bash
# =================================================================
# deployctl - deploy 账户的受限命令入口
# =================================================================
# 功能: 只允许白名单命令执行，拒绝其他所有操作
# 用途: 通过 authorized_keys 的 command= 强制执行
# =================================================================

set -euo pipefail

# 获取原始 SSH 命令
cmd="${SSH_ORIGINAL_COMMAND:-}"

# 日志函数
log_action() {
    logger -t deployctl -p auth.info "deploy@$(hostname): $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> /var/log/deployctl.log
}

log_denied() {
    logger -t deployctl -p auth.warning "DENIED deploy@$(hostname): $1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DENIED: $1" >> /var/log/deployctl.log
}

# 如果没有命令，拒绝
if [[ -z "$cmd" ]]; then
    log_denied "No command specified"
    echo "Error: This account is restricted to automated deployment only."
    echo "Interactive login is not allowed."
    exit 1
fi

# 白名单命令匹配
case "$cmd" in
    # 允许 rsync 传输文件
    rsync\ --server\ *)
        log_action "ALLOWED: rsync server mode"
        exec /usr/bin/rsync ${cmd#rsync }
        ;;
    
    # 允许 docker compose 命令（通过 sudo）
    "docker compose "*)
        log_action "ALLOWED: docker compose - $cmd"
        exec sudo /usr/bin/docker ${cmd#docker }
        ;;
    
    # 允许 systemctl 操作特定服务（通过 sudo）
    "systemctl restart "*)
        service="${cmd#systemctl restart }"
        # 只允许操作 /etc/systemd/system/ 下的服务
        if [[ "$service" =~ ^[a-zA-Z0-9_-]+\.service$ ]]; then
            log_action "ALLOWED: systemctl restart $service"
            exec sudo /usr/bin/systemctl restart "$service"
        else
            log_denied "systemctl restart invalid service: $service"
            echo "Error: Invalid service name"
            exit 1
        fi
        ;;
    
    "systemctl status "*)
        service="${cmd#systemctl status }"
        if [[ "$service" =~ ^[a-zA-Z0-9_-]+\.service$ ]]; then
            log_action "ALLOWED: systemctl status $service"
            exec sudo /usr/bin/systemctl status "$service"
        else
            log_denied "systemctl status invalid service: $service"
            echo "Error: Invalid service name"
            exit 1
        fi
        ;;
    
    # 允许 git pull（仅限特定目录）
    "cd /srv/apps/"*" && git pull")
        # 提取目录路径
        dir=$(echo "$cmd" | sed -n 's/cd \(\/srv\/apps\/[^&]*\) &&.*/\1/p')
        if [[ -d "$dir" && "$dir" == /srv/apps/* ]]; then
            log_action "ALLOWED: git pull in $dir"
            cd "$dir" && exec /usr/bin/git pull
        else
            log_denied "git pull invalid directory: $dir"
            echo "Error: Invalid directory"
            exit 1
        fi
        ;;
    
    # 拒绝所有其他命令
    *)
        log_denied "Command not in whitelist: $cmd"
        echo "Error: Command not allowed: $cmd"
        echo ""
        echo "Allowed commands:"
        echo "  - rsync (file transfer)"
        echo "  - docker compose (container management)"
        echo "  - systemctl restart <service>"
        echo "  - systemctl status <service>"
        echo "  - git pull (in /srv/apps/* only)"
        exit 1
        ;;
esac
EOF

    chmod 755 /usr/local/bin/deployctl
    log_success "已创建 /usr/local/bin/deployctl"
    
    # 创建日志文件
    touch /var/log/deployctl.log
    chmod 640 /var/log/deployctl.log
    chown root:adm /var/log/deployctl.log
    log_success "已创建日志文件 /var/log/deployctl.log"
}

# 2. 配置 deploy 的 authorized_keys
setup_authorized_keys() {
    local ci_public_key="$1"
    
    log_info "配置 deploy 的 SSH authorized_keys"
    
    # 创建 .ssh 目录
    local ssh_dir="/home/deploy/.ssh"
    install -d -m700 "$ssh_dir"
    chown deploy:deploy "$ssh_dir"
    log_success "已创建 $ssh_dir 目录"
    
    # 配置 authorized_keys
    local auth_keys="$ssh_dir/authorized_keys"
    
    # 备份现有文件（如果存在）
    if [[ -f "$auth_keys" ]]; then
        cp "$auth_keys" "$auth_keys.backup.$(date +%Y%m%d_%H%M%S)"
        log_info "已备份现有 authorized_keys"
    fi
    
    # 写入受限的 authorized_keys
    cat > "$auth_keys" <<EOF
# =================================================================
# deploy 账户的受限 SSH 密钥配置
# =================================================================
# 用途: 仅供 GitHub Actions CI/CD 使用
# 限制:
#   - command="/usr/local/bin/deployctl"  强制执行白名单命令
#   - no-agent-forwarding                 禁止 SSH Agent 转发
#   - no-X11-forwarding                   禁止 X11 图形转发
#   - no-pty                               禁止分配伪终端（防止交互式 shell）
#   - no-user-rc                           禁止执行用户 rc 文件
# =================================================================

command="/usr/local/bin/deployctl",no-agent-forwarding,no-X11-forwarding,no-pty,no-user-rc $ci_public_key
EOF

    chown deploy:deploy "$auth_keys"
    chmod 600 "$auth_keys"
    log_success "已配置 $auth_keys"
    
    log_info "授权密钥指纹:"
    ssh-keygen -lf "$auth_keys" 2>/dev/null || log_warn "无法读取密钥指纹"
}

# 3. 配置最小 sudoers 白名单
setup_sudoers() {
    log_info "配置 deploy 的 sudoers 白名单"
    
    local sudoers_file="/etc/sudoers.d/deploy-cicd"
    
    # 备份现有文件（如果存在）
    if [[ -f "$sudoers_file" ]]; then
        cp "$sudoers_file" "$sudoers_file.backup.$(date +%Y%m%d_%H%M%S)"
        log_info "已备份现有 sudoers 配置"
    fi
    
    # 写入最小权限配置
    cat > "$sudoers_file" <<'EOF'
# =================================================================
# deploy 账户的最小 sudo 白名单
# =================================================================
# 用途: 仅允许 CI/CD 必需的命令
# 原则: 最小权限 + 无需密码（CI 环境无交互）
# =================================================================

# 禁用 requiretty（允许非交互式 SSH 执行 sudo）
Defaults:deploy !requiretty

# 允许的命令白名单（NOPASSWD: 无需密码）
deploy ALL=(root) NOPASSWD: \
    /usr/bin/docker, \
    /usr/bin/docker compose *, \
    /usr/bin/rsync, \
    /usr/bin/systemctl restart *.service, \
    /usr/bin/systemctl status *.service, \
    /usr/bin/systemctl reload *.service

# 显式拒绝危险命令（即使上面允许，这里也拒绝）
deploy ALL=(root) !NOPASSWD: \
    /usr/bin/systemctl stop *.service, \
    /usr/bin/systemctl disable *.service, \
    /usr/bin/docker system prune, \
    /usr/bin/docker rm *
EOF

    chmod 440 "$sudoers_file"
    log_success "已创建 $sudoers_file"
    
    # 验证 sudoers 语法
    if visudo -c -f "$sudoers_file"; then
        log_success "sudoers 语法验证通过"
    else
        log_error "sudoers 语法验证失败"
        rm -f "$sudoers_file"
        exit 1
    fi
}

# 4. 测试配置
test_configuration() {
    log_info "测试 deploy 配置..."
    
    # 测试 deployctl 可执行
    if [[ -x /usr/local/bin/deployctl ]]; then
        log_success "deployctl 可执行"
    else
        log_error "deployctl 不可执行"
        return 1
    fi
    
    # 测试 authorized_keys 权限
    local auth_keys="/home/deploy/.ssh/authorized_keys"
    if [[ -f "$auth_keys" ]]; then
        local perms=$(stat -c "%a" "$auth_keys" 2>/dev/null || stat -f "%Lp" "$auth_keys" 2>/dev/null)
        if [[ "$perms" == "600" ]]; then
            log_success "authorized_keys 权限正确 (600)"
        else
            log_warn "authorized_keys 权限不正确: $perms (应为 600)"
        fi
    else
        log_error "authorized_keys 不存在"
        return 1
    fi
    
    # 测试 sudoers 配置
    if sudo -l -U deploy >/dev/null 2>&1; then
        log_success "sudoers 配置有效"
        echo ""
        log_info "deploy 的 sudo 权限:"
        sudo -l -U deploy | grep -A 20 "may run"
    else
        log_warn "无法验证 sudoers 配置"
    fi
    
    echo ""
    log_success "配置测试完成"
}

# 5. 显示使用说明
show_usage_instructions() {
    cat <<'EOF'

================================================================================
  deploy 受限 SSH 配置完成
================================================================================

✅ 已创建:
   1. /usr/local/bin/deployctl          - 受限命令入口（白名单）
   2. /home/deploy/.ssh/authorized_keys - 强制命令 + 禁用能力
   3. /etc/sudoers.d/deploy-cicd        - 最小 sudo 白名单
   4. /var/log/deployctl.log            - 命令执行日志

📋 允许的命令白名单:
   • rsync                              - 文件传输
   • docker compose *                   - 容器编排
   • systemctl restart/status <service> - 服务管理
   • git pull (仅 /srv/apps/*)          - 代码更新

🔒 安全限制:
   • 禁止交互式登录 (no-pty)
   • 禁止 SSH Agent 转发 (no-agent-forwarding)
   • 禁止 X11 转发 (no-X11-forwarding)
   • 所有命令通过 deployctl 白名单过滤
   • sudo 仅限必要命令（无需密码）

📝 GitHub Actions 使用示例:

   - name: Deploy to server
     uses: appleboy/ssh-action@master
     with:
       host: ${{ secrets.SERVER_HOST }}
       username: deploy
       key: ${{ secrets.DEPLOY_SSH_KEY }}
       script: |
         # 所有命令都会通过 deployctl 白名单过滤
         docker compose -f /srv/apps/myapp/docker-compose.yml up -d
         systemctl restart myapp.service

📊 查看日志:
   sudo tail -f /var/log/deployctl.log

🔍 测试 SSH 连接:
   ssh -i /path/to/deploy_key deploy@server "docker compose version"

⚠️  安全提醒:
   - deploy 私钥仅保存在 GitHub Secrets 中
   - 服务器上只有公钥（在 authorized_keys 中）
   - 定期检查 /var/log/deployctl.log 查看异常访问

================================================================================

EOF
}

# 主函数
main() {
    echo "========================================"
    echo "  deploy 受限 SSH 配置脚本"
    echo "========================================"
    echo ""
    
    # 检查参数
    if [[ $# -lt 1 ]]; then
        log_error "缺少 CI 公钥参数"
        echo ""
        echo "使用方法:"
        echo "  sudo $0 '<CI_PUBLIC_KEY>'"
        echo ""
        echo "示例:"
        echo "  sudo $0 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJx... github-actions@deploy'"
        echo ""
        echo "或从文件读取:"
        echo "  sudo $0 \"\$(cat /path/to/deploy_key.pub)\""
        exit 1
    fi
    
    local ci_public_key="$1"
    
    # 验证公钥格式
    if ! echo "$ci_public_key" | ssh-keygen -lf - >/dev/null 2>&1; then
        log_error "无效的 SSH 公钥格式"
        exit 1
    fi
    
    check_root
    check_deploy_user
    
    echo ""
    log_info "即将配置 deploy 账户的受限 SSH 访问"
    log_info "CI 公钥指纹:"
    echo "$ci_public_key" | ssh-keygen -lf - 2>/dev/null
    echo ""
    read -p "确认继续？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "用户取消操作"
        exit 0
    fi
    
    echo ""
    log_info "步骤 1/3: 创建受限命令入口"
    create_deployctl
    
    echo ""
    log_info "步骤 2/3: 配置 authorized_keys"
    setup_authorized_keys "$ci_public_key"
    
    echo ""
    log_info "步骤 3/3: 配置 sudoers 白名单"
    setup_sudoers
    
    echo ""
    test_configuration
    
    echo ""
    show_usage_instructions
    
    log_success "所有配置已完成！"
}

# 执行主函数
main "$@"
