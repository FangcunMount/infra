#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly INIT_SCRIPT="${SCRIPT_DIR}/init-perf-runner.sh"

ACTION="${1:-init}"
PERF_RUNNER_HOST="${PERF_RUNNER_HOST:-}"
PERF_RUNNER_SSH_PORT="${PERF_RUNNER_SSH_PORT:-22}"
PERF_RUNNER_SSH_IDENTITY_FILE="${PERF_RUNNER_SSH_IDENTITY_FILE:-}"
PERF_RUNNER_STRICT_HOST_KEY_CHECKING="${PERF_RUNNER_STRICT_HOST_KEY_CHECKING:-accept-new}"
PERF_QS_SERVER_SOURCE_DIR="${PERF_QS_SERVER_SOURCE_DIR:-}"
LOCAL_BUNDLE_DIR=""
REMOTE_SOURCE_ARCHIVE=""

usage() {
    cat <<'EOF'
用法:
  PERF_RUNNER_HOST=root@1.2.3.4 bash init-perf-runner-remote.sh init
  PERF_RUNNER_HOST=root@1.2.3.4 bash init-perf-runner-remote.sh check

SSH 配置:
  PERF_RUNNER_SSH_PORT=22
  PERF_RUNNER_SSH_IDENTITY_FILE=/absolute/path/to/key
  PERF_RUNNER_STRICT_HOST_KEY_CHECKING=accept-new|yes

本地源码模式:
  PERF_QS_SERVER_SOURCE_DIR=/absolute/path/to/qs-server
  设置后会排除 .git、tmp、.env* 和 secrets，上传源码快照代替 GitHub clone。

其余 PERF_* 配置会安全传给远端初始化脚本。
EOF
}

shell_quote() {
    local value="$1"
    local escaped
    escaped="$(printf '%s' "$value" | sed "s/'/'\"'\"'/g")"
    printf "'%s'" "$escaped"
}

append_env() {
    local name="$1"
    local value="${!name-}"
    if [[ -n "$value" ]]; then
        REMOTE_ENV+=" $(shell_quote "${name}=${value}")"
    fi
}

case "$ACTION" in
    -h|--help|help) usage; exit 0 ;;
    init|check) ;;
    *) printf '[ERROR] 未知动作: %s\n' "$ACTION" >&2; usage; exit 2 ;;
esac

if [[ -z "$PERF_RUNNER_HOST" ]]; then
    printf '[ERROR] 缺少 PERF_RUNNER_HOST，例如 root@1.2.3.4\n' >&2
    exit 2
fi
if [[ "$PERF_RUNNER_HOST" == -* || "$PERF_RUNNER_HOST" =~ [[:space:]] ]]; then
    printf '[ERROR] PERF_RUNNER_HOST 格式无效\n' >&2
    exit 2
fi
if [[ ! "$PERF_RUNNER_SSH_PORT" =~ ^[0-9]+$ ]]; then
    printf '[ERROR] PERF_RUNNER_SSH_PORT 必须是数字\n' >&2
    exit 2
fi
if [[ ! "$PERF_RUNNER_STRICT_HOST_KEY_CHECKING" =~ ^(yes|accept-new)$ ]]; then
    printf '[ERROR] 主机密钥策略只允许 yes 或 accept-new\n' >&2
    exit 2
fi
if [[ -n "$PERF_QS_SERVER_SOURCE_DIR" ]]; then
    case "$PERF_QS_SERVER_SOURCE_DIR" in
        /*) ;;
        *) printf '[ERROR] PERF_QS_SERVER_SOURCE_DIR 必须是绝对路径\n' >&2; exit 2 ;;
    esac
    for required_path in go.mod Makefile scripts/perf/perfctl; do
        if [[ ! -e "${PERF_QS_SERVER_SOURCE_DIR}/${required_path}" ]]; then
            printf '[ERROR] 本地 qs-server 缺少 %s: %s\n' \
                "$required_path" "$PERF_QS_SERVER_SOURCE_DIR" >&2
            exit 2
        fi
    done
    if [[ "$ACTION" != "init" ]]; then
        printf '[ERROR] PERF_QS_SERVER_SOURCE_DIR 仅适用于 init\n' >&2
        exit 2
    fi
fi

ssh_options=(
    -o BatchMode=yes
    -o ConnectTimeout=15
    -o "StrictHostKeyChecking=${PERF_RUNNER_STRICT_HOST_KEY_CHECKING}"
    -p "$PERF_RUNNER_SSH_PORT"
)
if [[ -n "$PERF_RUNNER_SSH_IDENTITY_FILE" ]]; then
    if [[ ! -r "$PERF_RUNNER_SSH_IDENTITY_FILE" ]]; then
        printf '[ERROR] SSH 私钥不可读: %s\n' "$PERF_RUNNER_SSH_IDENTITY_FILE" >&2
        exit 2
    fi
    ssh_options+=(-i "$PERF_RUNNER_SSH_IDENTITY_FILE")
fi

scp_options=(
    -o BatchMode=yes
    -o ConnectTimeout=15
    -o "StrictHostKeyChecking=${PERF_RUNNER_STRICT_HOST_KEY_CHECKING}"
    -P "$PERF_RUNNER_SSH_PORT"
)
if [[ -n "$PERF_RUNNER_SSH_IDENTITY_FILE" ]]; then
    scp_options+=(-i "$PERF_RUNNER_SSH_IDENTITY_FILE")
fi

REMOTE_ENV=""
for env_name in \
    PERF_RUNNER_USER PERF_WORKSPACE_ROOT PERF_GO_VERSION PERF_K6_VERSION \
    PERF_QS_SERVER_REPO PERF_QS_SERVER_REF PERF_SKIP_REPO PERF_UPDATE_REPO \
    PERF_RUN_VERIFY PERF_READY_URLS PERF_SKIP_NETWORK_CHECK PERF_GO_SHA256 \
    PERF_DOWNLOAD_ATTEMPTS PERF_DOWNLOAD_RETRY_DELAY_SECONDS \
    PERF_GO_PROXY PERF_GO_SUMDB; do
    append_env "$env_name"
done

cleanup() {
    if [[ -n "$LOCAL_BUNDLE_DIR" && "$LOCAL_BUNDLE_DIR" == /tmp/qs-perf-source.* ]]; then
        rm -rf -- "$LOCAL_BUNDLE_DIR"
    fi
    if [[ -n "$REMOTE_SOURCE_ARCHIVE" && "$REMOTE_SOURCE_ARCHIVE" == /tmp/qs-perf-source.* ]]; then
        ssh "${ssh_options[@]}" "$PERF_RUNNER_HOST" \
            "rm -f -- $(shell_quote "$REMOTE_SOURCE_ARCHIVE")" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

if [[ -n "$PERF_QS_SERVER_SOURCE_DIR" ]]; then
    LOCAL_BUNDLE_DIR="$(mktemp -d /tmp/qs-perf-source.XXXXXX)"
    local_archive="${LOCAL_BUNDLE_DIR}/qs-server.tar.gz"
    local_tar="${LOCAL_BUNDLE_DIR}/qs-server.tar"
    printf '[INFO] 打包本地 qs-server 源码快照: %s\n' "$PERF_QS_SERVER_SOURCE_DIR"
    if ! git -C "$PERF_QS_SERVER_SOURCE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        printf '[ERROR] 本地源码模式要求 PERF_QS_SERVER_SOURCE_DIR 是 Git 工作树\n' >&2
        exit 2
    fi
    if [[ -n "$(git -C "$PERF_QS_SERVER_SOURCE_DIR" status --porcelain)" ]]; then
        printf '[WARN] 本地 qs-server 有未提交修改；包含 tracked 修改，排除 untracked 文件\n' >&2
    fi
    git -C "$PERF_QS_SERVER_SOURCE_DIR" ls-files -z |
        while IFS= read -r -d '' source_path; do
            case "$source_path" in
                .env|.env.*|*/.env|*/.env.*|tmp/*|secrets/*) continue ;;
            esac
            if [[ ! -e "${PERF_QS_SERVER_SOURCE_DIR}/${source_path}" && \
                ! -L "${PERF_QS_SERVER_SOURCE_DIR}/${source_path}" ]]; then
                continue
            fi
            printf '%s\0' "$source_path"
        done |
        COPYFILE_DISABLE=1 tar --no-xattrs -cf "$local_tar" \
            -C "$PERF_QS_SERVER_SOURCE_DIR" --null -T -
    # gzip -n 不写入原文件名和当前时间，使相同源码的归档哈希可重复。
    gzip -n "$local_tar"

    if command -v sha256sum >/dev/null 2>&1; then
        source_sha256="$(sha256sum "$local_archive" | awk '{print $1}')"
    else
        source_sha256="$(shasum -a 256 "$local_archive" | awk '{print $1}')"
    fi
    REMOTE_SOURCE_ARCHIVE="$(ssh "${ssh_options[@]}" "$PERF_RUNNER_HOST" \
        'mktemp /tmp/qs-perf-source.XXXXXX')"
    case "$REMOTE_SOURCE_ARCHIVE" in
        /tmp/qs-perf-source.*) ;;
        *) printf '[ERROR] 远端源码临时路径无效\n' >&2; exit 1 ;;
    esac
    printf '[INFO] 上传源码快照 sha256=%s\n' "${source_sha256:0:12}"
    scp "${scp_options[@]}" "$local_archive" \
        "${PERF_RUNNER_HOST}:${REMOTE_SOURCE_ARCHIVE}"
    REMOTE_ENV+=" $(shell_quote "PERF_QS_SERVER_ARCHIVE=${REMOTE_SOURCE_ARCHIVE}")"
    REMOTE_ENV+=" $(shell_quote "PERF_QS_SERVER_ARCHIVE_SHA256=${source_sha256}")"
fi

quoted_action="$(shell_quote "$ACTION")"
remote_command="
set -eu
if [ \"\$(id -u)\" -eq 0 ]; then
    exec env${REMOTE_ENV} bash -s -- ${quoted_action}
fi
if ! command -v sudo >/dev/null 2>&1 || ! sudo -n true >/dev/null 2>&1; then
    echo '[ERROR] 远端用户不是 root，且没有免密 sudo；请改用 root@host 或配置 NOPASSWD sudo' >&2
    exit 1
fi
exec sudo -n env${REMOTE_ENV} bash -s -- ${quoted_action}
"

printf '[INFO] 在 %s 上执行压测机 %s\n' "$PERF_RUNNER_HOST" "$ACTION"
ssh "${ssh_options[@]}" "$PERF_RUNNER_HOST" "$remote_command" <"$INIT_SCRIPT"
