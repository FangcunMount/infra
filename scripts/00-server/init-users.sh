#!/usr/bin/env bash
set -euo pipefail

# Linux 用户初始化脚本
#
# 维护四类身份:
# 1. root        - 系统引导和紧急维护用户,不创建,只做基础 shell 环境整理
# 2. yangshujie  - 人工运维登录用户,可 sudo,不加入 docker 组
# 3. deploy      - CI/CD 部署用户,密码锁定,仅通过 SSH key + 受限 sudo 使用
# 4. www         - 业务运行时用户,不可登录,无 sudo/docker 权限,仅用于 UID/GID 映射

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

NON_INTERACTIVE=false
ENV_FILE="${ENV_FILE:-/opt/infra/.env}"
OPS_USER="${OPS_USER:-yangshujie}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
RUNTIME_USER="${RUNTIME_USER:-www}"
RUNTIME_HOME="${RUNTIME_HOME:-/var/www}"
RUNTIME_UID="${RUNTIME_UID:-2000}"
RUNTIME_GID="${RUNTIME_GID:-2000}"

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step() { echo -e "${CYAN}[STEP]${NC} $*"; }

handle_error() {
    local line_number=$1
    log_error "脚本在第 ${line_number} 行执行失败"
    log_warn "请检查用户、sudoers、目录权限是否处于半初始化状态"
    echo "  id ${OPS_USER}; id ${DEPLOY_USER}; id ${RUNTIME_USER}"
    echo "  ls -la /home/${OPS_USER} /home/${DEPLOY_USER} ${RUNTIME_HOME} 2>/dev/null"
    echo "  sudo visudo -c"
    exit 1
}

trap 'handle_error $LINENO' ERR

show_help() {
    cat <<EOF
Linux 用户初始化脚本

用法:
  sudo $0
  sudo $0 --non-interactive

环境变量:
  OPS_USER       人工运维用户,默认: ${OPS_USER}
  DEPLOY_USER    CI/CD 部署用户,默认: ${DEPLOY_USER}
  RUNTIME_USER   业务运行时用户,默认: ${RUNTIME_USER}
  RUNTIME_HOME   运行时用户 home,默认: ${RUNTIME_HOME}
  RUNTIME_UID    运行时用户 UID,默认: ${RUNTIME_UID}
  RUNTIME_GID    运行时用户 GID,默认: ${RUNTIME_GID}
  ENV_FILE       UID/GID 输出文件,默认: ${ENV_FILE}

说明:
  - ${OPS_USER} 拥有 sudo 权限,不加入 docker 组
  - ${DEPLOY_USER} 密码锁定,不加入 docker 组,通过 /etc/sudoers.d/deploy-cicd 受限提权
  - ${RUNTIME_USER} 使用 nologin,不允许 SSH/交互登录
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
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

confirm() {
    local prompt="$1"
    local default="${2:-N}"

    if [[ "${NON_INTERACTIVE}" == true ]]; then
        [[ "${default}" =~ ^[Yy]$ ]]
        return $?
    fi

    local suffix
    if [[ "${default}" =~ ^[Yy]$ ]]; then
        suffix="Y/n"
    else
        suffix="y/N"
    fi

    read -r -p "${prompt} (${suffix}): " reply
    reply="${reply:-$default}"
    [[ "${reply}" =~ ^[Yy]$ ]]
}

check_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        log_error "此脚本必须以 root 权限运行"
        echo "使用方法: sudo $0"
        exit 1
    fi
}

detect_os() {
    if [[ -f /etc/os-release ]]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        log_info "检测到系统: ${PRETTY_NAME:-${NAME:-unknown}}"
    else
        log_warn "无法读取 /etc/os-release, 将按通用 Linux 继续"
    fi
}

check_dependencies() {
    local deps=(useradd usermod groupadd groupmod chpasswd chmod chown getent id passwd)
    local missing=()

    for dep in "${deps[@]}"; do
        if ! command -v "${dep}" >/dev/null 2>&1; then
            missing+=("${dep}")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "缺少必要命令: ${missing[*]}"
        exit 1
    fi

    if ! command -v visudo >/dev/null 2>&1; then
        log_error "缺少 visudo, 请先安装 sudo 包"
        exit 1
    fi

    log_success "依赖命令检查通过"
}

nologin_shell() {
    if [[ -x /usr/sbin/nologin ]]; then
        echo "/usr/sbin/nologin"
    elif [[ -x /sbin/nologin ]]; then
        echo "/sbin/nologin"
    else
        echo "/bin/false"
    fi
}

sudo_group_name() {
    if getent group sudo >/dev/null 2>&1; then
        echo "sudo"
    elif getent group wheel >/dev/null 2>&1; then
        echo "wheel"
    else
        log_error "系统缺少 sudo/wheel 管理组"
        exit 1
    fi
}

user_in_group() {
    local user="$1"
    local group="$2"

    id -nG "${user}" 2>/dev/null | tr ' ' '\n' | grep -qx "${group}"
}

remove_from_group_if_present() {
    local user="$1"
    local group="$2"

    if ! getent group "${group}" >/dev/null 2>&1; then
        return 0
    fi
    if ! id "${user}" >/dev/null 2>&1; then
        return 0
    fi
    if ! user_in_group "${user}" "${group}"; then
        return 0
    fi

    log_warn "移除 ${user} 的 ${group} 组权限"
    if command -v gpasswd >/dev/null 2>&1; then
        gpasswd -d "${user}" "${group}" >/dev/null || true
    else
        log_warn "系统缺少 gpasswd, 请手动执行: gpasswd -d ${user} ${group}"
    fi
}

ensure_root_environment() {
    log_step "维护 root 用户环境"

    install -d -m 700 /root
    install -d -m 755 /root/workspace
    install -d -m 755 /root/bin

    local bashrc="/root/.bashrc"
    local marker="# === INFRA ROOT CONFIG ==="
    touch "${bashrc}"
    chmod 644 "${bashrc}"

    if grep -q "${marker}" "${bashrc}" 2>/dev/null; then
        log_info "root .bashrc 已包含 infra 配置,跳过"
        return 0
    fi

    cp "${bashrc}" "${bashrc}.backup.$(date +%Y%m%d_%H%M%S)"
    cat >>"${bashrc}" <<'EOF'

# === INFRA ROOT CONFIG ===
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'

export LANG="en_US.UTF-8"
export WORKSPACE="/root/workspace"
export PATH="/root/bin:$PATH"
export PS1='[\u@\h \W]# '

if [[ $- == *i* ]] && [[ -d "$WORKSPACE" ]]; then
    cd "$WORKSPACE"
fi

if command -v docker >/dev/null 2>&1; then
    alias dps='docker ps'
    alias dpsa='docker ps -a'
    alias di='docker images'
    alias dlog='docker logs -f'
    alias dexec='docker exec -it'
fi
# === END INFRA ROOT CONFIG ===
EOF

    log_success "root 用户环境已维护"
}

ensure_login_user() {
    local user="$1"

    if id "${user}" >/dev/null 2>&1; then
        log_info "用户 ${user} 已存在,更新 shell/home 基础配置"
        usermod -s /bin/bash "${user}"
    else
        log_info "创建可登录用户 ${user}"
        useradd -m -s /bin/bash "${user}"
        log_success "用户 ${user} 已创建"
    fi

    install -d -o "${user}" -g "${user}" -m 755 "/home/${user}"
    install -d -o "${user}" -g "${user}" -m 755 "/home/${user}/workspace"
    install -d -o "${user}" -g "${user}" -m 755 "/home/${user}/bin"
}

set_user_password_interactive() {
    local user="$1"
    local pass confirm

    if [[ "${NON_INTERACTIVE}" == true ]]; then
        log_warn "非交互模式: 跳过 ${user} 密码设置"
        return 0
    fi

    if ! confirm "是否设置/更新 ${user} 的登录密码?" "Y"; then
        log_info "跳过 ${user} 密码设置"
        return 0
    fi

    while true; do
        read -r -s -p "请输入 ${user} 的密码: " pass
        echo
        read -r -s -p "请再次输入 ${user} 的密码: " confirm
        echo

        if [[ -z "${pass}" ]]; then
            log_warn "密码不能为空"
        elif [[ "${pass}" != "${confirm}" ]]; then
            log_warn "两次密码不一致"
        elif [[ ${#pass} -lt 8 || ! "${pass}" =~ [A-Za-z] || ! "${pass}" =~ [0-9] ]]; then
            log_warn "密码至少 8 位,且包含字母和数字"
        else
            echo "${user}:${pass}" | chpasswd
            log_success "${user} 密码已设置"
            break
        fi
    done
}

grant_sudo() {
    local user="$1"
    local group
    group="$(sudo_group_name)"

    usermod -aG "${group}" "${user}"
    log_success "${user} 已加入 ${group} 管理组"
}

setup_user_bashrc() {
    local user="$1"
    local home="/home/${user}"
    local bashrc="${home}/.bashrc"
    local marker="# === INFRA USER CONFIG ==="

    touch "${bashrc}"
    chown "${user}:${user}" "${bashrc}"
    chmod 644 "${bashrc}"

    if grep -q "${marker}" "${bashrc}" 2>/dev/null; then
        log_info "${user} .bashrc 已包含 infra 配置,跳过"
        return 0
    fi

    cp "${bashrc}" "${bashrc}.backup.$(date +%Y%m%d_%H%M%S)"
    cat >>"${bashrc}" <<'EOF'

# === INFRA USER CONFIG ===
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias dps='sudo docker ps'
alias dpsa='sudo docker ps -a'
alias dlog='sudo docker logs -f'
alias dc='sudo docker compose'

export LANG="en_US.UTF-8"
export WORKSPACE="$HOME/workspace"
export PATH="$HOME/bin:$PATH"
export PS1='[\u@\h \W]\$ '

if [[ $- == *i* ]] && [[ -d "$WORKSPACE" ]]; then
    cd "$WORKSPACE"
fi
# === END INFRA USER CONFIG ===
EOF

    chown "${user}:${user}" "${bashrc}"
    log_success "${user} shell 环境已维护"
}

setup_deploy_user() {
    log_step "维护 ${DEPLOY_USER} CI/CD 部署用户"

    ensure_login_user "${DEPLOY_USER}"
    usermod -s /bin/bash "${DEPLOY_USER}"
    passwd -l "${DEPLOY_USER}" >/dev/null 2>&1 || true
    remove_from_group_if_present "${DEPLOY_USER}" docker
    remove_from_group_if_present "${DEPLOY_USER}" "$(sudo_group_name)"
    setup_user_bashrc "${DEPLOY_USER}"
    setup_deploy_sudoers

    log_success "${DEPLOY_USER} 已配置为密码锁定的 CI/CD 用户"
}

setup_deploy_sudoers() {
    local sudoers_file="/etc/sudoers.d/deploy-cicd"

    cat >"${sudoers_file}" <<EOF
# deploy 账户的 CI/CD sudo 白名单
# 仅供 GitHub Actions 自动部署使用。deploy 不加入 docker 组,通过 sudoers 显式授权。

Defaults:${DEPLOY_USER} !requiretty

${DEPLOY_USER} ALL=(root) NOPASSWD: \\
    /usr/bin/docker *, \\
    /usr/bin/docker-compose *, \\
    /usr/bin/true, \\
    /bin/true, \\
    /usr/bin/rsync *, \\
    /usr/bin/tar *, \\
    /usr/bin/mkdir *, \\
    /usr/bin/chown *, \\
    /usr/bin/chmod *, \\
    /usr/bin/rm *, \\
    /usr/bin/ls *, \\
    /usr/bin/namei *, \\
    /usr/bin/test *, \\
    /usr/bin/systemctl restart *.service, \\
    /usr/bin/systemctl status *.service, \\
    /usr/bin/systemctl reload *.service
EOF

    chmod 440 "${sudoers_file}"
    if visudo -c -f "${sudoers_file}" >/dev/null; then
        log_success "deploy sudoers 已写入 ${sudoers_file}"
    else
        rm -f "${sudoers_file}"
        log_error "deploy sudoers 语法校验失败"
        return 1
    fi
}

setup_runtime_user() {
    log_step "维护 ${RUNTIME_USER} 业务运行时用户"

    local shell
    shell="$(nologin_shell)"

    if [[ ! "${RUNTIME_UID}" =~ ^[0-9]+$ || ! "${RUNTIME_GID}" =~ ^[0-9]+$ ]]; then
        log_error "RUNTIME_UID/RUNTIME_GID 必须是数字: ${RUNTIME_UID}:${RUNTIME_GID}"
        return 1
    fi

    local owner
    owner="$(getent passwd "${RUNTIME_UID}" | cut -d: -f1 || true)"
    if [[ -n "${owner}" && "${owner}" != "${RUNTIME_USER}" ]]; then
        log_error "RUNTIME_UID=${RUNTIME_UID} 已被用户 ${owner} 占用"
        return 1
    fi

    owner="$(getent group "${RUNTIME_GID}" | cut -d: -f1 || true)"
    if [[ -n "${owner}" && "${owner}" != "${RUNTIME_USER}" ]]; then
        log_error "RUNTIME_GID=${RUNTIME_GID} 已被用户组 ${owner} 占用"
        return 1
    fi

    if getent group "${RUNTIME_USER}" >/dev/null 2>&1; then
        local current_gid
        current_gid="$(getent group "${RUNTIME_USER}" | cut -d: -f3)"
        if [[ "${current_gid}" != "${RUNTIME_GID}" ]]; then
            log_info "更新 ${RUNTIME_USER} 组 GID: ${current_gid} -> ${RUNTIME_GID}"
            groupmod -g "${RUNTIME_GID}" "${RUNTIME_USER}"
        fi
    else
        groupadd --gid "${RUNTIME_GID}" "${RUNTIME_USER}"
    fi

    if id "${RUNTIME_USER}" >/dev/null 2>&1; then
        local current_uid
        current_uid="$(id -u "${RUNTIME_USER}")"
        log_info "用户 ${RUNTIME_USER} 已存在,更新为不可登录运行时用户"
        if [[ "${current_uid}" != "${RUNTIME_UID}" ]]; then
            log_info "更新 ${RUNTIME_USER} 用户 UID: ${current_uid} -> ${RUNTIME_UID}"
        fi
        usermod -u "${RUNTIME_UID}" -d "${RUNTIME_HOME}" -s "${shell}" -g "${RUNTIME_USER}" "${RUNTIME_USER}"
    else
        useradd --uid "${RUNTIME_UID}" --home "${RUNTIME_HOME}" --shell "${shell}" --gid "${RUNTIME_USER}" "${RUNTIME_USER}"
        log_success "运行时用户 ${RUNTIME_USER} 已创建"
    fi

    passwd -l "${RUNTIME_USER}" >/dev/null 2>&1 || true
    remove_from_group_if_present "${RUNTIME_USER}" docker
    remove_from_group_if_present "${RUNTIME_USER}" "$(sudo_group_name)"
    setup_runtime_directories
    write_runtime_env
}

setup_runtime_directories() {
    local dirs=(
        "/data"
        "${RUNTIME_HOME}"
        "/var/www/certbot"
        "/srv/apps"
        "/var/log/apps"
        "/data/apps"
        "/data/image"
        "/data/infra"
        "/data/logs"
        "/data/ops"
        "/data/ssl"
    )

    for dir in "${dirs[@]}"; do
        local owner="${RUNTIME_USER}:${RUNTIME_USER}"
        local mode="755"

        case "${dir}" in
            /data/image|/data/ops)
                owner="root:root"
                ;;
            "${RUNTIME_HOME}"|/srv/apps|/var/log/apps)
                mode="750"
                ;;
        esac

        install -d -o "${owner%%:*}" -g "${owner##*:}" -m "${mode}" "${dir}"
        log_info "目录已维护: ${dir} (${owner} ${mode})"
    done

    chmod 0777 /data/image
}

write_runtime_env() {
    local uid gid
    uid="$(id -u "${RUNTIME_USER}")"
    gid="$(id -g "${RUNTIME_USER}")"

    install -d -m 755 "$(dirname "${ENV_FILE}")"
    touch "${ENV_FILE}"

    cp "${ENV_FILE}" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    sed -i \
        -e '/^RUNTIME_USER=/d' \
        -e '/^RUNTIME_GROUP=/d' \
        -e '/^WWW_UID=/d' \
        -e '/^WWW_GID=/d' \
        -e '/^APP_UID=/d' \
        -e '/^APP_GID=/d' \
        "${ENV_FILE}"

    cat >>"${ENV_FILE}" <<EOF

# Runtime user for application containers.
RUNTIME_USER=${RUNTIME_USER}
RUNTIME_GROUP=${RUNTIME_USER}
WWW_UID=${uid}
WWW_GID=${gid}
APP_UID=${uid}
APP_GID=${gid}
EOF

    log_success "运行时 UID/GID 已写入 ${ENV_FILE}"
    log_info "WWW_UID=${uid}, WWW_GID=${gid}"
}

show_plan() {
    cat <<EOF

将维护以下 Linux 用户模型:

  root
    - 系统引导和紧急维护用户
    - 只维护 /root/workspace、/root/bin、基础 .bashrc

  ${OPS_USER}
    - 你的人工登录用户
    - 加入 sudo/wheel 管理组
    - 不加入 docker 组,使用 sudo docker

  ${DEPLOY_USER}
    - GitHub Actions / CI/CD 部署用户
    - 密码锁定,不加入 sudo/docker 组
    - 通过 /etc/sudoers.d/deploy-cicd 获得最小部署权限
    - SSH 公钥建议使用 setup-deploy-ssh.sh 配置受限入口

  ${RUNTIME_USER}
    - 业务运行时 UID/GID 用户
    - 固定 UID/GID: ${RUNTIME_UID}:${RUNTIME_GID}
    - shell 为 nologin,不可交互登录
    - 拥有运行时目录和容器挂载目录

EOF
}

verify_user() {
    local user="$1"

    if id "${user}" >/dev/null 2>&1; then
        log_success "用户存在: ${user} ($(id -u "${user}"):$(id -g "${user}"))"
    else
        log_error "用户不存在: ${user}"
        return 1
    fi
}

verify_setup() {
    log_step "验证用户模型"

    verify_user root
    verify_user "${OPS_USER}"
    verify_user "${DEPLOY_USER}"
    verify_user "${RUNTIME_USER}"

    if ! user_in_group "${OPS_USER}" "$(sudo_group_name)"; then
        log_error "${OPS_USER} 不在 sudo/wheel 管理组"
        return 1
    fi

    for user in "${OPS_USER}" "${DEPLOY_USER}" "${RUNTIME_USER}"; do
        if user_in_group "${user}" docker; then
            log_warn "${user} 仍在 docker 组,建议移除"
        fi
    done

    local runtime_shell
    runtime_shell="$(getent passwd "${RUNTIME_USER}" | cut -d: -f7)"
    case "${runtime_shell}" in
        /usr/sbin/nologin|/sbin/nologin|/bin/false)
            log_success "${RUNTIME_USER} 已禁止交互登录"
            ;;
        *)
            log_error "${RUNTIME_USER} shell 异常: ${runtime_shell}"
            return 1
            ;;
    esac

    if [[ ! -f "${ENV_FILE}" ]] || ! grep -q '^WWW_UID=' "${ENV_FILE}"; then
        log_error "${ENV_FILE} 缺少 WWW_UID/WWW_GID"
        return 1
    fi

    log_success "用户模型验证完成"
}

main() {
    parse_args "$@"
    check_root
    detect_os
    check_dependencies
    show_plan

    if ! confirm "确认开始维护上述 4 类用户?" "Y"; then
        log_info "用户取消执行"
        exit 0
    fi

    mkdir -p /var/log/infra-init
    exec > >(tee -a "/var/log/infra-init/init-users-$(date +%Y%m%d_%H%M%S).log")
    exec 2> >(tee -a "/var/log/infra-init/init-users-$(date +%Y%m%d_%H%M%S).err" >&2)

    ensure_root_environment

    log_step "维护 ${OPS_USER} 人工运维用户"
    ensure_login_user "${OPS_USER}"
    grant_sudo "${OPS_USER}"
    remove_from_group_if_present "${OPS_USER}" docker
    setup_user_bashrc "${OPS_USER}"
    set_user_password_interactive "${OPS_USER}"

    setup_deploy_user
    setup_runtime_user
    verify_setup

    cat <<EOF

用户初始化完成:
  root:        已维护 shell 环境
  ${OPS_USER}: sudo 用户,不在 docker 组
  ${DEPLOY_USER}: 密码锁定,受限 sudo,等待配置 CI 公钥
  ${RUNTIME_USER}: nologin 运行时用户,UID/GID 已写入 ${ENV_FILE}

下一步:
  sudo bash scripts/00-server/setup-deploy-ssh.sh "\$(cat ~/.ssh/deploy_key.pub)"
  sudo bash scripts/00-server/install-docker.sh

EOF
}

main "$@"
