#!/usr/bin/env bash
#
# 重置服务器用户账户
# 用途: 完全删除由 init-users.sh 创建的所有用户和配置
# 使用: sudo ./reset-users.sh
#
# 警告: 这将删除以下内容:
#   - yangshujie 用户及其 home 目录
#   - deploy 用户及其 home 目录
#   - www 用户及其相关目录
#   - /opt/infra/.env 中的 WWW_UID/WWW_GID 配置
#
# 版本: 1.0
# 作者: Infrastructure Team
# 日期: 2025-10-24

set -euo pipefail

# ==============================================================================
# 颜色和格式定义
# ==============================================================================
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly MAGENTA='\033[0;35m'
readonly CYAN='\033[0;36m'
readonly WHITE='\033[1;37m'
readonly NC='\033[0m' # No Color
readonly BOLD='\033[1m'

# ==============================================================================
# 日志函数
# ==============================================================================
log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# ==============================================================================
# 权限检查
# ==============================================================================
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "此脚本必须以 root 权限运行"
        log_info "请使用: sudo $0"
        exit 1
    fi
}

# ==============================================================================
# 用户删除函数
# ==============================================================================
remove_user() {
    local username=$1
    
    log_info "检查用户 '$username'..."
    
    if ! id "$username" >/dev/null 2>&1; then
        log_warn "用户 '$username' 不存在，跳过"
        return 0
    fi
    
    log_info "删除用户 '$username' 及其 home 目录..."
    
    # 杀死该用户的所有进程
    if pgrep -u "$username" >/dev/null 2>&1; then
        log_info "  终止用户 '$username' 的所有进程..."
        pkill -TERM -u "$username" || true
        sleep 2
        pkill -KILL -u "$username" || true
    fi
    
    # 删除用户（包括 home 目录和邮箱）
    if userdel -r "$username" 2>/dev/null; then
        log_success "用户 '$username' 已删除"
    else
        log_warn "删除用户 '$username' 时出现警告（可能部分资源已不存在）"
    fi
    
    # 清理 sudoers 配置
    local sudoers_file="/etc/sudoers.d/${username}"
    if [[ -f "$sudoers_file" ]]; then
        log_info "  删除 sudoers 配置: $sudoers_file"
        rm -f "$sudoers_file"
    fi
    
    # 清理 deploy 的特殊配置
    if [[ "$username" == "deploy" ]]; then
        if [[ -f "/etc/sudoers.d/deploy-cicd" ]]; then
            log_info "  删除 deploy CI/CD sudoers 配置"
            rm -f "/etc/sudoers.d/deploy-cicd"
        fi
        
        if [[ -f "/usr/local/bin/deployctl" ]]; then
            log_info "  删除 deployctl 工具"
            rm -f "/usr/local/bin/deployctl"
        fi
    fi
}

# ==============================================================================
# 清理 www 用户相关目录
# ==============================================================================
clean_www_directories() {
    log_info "清理 www 用户的业务目录..."
    
    local dirs=(
        "/var/www"
        "/srv/apps"
        "/var/log/apps"
    )
    
    for dir in "${dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            log_info "  检查目录: $dir"
            
            # 检查是否为 www 用户所有
            local owner=$(stat -c '%U' "$dir" 2>/dev/null || stat -f '%Su' "$dir" 2>/dev/null || echo "unknown")
            
            if [[ "$owner" == "www" ]]; then
                log_warn "  删除目录: $dir (所有者: www)"
                echo -ne "${YELLOW}  确认删除 $dir 吗? (y/N): ${NC}"
                read -r confirm
                if [[ "$confirm" =~ ^[Yy]$ ]]; then
                    rm -rf "$dir"
                    log_success "  已删除: $dir"
                else
                    log_info "  保留目录: $dir"
                fi
            else
                log_info "  保留目录: $dir (所有者: $owner, 非 www 用户)"
            fi
        fi
    done
}

# ==============================================================================
# 清理环境变量配置
# ==============================================================================
clean_env_file() {
    local env_file="/opt/infra/.env"
    
    if [[ ! -f "$env_file" ]]; then
        log_info "环境文件不存在: $env_file"
        return 0
    fi
    
    log_info "从环境文件中删除 WWW_UID 和 WWW_GID..."
    
    # 备份原文件
    cp "$env_file" "${env_file}.backup.$(date +%Y%m%d_%H%M%S)"
    
    # 删除 WWW_UID 和 WWW_GID 配置
    sed -i.tmp '/^WWW_UID=/d; /^WWW_GID=/d' "$env_file"
    rm -f "${env_file}.tmp"
    
    log_success "已从 $env_file 删除 WWW_UID/WWW_GID 配置"
    log_info "  备份文件: ${env_file}.backup.*"
}

# ==============================================================================
# 主函数
# ==============================================================================
main() {
    log_info "========================================"
    log_info "用户重置脚本 v1.0"
    log_info "执行时间: $(date)"
    log_info "========================================"
    
    # 检查权限
    check_root
    
    # 显示警告
    echo
    log_warn "$(echo -e "${RED}${BOLD}警告: 此操作将删除以下用户及其所有数据:${NC}")"
    echo
    echo "  1. yangshujie"
    echo "     • Home 目录: /home/yangshujie"
    echo "     • sudo 权限配置"
    echo
    echo "  2. deploy"
    echo "     • Home 目录: /home/deploy"
    echo "     • sudo 权限配置"
    echo "     • deployctl 工具"
    echo
    echo "  3. www"
    echo "     • Home 目录: /var/www"
    echo "     • 业务目录: /srv/apps, /var/log/apps (需确认)"
    echo "     • 环境变量: WWW_UID, WWW_GID"
    echo
    log_warn "此操作不可逆！请确保已备份重要数据。"
    echo
    echo -ne "${YELLOW}${BOLD}确认继续执行吗? (yes/NO): ${NC}"
    read -r confirm
    
    if [[ "$confirm" != "yes" ]]; then
        log_info "操作已取消"
        exit 0
    fi
    
    echo
    log_info "========================================"
    log_info "开始删除用户..."
    log_info "========================================"
    
    # 删除用户（顺序：先删除普通用户，最后删除系统用户）
    remove_user "yangshujie"
    echo
    remove_user "deploy"
    echo
    
    # 清理 www 用户的目录（需要用户确认）
    clean_www_directories
    echo
    
    # 删除 www 用户
    remove_user "www"
    echo
    
    # 清理环境变量配置
    clean_env_file
    
    # 完成
    echo
    log_success "========================================"
    log_success "用户重置完成！"
    log_success "========================================"
    echo
    log_info "已删除的用户: yangshujie, deploy, www"
    log_info "现在可以重新运行 init-users.sh 来初始化用户"
    echo
    log_info "命令示例:"
    log_info "  sudo ./scripts/server/init-users.sh"
    log_info "  或"
    log_info "  make server-init-users"
    echo
}

# 执行主函数
main "$@"
