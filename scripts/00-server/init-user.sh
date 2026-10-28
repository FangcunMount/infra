#!/usr/bin/env bash
set -euo pipefail

# 独立新增一个 Linux 登录用户，复用批量脚本的 shell、密码和 sudo 配置。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=init-users.sh
# shellcheck source-path=SCRIPTDIR
source "${SCRIPT_DIR}/init-users.sh"

INIT_USER=""
INIT_USER_SUDO=false

init_user_help() {
    cat <<EOF
独立新增一个 Linux 登录用户

用法:
  sudo bash $0 --username alice
  sudo bash $0 --username alice --sudo
  sudo bash $0 --username alice --non-interactive

选项:
  --username NAME    必填，新增的用户名
  --sudo             加入 sudo/wheel 管理组，默认不授予 sudo 权限
  --non-interactive  跳过确认和密码设置，随后需另行配置密码或 SSH 公钥
  -h, --help         显示帮助

只新增指定用户及 /home/NAME 下的 home、workspace、bin 和 .bashrc。
用户名已存在时退出，不修改已有账户；不加入 docker 组。
EOF
}

init_user_parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --username)
                if [[ $# -lt 2 || -z "$2" || "$2" == --* ]]; then
                    log_error "--username 需要指定用户名"
                    return 1
                fi
                INIT_USER="$2"
                shift 2
                ;;
            --sudo)
                INIT_USER_SUDO=true
                shift
                ;;
            --non-interactive)
                NON_INTERACTIVE=true
                shift
                ;;
            -h|--help)
                init_user_help
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                init_user_help
                return 1
                ;;
        esac
    done

    if [[ ! "${INIT_USER}" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
        log_error "请通过 --username 指定 1–32 位用户名：小写字母或下划线开头，仅含小写字母、数字、下划线和连字符"
        return 1
    fi
}

init_user_preflight() {
    local dep
    local deps=(useradd getent id install touch chmod chown cp grep chpasswd)
    if [[ "${INIT_USER_SUDO}" == true ]]; then
        deps+=(usermod)
    fi
    for dep in "${deps[@]}"; do
        if ! command -v "${dep}" >/dev/null 2>&1; then
            log_error "缺少必要命令: ${dep}，请在 Linux 服务器上运行"
            return 1
        fi
    done

    if id "${INIT_USER}" >/dev/null 2>&1; then
        log_error "用户 ${INIT_USER} 已存在，不修改已有账户"
        return 1
    fi
    if getent group "${INIT_USER}" >/dev/null 2>&1; then
        log_error "同名用户组 ${INIT_USER} 已存在，请选择其他用户名"
        return 1
    fi
    if [[ -e "/home/${INIT_USER}" || -L "/home/${INIT_USER}" ]]; then
        log_error "/home/${INIT_USER} 已存在，不接管已有目录"
        return 1
    fi
    if [[ "${INIT_USER_SUDO}" == true ]]; then
        sudo_group_name >/dev/null
    fi
}

init_user_main() {
    init_user_parse_args "$@"
    check_root
    init_user_preflight

    log_info "新增用户 ${INIT_USER}，home=/home/${INIT_USER}，sudo=${INIT_USER_SUDO}"
    if ! confirm "确认新增此用户?" "Y"; then
        log_info "用户取消执行"
        return 0
    fi

    # 显式创建同名主组，不依赖服务器的 USERGROUPS_ENAB 默认配置。
    useradd -m -U -d "/home/${INIT_USER}" -s /bin/bash -- "${INIT_USER}"
    install -d -o "${INIT_USER}" -g "${INIT_USER}" -m 755 "/home/${INIT_USER}/workspace"
    install -d -o "${INIT_USER}" -g "${INIT_USER}" -m 755 "/home/${INIT_USER}/bin"
    setup_user_bashrc "${INIT_USER}"
    if [[ "${INIT_USER_SUDO}" == true ]]; then
        grant_sudo "${INIT_USER}"
    fi
    set_user_password_interactive "${INIT_USER}"

    verify_user "${INIT_USER}"
    log_success "单用户初始化完成: ${INIT_USER}"
    log_info "如未设置密码，请另行执行 sudo passwd ${INIT_USER} 或配置该用户的 SSH 公钥"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    init_user_main "$@"
fi
