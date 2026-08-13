#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly INIT_SCRIPT="${SCRIPT_DIR}/init-perf-runner.sh"

ACTION="${1:-init}"
PERF_RUNNER_HOST="${PERF_RUNNER_HOST:-}"
PERF_RUNNER_SSH_PORT="${PERF_RUNNER_SSH_PORT:-22}"
PERF_RUNNER_SSH_IDENTITY_FILE="${PERF_RUNNER_SSH_IDENTITY_FILE:-}"
PERF_RUNNER_STRICT_HOST_KEY_CHECKING="${PERF_RUNNER_STRICT_HOST_KEY_CHECKING:-accept-new}"

usage() {
    cat <<'EOF'
用法:
  PERF_RUNNER_HOST=root@1.2.3.4 bash init-perf-runner-remote.sh init
  PERF_RUNNER_HOST=root@1.2.3.4 bash init-perf-runner-remote.sh check

SSH 配置:
  PERF_RUNNER_SSH_PORT=22
  PERF_RUNNER_SSH_IDENTITY_FILE=/absolute/path/to/key
  PERF_RUNNER_STRICT_HOST_KEY_CHECKING=accept-new|yes

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

REMOTE_ENV=""
for env_name in \
    PERF_RUNNER_USER PERF_WORKSPACE_ROOT PERF_GO_VERSION PERF_K6_VERSION \
    PERF_QS_SERVER_REPO PERF_QS_SERVER_REF PERF_SKIP_REPO PERF_UPDATE_REPO \
    PERF_RUN_VERIFY PERF_READY_URLS PERF_SKIP_NETWORK_CHECK PERF_GO_SHA256; do
    append_env "$env_name"
done

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
