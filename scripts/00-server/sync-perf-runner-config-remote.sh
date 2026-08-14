#!/usr/bin/env bash
set -Eeuo pipefail

# 从控制机向独立压测机同步运行环境和两份 K6 配置。
# 文件内容不会写入命令行、日志或 Git；远端最终权限固定为 0600。

PERF_RUNNER_HOST="${PERF_RUNNER_HOST:-}"
PERF_RUNNER_SSH_PORT="${PERF_RUNNER_SSH_PORT:-22}"
PERF_RUNNER_SSH_IDENTITY_FILE="${PERF_RUNNER_SSH_IDENTITY_FILE:-}"
PERF_RUNNER_STRICT_HOST_KEY_CHECKING="${PERF_RUNNER_STRICT_HOST_KEY_CHECKING:-accept-new}"
PERF_RUNNER_USER="${PERF_RUNNER_USER:-}"
PERF_WORKSPACE_ROOT="${PERF_WORKSPACE_ROOT:-/opt/qs-perf}"
PERF_RUNNER_ENV_FILE="${PERF_RUNNER_ENV_FILE:-}"
PERF_RUNNER_IAM_USERS_FILE="${PERF_RUNNER_IAM_USERS_FILE:-}"
PERF_RUNNER_CONFIG_FILE="${PERF_RUNNER_CONFIG_FILE:-}"
PERF_RUNNER_AUTO_PREPARE="${PERF_RUNNER_AUTO_PREPARE:-true}"

LOCAL_STAGE_DIR=""
REMOTE_STAGE_DIR=""

usage() {
    cat <<'EOF'
用法:
  PERF_RUNNER_HOST=root@1.2.3.4 \
  PERF_RUNNER_ENV_FILE=/absolute/path/to/perf.env \
  PERF_RUNNER_IAM_USERS_FILE=/absolute/path/to/iam-users.json \
  PERF_RUNNER_CONFIG_FILE=/absolute/path/to/qs-perf.config.json \
  bash sync-perf-runner-config-remote.sh

perf.env 支持空行、# 注释以及以下形式：
  KEY=value
  export KEY=value

值按字面量处理，不执行 shell 展开。三份文件必须一起提供。
默认在同步后刷新 token 并执行 perf-preflight；设置
PERF_RUNNER_AUTO_PREPARE=false 可只同步文件。
EOF
}

shell_quote() {
    local value="$1"
    local escaped
    escaped="$(printf '%s' "$value" | sed "s/'/'\"'\"'/g")"
    printf "'%s'" "$escaped"
}

is_allowed_env_key() {
    case "$1" in
        COLLECTION_METRICS_URL|COLLECTION_READYZ_URL|COLLECTION_RESILIENCE_URL|COLLECTION_REDIS_URL|\
        APISERVER_METRICS_URL|APISERVER_READYZ_URL|\
        WORKER_METRICS_URL|WORKER_READYZ_URL|WORKER_RESILIENCE_URL|WORKER_REDIS_URL|\
        NSQD_STATS_URL|NSQLOOKUPD_NODES_URL|\
        EXPECTED_COLLECTION_REPLICAS|EXPECTED_WORKER_REPLICAS|\
        PERF_ISOLATED_ENV|PERF_NSQ_TOPICS|PERF_ORG_ID|PERF_RECOVERY_TIMEOUT|PERF_RECOVERY_POLL|\
        IAM_BASE_URL|IAM_LOGIN_URL|IAM_TENANT_ID|IAM_DEVICE_ID_PREFIX|\
        IAM_LOGIN_RETRIES|IAM_LOGIN_RETRY_DELAY|IAM_LOGIN_INTERVAL)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

normalize_env_file() {
    local source_file="$1"
    local output_file="$2"
    local line line_number=0 key value
    local -A seen=()
    local -a required=(
        COLLECTION_METRICS_URL COLLECTION_READYZ_URL
        APISERVER_METRICS_URL APISERVER_READYZ_URL
        WORKER_METRICS_URL WORKER_READYZ_URL
        NSQD_STATS_URL EXPECTED_COLLECTION_REPLICAS EXPECTED_WORKER_REPLICAS
        PERF_ISOLATED_ENV
    )

    : >"$output_file"
    while IFS= read -r line || [[ -n "$line" ]]; do
        line_number=$((line_number + 1))
        line="${line%$'\r'}"
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        if [[ "$line" == export\ * ]]; then
            line="${line#export }"
        fi
        if [[ "$line" != *=* ]]; then
            printf '[ERROR] perf.env 第 %s 行不是 KEY=value\n' "$line_number" >&2
            return 1
        fi
        key="${line%%=*}"
        value="${line#*=}"
        if [[ ! "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || ! is_allowed_env_key "$key"; then
            printf '[ERROR] perf.env 第 %s 行包含不允许的变量名: %s\n' \
                "$line_number" "$key" >&2
            return 1
        fi
        if [[ -n "${seen[$key]+set}" ]]; then
            printf '[ERROR] perf.env 变量重复: %s\n' "$key" >&2
            return 1
        fi
        if (( ${#value} >= 2 )) && [[ "$value" == \"*\" && "$value" == *\" ]]; then
            value="${value:1:${#value}-2}"
        elif (( ${#value} >= 2 )) && [[ "$value" == \'*\' && "$value" == *\' ]]; then
            value="${value:1:${#value}-2}"
        fi
        if [[ "$value" == *$'\n'* || "$value" == *$'\r'* ]]; then
            printf '[ERROR] perf.env 第 %s 行包含换行字符\n' "$line_number" >&2
            return 1
        fi
        printf 'export %s=%q\n' "$key" "$value" >>"$output_file"
        seen[$key]=1
    done <"$source_file"

    for key in "${required[@]}"; do
        if [[ -z "${seen[$key]+set}" ]]; then
            printf '[ERROR] perf.env 缺少必需变量: %s\n' "$key" >&2
            return 1
        fi
    done
}

validate_local_inputs() {
    local label path mode mode_value
    for label in PERF_RUNNER_ENV_FILE PERF_RUNNER_IAM_USERS_FILE PERF_RUNNER_CONFIG_FILE; do
        path="${!label}"
        if [[ -z "$path" || "$path" != /* || ! -f "$path" || ! -r "$path" ]]; then
            printf '[ERROR] %s 必须是可读的绝对文件路径\n' "$label" >&2
            return 1
        fi
        if mode="$(stat -f '%Lp' "$path" 2>/dev/null)"; then
            :
        else
            mode="$(stat -c '%a' "$path")"
        fi
        if [[ ! "$mode" =~ ^[0-7]{3,4}$ ]]; then
            printf '[ERROR] 无法判断 %s 的权限\n' "$label" >&2
            return 1
        fi
        mode_value=$((8#$mode))
        if (( (mode_value & 077) != 0 )); then
            printf '[ERROR] %s 权限过宽（%s），请先 chmod 0600\n' "$label" "$mode" >&2
            return 1
        fi
    done
    command -v jq >/dev/null 2>&1 || {
        printf '[ERROR] 本机缺少 jq\n' >&2
        return 1
    }
    jq -e '
        type == "object" and
        (.collection_users | type == "array" and length > 0) and
        (.apiserver_users | type == "array" and length > 0) and
        ([.collection_users[], .apiserver_users[]] |
            all((.username // "") != "" and (.password // "") != ""))
    ' \
        "$PERF_RUNNER_IAM_USERS_FILE" >/dev/null || {
        printf '[ERROR] iam-users.json 结构无效、用户组为空或缺少用户名/密码\n' >&2
        return 1
    }
    jq -e '
        type == "object" and
        (.qpsProfiles | type == "object") and
        (.qpsProfile | type == "string") and
        (.qpsProfiles[.qpsProfile] | type == "object") and
        (.collectionBaseUrl | type == "string" and length > 0) and
        (.apiserverBaseUrl | type == "string" and length > 0)
    ' \
        "$PERF_RUNNER_CONFIG_FILE" >/dev/null || {
        printf '[ERROR] qs-perf.config.json 缺少有效 profile 或服务入口\n' >&2
        return 1
    }
}

is_true() {
    case "${1,,}" in
        1|true|yes|y) return 0 ;;
        *) return 1 ;;
    esac
}

sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

main() {
    case "${1:-}" in
        -h|--help|help) usage; return ;;
        "") ;;
        *) printf '[ERROR] 不支持位置参数\n' >&2; usage; return 2 ;;
    esac

    if [[ -z "$PERF_RUNNER_HOST" || "$PERF_RUNNER_HOST" == -* || \
        "$PERF_RUNNER_HOST" =~ [[:space:]] ]]; then
        printf '[ERROR] PERF_RUNNER_HOST 格式无效\n' >&2
        return 2
    fi
    if [[ ! "$PERF_RUNNER_SSH_PORT" =~ ^[0-9]+$ ]]; then
        printf '[ERROR] PERF_RUNNER_SSH_PORT 必须是数字\n' >&2
        return 2
    fi
    if [[ ! "$PERF_RUNNER_STRICT_HOST_KEY_CHECKING" =~ ^(yes|accept-new)$ ]]; then
        printf '[ERROR] 主机密钥策略只允许 yes 或 accept-new\n' >&2
        return 2
    fi
    if ! is_true "$PERF_RUNNER_AUTO_PREPARE" && [[ "${PERF_RUNNER_AUTO_PREPARE,,}" != "false" ]]; then
        printf '[ERROR] PERF_RUNNER_AUTO_PREPARE 只允许 true 或 false\n' >&2
        return 2
    fi
    if [[ -n "$PERF_RUNNER_USER" && ! "$PERF_RUNNER_USER" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]]; then
        printf '[ERROR] PERF_RUNNER_USER 不是有效的 Linux 用户名\n' >&2
        return 2
    fi
    case "$PERF_WORKSPACE_ROOT" in
        /|/bin|/boot|/dev|/etc|/home|/lib|/lib64|/opt|/proc|/root|/run|/sbin|/sys|/tmp|/usr|/var)
            printf '[ERROR] PERF_WORKSPACE_ROOT 范围过大或不安全\n' >&2
            return 2
            ;;
        /*) ;;
        *) printf '[ERROR] PERF_WORKSPACE_ROOT 必须是绝对路径\n' >&2; return 2 ;;
    esac
    if [[ ! "$PERF_WORKSPACE_ROOT" =~ ^/[a-zA-Z0-9._/-]+$ ]]; then
        printf '[ERROR] PERF_WORKSPACE_ROOT 包含不安全字符\n' >&2
        return 2
    fi

    validate_local_inputs

    local -a ssh_options=(
        -o BatchMode=yes
        -o ConnectTimeout=15
        -o "StrictHostKeyChecking=${PERF_RUNNER_STRICT_HOST_KEY_CHECKING}"
        -p "$PERF_RUNNER_SSH_PORT"
    )
    local -a scp_options=(
        -q
        -o BatchMode=yes
        -o ConnectTimeout=15
        -o "StrictHostKeyChecking=${PERF_RUNNER_STRICT_HOST_KEY_CHECKING}"
        -P "$PERF_RUNNER_SSH_PORT"
    )
    if [[ -n "$PERF_RUNNER_SSH_IDENTITY_FILE" ]]; then
        if [[ ! -r "$PERF_RUNNER_SSH_IDENTITY_FILE" ]]; then
            printf '[ERROR] SSH 私钥不可读: %s\n' "$PERF_RUNNER_SSH_IDENTITY_FILE" >&2
            return 2
        fi
        ssh_options+=(-i "$PERF_RUNNER_SSH_IDENTITY_FILE")
        scp_options+=(-i "$PERF_RUNNER_SSH_IDENTITY_FILE")
    fi

    LOCAL_STAGE_DIR="$(mktemp -d /tmp/qs-perf-materials.XXXXXX)"
    local normalized_env="${LOCAL_STAGE_DIR}/perf.env"
    normalize_env_file "$PERF_RUNNER_ENV_FILE" "$normalized_env"
    chmod 0600 "$normalized_env"

    local env_sha iam_sha config_sha
    env_sha="$(sha256_file "$normalized_env")"
    iam_sha="$(sha256_file "$PERF_RUNNER_IAM_USERS_FILE")"
    config_sha="$(sha256_file "$PERF_RUNNER_CONFIG_FILE")"

    REMOTE_STAGE_DIR="$(ssh "${ssh_options[@]}" "$PERF_RUNNER_HOST" \
        'umask 077; mktemp -d /tmp/qs-perf-materials.XXXXXX')"
    case "$REMOTE_STAGE_DIR" in
        /tmp/qs-perf-materials.*) ;;
        *) printf '[ERROR] 远端临时目录无效\n' >&2; return 1 ;;
    esac

    printf '[INFO] 上传压测环境与配置（内容不回显）\n'
    scp "${scp_options[@]}" "$normalized_env" \
        "${PERF_RUNNER_HOST}:${REMOTE_STAGE_DIR}/perf.env"
    scp "${scp_options[@]}" "$PERF_RUNNER_IAM_USERS_FILE" \
        "${PERF_RUNNER_HOST}:${REMOTE_STAGE_DIR}/iam-users.json"
    scp "${scp_options[@]}" "$PERF_RUNNER_CONFIG_FILE" \
        "${PERF_RUNNER_HOST}:${REMOTE_STAGE_DIR}/qs-perf.config.json"

    local remote_env=""
    local name value
    for name in PERF_RUNNER_USER PERF_WORKSPACE_ROOT; do
        value="${!name}"
        [[ -n "$value" ]] && remote_env+=" $(shell_quote "${name}=${value}")"
    done
    remote_env+=" $(shell_quote "PERF_MATERIALS_STAGE=${REMOTE_STAGE_DIR}")"
    remote_env+=" $(shell_quote "PERF_ENV_SHA256=${env_sha}")"
    remote_env+=" $(shell_quote "PERF_IAM_SHA256=${iam_sha}")"
    remote_env+=" $(shell_quote "PERF_CONFIG_SHA256=${config_sha}")"
    remote_env+=" $(shell_quote "PERF_RUNNER_AUTO_PREPARE=${PERF_RUNNER_AUTO_PREPARE}")"

    local remote_command
    remote_command="
set -Eeuo pipefail
install_materials() {
    runner_user=\"\${PERF_RUNNER_USER:-\${SUDO_USER:-\$(id -un)}}\"
    id \"\$runner_user\" >/dev/null 2>&1 || { echo '[ERROR] 压测用户不存在' >&2; return 1; }
    runner_group=\"\$(id -gn \"\$runner_user\")\"
    repo_dir=\"\${PERF_WORKSPACE_ROOT}/qs-server\"
    test -f \"\${repo_dir}/go.mod\" || { echo '[ERROR] 远端 qs-server 尚未初始化' >&2; return 1; }
    case \"\$PERF_MATERIALS_STAGE\" in /tmp/qs-perf-materials.*) ;; *) return 1 ;; esac
    chmod 0700 \"\$PERF_MATERIALS_STAGE\"
    actual_env=\"\$(sha256sum \"\$PERF_MATERIALS_STAGE/perf.env\" | awk '{print \$1}')\"
    actual_iam=\"\$(sha256sum \"\$PERF_MATERIALS_STAGE/iam-users.json\" | awk '{print \$1}')\"
    actual_config=\"\$(sha256sum \"\$PERF_MATERIALS_STAGE/qs-perf.config.json\" | awk '{print \$1}')\"
    test \"\$actual_env\" = \"\$PERF_ENV_SHA256\" || { echo '[ERROR] perf.env SHA256 不一致' >&2; return 1; }
    test \"\$actual_iam\" = \"\$PERF_IAM_SHA256\" || { echo '[ERROR] iam-users.json SHA256 不一致' >&2; return 1; }
    test \"\$actual_config\" = \"\$PERF_CONFIG_SHA256\" || { echo '[ERROR] qs-perf.config.json SHA256 不一致' >&2; return 1; }
    jq -e 'type == \"object\" and (.collection_users | type == \"array\" and length > 0) and (.apiserver_users | type == \"array\" and length > 0)' \\
        \"\$PERF_MATERIALS_STAGE/iam-users.json\" >/dev/null
    jq -e 'type == \"object\" and (.qpsProfiles | type == \"object\") and (.qpsProfile | type == \"string\") and (.qpsProfiles[.qpsProfile] | type == \"object\")' \\
        \"\$PERF_MATERIALS_STAGE/qs-perf.config.json\" >/dev/null
    install -d -m 0700 -o \"\$runner_user\" -g \"\$runner_group\" \\
        \"\${PERF_WORKSPACE_ROOT}/secrets\" \"\${repo_dir}/tmp/perf\"
    install -m 0600 -o \"\$runner_user\" -g \"\$runner_group\" \\
        \"\$PERF_MATERIALS_STAGE/perf.env\" \"\${PERF_WORKSPACE_ROOT}/secrets/perf.env\"
    install -m 0600 -o \"\$runner_user\" -g \"\$runner_group\" \\
        \"\$PERF_MATERIALS_STAGE/iam-users.json\" \"\${repo_dir}/tmp/perf/iam-users.json\"
    install -m 0600 -o \"\$runner_user\" -g \"\$runner_group\" \\
        \"\$PERF_MATERIALS_STAGE/qs-perf.config.json\" \"\${repo_dir}/tmp/perf/qs-perf.config.json\"
    loader=\"\${PERF_WORKSPACE_ROOT}/bin/perf-with-env\"
    loader_tmp=\"\${loader}.new.\$\$\"
    printf '%s\\n' \\
        '#!/usr/bin/env bash' \\
        'set -Eeuo pipefail' \\
        \"env_file='\${PERF_WORKSPACE_ROOT}/secrets/perf.env'\" \\
        '[[ -r \"\$env_file\" ]] || { echo \"[ERROR] perf.env 不可读\" >&2; exit 1; }' \\
        'source \"\$env_file\"' \\
        'exec \"\$@\"' >\"\$loader_tmp\"
    chown \"\$runner_user:\$runner_group\" \"\$loader_tmp\"
    chmod 0700 \"\$loader_tmp\"
    mv -f \"\$loader_tmp\" \"\$loader\"
    prepare=\"\${PERF_WORKSPACE_ROOT}/bin/perf-prepare\"
    prepare_tmp=\"\${prepare}.new.\$\$\"
    printf '%s\\n' \\
        '#!/usr/bin/env bash' \\
        'set -Eeuo pipefail' \\
        \"workspace_root='\${PERF_WORKSPACE_ROOT}'\" \\
        'repo_dir=\"\${workspace_root}/qs-server\"' \\
        'loader=\"\${workspace_root}/bin/perf-with-env\"' \\
        'fix_permissions() { for file in \"\$repo_dir/tmp/perf/iam-users.json\" \"\$repo_dir/tmp/perf/qs-perf.config.json\" \"\$repo_dir/tmp/perf/tokens.json\" \"\$repo_dir/tmp/perf/apiserver-tokens.json\"; do [[ ! -e \"\$file\" ]] || chmod 0600 \"\$file\"; done; }' \\
        'trap fix_permissions EXIT' \\
        'command -v node >/dev/null 2>&1 || { echo \"[ERROR] 缺少 node；请重新执行 perf-runner-init-remote\" >&2; exit 1; }' \\
        '\"\$loader\" make -C \"\$repo_dir\" perf-tokens' \\
        '\"\$loader\" make -C \"\$repo_dir\" perf-preflight' >\"\$prepare_tmp\"
    chown \"\$runner_user:\$runner_group\" \"\$prepare_tmp\"
    chmod 0700 \"\$prepare_tmp\"
    mv -f \"\$prepare_tmp\" \"\$prepare\"

    run=\"\${PERF_WORKSPACE_ROOT}/bin/perf-run\"
    run_tmp=\"\${run}.new.\$\$\"
    printf '%s\\n' \\
        '#!/usr/bin/env bash' \\
        'set -Eeuo pipefail' \\
        \"workspace_root='\${PERF_WORKSPACE_ROOT}'\" \\
        'repo_dir=\"\${workspace_root}/qs-server\"' \\
        'fix_permissions() { for file in \"\$repo_dir/tmp/perf/iam-users.json\" \"\$repo_dir/tmp/perf/qs-perf.config.json\" \"\$repo_dir/tmp/perf/tokens.json\" \"\$repo_dir/tmp/perf/apiserver-tokens.json\"; do [[ ! -e \"\$file\" ]] || chmod 0600 \"\$file\"; done; }' \\
        'trap fix_permissions EXIT' \\
        '\"\${workspace_root}/bin/perf-prepare\"' \\
        '\"\${workspace_root}/bin/perf-with-env\" make -C \"\$repo_dir\" perf-run PERF_RUN_ROOT=\"\${workspace_root}/runs\" \"\$@\"' >\"\$run_tmp\"
    chown \"\$runner_user:\$runner_group\" \"\$run_tmp\"
    chmod 0700 \"\$run_tmp\"
    mv -f \"\$run_tmp\" \"\$run\"

    echo '[OK] 压测环境与配置已安全同步'
    echo \"环境文件: \${PERF_WORKSPACE_ROOT}/secrets/perf.env (0600)\"
    echo \"K6 配置目录: \${repo_dir}/tmp/perf (0700; files 0600)\"
    echo \"执行入口: \${PERF_WORKSPACE_ROOT}/bin/perf-with-env\"
    echo \"一键压测: \${PERF_WORKSPACE_ROOT}/bin/perf-run PLAN=baseline\"

    case \"\${PERF_RUNNER_AUTO_PREPARE,,}\" in
        1|true|yes|y)
            echo '[INFO] 刷新两组 IAM token 并执行完整 perf-preflight'
            if [ \"\$(id -u)\" -eq \"\$(id -u \"\$runner_user\")\" ]; then
                \"\$prepare\"
            else
                runner_home=\"\$(getent passwd \"\$runner_user\" | cut -d: -f6)\"
                runuser -u \"\$runner_user\" -- env HOME=\"\$runner_home\" \"\$prepare\"
            fi
            echo '[OK] token 与 perf-preflight 已准备完成'
            ;;
        false) echo '[WARN] 已跳过 token 刷新与 perf-preflight' ;;
        *) echo '[ERROR] PERF_RUNNER_AUTO_PREPARE 只允许 true 或 false' >&2; return 1 ;;
    esac
}
cleanup() {
    case \"\${PERF_MATERIALS_STAGE:-}\" in
        /tmp/qs-perf-materials.*) rm -rf -- \"\$PERF_MATERIALS_STAGE\" ;;
    esac
}
trap cleanup EXIT
if [ \"\$(id -u)\" -eq 0 ]; then
    install_materials
elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    export -f install_materials cleanup
    sudo -n env${remote_env} bash -c 'trap cleanup EXIT; install_materials'
else
    echo '[ERROR] 远端用户不是 root，且没有免密 sudo' >&2
    exit 1
fi
"

    printf '[INFO] 在 %s 上安装压测材料 sha256(env=%s iam=%s config=%s)\n' \
        "$PERF_RUNNER_HOST" "${env_sha:0:12}" "${iam_sha:0:12}" "${config_sha:0:12}"
    ssh "${ssh_options[@]}" "$PERF_RUNNER_HOST" \
        "env${remote_env} bash -c $(shell_quote "$remote_command")"
    REMOTE_STAGE_DIR=""
}

cleanup() {
    if [[ -n "$LOCAL_STAGE_DIR" && "$LOCAL_STAGE_DIR" == /tmp/qs-perf-materials.* ]]; then
        rm -rf -- "$LOCAL_STAGE_DIR"
    fi
    if [[ -n "$REMOTE_STAGE_DIR" && "$REMOTE_STAGE_DIR" == /tmp/qs-perf-materials.* && \
        -n "$PERF_RUNNER_HOST" ]]; then
        local -a options=(
            -o BatchMode=yes -o ConnectTimeout=15
            -o "StrictHostKeyChecking=${PERF_RUNNER_STRICT_HOST_KEY_CHECKING}"
            -p "$PERF_RUNNER_SSH_PORT"
        )
        [[ -n "$PERF_RUNNER_SSH_IDENTITY_FILE" ]] && options+=(-i "$PERF_RUNNER_SSH_IDENTITY_FILE")
        ssh "${options[@]}" "$PERF_RUNNER_HOST" \
            "rm -rf -- $(shell_quote "$REMOTE_STAGE_DIR")" >/dev/null 2>&1 || true
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    trap cleanup EXIT
    main "$@"
fi
