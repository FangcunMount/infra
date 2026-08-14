#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly INIT_SCRIPT="${SCRIPT_DIR}/init-perf-runner.sh"

# --help 在平台检查前返回，因此可以在 Mac 上加载并测试纯下载函数。
# shellcheck source=init-perf-runner.sh
source "$INIT_SCRIPT" --help >/dev/null

TEST_TMP_DIR="$(mktemp -d)"
trap 'rm -rf -- "$TEST_TMP_DIR"' EXIT

CURL_ATTEMPTS=0
curl() {
    local output=""
    while (( $# > 0 )); do
        case "$1" in
            --output)
                output="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    if [[ -z "$output" ]]; then
        return 2
    fi

    CURL_ATTEMPTS=$((CURL_ATTEMPTS + 1))
    if (( CURL_ATTEMPTS < 3 )); then
        printf 'partial-attempt-%s\n' "$CURL_ATTEMPTS" >"$output"
        return 56
    fi
    printf 'complete\n' >"$output"
}

PERF_DOWNLOAD_ATTEMPTS=3
PERF_DOWNLOAD_RETRY_DELAY_SECONDS=0
output_file="${TEST_TMP_DIR}/artifact.tar.gz"
download "https://example.invalid/artifact.tar.gz" "$output_file" 2>/dev/null

if (( CURL_ATTEMPTS != 3 )); then
    printf '[ERROR] 期望下载尝试 3 次，实际 %s 次\n' "$CURL_ATTEMPTS" >&2
    exit 1
fi
if [[ "$(<"$output_file")" != "complete" ]]; then
    printf '[ERROR] 成功结果包含失败尝试的残留内容\n' >&2
    exit 1
fi
if [[ -e "${output_file}.part" ]]; then
    printf '[ERROR] 成功后仍保留临时下载文件\n' >&2
    exit 1
fi

CURL_ATTEMPTS=0
curl() {
    local output=""
    while (( $# > 0 )); do
        case "$1" in
            --output)
                output="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    CURL_ATTEMPTS=$((CURL_ATTEMPTS + 1))
    printf 'partial\n' >"$output"
    return 56
}

PERF_DOWNLOAD_ATTEMPTS=2
failed_output="${TEST_TMP_DIR}/failed.tar.gz"
if download "https://example.invalid/failed.tar.gz" "$failed_output" 2>/dev/null; then
    printf '[ERROR] 下载全部失败时错误地返回成功\n' >&2
    exit 1
fi
if (( CURL_ATTEMPTS != 2 )); then
    printf '[ERROR] 期望失败下载尝试 2 次，实际 %s 次\n' "$CURL_ATTEMPTS" >&2
    exit 1
fi
if [[ -e "$failed_output" || -e "${failed_output}.part" ]]; then
    printf '[ERROR] 下载全部失败后遗留了不完整文件\n' >&2
    exit 1
fi

invalid_repo="${TEST_TMP_DIR}/invalid-repo"
git init -q "$invalid_repo"
if repository_checkout_is_usable "$invalid_repo"; then
    printf '[ERROR] 无提交、缺少 go.mod 的 checkout 被错误地视为可用\n' >&2
    exit 1
fi

valid_repo="${TEST_TMP_DIR}/valid-repo"
git init -q "$valid_repo"
mkdir -p "$valid_repo/scripts/perf/perfctl"
printf 'module example.invalid/qs-server\n' >"$valid_repo/go.mod"
printf '.PHONY: perf-verify\nperf-verify:\n\t@true\n' >"$valid_repo/Makefile"
printf 'package main\n' >"$valid_repo/scripts/perf/perfctl/main.go"
git -C "$valid_repo" add go.mod Makefile scripts/perf/perfctl/main.go
git -C "$valid_repo" \
    -c user.name=perf-test \
    -c user.email=perf-test@example.invalid \
    -c commit.gpgsign=false \
    commit -q -m 'test fixture'
if ! repository_checkout_is_usable "$valid_repo"; then
    printf '[ERROR] 完整 checkout 未被识别为可用\n' >&2
    exit 1
fi

snapshot_repo="${TEST_TMP_DIR}/snapshot-repo"
mkdir -p "$snapshot_repo/scripts/perf/perfctl"
printf 'module example.invalid/qs-server\n' >"$snapshot_repo/go.mod"
printf '.PHONY: perf-verify\nperf-verify:\n\t@true\n' >"$snapshot_repo/Makefile"
printf 'package main\n' >"$snapshot_repo/scripts/perf/perfctl/main.go"
printf '%064d\n' 0 >"$snapshot_repo/.perf-source-snapshot"
if ! repository_checkout_is_usable "$snapshot_repo"; then
    printf '[ERROR] 完整的本地源码快照未被识别为可用\n' >&2
    exit 1
fi

printf '[OK] 压测机下载重试与源码快照回归通过\n'
