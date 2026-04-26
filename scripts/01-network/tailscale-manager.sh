#!/usr/bin/env bash
set -euo pipefail

# Tailscale helper for the four-node Swarm underlay.
# Goal: keep Mihomo as an application proxy, and use Tailscale only as the
# encrypted node-to-node network for Docker Swarm advertise/data-path.

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step() { echo -e "${CYAN}[STEP]${NC} $*"; }

TAILSCALE_HOSTNAME="${TAILSCALE_HOSTNAME:-$(hostname -s 2>/dev/null || hostname)}"
TAILSCALE_AUTH_KEY="${TAILSCALE_AUTH_KEY:-}"
TAILSCALE_EXTRA_ARGS="${TAILSCALE_EXTRA_ARGS:-}"

show_help() {
    cat <<EOF
Tailscale Swarm underlay 管理脚本

用法:
  sudo $0 install
  sudo $0 up
  $0 status
  $0 ip
  sudo $0 check
  $0 swarm-env

环境变量:
  TAILSCALE_HOSTNAME   Tailscale 设备名,默认: ${TAILSCALE_HOSTNAME}
  TAILSCALE_AUTH_KEY   可选,用于非交互登录
  TAILSCALE_EXTRA_ARGS 可选,追加给 tailscale up 的参数

设计约束:
  - Tailscale 只承载节点互联,不启用 exit-node/subnet-route/DNS 接管。
  - Mihomo 继续作为应用代理,不要让 Mihomo TUN 劫持 100.64.0.0/10。
  - Swarm advertise/data-path 使用 tailscale ip -4 输出的地址。
EOF
}

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        log_error "此操作需要 root 权限"
        exit 1
    fi
}

require_tailscale() {
    if ! command -v tailscale >/dev/null 2>&1; then
        log_error "tailscale 未安装。请先执行: sudo $0 install"
        exit 1
    fi
}

install_tailscale() {
    require_root

    if command -v tailscale >/dev/null 2>&1; then
        log_success "tailscale 已安装: $(tailscale version | head -n1)"
        return 0
    fi

    log_step "安装 Tailscale"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL https://tailscale.com/install.sh | sh
    else
        log_error "缺少 curl，无法执行官方安装脚本"
        exit 1
    fi

    systemctl enable --now tailscaled
    log_success "tailscale 安装完成"
}

tailscale_up() {
    require_root
    require_tailscale

    log_step "启动 Tailscale: ${TAILSCALE_HOSTNAME}"
    systemctl enable --now tailscaled

    local args=(
        up
        --hostname="${TAILSCALE_HOSTNAME}"
        --accept-dns=false
        --accept-routes=false
        --ssh=false
    )

    if [[ -n "${TAILSCALE_AUTH_KEY}" ]]; then
        args+=(--auth-key="${TAILSCALE_AUTH_KEY}")
    fi

    if [[ -n "${TAILSCALE_EXTRA_ARGS}" ]]; then
        # shellcheck disable=SC2206
        local extra_args=( ${TAILSCALE_EXTRA_ARGS} )
        args+=("${extra_args[@]}")
    fi

    tailscale "${args[@]}"
    log_success "Tailscale 已启动"
    print_ip
}

print_ip() {
    require_tailscale

    local ip
    ip="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
    if [[ -z "${ip}" ]]; then
        log_error "未获取到 Tailscale IPv4，请先登录 tailscale up"
        exit 1
    fi

    echo "${ip}"
}

show_status() {
    require_tailscale

    log_step "Tailscale 状态"
    tailscale status || true
    echo
    log_info "本机 Tailscale IPv4:"
    print_ip
}

print_swarm_env() {
    local ip
    ip="$(print_ip)"

    cat <<EOF
SWARM_ADVERTISE_ADDR=${ip}
SWARM_DATA_PATH_ADDR=${ip}
INFRA_NETWORK_ENCRYPTED=false
EOF
}

check_mihomo_conflict() {
    local mihomo_active=false
    if systemctl is-active --quiet mihomo 2>/dev/null || systemctl is-active --quiet mihomo.service 2>/dev/null || pgrep -f "mihomo" >/dev/null 2>&1; then
        mihomo_active=true
    fi

    if [[ "${mihomo_active}" != "true" ]]; then
        log_info "未检测到运行中的 Mihomo"
        return 0
    fi

    log_warn "检测到 Mihomo 正在运行。Tailscale 可以共存，但需要确保以下流量 DIRECT:"
    cat <<'EOF'
  - IP-CIDR,100.64.0.0/10,DIRECT,no-resolve
  - IP-CIDR,100.100.100.100/32,DIRECT,no-resolve
  - DOMAIN-SUFFIX,ts.net,DIRECT
  - DOMAIN-SUFFIX,tailscale.com,DIRECT

如果 Mihomo 开启 TUN/透明代理，请确认 Tailscale 流量没有被劫持。
本方案的推荐边界是：Mihomo 负责应用代理，Tailscale 负责节点互联。
EOF
}

check_routes() {
    require_tailscale

    local ip
    ip="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
    if [[ -z "${ip}" ]]; then
        log_error "Tailscale IPv4 不存在"
        return 1
    fi

    log_info "Tailscale IPv4: ${ip}"

    if ip route get 100.100.100.100 >/dev/null 2>&1; then
        log_info "MagicDNS 地址路由:"
        ip route get 100.100.100.100 || true
    fi

    if ip route | grep -q '^default .*tailscale0'; then
        log_warn "检测到默认路由可能走 tailscale。Swarm 节点网络不建议使用 exit-node。"
    else
        log_success "未检测到 Tailscale 接管默认路由"
    fi
}

run_check() {
    require_root
    require_tailscale

    log_step "检查 Tailscale / Mihomo / Swarm underlay"
    systemctl is-active --quiet tailscaled || {
        log_error "tailscaled 未运行"
        exit 1
    }

    check_routes
    check_mihomo_conflict

    echo
    log_success "检查完成。Swarm advertise/data-path 请使用:"
    print_swarm_env
}

main() {
    case "${1:-help}" in
        install) install_tailscale ;;
        up) tailscale_up ;;
        status) show_status ;;
        ip) print_ip ;;
        check) run_check ;;
        swarm-env) print_swarm_env ;;
        help|--help|-h) show_help ;;
        *)
            log_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
