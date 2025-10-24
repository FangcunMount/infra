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
    echo "  help        - 显示此帮助信息"
    echo
    echo "示例:"
    echo "  $0 enable   # 启用 VPN"
    echo "  $0 test     # 测试连接"
    echo "  $0 status   # 查看状态"
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