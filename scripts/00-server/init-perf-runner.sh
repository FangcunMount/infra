#!/usr/bin/env bash
set -Eeuo pipefail

# 初始化一台独立的 qs-server K6 压测机。
#
# 设计边界：
# - 只安装压测客户端工具，不安装 Docker，也不把压测机加入生产 Swarm。
# - Go/k6 使用固定版本和官方校验和，重复执行不会重复安装相同版本。
# - 不接收、不生成、不打印 token 或数据库连接串。

readonly DEFAULT_WORKSPACE_ROOT="/opt/qs-perf"
readonly DEFAULT_GO_VERSION="1.25.12"
readonly DEFAULT_K6_VERSION="v1.5.0"
readonly DEFAULT_QS_SERVER_REPO="https://github.com/FangcunMount/qs-server.git"
readonly DEFAULT_QS_SERVER_REF="main"
readonly DEFAULT_READY_URLS="https://collect.fangcunmount.cn/readyz https://qs.fangcunmount.cn/readyz"

ACTION="${1:-init}"
if [[ $# -gt 0 ]]; then
    shift
fi

PERF_WORKSPACE_ROOT="${PERF_WORKSPACE_ROOT:-${DEFAULT_WORKSPACE_ROOT}}"
PERF_GO_VERSION="${PERF_GO_VERSION:-${DEFAULT_GO_VERSION}}"
PERF_K6_VERSION="${PERF_K6_VERSION:-${DEFAULT_K6_VERSION}}"
PERF_QS_SERVER_REPO="${PERF_QS_SERVER_REPO:-${DEFAULT_QS_SERVER_REPO}}"
PERF_QS_SERVER_REF="${PERF_QS_SERVER_REF:-${DEFAULT_QS_SERVER_REF}}"
PERF_READY_URLS="${PERF_READY_URLS:-${DEFAULT_READY_URLS}}"
PERF_SKIP_REPO="${PERF_SKIP_REPO:-false}"
PERF_UPDATE_REPO="${PERF_UPDATE_REPO:-false}"
PERF_RUN_VERIFY="${PERF_RUN_VERIFY:-true}"
PERF_SKIP_NETWORK_CHECK="${PERF_SKIP_NETWORK_CHECK:-false}"
PERF_RUNNER_USER="${PERF_RUNNER_USER:-${SUDO_USER:-$(id -un)}}"
RUNNER_HOME_DIR=""
TMP_DIR=""

if [[ -t 1 ]]; then
    readonly RED=$'\033[0;31m'
    readonly GREEN=$'\033[0;32m'
    readonly YELLOW=$'\033[1;33m'
    readonly BLUE=$'\033[0;34m'
    readonly RESET=$'\033[0m'
else
    readonly RED=""
    readonly GREEN=""
    readonly YELLOW=""
    readonly BLUE=""
    readonly RESET=""
fi

log_info() { printf '%s[INFO]%s %s\n' "$BLUE" "$RESET" "$*"; }
log_ok() { printf '%s[OK]%s %s\n' "$GREEN" "$RESET" "$*"; }
log_warn() { printf '%s[WARN]%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
log_error() { printf '%s[ERROR]%s %s\n' "$RED" "$RESET" "$*" >&2; }

usage() {
    cat <<'EOF'
用法:
  sudo bash init-perf-runner.sh init
  bash init-perf-runner.sh check

可选环境变量:
  PERF_RUNNER_USER          压测执行用户，默认 sudo 发起用户
  PERF_WORKSPACE_ROOT       工作目录，默认 /opt/qs-perf
  PERF_GO_VERSION           Go 版本，默认 1.25.12
  PERF_K6_VERSION           k6 版本，默认 v1.5.0
  PERF_QS_SERVER_REPO       qs-server Git 地址
  PERF_QS_SERVER_REF        clone 的分支或 tag，默认 main
  PERF_SKIP_REPO            true 时只安装工具，不 clone qs-server
  PERF_UPDATE_REPO          true 时更新已有且干净的 qs-server checkout
  PERF_RUN_VERIFY           true 时执行 make perf-verify，默认 true
  PERF_READY_URLS           空格分隔的就绪探针 URL
  PERF_SKIP_NETWORK_CHECK   true 时跳过公网就绪探针
  PERF_GO_SHA256            可选，覆盖 Go 官方元数据中的 SHA256
EOF
}

is_true() {
    case "${1,,}" in
        1|true|yes|y) return 0 ;;
        *) return 1 ;;
    esac
}

require_linux() {
    if [[ "$(uname -s)" != "Linux" ]]; then
        log_error "压测机初始化仅支持 Linux；当前系统为 $(uname -s)"
        exit 1
    fi
}

require_root() {
    if [[ "$EUID" -ne 0 ]]; then
        log_error "init 必须以 root 运行，请使用 sudo 或远程初始化入口"
        exit 1
    fi
}

validate_config() {
    if [[ ! "$PERF_RUNNER_USER" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]]; then
        log_error "PERF_RUNNER_USER 不是有效的 Linux 用户名: $PERF_RUNNER_USER"
        exit 1
    fi
    if ! id "$PERF_RUNNER_USER" >/dev/null 2>&1; then
        log_error "压测执行用户不存在: $PERF_RUNNER_USER"
        exit 1
    fi
    RUNNER_HOME_DIR="$(getent passwd "$PERF_RUNNER_USER" | cut -d: -f6)"
    if [[ -z "$RUNNER_HOME_DIR" || ! -d "$RUNNER_HOME_DIR" ]]; then
        log_error "压测执行用户没有可用的 home 目录: $PERF_RUNNER_USER"
        exit 1
    fi
    case "$PERF_WORKSPACE_ROOT" in
        /*) ;;
        *) log_error "PERF_WORKSPACE_ROOT 必须是绝对路径"; exit 1 ;;
    esac
    if [[ ! "$PERF_WORKSPACE_ROOT" =~ ^/[a-zA-Z0-9._/-]+$ ]]; then
        log_error "PERF_WORKSPACE_ROOT 仅允许字母、数字、点、下划线、横线和斜线"
        exit 1
    fi
    case "$PERF_WORKSPACE_ROOT" in
        /|/bin|/boot|/dev|/etc|/home|/lib|/lib64|/opt|/proc|/root|/run|/sbin|/sys|/tmp|/usr|/var)
            log_error "PERF_WORKSPACE_ROOT 范围过大或不安全: $PERF_WORKSPACE_ROOT"
            exit 1
            ;;
    esac
    if [[ "$PERF_GO_VERSION" == *[!0-9.]* || "$PERF_K6_VERSION" != v* ]]; then
        log_error "版本格式无效: Go=$PERF_GO_VERSION, k6=$PERF_K6_VERSION"
        exit 1
    fi
}

detect_arch() {
    case "$(uname -m)" in
        x86_64|amd64) printf 'amd64\n' ;;
        aarch64|arm64) printf 'arm64\n' ;;
        *) log_error "不支持的 CPU 架构: $(uname -m)"; exit 1 ;;
    esac
}

install_packages() {
    log_info "安装基础工具与网络诊断工具"
    if command -v apt-get >/dev/null 2>&1; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update
        apt-get install -y --no-install-recommends \
            ca-certificates coreutils curl dnsutils findutils git gzip jq make mtr-tiny \
            procps sysstat tar util-linux xz-utils
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y \
            bind-utils ca-certificates coreutils curl findutils git gzip jq make \
            mtr procps-ng shadow-utils sysstat tar util-linux xz
    elif command -v yum >/dev/null 2>&1; then
        yum install -y \
            bind-utils ca-certificates coreutils curl findutils git gzip jq make \
            mtr procps-ng shadow-utils sysstat tar util-linux xz
    else
        log_error "不支持的包管理器；当前支持 apt、dnf 和 yum"
        exit 1
    fi
}

download() {
    local url="$1"
    local output="$2"
    curl --fail --location --silent --show-error \
        --retry 3 --retry-delay 2 --connect-timeout 15 \
        "$url" --output "$output"
}

verify_sha256() {
    local file="$1"
    local checksum="$2"
    if [[ ! "$checksum" =~ ^[0-9a-fA-F]{64}$ ]]; then
        log_error "无效的 SHA256: ${checksum:0:16}..."
        exit 1
    fi
    printf '%s  %s\n' "$checksum" "$file" | sha256sum --check --status
}

install_go() {
    local arch="$1"
    local tmp_dir="$2"
    local expected="go${PERF_GO_VERSION}"
    local current=""
    if [[ -x /usr/local/go/bin/go ]]; then
        current="$(/usr/local/go/bin/go env GOVERSION 2>/dev/null || true)"
    fi
    if [[ "$current" == "$expected" ]]; then
        log_ok "Go $PERF_GO_VERSION 已安装"
        return
    fi

    local filename="go${PERF_GO_VERSION}.linux-${arch}.tar.gz"
    local archive="${tmp_dir}/${filename}"
    local checksum="${PERF_GO_SHA256:-}"
    if [[ -z "$checksum" ]]; then
        local metadata="${tmp_dir}/go-downloads.json"
        download "https://go.dev/dl/?mode=json&include=all" "$metadata"
        checksum="$(jq -r --arg filename "$filename" \
            '.[] | .files[] | select(.filename == $filename) | .sha256' \
            "$metadata" | head -n 1)"
        if [[ -z "$checksum" || "$checksum" == "null" ]]; then
            log_error "Go 官方下载元数据中未找到 $filename"
            log_error "请确认版本，或通过 PERF_GO_SHA256 显式提供校验和"
            exit 1
        fi
    fi

    log_info "下载并校验 Go $PERF_GO_VERSION ($arch)"
    download "https://go.dev/dl/${filename}" "$archive"
    verify_sha256 "$archive" "$checksum"

    if [[ -e /usr/local/go ]]; then
        local backup="/usr/local/go.backup.$(date +%Y%m%d-%H%M%S)"
        mv /usr/local/go "$backup"
        log_warn "原 Go 目录已保留为 $backup"
    fi
    tar -C /usr/local -xzf "$archive"
    for binary in go gofmt; do
        if [[ ! -e "/usr/local/bin/${binary}" || -L "/usr/local/bin/${binary}" ]]; then
            ln -sfn "/usr/local/go/bin/${binary}" "/usr/local/bin/${binary}"
        fi
    done
    log_ok "Go $PERF_GO_VERSION 安装完成"
}

install_k6() {
    local arch="$1"
    local tmp_dir="$2"
    if command -v k6 >/dev/null 2>&1 && k6 version 2>/dev/null | grep -Fq "k6 ${PERF_K6_VERSION}"; then
        log_ok "k6 $PERF_K6_VERSION 已安装"
        return
    fi

    local filename="k6-${PERF_K6_VERSION}-linux-${arch}.tar.gz"
    local checksums_name="k6-${PERF_K6_VERSION}-checksums.txt"
    local release_base="https://github.com/grafana/k6/releases/download/${PERF_K6_VERSION}"
    local archive="${tmp_dir}/${filename}"
    local checksums="${tmp_dir}/${checksums_name}"

    log_info "下载并校验 k6 $PERF_K6_VERSION ($arch)"
    download "${release_base}/${filename}" "$archive"
    download "${release_base}/${checksums_name}" "$checksums"
    local checksum
    checksum="$(awk -v filename="$filename" '$2 == filename {print $1}' "$checksums" | head -n 1)"
    if [[ -z "$checksum" ]]; then
        log_error "k6 校验和文件中未找到 $filename"
        exit 1
    fi
    verify_sha256 "$archive" "$checksum"
    tar -C "$tmp_dir" -xzf "$archive"
    local binary
    binary="$(find "$tmp_dir" -type f -name k6 -perm -u+x -print -quit)"
    if [[ -z "$binary" ]]; then
        log_error "k6 压缩包内未找到可执行文件"
        exit 1
    fi
    install -m 0755 "$binary" /usr/local/bin/k6
    log_ok "k6 $PERF_K6_VERSION 安装完成"
}

configure_runner() {
    local runner_group
    runner_group="$(id -gn "$PERF_RUNNER_USER")"

    install -d -m 0755 -o "$PERF_RUNNER_USER" -g "$runner_group" "$PERF_WORKSPACE_ROOT"
    install -d -m 0755 -o "$PERF_RUNNER_USER" -g "$runner_group" \
        "$PERF_WORKSPACE_ROOT/bin" "$PERF_WORKSPACE_ROOT/runs"
    install -d -m 0700 -o "$PERF_RUNNER_USER" -g "$runner_group" \
        "$PERF_WORKSPACE_ROOT/secrets"

    local profile_file
    profile_file="$(mktemp)"
    printf '%s\n' \
        '# Managed by infra/scripts/00-server/init-perf-runner.sh' \
        'export PATH="/usr/local/go/bin:/usr/local/bin:$PATH"' \
        "export PERF_WORKSPACE_ROOT=\"${PERF_WORKSPACE_ROOT}\"" \
        "export PERF_RUN_ROOT=\"${PERF_WORKSPACE_ROOT}/runs\"" >"$profile_file"
    install -m 0644 "$profile_file" /etc/profile.d/qs-perf.sh
    rm -f "$profile_file"

    local limits_file
    limits_file="$(mktemp)"
    printf '%s soft nofile 65535\n%s hard nofile 65535\n' \
        "$PERF_RUNNER_USER" "$PERF_RUNNER_USER" >"$limits_file"
    install -m 0644 "$limits_file" /etc/security/limits.d/99-qs-perf-runner.conf
    rm -f "$limits_file"
    log_ok "工作目录与文件句柄上限已配置"
}

run_as_runner() {
    if [[ "$EUID" -eq 0 && "$PERF_RUNNER_USER" != "root" ]]; then
        runuser -u "$PERF_RUNNER_USER" -- \
            env HOME="$RUNNER_HOME_DIR" USER="$PERF_RUNNER_USER" LOGNAME="$PERF_RUNNER_USER" "$@"
    else
        "$@"
    fi
}

prepare_repository() {
    if is_true "$PERF_SKIP_REPO"; then
        log_warn "已跳过 qs-server clone 与工具链验证"
        return
    fi

    local repo_dir="${PERF_WORKSPACE_ROOT}/qs-server"
    if [[ ! -d "$repo_dir/.git" ]]; then
        log_info "clone qs-server ($PERF_QS_SERVER_REF)"
        run_as_runner git clone --depth 1 --branch "$PERF_QS_SERVER_REF" \
            "$PERF_QS_SERVER_REPO" "$repo_dir"
    elif is_true "$PERF_UPDATE_REPO"; then
        if [[ -n "$(run_as_runner git -C "$repo_dir" status --porcelain)" ]]; then
            log_warn "已有 qs-server checkout 存在未提交修改，跳过更新"
        else
            log_info "更新已有 qs-server checkout"
            run_as_runner git -C "$repo_dir" fetch --depth 1 origin "$PERF_QS_SERVER_REF"
            run_as_runner git -C "$repo_dir" checkout --detach FETCH_HEAD
        fi
    else
        log_ok "保留已有 qs-server checkout（PERF_UPDATE_REPO=false）"
    fi

    log_info "构建 perfctl"
    run_as_runner env PATH="/usr/local/go/bin:/usr/local/bin:${PATH}" \
        /usr/local/go/bin/go -C "$repo_dir" build \
        -o "${PERF_WORKSPACE_ROOT}/bin/perfctl" ./scripts/perf/perfctl

    if is_true "$PERF_RUN_VERIFY"; then
        log_info "执行 qs-server 压测工具链回归: make perf-verify"
        run_as_runner env PATH="/usr/local/go/bin:/usr/local/bin:${PATH}" \
            make -C "$repo_dir" perf-verify
    fi
}

check_resources() {
    local cpu_count mem_kib disk_kib mem_gib disk_gib
    cpu_count="$(getconf _NPROCESSORS_ONLN)"
    mem_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
    if [[ -d "$PERF_WORKSPACE_ROOT" ]]; then
        disk_kib="$(df -Pk "$PERF_WORKSPACE_ROOT" | awk 'NR == 2 {print $4}')"
    else
        disk_kib="$(df -Pk / | awk 'NR == 2 {print $4}')"
    fi
    mem_gib="$(awk -v kib="$mem_kib" 'BEGIN {printf "%.1f", kib / 1024 / 1024}')"
    disk_gib="$(awk -v kib="$disk_kib" 'BEGIN {printf "%.1f", kib / 1024 / 1024}')"

    printf '资源: CPU=%s, Memory=%s GiB, DiskAvailable=%s GiB\n' \
        "$cpu_count" "$mem_gib" "$disk_gib"
    if (( cpu_count < 4 )); then
        log_warn "CPU 少于建议的 4 核；适合 smoke，不建议作为正式 admission 结果"
    fi
    if (( mem_kib < 7 * 1024 * 1024 )); then
        log_warn "内存少于建议的 8 GiB"
    fi
    if (( disk_kib < 10 * 1024 * 1024 )); then
        log_warn "可用磁盘少于建议的 10 GiB"
    fi
}

check_command_versions() {
    local failed=0
    if [[ "$(/usr/local/go/bin/go env GOVERSION 2>/dev/null || true)" != "go${PERF_GO_VERSION}" ]]; then
        log_error "Go 版本不符合要求: 期望 go${PERF_GO_VERSION}"
        failed=1
    else
        log_ok "$(/usr/local/go/bin/go version)"
    fi
    if ! command -v k6 >/dev/null 2>&1 || ! k6 version | grep -Fq "k6 ${PERF_K6_VERSION}"; then
        log_error "k6 版本不符合要求: 期望 ${PERF_K6_VERSION}"
        failed=1
    else
        log_ok "$(k6 version | head -n 1)"
    fi
    for command_name in curl git jq make mtr sar; do
        if ! command -v "$command_name" >/dev/null 2>&1; then
            log_error "缺少命令: $command_name"
            failed=1
        fi
    done
    return "$failed"
}

check_repository() {
    if is_true "$PERF_SKIP_REPO"; then
        return
    fi
    local repo_dir="${PERF_WORKSPACE_ROOT}/qs-server"
    if [[ ! -d "$repo_dir/.git" || ! -x "${PERF_WORKSPACE_ROOT}/bin/perfctl" ]]; then
        log_error "qs-server 或 perfctl 尚未准备完成"
        return 1
    fi
    log_ok "qs-server=$(run_as_runner git -C "$repo_dir" rev-parse --short HEAD)"
}

check_network() {
    if is_true "$PERF_SKIP_NETWORK_CHECK"; then
        log_warn "已跳过公网连通性检查"
        return
    fi
    local url
    local failed=0
    for url in $PERF_READY_URLS; do
        local result
        if result="$(curl --fail --silent --show-error --output /dev/null \
            --connect-timeout 10 --max-time 20 \
            --write-out 'status=%{http_code} remote_ip=%{remote_ip} total=%{time_total}s' \
            "$url")"; then
            log_ok "$url $result"
        else
            log_error "无法访问 $url"
            failed=1
        fi
    done
    return "$failed"
}

run_checks() {
    local failed=0
    check_resources || failed=1
    check_command_versions || failed=1
    check_repository || failed=1
    check_network || failed=1
    if (( failed != 0 )); then
        log_error "压测机检查未通过"
        return 1
    fi
    log_ok "压测机准备完成"
    printf '\n工作目录: %s\n结果目录: %s/runs\n' \
        "$PERF_WORKSPACE_ROOT" "$PERF_WORKSPACE_ROOT"
    if ! is_true "$PERF_SKIP_REPO"; then
        printf '代码目录: %s/qs-server\n' "$PERF_WORKSPACE_ROOT"
        printf '下一步: 重新登录以应用 nofile 限制，然后安全写入 token/config，再执行 make perf-preflight。\n'
    fi
}

main() {
    case "$ACTION" in
        -h|--help|help)
            usage
            return
            ;;
        init|check) ;;
        *) log_error "未知动作: $ACTION"; usage; exit 2 ;;
    esac

    if [[ $# -ne 0 ]]; then
        log_error "不支持位置参数；请通过环境变量传递配置"
        usage
        exit 2
    fi
    require_linux
    validate_config

    if [[ "$ACTION" == "check" ]]; then
        run_checks
        return
    fi

    require_root
    TMP_DIR="$(mktemp -d /tmp/qs-perf-init.XXXXXX)"
    trap 'if [[ -n "$TMP_DIR" && "$TMP_DIR" == /tmp/qs-perf-init.* ]]; then rm -rf -- "$TMP_DIR"; fi' EXIT

    local arch
    arch="$(detect_arch)"
    install_packages
    install_go "$arch" "$TMP_DIR"
    install_k6 "$arch" "$TMP_DIR"
    configure_runner
    prepare_repository
    run_checks
}

main "$@"
