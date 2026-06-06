#!/bin/bash

# Docker VPN 管理脚本

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Mihomo API 配置
MIHOMO_API="http://127.0.0.1:9090"

# 显示帮助信息
show_help() {
    echo "Docker VPN 管理脚本"
    echo "==================="
    echo
    echo "用法: $0 [命令]"
    echo
    echo "命令:"
    echo "  status      - 显示 VPN 状态"
    echo "  test        - 测试 VPN 连接"
    echo "  enable      - 启用 VPN 模式"
    echo "  disable     - 禁用 VPN 模式（直连）"
    echo "  proxies     - 显示所有代理组状态"
    echo "  switch      - 切换漏网之鱼代理选择"
    echo "  docker-test - 测试 Docker 容器 VPN 连接"
    echo "  speed       - 测试 Mihomo 出站延迟与下载速度"
    echo "  help        - 显示此帮助信息"
    echo
    echo "示例:"
    echo "  $0 enable   # 启用 VPN"
    echo "  $0 test     # 测试连接"
    echo "  $0 speed    # 测速 (GitHub 下载等)"
    echo "  $0 status   # 查看状态"
    echo
    echo "测速环境变量:"
    echo "  VPN_SPEED_URL              自定义下载 URL"
    echo "  VPN_SPEED_BYTES=5242880    采样下载字节数 (默认 5MB)"
    echo "  VPN_SPEED_COMPARE_DIRECT=1 同时测直连基线"
    echo "  VPN_SPEED_TIMEOUT=60       curl 超时秒数"
}

# 获取当前漏网之鱼代理选择
get_current_proxy() {
    curl -s "$MIHOMO_API/proxies" | jq -r '.proxies["漏网之鱼"].now' 2>/dev/null || echo "unknown"
}

# 获取可用的代理选项
get_proxy_options() {
    curl -s "$MIHOMO_API/proxies" | jq -r '.proxies["漏网之鱼"].all[]' 2>/dev/null || echo ""
}

# 切换代理
switch_proxy() {
    local proxy_name="$1"
    local result
    
    result=$(curl -s -X PUT -H "Content-Type: application/json" \
        -d "{\"name\":\"$proxy_name\"}" \
        "$MIHOMO_API/proxies/漏网之鱼")
    
    if [ $? -eq 0 ]; then
        log_success "已切换到: $proxy_name"
        return 0
    else
        log_error "切换失败"
        return 1
    fi
}

# 测试网络连接
test_connection() {
    local test_type="$1"
    local proxy_flag="$2"
    
    if [ "$test_type" = "host" ]; then
        if [ -n "$proxy_flag" ]; then
            curl -s --connect-timeout 5 --proxy "$proxy_flag" http://httpbin.org/ip 2>/dev/null | jq -r '.origin' 2>/dev/null || echo "failed"
        else
            curl -s --connect-timeout 5 http://httpbin.org/ip 2>/dev/null | jq -r '.origin' 2>/dev/null || echo "failed"
        fi
    else
        # Docker 测试
        if [ -n "$proxy_flag" ]; then
            docker run --rm --network host alpine/curl:latest curl -s --connect-timeout 5 --proxy "$proxy_flag" http://httpbin.org/ip 2>/dev/null | jq -r '.origin' 2>/dev/null || echo "failed"
        else
            docker run --rm alpine/curl:latest curl -s --connect-timeout 5 http://httpbin.org/ip 2>/dev/null | jq -r '.origin' 2>/dev/null || echo "failed"
        fi
    fi
}

# 显示 VPN 状态
show_status() {
    echo "========================================"
    echo "🔍 Docker VPN 状态"
    echo "========================================"
    
    # Mihomo 服务状态
    if systemctl is-active --quiet mihomo 2>/dev/null; then
        log_success "✅ Mihomo VPN 服务: 运行中"
    else
        log_error "❌ Mihomo VPN 服务: 已停止"
        return 1
    fi
    
    # 代理端口
    if nc -z 127.0.0.1 7890 >/dev/null 2>&1; then
        log_success "✅ HTTP 代理端口 7890: 可用"
    else
        log_error "❌ HTTP 代理端口 7890: 不可用"
    fi
    
    # 当前代理选择
    local current_proxy=$(get_current_proxy)
    if [ "$current_proxy" != "unknown" ]; then
        log_info "当前漏网之鱼选择: $current_proxy"
        
        if [ "$current_proxy" = "DIRECT" ]; then
            log_warn "⚠️  当前为直连模式"
        else
            log_success "✅ 当前为 VPN 模式"
        fi
    else
        log_error "❌ 无法获取代理状态"
    fi
    
    echo
}

# 测试连接功能
test_connections() {
    echo "========================================"
    echo "🧪 网络连接测试"
    echo "========================================"
    
    # 宿主机直连测试
    log_info "测试宿主机直连..."
    local host_direct=$(test_connection "host" "")
    echo "宿主机直连 IP: $host_direct"
    
    # 宿主机 VPN 测试
    log_info "测试宿主机 VPN..."
    local host_vpn=$(test_connection "host" "http://127.0.0.1:7890")
    echo "宿主机 VPN IP: $host_vpn"
    
    # Docker 直连测试
    log_info "测试 Docker 直连..."
    local docker_direct=$(test_connection "docker" "")
    echo "Docker 直连 IP: $docker_direct"
    
    # Docker VPN 测试
    log_info "测试 Docker VPN..."
    local docker_vpn=$(test_connection "docker" "http://127.0.0.1:7890")
    echo "Docker VPN IP: $docker_vpn"
    
    echo
    echo "结果分析:"
    if [ "$host_direct" != "$host_vpn" ] && [ "$host_vpn" != "failed" ]; then
        log_success "✅ 宿主机 VPN 工作正常"
    else
        log_warn "⚠️  宿主机 VPN 可能有问题"
    fi
    
    if [ "$docker_direct" != "$docker_vpn" ] && [ "$docker_vpn" != "failed" ]; then
        log_success "✅ Docker VPN 工作正常"
    else
        log_warn "⚠️  Docker VPN 可能有问题"
    fi
    
    echo
}

# 启用 VPN 模式
enable_vpn() {
    log_info "启用 VPN 模式..."
    
    # 获取可用的非直连代理
    local options=$(get_proxy_options | grep -v "DIRECT" | head -1)
    
    if [ -n "$options" ]; then
        local target_proxy="自动选择"
        if get_proxy_options | grep -q "自动选择"; then
            target_proxy="自动选择"
        elif get_proxy_options | grep -q "手动切换"; then
            target_proxy="手动切换"
        else
            target_proxy=$(get_proxy_options | grep -v "DIRECT" | head -1)
        fi
        
        switch_proxy "$target_proxy"
        sleep 2
        show_status
    else
        log_error "没有可用的 VPN 代理"
        return 1
    fi
}

# 禁用 VPN 模式
disable_vpn() {
    log_info "禁用 VPN 模式（切换到直连）..."
    switch_proxy "DIRECT"
    sleep 2
    show_status
}

# 显示所有代理组状态
show_proxies() {
    echo "========================================"
    echo "🔗 代理组状态"
    echo "========================================"
    
    local proxies=$(curl -s "$MIHOMO_API/proxies" | jq -r '.proxies | keys[]' 2>/dev/null)
    
    for proxy in $proxies; do
        local current=$(curl -s "$MIHOMO_API/proxies" | jq -r ".proxies[\"$proxy\"].now" 2>/dev/null)
        local type=$(curl -s "$MIHOMO_API/proxies" | jq -r ".proxies[\"$proxy\"].type" 2>/dev/null)
        
        if [ "$type" = "Selector" ]; then
            echo "$proxy: $current"
        fi
    done
    echo
}

# 交互式切换代理
interactive_switch() {
    echo "========================================"
    echo "🔄 切换漏网之鱼代理"
    echo "========================================"
    
    local current=$(get_current_proxy)
    echo "当前选择: $current"
    echo
    
    local options=$(get_proxy_options)
    local i=1
    
    echo "可用选项:"
    for option in $options; do
        echo "$i) $option"
        i=$((i+1))
    done
    echo
    
    read -p "请选择代理 (输入数字): " choice
    
    if [[ "$choice" =~ ^[0-9]+$ ]]; then
        local selected=$(echo "$options" | sed -n "${choice}p")
        if [ -n "$selected" ]; then
            switch_proxy "$selected"
            sleep 2
            show_status
        else
            log_error "无效选择"
        fi
    else
        log_error "请输入数字"
    fi
}

# Mihomo 出站测速
MIHOMO_PROXY="http://127.0.0.1:7890"
SPEED_DELAY_URL="http://www.gstatic.com/generate_204"
SPEED_GITHUB_URL="${VPN_SPEED_URL:-https://codeload.github.com/git/git/tar.gz/v2.45.0}"
SPEED_SAMPLE_BYTES="${VPN_SPEED_BYTES:-5242880}"
SPEED_TIMEOUT="${VPN_SPEED_TIMEOUT:-60}"

url_encode() {
    printf '%s' "$1" | jq -sRr @uri
}

format_speed() {
    awk -v b="${1:-0}" 'BEGIN {
        if (b >= 1048576) printf "%.2f MB/s", b / 1048576;
        else if (b >= 1024) printf "%.2f KB/s", b / 1024;
        else printf "%.0f B/s", b;
    }'
}

format_bytes() {
    awk -v b="${1:-0}" 'BEGIN {
        if (b >= 1073741824) printf "%.2f GB", b / 1073741824;
        else if (b >= 1048576) printf "%.2f MB", b / 1048576;
        else if (b >= 1024) printf "%.2f KB", b / 1024;
        else printf "%.0f B", b;
    }'
}

is_proxy_group_type() {
    case "$1" in
        Selector|URLTest|Fallback|LoadBalance|Relay) return 0 ;;
        *) return 1 ;;
    esac
}

resolve_active_proxy() {
    local name="${1:-GLOBAL}"
    local info type now

    for _ in 1 2 3 8; do
        info=$(curl -s --connect-timeout 3 "${MIHOMO_API}/proxies/$(url_encode "$name")" 2>/dev/null || echo "")
        if [ -z "$info" ]; then
            echo "$name"
            return 0
        fi

        type=$(echo "$info" | jq -r '.type // empty' 2>/dev/null)
        now=$(echo "$info" | jq -r '.now // empty' 2>/dev/null)

        if is_proxy_group_type "$type"; then
            if [ -z "$now" ] || [ "$now" = "null" ]; then
                echo "$name"
                return 0
            fi
            name="$now"
        else
            echo "$name"
            return 0
        fi
    done

    echo "$name"
}

get_proxy_chain() {
    local name="${1:-GLOBAL}"
    local chain="$name"
    local info type now

    for _ in 1 2 3 4 5; do
        info=$(curl -s --connect-timeout 3 "${MIHOMO_API}/proxies/$(url_encode "$name")" 2>/dev/null || echo "")
        [ -z "$info" ] && break

        type=$(echo "$info" | jq -r '.type // empty' 2>/dev/null)
        now=$(echo "$info" | jq -r '.now // empty' 2>/dev/null)

        if is_proxy_group_type "$type"; then
            if [ -z "$now" ] || [ "$now" = "null" ]; then
                break
            fi
            chain="${chain} → ${now}"
            name="$now"
        else
            break
        fi
    done

    echo "$chain"
}

test_mihomo_delay() {
    local proxy_name="$1"
    local encoded response delay

    encoded=$(url_encode "$proxy_name")
    response=$(curl -s --connect-timeout 3 \
        "${MIHOMO_API}/proxies/${encoded}/delay?timeout=5000&url=${SPEED_DELAY_URL}" 2>/dev/null || echo "")

    delay=$(echo "$response" | jq -r '.delay // empty' 2>/dev/null)
    if [ -n "$delay" ] && [ "$delay" != "null" ] && [ "$delay" -ge 0 ] 2>/dev/null; then
        echo "${delay}"
        return 0
    fi

    echo "failed"
    return 1
}

run_curl_probe() {
    local use_proxy="$1"
    local url="$2"
    local with_range="${3:-1}"
    local curl_args=(
        -s -o /dev/null
        --connect-timeout 10
        --max-time "$SPEED_TIMEOUT"
        -w "%{http_code} %{time_namelookup} %{time_connect} %{time_appconnect} %{time_starttransfer} %{time_total} %{size_download} %{speed_download}"
    )

    if [ "$with_range" = "1" ]; then
        local range_end=$((SPEED_SAMPLE_BYTES - 1))
        curl_args+=(-r "0-${range_end}")
    fi

    if [ "$use_proxy" = "proxy" ]; then
        curl_args+=(--proxy "$MIHOMO_PROXY")
    fi

    curl "${curl_args[@]}" "$url" 2>/dev/null || echo "failed"
}

get_proxy_exit_ip() {
    local url ip

    for url in "https://api.ipify.org?format=json" "http://icanhazip.com" "http://httpbin.org/ip"; do
        ip=$(curl -s --connect-timeout 8 --max-time 15 --proxy "$MIHOMO_PROXY" "$url" 2>/dev/null || echo "")
        if [ -z "$ip" ]; then
            continue
        fi
        if [[ "$url" == *"ipify"* ]]; then
            ip=$(echo "$ip" | jq -r '.ip // empty' 2>/dev/null)
        elif [[ "$url" == *"httpbin"* ]]; then
            ip=$(echo "$ip" | jq -r '.origin // empty' 2>/dev/null)
        else
            ip=$(echo "$ip" | tr -d '\n\r ')
        fi
        if [ -n "$ip" ]; then
            echo "$ip"
            return 0
        fi
    done

    echo ""
    return 1
}

print_probe_result() {
    local label="$1"
    local mode="$2"
    local metrics="$3"

    if [ "$metrics" = "failed" ] || [ -z "$metrics" ]; then
        log_warn "⚠️  ${label} (${mode}): 失败"
        return 1
    fi

    local http_code time_namelookup time_connect time_appconnect time_starttransfer time_total size_download speed_download
    read -r http_code time_namelookup time_connect time_appconnect time_starttransfer time_total size_download speed_download <<< "$metrics"

    if [ "$http_code" != "200" ] && [ "$http_code" != "206" ]; then
        log_warn "⚠️  ${label} (${mode}): HTTP ${http_code}"
        return 1
    fi

    local speed_human size_human timed_out=0
    speed_human=$(format_speed "$speed_download")
    size_human=$(format_bytes "$size_download")

    if awk -v t="$time_total" -v limit="$SPEED_TIMEOUT" 'BEGIN { exit !(t >= limit - 0.5) }'; then
        timed_out=1
    fi

    echo "  ${label} (${mode})"
    echo "    下载: ${size_human} @ ${speed_human}, 总耗时 ${time_total}s"
    echo "    时序: DNS ${time_namelookup}s / TCP ${time_connect}s / TLS ${time_appconnect}s / 首字节 ${time_starttransfer}s"
    if [ "$timed_out" -eq 1 ]; then
        log_warn "    ⚠️  已达 ${SPEED_TIMEOUT}s 超时上限，实际带宽可能更高"
    fi
    return 0
}

analyze_speed_ratio() {
    local proxy_metrics="$1"
    local direct_metrics="$2"

    if [ "$proxy_metrics" = "failed" ] || [ "$direct_metrics" = "failed" ]; then
        return 0
    fi

    local proxy_speed direct_speed
    proxy_speed=$(awk '{print $8}' <<< "$proxy_metrics")
    direct_speed=$(awk '{print $8}' <<< "$direct_metrics")

    echo
    echo "── 结果分析 ──"
    awk -v p="$proxy_speed" -v d="$direct_speed" 'BEGIN {
        if (d <= 0 || p <= 0) exit
        ratio = p / d
        if (ratio >= 0.85 && ratio <= 1.15) {
            print "  代理与直连速度接近（比值 " sprintf("%.2f", ratio) "），瓶颈大概率不在 Mihomo，而是："
            print "    · 服务器到 GitHub 的国际出口带宽本身较慢"
            print "    · GitHub/codeload 对当前 IP 限速"
            print "    · 测速采样触达超时上限（见上方警告）"
        } else if (ratio < 0.85) {
            print "  代理明显慢于直连（比值 " sprintf("%.2f", ratio) "），建议："
            print "    · make vpn-switch 换一个节点"
            print "    · 检查订阅节点是否过载"
        } else {
            print "  代理快于直连（比值 " sprintf("%.2f", ratio) "），翻墙链路工作正常"
        }
    }'
}

speed_test() {
    echo "========================================"
    echo "📊 Mihomo 出站测速"
    echo "========================================"

    if ! systemctl is-active --quiet mihomo 2>/dev/null && ! pgrep -f "mihomo" >/dev/null 2>&1; then
        log_error "❌ Mihomo 服务未运行，请先执行: make vpn-setup 或 systemctl start mihomo"
        return 1
    fi

    if ! nc -z 127.0.0.1 7890 >/dev/null 2>&1; then
        log_error "❌ HTTP 代理端口 7890 不可用"
        return 1
    fi

    if ! curl -s --connect-timeout 3 "${MIHOMO_API}/version" >/dev/null 2>&1; then
        log_error "❌ Mihomo API (9090) 不可用"
        return 1
    fi

    local proxy_chain active_proxy auto_proxy proxy_ip proxy_delay
    proxy_chain=$(get_proxy_chain "GLOBAL")
    active_proxy=$(resolve_active_proxy "GLOBAL")
    auto_proxy=$(resolve_active_proxy "自动选择")

    echo
    log_info "当前代理链路: ${proxy_chain}"
    if [ "$auto_proxy" != "$active_proxy" ] && [ "$auto_proxy" != "自动选择" ]; then
        log_info "自动选择当前节点: ${auto_proxy}"
    fi
    if [ "$active_proxy" = "DIRECT" ]; then
        log_warn "⚠️  当前为直连模式，测速结果不代表 VPN 节点性能"
        log_info "建议先执行: make vpn-enable"
    elif is_proxy_group_type "$(curl -s --connect-timeout 3 "${MIHOMO_API}/proxies/$(url_encode "$active_proxy")" 2>/dev/null | jq -r '.type // empty' 2>/dev/null)"; then
        log_warn "⚠️  当前解析到的是代理组 (${active_proxy})，非具体节点，延迟测试可能失败"
        log_info "可执行 make vpn-proxies 查看各组实际选择"
    fi

    proxy_ip=$(get_proxy_exit_ip || true)
    if [ -n "$proxy_ip" ]; then
        log_info "代理出口 IP: ${proxy_ip}"
    else
        log_warn "⚠️  无法获取代理出口 IP（不影响 GitHub 测速，仅作参考）"
    fi

    echo
    echo "── 延迟 ──"
    proxy_delay=$(test_mihomo_delay "$active_proxy" || true)
    if [ "$proxy_delay" = "failed" ] && [ "$auto_proxy" != "$active_proxy" ]; then
        proxy_delay=$(test_mihomo_delay "$auto_proxy" || true)
        active_proxy="$auto_proxy"
    fi
    if [ "$proxy_delay" != "failed" ]; then
        log_success "✅ 节点延迟 (${active_proxy}): ${proxy_delay} ms"
    else
        log_warn "⚠️  节点延迟测试失败 (${active_proxy})"
        log_info "可对代理组批量测延迟: curl -s \"${MIHOMO_API}/group/自动选择/delay?timeout=5000&url=${SPEED_DELAY_URL}\" | jq"
    fi

    local github_probe
    github_probe=$(run_curl_probe "proxy" "https://api.github.com/zen" 0 || true)
    print_probe_result "GitHub API 连通" "代理" "$github_probe" || true

    echo
    echo "── 下载测速 (采样 $(format_bytes "$SPEED_SAMPLE_BYTES")) ──"
    log_info "测速 URL: ${SPEED_GITHUB_URL}"

    local proxy_download
    proxy_download=$(run_curl_probe "proxy" "$SPEED_GITHUB_URL" 1 || true)
    if print_probe_result "GitHub 下载" "代理" "$proxy_download"; then
        log_success "✅ 代理下载测速完成"
    else
        log_warn "⚠️  代理下载测速失败，可尝试: VPN_SPEED_URL=<其他URL> make vpn-speed"
    fi

    if [ "${VPN_SPEED_COMPARE_DIRECT:-}" = "1" ]; then
        echo
        echo "── 直连对比 ──"
        local direct_download
        direct_download=$(run_curl_probe "direct" "$SPEED_GITHUB_URL" 1 || true)
        print_probe_result "GitHub 下载" "直连" "$direct_download" || log_warn "⚠️  直连下载失败（国内环境常见）"
        analyze_speed_ratio "$proxy_download" "$direct_download"
    else
        echo
        log_info "提示: 加 VPN_SPEED_COMPARE_DIRECT=1 可同时测直连基线并自动分析瓶颈"
    fi

    echo
}

# Docker VPN 测试
docker_vpn_test() {
    # 检查 Docker 是否安装（仅此命令需要）
    if ! command -v docker >/dev/null 2>&1; then
        log_error "docker-test 命令需要 Docker"
        log_info "请先安装 Docker: make server-install-docker"
        exit 1
    fi
    
    echo "========================================"
    echo "🐳 Docker VPN 专项测试"
    echo "========================================"
    
    log_info "测试 1: 普通网络模式 + 环境变量"
    docker run --rm \
        --env HTTP_PROXY=http://172.18.0.1:7890 \
        --env HTTPS_PROXY=http://172.18.0.1:7890 \
        alpine/curl:latest \
        curl -s --connect-timeout 5 http://httpbin.org/ip | jq -r '.origin' 2>/dev/null || echo "失败"
    
    log_info "测试 2: Host 网络模式 + --proxy 参数"
    docker run --rm --network host \
        alpine/curl:latest \
        curl -s --connect-timeout 5 --proxy http://127.0.0.1:7890 http://httpbin.org/ip | jq -r '.origin' 2>/dev/null || echo "失败"
    
    log_info "测试 3: 普通网络模式 + --proxy 参数"
    docker run --rm \
        alpine/curl:latest \
        curl -s --connect-timeout 5 --proxy http://172.18.0.1:7890 http://httpbin.org/ip | jq -r '.origin' 2>/dev/null || echo "失败"
    
    echo
    log_info "推荐的 Docker VPN 使用方法:"
    echo "  docker run --network host --rm alpine/curl curl --proxy http://127.0.0.1:7890 [URL]"
    echo "  或者"
    echo "  docker run --rm alpine/curl curl --proxy http://172.18.0.1:7890 [URL]"
    echo
}

# 主程序
main() {
    case "${1:-help}" in
        "status")
            show_status
            ;;
        "test")
            test_connections
            ;;
        "enable")
            enable_vpn
            ;;
        "disable")
            disable_vpn
            ;;
        "proxies")
            show_proxies
            ;;
        "switch")
            interactive_switch
            ;;
        "docker-test")
            docker_vpn_test
            ;;
        "speed")
            speed_test
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            log_error "未知命令: $1"
            echo
            show_help
            exit 1
            ;;
    esac
}

# 检查依赖
if ! command -v curl >/dev/null 2>&1; then
    log_error "需要 curl 命令"
    log_info "安装: apt-get install -y curl (Ubuntu/Debian) 或 yum install -y curl (CentOS/RHEL)"
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    log_error "需要 jq 命令"
    log_info "安装: apt-get install -y jq (Ubuntu/Debian) 或 yum install -y jq (CentOS/RHEL)"
    exit 1
fi

# 注意: docker 命令仅 docker-test 子命令需要，其他命令不依赖 Docker

# 运行主程序
main "$@"