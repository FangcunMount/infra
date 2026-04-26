#!/usr/bin/env bash
set -euo pipefail

# 交互式 Linux 初始化脚本
# 目标: 在 serverA/serverB/serverC/serverD 上完成通用系统初始化。

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NETWORK_DIR="${PROJECT_ROOT}/scripts/01-network"

ASSUME_YES=false
NON_INTERACTIVE=false

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step() { echo -e "${CYAN}[STEP]${NC} $*"; }

show_help() {
    cat <<EOF
交互式 Linux 初始化脚本

用法:
  sudo $0
  sudo $0 --yes
  sudo $0 --non-interactive

选项:
  --yes              使用推荐默认项,仍保留子脚本自身的交互
  --non-interactive  尽量无交互执行推荐初始化项
  -h, --help         显示帮助

推荐在每台新服务器上执行:
  sudo bash scripts/00-server/initialize.sh
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --yes|-y)
                ASSUME_YES=true
                shift
                ;;
            --non-interactive)
                ASSUME_YES=true
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

check_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        log_error "此脚本必须以 root 权限运行"
        echo "使用方法: sudo $0"
        exit 1
    fi
}

confirm() {
    local prompt="$1"
    local default="${2:-N}"

    if [[ "${ASSUME_YES}" == true ]]; then
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

prompt_text() {
    local prompt="$1"
    local default="${2:-}"

    if [[ "${NON_INTERACTIVE}" == true ]]; then
        echo "${default}"
        return 0
    fi

    read -r -p "${prompt}" value
    echo "${value:-$default}"
}

require_script() {
    local script="$1"
    if [[ ! -f "${script}" ]]; then
        log_error "缺少脚本: ${script}"
        exit 1
    fi
}

run_step() {
    local name="$1"
    local script="$2"
    shift 2

    require_script "${script}"
    echo
    log_step "${name}"
    log_info "执行: ${script} $*"

    if bash "${script}" "$@"; then
        log_success "${name} 完成"
        return 0
    fi

    log_error "${name} 失败"
    return 1
}

show_plan() {
    local host_ip
    host_ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"

    cat <<EOF

================================================================================
Linux 初始化计划
================================================================================

当前机器:
  hostname: $(hostname)
  ip:       ${host_ip:-unknown}

推荐初始化项:
  1. 用户模型: root + yangshujie + deploy + www
  2. Docker Engine + Docker Compose
  3. 宿主机参数调优
  4. deploy 受限 SSH 公钥配置
  5. VPN/Mihomo 代理配置（可选）

不会自动执行:
  - Docker Swarm init/join
  - 业务组件启动
  - Mongo/NSQ/Nginx 等服务部署

EOF
}

configure_deploy_ssh_interactive() {
    local script="${SCRIPT_DIR}/setup-deploy-ssh.sh"
    require_script "${script}"

    if [[ "${NON_INTERACTIVE}" == true ]]; then
        log_warn "非交互模式缺少 CI 公钥输入,跳过 deploy SSH 配置"
        return 0
    fi

    echo
    log_info "请粘贴 GitHub Actions deploy 公钥,留空则跳过。"
    local public_key
    public_key="$(prompt_text "CI public key: ")"

    if [[ -z "${public_key}" ]]; then
        log_info "跳过 deploy SSH 配置"
        return 0
    fi

    run_step "配置 deploy 受限 SSH" "${script}" "${public_key}"
}

show_completion() {
    cat <<EOF

================================================================================
Linux 初始化流程结束
================================================================================

建议继续按目标机器角色执行:
  serverA: Swarm manager, nginx + qs-apiserver
  serverB: Swarm manager, qs-collection-server + IAM
  serverC: Swarm worker,  mongodb
  serverD: Swarm manager, qs-worker + operating + nsq

下一步常用命令:
  make swarm-init                         # serverA 初始化 Swarm
  make swarm-join-manager                 # serverB/serverD 加入 manager
  make swarm-join-worker                  # serverC 加入 worker
  make init ENV=prod INIT_TARGET=serverA  # 按节点初始化 infra 网络和目录

EOF
}

main() {
    parse_args "$@"
    check_root

    mkdir -p /var/log/infra-init
    exec > >(tee -a "/var/log/infra-init/system-init-$(date +%Y%m%d_%H%M%S).log")
    exec 2> >(tee -a "/var/log/infra-init/system-init-$(date +%Y%m%d_%H%M%S).err" >&2)

    show_plan

    if ! confirm "开始交互式 Linux 初始化?" "Y"; then
        log_info "用户取消执行"
        exit 0
    fi

    local completed=0
    local failed=0

    if confirm "初始化 4 类 Linux 用户?" "Y"; then
        local -a args=()
        if [[ "${NON_INTERACTIVE}" == true ]]; then
            args+=(--non-interactive)
        fi
        if run_step "初始化用户模型" "${SCRIPT_DIR}/init-users.sh" "${args[@]}"; then
            ((completed+=1))
        else
            ((failed+=1))
        fi
    fi

    if confirm "安装或更新 Docker Engine/Compose?" "Y"; then
        if run_step "安装 Docker" "${SCRIPT_DIR}/install-docker.sh"; then
            ((completed+=1))
        else
            ((failed+=1))
        fi
    fi

    if confirm "执行宿主机参数调优?" "Y"; then
        if run_step "宿主机参数调优" "${SCRIPT_DIR}/tune-host.sh"; then
            ((completed+=1))
        else
            ((failed+=1))
        fi
    fi

    if confirm "现在配置 deploy 的 CI/CD SSH 公钥?" "N"; then
        if configure_deploy_ssh_interactive; then
            ((completed+=1))
        else
            ((failed+=1))
        fi
    fi

    if [[ -f "${NETWORK_DIR}/vpn-setup.sh" ]] && confirm "安装配置 VPN/Mihomo 代理?" "N"; then
        if run_step "安装配置 VPN/Mihomo" "${NETWORK_DIR}/vpn-setup.sh"; then
            ((completed+=1))
        else
            ((failed+=1))
        fi
    fi

    echo
    log_info "执行统计: completed=${completed}, failed=${failed}"

    if [[ "${failed}" -gt 0 ]]; then
        log_warn "部分步骤失败,请根据日志修复后重跑对应步骤"
        exit 1
    fi

    show_completion
}

main "$@"
