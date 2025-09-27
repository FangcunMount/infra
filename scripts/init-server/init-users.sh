#!/usr/bin/env bash
set -euo pipefail

# 用户初始化脚本
# 创建用户 www 和 yangshujie，设置密码、sudo 权限，为 www 创建 SSH 密钥对，配置 .bashrc

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

# 创建用户
create_user() {
    local user=$1
    if id -u "$user" >/dev/null 2>&1; then
        log_warn "用户 '$user' 已存在，跳过创建"
    else
        log_info "创建用户 '$user'..."
        useradd -m -s /bin/bash "$user"
        log_success "用户 '$user' 创建成功"
    fi
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
    
    # 创建 sudoers 文件（可选，允许无密码 sudo）
    # echo "$user ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/$user"
    
    log_success "用户 '$user' 已获得 sudo 权限"
}

# 为 www 用户创建 SSH 密钥对
create_ssh_keys() {
    local user="www"
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
    
    log_info "SSH 公钥 (请复制到 GitHub Deploy Key):"
    echo "----------------------------------------"
    cat "$key_path.pub"
    echo "----------------------------------------"
    log_info "SSH 配置文件已创建: $ssh_dir/config"
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

# 主函数
main() {
    log_info "========================================"
    log_info "用户环境初始化脚本开始执行"
    log_info "执行时间: $(date)"
    log_info "========================================"
    
    # 初始检查
    check_root
    detect_os
    check_dependencies
    
    # 用户确认
    echo
    log_warn "此脚本将执行以下操作："
    echo "  • 设置系统默认 Shell 为 bash"
    echo "  • 配置 root 用户 .bashrc（会备份原文件）"
    echo "  • 创建用户 www 和 yangshujie"
    echo "  • 为用户设置密码和 sudo 权限"
    echo "  • 为 www 用户生成 SSH 密钥对"
    echo "  • 配置用户 .bashrc 和工作环境"
    echo
    read -p "确认继续执行？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "用户取消执行"
        exit 0
    fi
    
    setup_logging
    
    # 0. 设置系统默认 Shell 和配置 root
    set_default_shell
    setup_root_bashrc
    
    # 1. 创建用户
    create_user "www"
    create_user "yangshujie"
    
    # 2. 设置密码
    set_user_password "www"
    set_user_password "yangshujie"
    
    # 3. 添加 sudo 权限
    add_sudo_privilege "www"
    add_sudo_privilege "yangshujie"
    
    # 4. 为 www 用户创建 SSH 密钥对
    create_ssh_keys
    
# 验证用户配置
verify_user_setup() {
    local user=$1
    local errors=0
    
    log_info "验证用户 '$user' 的配置..."
    
    # 检查用户是否存在
    if ! id "$user" >/dev/null 2>&1; then
        log_error "用户 '$user' 不存在"
        ((errors++))
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
    
    # 检查 sudo 权限
    if ! groups "$user" | grep -q sudo; then
        log_error "用户 '$user' 没有 sudo 权限"
        ((errors++))
    fi
    
    # 检查 SSH 密钥 (仅对 www 用户)
    if [[ "$user" == "www" ]]; then
        if [[ ! -f "/home/$user/.ssh/id_ed25519" ]]; then
            log_error "用户 '$user' SSH 私钥不存在"
            ((errors++))
        fi
        if [[ ! -f "/home/$user/.ssh/id_ed25519.pub" ]]; then
            log_error "用户 '$user' SSH 公钥不存在"
            ((errors++))
        fi
    fi
    
    if [[ $errors -eq 0 ]]; then
        log_success "用户 '$user' 配置验证通过"
    else
        log_warn "用户 '$user' 配置验证发现 $errors 个问题"
    fi
    
    return $errors
}

    # 5. 配置 .bashrc 文件
    setup_user_bashrc "www"
    setup_user_bashrc "yangshujie"
    
    # 6. 验证配置
    log_info "========================================"
    log_info "验证用户配置..."
    log_info "========================================"
    verify_user_setup "www"
    verify_user_setup "yangshujie"
    
    echo
    log_success "用户环境初始化完成！"
    log_info "完成的配置："
    echo "  ✅ 设置系统默认 Shell 为 bash"
    echo "  ✅ 配置 root 用户 .bashrc（已备份原文件）"
    echo "  ✅ 创建用户 www 和 yangshujie"
    echo "  ✅ 为用户设置密码和 sudo 权限"
    echo "  ✅ 为 www 用户生成 SSH 密钥对"
    echo "  ✅ 配置用户 .bashrc 和工作目录"
    echo
    log_info "下一步操作："
    echo "  1. 将 www 用户的 SSH 公钥添加到 GitHub Deploy Key"
    echo "  2. 使用新用户登录测试: su - www 或 su - yangshujie"
    echo "  3. 验证 workspace 目录和环境变量是否正确"
    echo "  4. 重新登录以应用新的 .bashrc 配置"
}

# 执行主函数
main "$@"
