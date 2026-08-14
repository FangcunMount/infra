#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=sync-perf-runner-config-remote.sh
source "${SCRIPT_DIR}/sync-perf-runner-config-remote.sh"

TEST_TMP_DIR="$(mktemp -d)"
trap 'rm -rf -- "$TEST_TMP_DIR"' EXIT

env_source="${TEST_TMP_DIR}/perf.env"
env_normalized="${TEST_TMP_DIR}/normalized.env"
marker="${TEST_TMP_DIR}/must-not-exist"
printf '%s\n' \
    '# perf observability' \
    'export COLLECTION_METRICS_URL=https://collect.example.test/perf/metrics' \
    'COLLECTION_READYZ_URL=https://collect.example.test/perf/readyz' \
    'APISERVER_METRICS_URL=https://api.example.test/metrics' \
    'APISERVER_READYZ_URL=https://api.example.test/readyz' \
    'WORKER_METRICS_URL=https://worker.example.test/metrics' \
    'WORKER_READYZ_URL=https://worker.example.test/readyz' \
    'NSQD_STATS_URL=https://nsqd.example.test/stats' \
    'EXPECTED_COLLECTION_REPLICAS=2' \
    'EXPECTED_WORKER_REPLICAS=3' \
    'PERF_ISOLATED_ENV=true' \
    'PERF_RECOVERY_TIMEOUT=5m' \
    'PERF_RECOVERY_POLL=10s' \
    "PERF_NSQ_TOPICS=topic-a,\$(touch ${marker})" >"$env_source"
chmod 0600 "$env_source"

normalize_env_file "$env_source" "$env_normalized"
actual_topics="$(bash -c 'source "$1"; printf "%s" "$PERF_NSQ_TOPICS"' _ "$env_normalized")"
if [[ "$actual_topics" != "topic-a,\$(touch ${marker})" || -e "$marker" ]]; then
    printf '[ERROR] perf.env 值未按字面量安全规范化\n' >&2
    exit 1
fi

invalid_env="${TEST_TMP_DIR}/invalid.env"
printf '%s\n' \
    'PATH=/tmp/unsafe' \
    'COLLECTION_METRICS_URL=https://collect.example.test/metrics' >"$invalid_env"
if normalize_env_file "$invalid_env" "${TEST_TMP_DIR}/invalid-normalized.env" 2>/dev/null; then
    printf '[ERROR] 不安全环境变量被错误接受\n' >&2
    exit 1
fi

iam_file="${TEST_TMP_DIR}/iam-users.json"
config_file="${TEST_TMP_DIR}/qs-perf.config.json"
printf '%s\n' '{"collection_users":[{"username":"collection","password":"secret"}],"apiserver_users":[{"username":"api","password":"secret"}]}' >"$iam_file"
printf '%s\n' '{"qpsProfile":"smoke_4","qpsProfiles":{"smoke_4":{}},"collectionBaseUrl":"https://collect.example.test","apiserverBaseUrl":"https://api.example.test"}' >"$config_file"
chmod 0600 "$iam_file" "$config_file"
PERF_RUNNER_ENV_FILE="$env_source"
PERF_RUNNER_IAM_USERS_FILE="$iam_file"
PERF_RUNNER_CONFIG_FILE="$config_file"
chmod 0644 "$iam_file"
if validate_local_inputs 2>/dev/null; then
    printf '[ERROR] 权限过宽的 IAM 文件被错误接受\n' >&2
    exit 1
fi
chmod 0600 "$iam_file"
validate_local_inputs

remote_command_capture="${TEST_TMP_DIR}/remote-command.txt"
ssh() {
    local last_arg="${!#}"
    if [[ "$last_arg" == 'umask 077; mktemp -d /tmp/qs-perf-materials.XXXXXX' ]]; then
        printf '/tmp/qs-perf-materials.test12\n'
        return
    fi
    printf '%s\n' "$last_arg" >"$remote_command_capture"
}
scp() { :; }

PERF_RUNNER_HOST=root@runner.example.test
PERF_RUNNER_SSH_PORT=22
PERF_RUNNER_SSH_IDENTITY_FILE=""
PERF_RUNNER_STRICT_HOST_KEY_CHECKING=accept-new
PERF_RUNNER_USER=root
PERF_WORKSPACE_ROOT=/opt/qs-perf
PERF_RUNNER_AUTO_PREPARE=true
main >/dev/null
bash -n "$remote_command_capture"
if ! grep -Fq 'print $1' "$remote_command_capture"; then
    printf '[ERROR] 远端 SHA256 校验命令转义错误\n' >&2
    exit 1
fi
if ! grep -Fq 'perf-tokens' "$remote_command_capture" || \
    ! grep -Fq 'perf-preflight' "$remote_command_capture" || \
    ! grep -Fq 'perf-run PLAN=baseline' "$remote_command_capture" || \
    ! grep -Fq 'chmod 0600' "$remote_command_capture" || \
    ! grep -Fq 'trap fix_permissions EXIT' "$remote_command_capture"; then
    printf '[ERROR] 远端同步没有生成一键准备与压测入口\n' >&2
    exit 1
fi

printf '[OK] 压测环境与配置同步回归通过\n'
