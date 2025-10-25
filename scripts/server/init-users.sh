#!/usr/bin/env bash
set -euo pipefail

# 用户初始化脚本 v2.1 (安全加固版)
# 创建三种账户类型:
# 1. yangshujie - 运维账户 (人用,可登录,有 sudo 权限,无 docker 组)
# 2. deploy - CI/CD 账户 (仅供 GitHub Actions 使用,不可交互登录,无 docker 组)
# 3. www - 业务进程账户 (仅服务,不可登录,无特殊权限)
#
# 安全原则:
# - yangshujie 通过 sudo 进行 docker 操作,不进入 docker 组 (避免 root 等价)
# - deploy 禁止交互登录,仅通过受限 SSH 执行白名单命令
# - deploy 不在服务器上生成 GitHub SSH 密钥 (密钥由 GitHub Actions 管理)
# - www 仅作为服务进程所有者,无任何特权
#
# 使用方式:
#   sudo ./init-users.sh              # 交互式创建所有账户
#   sudo ./init-users.sh --non-interactive  # 非交互式(CI环境)

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 全局变量
NON_INTERACTIVE=false
ENV_FILE="/opt/infra/.env"

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

# 错误处理函数
handle_error() {
    local line_number=$1
    log_error "脚本在第 $line_number 行执行失败"
    log_info "正在进行清理操作..."
    cleanup_on_error
    exit 1
}

# 错误清理函数
cleanup_on_error() {
    log_warn "如果用户创建过程中出现错误，请手动检查："
    echo "  1. 检查用户是否已创建: id www; id yangshujie"
    echo "  2. 检查 SSH 密钥状态: ls -la /home/www/.ssh/"
    echo "  3. 检查 sudo 权限: groups www; groups yangshujie"
    echo "  4. 必要时手动清理: userdel -r username"
}

# 设置错误陷阱
trap 'handle_error $LINENO' ERR

# 检测操作系统类型
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$NAME
        OS_VERSION=$VERSION_ID
    elif [[ -f /etc/redhat-release ]]; then
        OS="Red Hat Enterprise Linux"
    elif [[ -f /etc/debian_version ]]; then
        OS="Debian"
    else
        OS="Unknown"
    fi
    
    log_info "检测到操作系统: $OS"
    
    # 检查是否支持的系统
    case "$OS" in
        *"Ubuntu"*|*"Debian"*|*"CentOS"*|*"Red Hat"*|*"Rocky"*|*"AlmaLinux"*)
            log_success "支持的操作系统"
            ;;
        *)
            log_warn "未测试的操作系统，脚本可能需要调整"
            ;;
    esac
}

# 检查是否为 root 用户
check_root() {
    if [[ ${EUID} -ne 0 ]]; then
        log_error "此脚本必须以 root 用户身份运行"
        echo "使用方法: sudo $0"
        exit 1
    fi
}

# 检查必要的命令是否存在
check_dependencies() {
    local deps=("useradd" "usermod" "chpasswd" "ssh-keygen" "chmod" "chown")
    local missing_deps=()
    
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" >/dev/null 2>&1; then
            missing_deps+=("$dep")
        fi
    done
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "缺少必要的命令: ${missing_deps[*]}"
        log_error "请安装相应的软件包后重试"
        exit 1
    fi
    
    log_success "所有必要命令检查通过"
}

# 创建普通用户 (可登录)
create_user() {
    local user=$1
    if id -u "$user" >/dev/null 2>&1; then
        log_warn "用户 '$user' 已存在，跳过创建"
        return 0
    fi
    
    log_info "创建用户 '$user' (可登录)..."
    useradd -m -s /bin/bash "$user"
    log_success "用户 '$user' 创建成功"
}

# 创建系统服务用户 (不可登录)
create_system_user() {
    local user=$1
    local home_dir=$2
    
    if id -u "$user" >/dev/null 2>&1; then
        log_warn "用户 '$user' 已存在，跳过创建"
        return 0
    fi
    
    log_info "创建系统服务用户 '$user' (不可登录)..."
    
    # 创建系统用户,不可登录
    useradd --system --home "$home_dir" --shell /usr/sbin/nologin --user-group "$user"
    
    # 创建主目录(如果不存在)
    if [[ ! -d "$home_dir" ]]; then
        mkdir -p "$home_dir"
        chown "$user:$user" "$home_dir"
        chmod 755 "$home_dir"
    fi
    
    log_success "系统用户 '$user' 创建成功"
    log_info "  UID/GID: $(id -u $user)/$(id -g $user)"
    log_info "  主目录: $home_dir"
    log_info "  Shell: /usr/sbin/nologin (不可登录)"
}

# 验证密码强度
validate_password_strength() {
    local pass=$1
    local min_length=8
    
    # 检查密码长度
    if [[ ${#pass} -lt $min_length ]]; then
        echo "密码长度至少需要 $min_length 个字符"
        return 1
    fi
    
    # 检查是否包含数字
    if [[ ! "$pass" =~ [0-9] ]]; then
        echo "密码必须包含至少一个数字"
        return 1
    fi
    
    # 检查是否包含字母
    if [[ ! "$pass" =~ [a-zA-Z] ]]; then
        echo "密码必须包含至少一个字母"
        return 1
    fi
    
    return 0
}

# 设置用户密码
set_user_password() {
    local user=$1
    local pass confirm
    
    log_info "为用户 '$user' 设置密码..."
    log_info "密码要求: 至少8位，包含字母和数字"
    
    while true; do
        read -s -p "请输入 $user 的密码: " pass
        echo
        read -s -p "请确认 $user 的密码: " confirm
        echo
        
        if [[ -z "$pass" ]]; then
            log_warn "密码不能为空，请重新输入"
        elif [[ "$pass" != "$confirm" ]]; then
            log_warn "两次输入的密码不匹配，请重新输入"
        elif ! validate_password_strength "$pass"; then
            log_warn "密码强度不足，请重新输入"
        else
            echo "$user:$pass" | chpasswd
            log_success "用户 '$user' 密码设置成功"
            break
        fi
    done
}

# 添加 sudo 权限
add_sudo_privilege() {
    local user=$1
    log_info "为用户 '$user' 添加 sudo 权限..."
    
    # 添加到 sudo 组
    usermod -aG sudo "$user"
    
    log_success "用户 '$user' 已获得 sudo 权限"
}

# 添加 docker 权限
add_docker_privilege() {
    local user=$1
    log_info "为用户 '$user' 添加 docker 权限..."
    
    # 检查 docker 组是否存在
    if ! getent group docker >/dev/null 2>&1; then
        log_warn "docker 组不存在，将在 Docker 安装后自动添加"
        return 0
    fi
    
    # 添加到 docker 组
    usermod -aG docker "$user"
    
    log_success "用户 '$user' 已获得 docker 权限"
}

# 配置 deploy 账户的受限 sudo 权限
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

# 为用户创建 SSH 密钥对
create_ssh_keys() {
    local user=$1
    local home_dir="/home/$user"
    local ssh_dir="$home_dir/.ssh"
    local key_path="$ssh_dir/id_ed25519"
    
    log_info "为用户 '$user' 创建 SSH 密钥对..."
    
    # 创建 .ssh 目录
    mkdir -p "$ssh_dir"
    chmod 700 "$ssh_dir"
    
    if [[ -f "$key_path" ]]; then
        log_warn "SSH 密钥已存在: $key_path"
    else
        # 生成 SSH 密钥对
        ssh-keygen -t ed25519 -C "$user@$(hostname)" -f "$key_path" -N ""
        log_success "SSH 密钥对创建成功"
    fi
    
    # 设置正确的权限和所有者
    chown -R "$user:$user" "$ssh_dir"
    chmod 600 "$key_path"
    chmod 644 "$key_path.pub"
    
    # 创建 authorized_keys 文件
    local authorized_keys="$ssh_dir/authorized_keys"
    touch "$authorized_keys"
    chmod 600 "$authorized_keys"
    chown "$user:$user" "$authorized_keys"
    
    # 创建 SSH 配置文件
    cat > "$ssh_dir/config" << EOF
Host github.com
    HostName github.com
    User git
    IdentityFile $key_path
    IdentitiesOnly yes
EOF
    chmod 600 "$ssh_dir/config"
    chown "$user:$user" "$ssh_dir/config"
    
    log_info "SSH 公钥 (用户: $user):"
    echo "----------------------------------------"
    cat "$key_path.pub"
    echo "----------------------------------------"
    log_info "SSH 配置文件已创建: $ssh_dir/config"
}

# 配置 www 用户的业务目录
setup_www_directories() {
    log_info "配置 www 用户的业务目录..."
    
    local www_uid=$(id -u www)
    local www_gid=$(id -g www)
    
    # 创建业务数据目录
    local dirs=(
        "/var/www"         # www 主目录
        "/srv/apps"        # 应用部署目录
        "/var/log/apps"    # 应用日志目录
    )
    
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
        fi
        chown -R www:www "$dir"
        chmod 750 "$dir"
        log_success "创建并配置目录: $dir (www:www 750)"
    done
    
    # 将 UID/GID 写入环境文件
    if [[ ! -d "$(dirname $ENV_FILE)" ]]; then
        mkdir -p "$(dirname $ENV_FILE)"
    fi
    
    # 更新或添加 WWW_UID/WWW_GID
    if [[ -f "$ENV_FILE" ]]; then
        # 删除旧的定义
        sed -i '/^WWW_UID=/d' "$ENV_FILE" 2>/dev/null || true
        sed -i '/^WWW_GID=/d' "$ENV_FILE" 2>/dev/null || true
    fi
    
    cat >> "$ENV_FILE" << EOF

# www 用户 UID/GID (用于 Docker 容器)
WWW_UID=$www_uid
WWW_GID=$www_gid
EOF
    
    log_success "www 用户 UID/GID 已写入: $ENV_FILE"
    log_info "  WWW_UID=$www_uid"
    log_info "  WWW_GID=$www_gid"
    log_info "在 docker-compose.yml 中使用: user: \"\${WWW_UID}:\${WWW_GID}\""
}

# 配置用户 .bashrc 文件
setup_user_bashrc() {
    local user=$1
    local home_dir="/home/$user"
    local bashrc_file="$home_dir/.bashrc"
    
    log_info "配置用户 '$user' 的 .bashrc 文件..."
    
    # 备份原有的 .bashrc（如果存在）
    if [[ -f "$bashrc_file" ]]; then
        cp "$bashrc_file" "$bashrc_file.backup.$(date +%Y%m%d_%H%M%S)"
        log_info "已备份原有 .bashrc 文件"
    fi
    
    # 检查是否已经添加过自定义配置
    local marker="# === INIT-USERS CUSTOM CONFIG ==="
    if grep -q "$marker" "$bashrc_file" 2>/dev/null; then
        log_warn "检测到已存在自定义配置，跳过添加"
        return 0
    fi
    
    # 追加自定义配置到 .bashrc 文件
    cat >> "$bashrc_file" << EOF

$marker
# User specific aliases and functions

alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'

# Source global definitions
if [ -f /etc/bashrc ]; then
    . /etc/bashrc
fi

# Create workspace directory if not exists
if [ ! -d \$HOME/workspace ]; then
    mkdir -p \$HOME/workspace
fi

# User specific environment
# Basic envs
export LANG="en_US.UTF-8" # 设置系统语言为 en_US.UTF-8，避免终端出现中文乱码
export PS1='[\u@\h \W]\$ ' # 设置展示命令行提示符: 用户名@主机名 当前目录
export WORKSPACE="\$HOME/workspace" # 设置工作目录
export PATH=\$HOME/bin:\$PATH # 将 \$HOME/bin 目录加入到 PATH 变量中

# Default entry folder (only if in interactive shell)
if [[ \$- == *i* ]] && [[ -d \$WORKSPACE ]]; then
    cd \$WORKSPACE # 登录系统，默认进入 workspace 目录
fi

# User specific aliases and functions
# === END CUSTOM CONFIG ===
EOF

    # 设置文件权限和所有者
    chown "$user:$user" "$bashrc_file"
    chmod 644 "$bashrc_file"
    
    # 创建 workspace 目录
    local workspace_dir="$home_dir/workspace"
    mkdir -p "$workspace_dir"
    chown "$user:$user" "$workspace_dir"
    
    # 创建 bin 目录
    local bin_dir="$home_dir/bin"
    mkdir -p "$bin_dir"
    chown "$user:$user" "$bin_dir"
    
    log_success "用户 '$user' 的 .bashrc 配置完成"
}

# 设置系统默认 Shell 为 bash
set_default_shell() {
    log_info "设置系统默认 Shell 为 bash..."
    
    # 确保 bash 是默认 shell
    if command -v bash >/dev/null 2>&1; then
        # 设置新用户默认使用 bash
        if [[ -f /etc/default/useradd ]]; then
            sed -i 's/^SHELL=.*/SHELL=\/bin\/bash/' /etc/default/useradd 2>/dev/null || true
        fi
        
        # 如果没有 useradd 配置文件，创建一个
        if [[ ! -f /etc/default/useradd ]]; then
            echo "SHELL=/bin/bash" >> /etc/default/useradd
        fi
        
        log_success "系统默认 Shell 已设置为 bash"
    else
        log_warn "系统中未找到 bash，跳过默认 Shell 设置"
    fi
}

# 配置 root 用户的 .bashrc
setup_root_bashrc() {
    local bashrc_file="/root/.bashrc"
    
    log_info "配置 root 用户的 .bashrc 文件..."
    
    # 备份原有的 .bashrc（如果存在）
    if [[ -f "$bashrc_file" ]]; then
        cp "$bashrc_file" "$bashrc_file.backup.$(date +%Y%m%d_%H%M%S)"
        log_info "已备份原有 root .bashrc 文件"
    fi
    
    # 检查是否已经添加过自定义配置
    local marker="# === ROOT INIT-USERS CUSTOM CONFIG ==="
    if grep -q "$marker" "$bashrc_file" 2>/dev/null; then
        log_warn "检测到 root 已存在自定义配置，跳过添加"
        return 0
    fi
    
    # 追加自定义配置到 root .bashrc 文件
    cat >> "$bashrc_file" << 'EOF'

# === ROOT INIT-USERS CUSTOM CONFIG ===
# Root user .bashrc configuration

# User specific aliases and functions
alias rm='rm -i'
alias cp='cp -i'
alias mv='mv -i'
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

# Source global definitions
if [ -f /etc/bashrc ]; then
    . /etc/bashrc
fi

# Create workspace directory if not exists
if [ ! -d /root/workspace ]; then
    mkdir -p /root/workspace
fi

# Root specific environment
# Basic envs
export LANG="en_US.UTF-8" # 设置系统语言为 en_US.UTF-8，避免终端出现中文乱码
export PS1='[\u@\h \W]# ' # 设置展示命令行提示符: 用户名@主机名 当前目录 (root用户显示#)
export WORKSPACE="/root/workspace" # 设置工作目录
export PATH=/root/bin:$PATH # 将 /root/bin 目录加入到 PATH 变量中

# Default entry folder (only if in interactive shell)
if [[ $- == *i* ]] && [[ -d $WORKSPACE ]]; then
    cd $WORKSPACE # 登录系统，默认进入 workspace 目录
fi

# Root specific aliases and functions
alias status='systemctl status'
alias start='systemctl start'
alias stop='systemctl stop'
alias restart='systemctl restart'
alias reload='systemctl reload'
alias enable='systemctl enable'
alias disable='systemctl disable'

# Docker aliases (if docker is available)
if command -v docker >/dev/null 2>&1; then
    alias dps='docker ps'
    alias dpsa='docker ps -a'
    alias di='docker images'
    alias dlog='docker logs -f'
    alias dexec='docker exec -it'
fi
# === END ROOT CUSTOM CONFIG ===
EOF

    # 设置文件权限
    chmod 644 "$bashrc_file"
    
    # 创建 root workspace 目录
    mkdir -p /root/workspace
    
    # 创建 root bin 目录
    mkdir -p /root/bin
    
    log_success "root 用户的 .bashrc 配置完成"
}

# 创建日志文件
setup_logging() {
    local log_dir="/var/log/init-users"
    local log_file="$log_dir/init-users-$(date +%Y%m%d_%H%M%S).log"
    
    mkdir -p "$log_dir"
    
    # 同时输出到终端和日志文件
    exec 1> >(tee -a "$log_file")
    exec 2> >(tee -a "$log_file" >&2)
    
    log_info "日志文件: $log_file"
}

# 解析命令行参数
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --non-interactive)
                NON_INTERACTIVE=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# 显示帮助信息
show_help() {
    cat << EOF
用户初始化脚本 v2.0

用途:
  创建三种账户类型:
  1. yangshujie - 运维账户 (人用,可登录,有 sudo/docker 权限)
  2. deploy - CI/CD 账户 (自动化部署,有 docker 权限,可登录)
  3. www - 业务进程账户 (仅服务,不可登录,无特殊权限)

使用方式:
  sudo $0              # 交互式创建所有账户
  sudo $0 --non-interactive  # 非交互式(CI环境,使用默认密码)

选项:
  --non-interactive    非交互模式(跳过密码设置和确认)
  -h, --help          显示此帮助信息
EOF
}

# 主函数
main() {
    log_info "========================================"
    log_info "用户环境初始化脚本 v2.0 开始执行"
    log_info "执行时间: $(date)"
    log_info "========================================"
    
    # 解析参数
    parse_args "$@"
    
    # 初始检查
    check_root
    detect_os
    check_dependencies
    
    # 用户确认
    if [[ "$NON_INTERACTIVE" != true ]]; then
        echo
        log_warn "此脚本将执行以下操作："
        echo "  • 设置系统默认 Shell 为 bash"
        echo "  • 配置 root 用户 .bashrc（会备份原文件）"
        echo
        echo "  账户类型 1: yangshujie (运维账户)"
        echo "    - 可登录 SSH"
        echo "    - sudo 权限 (系统管理)"
        echo "    - ❌ 不进入 docker 组 (避免 root 等价权限)"
        echo "    - 使用 'sudo docker' 操作容器"
        echo "    - 配置 .bashrc 和工作环境"
        echo
        echo "  账户类型 2: deploy (CI/CD 账户) - 方案 A: 受限 sudo"
        echo "    - ✅ 可 SSH 登录 (仅 SSH 密钥认证,无密码)"
        echo "    - ✅ 受限 sudo 权限 (docker/systemctl/rsync/chown/chmod/mkdir)"
        echo "    - ❌ 不进入 docker 组 (避免 root 等价权限)"
        echo "    - 使用 'sudo docker' 操作容器"
        echo "    - SSH 密钥由 GitHub Actions 管理"
        echo "    - 所有操作有 sudo 审计日志"
        echo
        echo "  账户类型 3: www (业务进程账户)"
        echo "    - 不可登录 (Shell: /usr/sbin/nologin)"
        echo "    - 无 sudo/docker 权限"
        echo "    - 用于运行业务进程和容器"
        echo "    - 创建业务目录: /var/www, /srv/apps, /var/log/apps"
        echo "    - 导出 WWW_UID/WWW_GID 到 $ENV_FILE"
        echo
        read -p "确认继续执行？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "用户取消执行"
            exit 0
        fi
    fi
    
    setup_logging
    
    # 0. 设置系统默认 Shell 和配置 root
    log_info "========================================"
    log_info "步骤 1: 配置系统环境"
    log_info "========================================"
    set_default_shell
    setup_root_bashrc
    
    # 1. 创建 yangshujie (运维账户)
    log_info "========================================"
    log_info "步骤 2: 创建 yangshujie (运维账户)"
    log_info "========================================"
    create_user "yangshujie"
    if [[ "$NON_INTERACTIVE" != true ]]; then
        set_user_password "yangshujie"
    else
        log_warn "非交互模式: 跳过 yangshujie 密码设置"
    fi
    add_sudo_privilege "yangshujie"
    # ❌ 安全加固: 不将 yangshujie 加入 docker 组 (docker 组 = root 等价权限)
    # yangshujie 应通过 sudo docker 命令操作容器,避免获得 root 等价权限
    # add_docker_privilege "yangshujie"
    setup_user_bashrc "yangshujie"
    
    # 2. 创建 deploy (CI/CD 账户)
    log_info "========================================"
    log_info "步骤 3: 创建 deploy (CI/CD 账户)"
    log_info "========================================"
    create_user "deploy"
    if [[ "$NON_INTERACTIVE" != true ]]; then
        set_user_password "deploy"
    else
        log_warn "非交互模式: 跳过 deploy 密码设置"
    fi
    
    # ✅ 方案 A: 允许 deploy 登录 + 受限 sudo (推荐)
    # 理由:
    # 1. GitHub Actions 需要灵活执行部署命令
    # 2. 通过受限 sudo 控制权限,而非完全禁止登录
    # 3. 不将 deploy 加入 docker 组,避免 root 等价权限
    # 4. deploy 只能通过 SSH 密钥登录,不设置密码
    
    log_info "配置 deploy 为可登录账户（仅 SSH 密钥认证）..."
    # deploy 使用 bash shell（允许登录）
    usermod -s /bin/bash deploy
    # 锁定密码（只能通过 SSH 密钥登录，不能用密码）
    passwd -l deploy
    log_success "deploy 已配置为可 SSH 登录（仅密钥认证）"
    
    # 配置 deploy 的受限 sudo 权限
    setup_deploy_sudo_privileges
    
    setup_user_bashrc "deploy"
    
    # 3. 创建 www (系统服务账户)
    log_info "========================================"
    log_info "步骤 4: 创建 www (业务进程账户)"
    log_info "========================================"
    create_system_user "www" "/var/www"
    setup_www_directories
    
# 验证用户配置
verify_user_setup() {
    local user=$1
    local errors=0
    
    log_info "验证用户 '$user' 的配置..."
    
    # 检查用户是否存在
    if ! id "$user" >/dev/null 2>&1; then
        log_error "用户 '$user' 不存在"
        ((errors++))
        return $errors
    fi
    
    # 检查用户主目录
    if [[ ! -d "/home/$user" ]]; then
        log_error "用户 '$user' 主目录不存在"
        ((errors++))
    fi
    
    # 检查 .bashrc 文件
    if [[ ! -f "/home/$user/.bashrc" ]]; then
        log_error "用户 '$user' .bashrc 文件不存在"
        ((errors++))
    fi
    
    # 检查 workspace 目录
    if [[ ! -d "/home/$user/workspace" ]]; then
        log_error "用户 '$user' workspace 目录不存在"
        ((errors++))
    fi
    
    # 检查 yangshujie 的 sudo 权限
    if [[ "$user" == "yangshujie" ]]; then
        if ! groups "$user" | grep -q sudo; then
            log_error "用户 '$user' 没有 sudo 权限"
            ((errors++))
        fi
    fi
    
    # v2.1 安全模型: yangshujie 和 deploy 都不应该在 docker 组
    # yangshujie 使用 'sudo docker', deploy 通过受限 SSH 执行白名单命令
    if [[ "$user" == "yangshujie" ]] || [[ "$user" == "deploy" ]]; then
        if getent group docker >/dev/null 2>&1; then
            if groups "$user" | grep -q docker; then
                log_warn "警告: 用户 '$user' 在 docker 组 (不符合安全最佳实践)"
                log_warn "  建议移除: sudo gpasswd -d $user docker"
            fi
        fi
    fi
    
    # 检查 deploy 的安全配置
    if [[ "$user" == "deploy" ]]; then
        # 检查是否禁止交互登录
        deploy_shell=$(getent passwd deploy | cut -d: -f7)
        if [[ "$deploy_shell" != "/usr/sbin/nologin" ]]; then
            log_warn "警告: deploy 账户 Shell 应为 /usr/sbin/nologin (当前: $deploy_shell)"
        fi
        
        # 检查密码是否锁定
        if passwd -S deploy 2>/dev/null | grep -q "^deploy P"; then
            log_warn "警告: deploy 账户密码未锁定，建议执行: sudo passwd -l deploy"
        fi
        
        # SSH 密钥由 GitHub Actions 管理，不在服务器上生成
        log_info "  deploy SSH 密钥由 GitHub Actions Secrets 管理"
        log_info "  访问通过 setup-deploy-ssh.sh 配置受限 SSH"
    fi
    
    if [[ $errors -eq 0 ]]; then
        log_success "用户 '$user' 配置验证通过"
    else
        log_warn "用户 '$user' 配置验证发现 $errors 个问题"
    fi
    
    return $errors
}

    
    # 4. 验证配置
    log_info "========================================"
    log_info "步骤 5: 验证用户配置"
    log_info "========================================"
    verify_user_setup "yangshujie"
    verify_user_setup "deploy"
    verify_system_user_setup "www"
    
    # 5. 显示总结
    echo
    log_success "========================================"
    log_success "用户环境初始化完成！"
    log_success "========================================"
    echo
    log_info "✅ 完成的配置:"
    echo
    echo "  系统配置:"
    echo "    • 设置系统默认 Shell 为 bash"
    echo "    • 配置 root 用户 .bashrc（已备份原文件）"
    echo
    echo "  账户 1: yangshujie (运维账户) - 安全加固版"
    echo "    • 用户类型: 可登录用户"
    echo "    • 权限: sudo (系统管理)"
    echo "    • ❌ 不在 docker 组 (避免 root 等价权限)"
    echo "    • Docker 操作: 使用 'sudo docker' 命令"
    echo "    • 用途: 日常运维和系统管理"
    echo "    • 登录测试: su - yangshujie"
    echo
    echo "  账户 2: deploy (CI/CD 账户) - 安全加固版"
    echo "    • 用户类型: 系统用户 (禁止交互登录)"
    echo "    • Shell: /usr/sbin/nologin"
    echo "    • 密码: 已锁定 (passwd -l)"
    echo "    • ❌ 不在 docker 组 (CI 不应有 root 等价权限)"
    echo "    • ❌ 未生成 SSH 密钥 (由 GitHub Actions 管理)"
    echo "    • 用途: 仅供 GitHub Actions 通过受限 SSH 使用"
    echo "    • 登录测试: su - deploy (预期失败: This account is currently not available)"
    echo
    echo "  账户 3: www (业务进程账户)"
    echo "    • 用户类型: 系统用户 (不可登录)"
    echo "    • Shell: /usr/sbin/nologin"
    echo "    • UID/GID: $(id -u www)/$(id -g www)"
    echo "    • 业务目录: /var/www, /srv/apps, /var/log/apps"
    echo "    • 用途: 运行业务进程和容器"
    echo "    • 环境文件: $ENV_FILE"
    echo
    log_info "📝 下一步操作 (必需):"
    echo
    echo "  1. 🔐 配置 deploy 的受限 SSH (用于 CI/CD):"
    echo "     # 在本地生成 SSH 密钥对"
    echo "     ssh-keygen -t ed25519 -C \"github-actions@deploy\" -f ~/.ssh/deploy_key"
    echo
    echo "     # 在服务器上配置受限 SSH"
    echo "     sudo ./scripts/server/setup-deploy-ssh.sh \"\$(cat ~/.ssh/deploy_key.pub)\""
    echo
    echo "     详细步骤: docs/server/github-actions-deploy.md"
    echo
    echo "  2. 🐳 运维人员使用 Docker:"
    echo "     sudo docker ps                # 查看容器"
    echo "     sudo docker compose up -d     # 启动服务"
    echo "     make mysql-start              # Makefile 命令（内部自动使用 sudo）"
    echo
    echo "  3. 📦 业务容器使用 www 用户:"
    echo "     services:"
    echo "       app:"
    echo "         user: \"\${WWW_UID}:\${WWW_GID}\""
    echo "         env_file: /opt/infra/.env"
    echo
    echo "  4. 🔍 验证安全配置:"
    echo "     groups yangshujie  # 预期: yangshujie sudo (无 docker)"
    echo "     groups deploy      # 预期: deploy (无 docker)"
    echo "     groups www         # 预期: www (无任何特权组)"
    echo
    log_info "⚠️  重要安全提醒:"
    echo
    echo "  ❌ 不要将 yangshujie 加入 docker 组 (docker 组 = root 等价权限)"
    echo "  ✅ 使用 'sudo docker' 命令操作容器 (有审计、需密码)"
    echo
    echo "  ❌ 不要让 deploy 可以交互登录 (已禁用)"
    echo "  ✅ deploy 仅通过受限 SSH + 白名单命令使用"
    echo
    echo "  ❌ 不要在服务器上给 deploy 生成 GitHub SSH 密钥"
    echo "  ✅ 密钥在 GitHub Secrets 中管理，服务器只有公钥"
    echo
    log_info "📖 详细文档:"
    echo
    echo "  • 安全加固说明: docs/server/user-security-hardening.md"
    echo "  • GitHub Actions 集成: docs/server/github-actions-deploy.md"
    echo "  • 快速参考: docs/server/SECURITY_QUICKREF.md"
    echo "  • www 用户指南: docs/server/www-user-guide.md"
}

# 验证系统用户配置
verify_system_user_setup() {
    local user=$1
    local errors=0
    
    log_info "验证系统用户 '$user' 的配置..."
    
    # 检查用户是否存在
    if ! id "$user" >/dev/null 2>&1; then
        log_error "用户 '$user' 不存在"
        ((errors++))
    fi
    
    # 检查 Shell 是否为 nologin
    local user_shell=$(getent passwd "$user" | cut -d: -f7)
    if [[ "$user_shell" != "/usr/sbin/nologin" ]]; then
        log_warn "用户 '$user' Shell 不是 /usr/sbin/nologin (当前: $user_shell)"
    fi
    
    # 检查业务目录
    local dirs=("/var/www" "/srv/apps" "/var/log/apps")
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            log_error "目录不存在: $dir"
            ((errors++))
        else
            local owner=$(stat -c '%U:%G' "$dir" 2>/dev/null || stat -f '%Su:%Sg' "$dir" 2>/dev/null)
            if [[ "$owner" != "$user:$user" ]]; then
                log_warn "目录 $dir 所有者不正确 (应为 $user:$user, 当前: $owner)"
            fi
        fi
    done
    
    # 检查环境文件
    if [[ ! -f "$ENV_FILE" ]]; then
        log_error "环境文件不存在: $ENV_FILE"
        ((errors++))
    elif ! grep -q "^WWW_UID=" "$ENV_FILE"; then
        log_error "环境文件缺少 WWW_UID: $ENV_FILE"
        ((errors++))
    fi
    
    if [[ $errors -eq 0 ]]; then
        log_success "系统用户 '$user' 配置验证通过"
    else
        log_warn "系统用户 '$user' 配置验证发现 $errors 个问题"
    fi
    
    return $errors
}

# 执行主函数
main "$@"
