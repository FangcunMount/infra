#!/usr/bin/env bash
set -euo pipefail

# =================================================================
# deploy 账户 CI/CD SSH 配置脚本
# =================================================================
# 功能：
# 1. 配置 deploy 的 authorized_keys（禁用交互能力,不强制 command）
# 2. 配置 CI/CD 需要的 sudoers 白名单
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

# 1. 配置 deploy 的 authorized_keys
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
# deploy 账户的 CI/CD SSH 密钥配置
# =================================================================
# 用途: 仅供 GitHub Actions CI/CD 使用
# 限制:
#   - no-agent-forwarding                 禁止 SSH Agent 转发
#   - no-X11-forwarding                   禁止 X11 图形转发
#   - no-port-forwarding                  禁止端口转发
#   - no-pty                               禁止分配伪终端（防止交互式 shell）
#   - no-user-rc                           禁止执行用户 rc 文件
# 说明:
#   当前 CI/CD 使用 appleboy/scp-action + ssh-action,需要能执行 tar/scp/ssh 脚本。
#   因此这里不能使用 authorized_keys 的 command= 强制入口,否则部署会被拦截。
# =================================================================

no-agent-forwarding,no-X11-forwarding,no-port-forwarding,no-pty,no-user-rc $ci_public_key
EOF

    chown deploy:deploy "$auth_keys"
    chmod 600 "$auth_keys"
    log_success "已配置 $auth_keys"
    
    log_info "授权密钥指纹:"
    ssh-keygen -lf "$auth_keys" 2>/dev/null || log_warn "无法读取密钥指纹"
}

# 2. 配置 sudoers 白名单
setup_sudoers() {
    log_info "配置 deploy 的 CI/CD sudoers 白名单"
    
    local sudoers_file="/etc/sudoers.d/deploy-cicd"
    
    # 备份现有文件（如果存在）
    if [[ -f "$sudoers_file" ]]; then
        cp "$sudoers_file" "$sudoers_file.backup.$(date +%Y%m%d_%H%M%S)"
        log_info "已备份现有 sudoers 配置"
    fi
    
    # 写入最小权限配置
    cat > "$sudoers_file" <<'EOF'
# =================================================================
# deploy 账户的 CI/CD sudo 白名单
# =================================================================
# 用途: 支持 GitHub Actions 通过 scp/ssh 完成容器部署
# 原则: deploy 不加入 docker 组,仅通过 sudo 执行部署所需命令
# =================================================================

# 禁用 requiretty（允许非交互式 SSH 执行 sudo）
Defaults:deploy !requiretty

# 允许的命令白名单（NOPASSWD: 无需密码）
deploy ALL=(root) NOPASSWD: \
    /usr/bin/docker *, \
    /usr/bin/docker-compose *, \
    /usr/bin/true, \
    /bin/true, \
    /usr/bin/rsync *, \
    /usr/bin/tar *, \
    /usr/bin/mkdir *, \
    /usr/bin/chown *, \
    /usr/bin/chmod *, \
    /usr/bin/rm *, \
    /usr/bin/ls *, \
    /usr/bin/namei *, \
    /usr/bin/test *, \
    /usr/bin/systemctl restart *.service, \
    /usr/bin/systemctl status *.service, \
    /usr/bin/systemctl reload *.service

# 说明:
#   /usr/bin/docker * 权限等价于较高运维权限,但当前 CI/CD 需要 docker login、
#   docker compose、docker network、docker inspect、docker exec、docker logs 等命令。
#   安全边界放在 SSH 私钥保护、禁用交互能力、审计 deploy 登录和仓库 Secrets 管理上。
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

# 3. 测试配置
test_configuration() {
    log_info "测试 deploy 配置..."
    
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

# 4. 显示使用说明
show_usage_instructions() {
    cat <<'EOF'

================================================================================
  deploy CI/CD SSH 配置完成
================================================================================

✅ 已创建:
   1. /home/deploy/.ssh/authorized_keys - CI 公钥 + 禁用交互能力
   2. /etc/sudoers.d/deploy-cicd        - CI/CD sudo 白名单

📋 支持的 CI/CD 行为:
   • appleboy/scp-action 上传 tar 包
   • appleboy/ssh-action 执行多行部署脚本
   • sudo docker login / pull / compose / network / inspect / logs

🔒 安全限制:
   • 禁止交互式登录 (no-pty)
   • 禁止 SSH Agent 转发 (no-agent-forwarding)
   • 禁止 X11 转发 (no-X11-forwarding)
   • 禁止端口转发 (no-port-forwarding)
   • deploy 不加入 docker 组,通过 sudoers 明确授权部署命令
   • deploy 密码锁定,仅接受 CI 公钥登录

📝 GitHub Actions 使用示例:

   - name: Deploy to server
     uses: appleboy/ssh-action@master
     with:
       host: ${{ secrets.SERVER_HOST }}
       username: deploy
       key: ${{ secrets.DEPLOY_SSH_KEY }}
       script: |
         sudo docker compose -f /opt/qs-server/apiserver/docker-compose.yml up -d

🔍 测试 SSH 连接:
   ssh -i /path/to/deploy_key deploy@server "sudo docker compose version"

⚠️  安全提醒:
   - deploy 私钥仅保存在 GitHub Secrets 中
   - 服务器上只有公钥（在 authorized_keys 中）
   - 定期检查 /var/log/auth.log 或 /var/log/secure 查看 deploy 登录记录

================================================================================

EOF
}

# 主函数
main() {
    echo "========================================"
    echo "  deploy CI/CD SSH 配置脚本"
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
    # 方法1: 基本格式验证 (更宽松)
    if ! echo "$ci_public_key" | grep -qE '^(ssh-rsa|ssh-ed25519|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521) [A-Za-z0-9+/]+=* '; then
        log_error "无效的 SSH 公钥格式"
        log_info "公钥应包含: <key-type> <key-data> <comment>"
        log_info "示例: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJx... github-actions@deploy"
        exit 1
    fi
    
    # 方法2: 使用 ssh-keygen 验证 (如果可用)
    if ! echo "$ci_public_key" | ssh-keygen -lf - >/dev/null 2>&1; then
        log_warn "ssh-keygen 验证失败，但格式看起来正确，继续执行..."
    fi
    
    check_root
    check_deploy_user
    
    echo ""
    log_info "即将配置 deploy 账户的 CI/CD SSH 访问"
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
    log_info "步骤 1/2: 配置 authorized_keys"
    setup_authorized_keys "$ci_public_key"
    
    echo ""
    log_info "步骤 2/2: 配置 sudoers 白名单"
    setup_sudoers
    
    echo ""
    test_configuration
    
    echo ""
    show_usage_instructions
    
    log_success "所有配置已完成！"
}

# 执行主函数
main "$@"
