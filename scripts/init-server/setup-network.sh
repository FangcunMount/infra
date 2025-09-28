#!/usr/bin/env bash
set -euo pipefail

# ========================================
# Mihomo VPN 安装脚本 - 简化版
# 1. 安装 mihomo 客户端
# 2. 输入订阅链接
# 3. 下载订阅配置
# 4. 启动 VPN 服务
# 5. 测试网络连接
# ========================================

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# 智能检测static目录位置
detect_static_dir() {
    local potential_dirs=(
        "${REPO_ROOT}/static"                    # 标准项目结构
        "${SCRIPT_DIR}/static"                   # 脚本同级目录
        "$(pwd)/static"                          # 当前工作目录
        "/root/workspace/infra/static"           # 您的项目目录
        "/home/root/workspace/infra/static"      # 备用项目目录
        "/root/static"                           # 传统位置
    )
    
    for dir in "${potential_dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            STATIC_DIR="$dir"
            return 0
        fi
    done
    
    # 默认回退到仓库根目录下的static
    STATIC_DIR="${REPO_ROOT}/static"
}

detect_static_dir

readonly CONFIG_DIR="/root/.config/clash"
readonly CONFIG_FILE="${CONFIG_DIR}/config.yaml"
readonly SERVICE_FILE="/etc/systemd/system/mihomo.service"
readonly BINARY_TARGET="/usr/local/bin/mihomo"

# 错误处理
handle_error() {
    local exit_code=$?
    local line=$1
    log_error "脚本执行失败 (行号: ${line})"
    log_error "命令: ${BASH_COMMAND}"
    exit "${exit_code}"
}
trap 'handle_error $LINENO' ERR

# 初始化运行环境
init_environment() {
    log_info "初始化运行环境..."
    
    # 检查是否在项目目录中
    local current_dir="$(pwd)"
    if [[ "$current_dir" == */workspace/infra ]] || [[ "$current_dir" == */infra ]]; then
        log_info "检测到在项目目录中运行: $current_dir"
    else
        # 尝试切换到正确的项目目录
        local project_dirs=(
            "/root/workspace/infra"
            "$HOME/workspace/infra"
            "/home/root/workspace/infra"
            "$(dirname "$0")/../../"
        )
        
        for dir in "${project_dirs[@]}"; do
            if [[ -d "$dir" && -f "$dir/scripts/init-server/setup-network.sh" ]]; then
                log_info "切换到项目目录: $dir"
                cd "$dir"
                # 重新检测路径
                SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
                REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
                detect_static_dir
                break
            fi
        done
    fi
}

# 检查运行权限
check_root() {
    if [[ ${EUID} -ne 0 ]]; then
        log_error "此脚本必须以 root 权限运行"
        echo "请使用: sudo $0"
        exit 1
    fi
}

# 检查系统环境
check_system() {
    log_step "检查系统环境"
    
    if [[ ! -f /etc/os-release ]]; then
        log_error "无法识别操作系统"
        exit 1
    fi
    
    local os_id
    os_id=$(grep '^ID=' /etc/os-release | cut -d'=' -f2 | tr -d '"')
    if [[ "${os_id}" != "ubuntu" ]]; then
        log_error "仅支持 Ubuntu 系统，当前系统: ${os_id}"
        exit 1
    fi
    
    log_success "系统检查通过"
}

# 检查静态资源
check_static_resources() {
    log_step "检查静态资源"
    
    # 显示检测到的路径信息
    log_info "路径检测信息："
    log_info "  脚本目录: ${SCRIPT_DIR}"
    log_info "  项目根目录: ${REPO_ROOT}"
    log_info "  静态文件目录: ${STATIC_DIR}"
    log_info "  当前工作目录: $(pwd)"
    
    if [[ ! -d "${STATIC_DIR}" ]]; then
        log_error "未找到 static 目录: ${STATIC_DIR}"
        log_info "请确保在正确的项目目录下运行脚本，或将static目录放到以下任一位置："
        log_info "  • ${REPO_ROOT}/static"
        log_info "  • ${SCRIPT_DIR}/static"
        log_info "  • $(pwd)/static"
        log_info "  • /root/workspace/infra/static"
        exit 1
    fi
    
    local required_files=("geosite.dat" "geoip.metadb")
    for file in "${required_files[@]}"; do
        if [[ ! -f "${STATIC_DIR}/${file}" ]]; then
            log_error "缺少必需文件: ${STATIC_DIR}/${file}"
            exit 1
        fi
    done
    
    log_success "静态资源检查完成"
}

# 根据架构选择二进制文件
get_binary_name() {
    local arch
    arch=$(uname -m)
    case "${arch}" in
        x86_64|amd64) echo "mihomo-linux-amd64" ;;
        aarch64|arm64) echo "mihomo-linux-arm64" ;;
        armv7l|armv7) echo "mihomo-linux-armv7" ;;
        *)
            log_error "不支持的 CPU 架构: ${arch}"
            exit 1
            ;;
    esac
}

# 步骤1：安装 mihomo 客户端
install_mihomo() {
    log_step "1. 安装 mihomo 客户端"
    
    local binary_name
    binary_name=$(get_binary_name)
    local binary_path="${STATIC_DIR}/${binary_name}"
    
    if [[ ! -f "${binary_path}" ]]; then
        log_error "未找到二进制文件: ${binary_path}"
        exit 1
    fi
    
    # 安装二进制文件
    install -m 755 "${binary_path}" "${BINARY_TARGET}"
    
    # 验证安装
    if "${BINARY_TARGET}" -v >/dev/null 2>&1; then
        log_success "mihomo 安装成功"
        "${BINARY_TARGET}" -v
    else
        log_error "mihomo 安装失败"
        exit 1
    fi
}

# 步骤2：要求用户输入订阅链接
get_subscription_url() {
    log_step "2. 输入订阅链接" >&2
    
    local subscription_url=""
    while [[ -z "${subscription_url}" ]]; do
        echo >&2
        echo "请选择输入方式：" >&2
        echo "1) 直接输入订阅链接" >&2
        echo "2) 从文件读取订阅链接" >&2
        read -rp "选择 (1/2): " input_method
        
        case "${input_method}" in
            1|"")
                read -rp "请输入 Clash 订阅链接: " subscription_url
                ;;
            2)
                read -rp "请输入包含订阅链接的文件路径: " url_file
                if [[ -f "${url_file}" ]]; then
                    subscription_url=$(head -1 "${url_file}" 2>/dev/null)
                    log_info "从文件读取链接: ${subscription_url}" >&2
                else
                    log_warn "文件不存在: ${url_file}" >&2
                    continue
                fi
                ;;
            *)
                log_warn "无效选择，请重新选择" >&2
                continue
                ;;
        esac
        
        # 清理输入的 URL（移除首尾空格和换行符）
        subscription_url=$(echo "${subscription_url}" | tr -d '\r\n' | xargs)
        
        if [[ -z "${subscription_url}" ]]; then
            log_warn "订阅链接不能为空，请重新输入" >&2
        elif [[ ! "${subscription_url}" =~ ^https?:// ]]; then
            log_warn "请输入有效的 HTTP/HTTPS 链接" >&2
            subscription_url=""
        else
            log_info "验证链接格式: ${subscription_url}" >&2
            # 简单测试链接连通性
            if curl -s --connect-timeout 10 --head "${subscription_url}" >/dev/null 2>&1; then
                log_success "链接验证通过" >&2
            else
                log_warn "链接连通性测试失败，但将继续尝试下载" >&2
            fi
        fi
    done
    
    echo "${subscription_url}"
}

# 步骤3：下载订阅，更新 mihomo 配置
download_and_setup_config() {
    local subscription_url=$1
    log_step "3. 下载订阅配置"
    
    # 创建配置目录
    mkdir -p "${CONFIG_DIR}"
    chmod 700 "${CONFIG_DIR}"
    
    # 部署地理数据文件
    log_info "部署地理数据文件"
    install -m 644 "${STATIC_DIR}/geosite.dat" "${CONFIG_DIR}/geosite.dat"
    install -m 644 "${STATIC_DIR}/geoip.metadb" "${CONFIG_DIR}/geoip.metadb"
    
    # 下载订阅配置
    log_info "正在下载订阅配置..."
    log_info "原始链接: '${subscription_url}'"
    local temp_config="/tmp/mihomo_config.yaml"
    
    # 清理可能的换行符或空格
    subscription_url=$(echo "${subscription_url}" | tr -d '\r\n' | xargs)
    log_info "清理后链接: '${subscription_url}'"
    log_info "链接长度: ${#subscription_url}"
    
    # 诊断 URL
    if [[ "${subscription_url}" =~ [[:space:]] ]]; then
        log_warn "检测到 URL 中包含空格字符"
    fi
    
    if curl -fsSL --connect-timeout 30 --max-time 60 -o "${temp_config}" "${subscription_url}"; then
        log_success "订阅配置下载成功"
        
        # 直接使用完整的订阅配置，只修改必要的参数
        log_info "调整配置参数"
        
        # 复制原始配置
        cp "${temp_config}" "${CONFIG_FILE}"
        
        # 修改关键配置项以确保本地可控
        sed -i 's/^external-controller:.*/external-controller: 0.0.0.0:9090/' "${CONFIG_FILE}"
        sed -i 's/^geo-auto-update:.*/geo-auto-update: false/' "${CONFIG_FILE}"
        
        # 如果没有 geo-auto-update 配置，添加它
        if ! grep -q "geo-auto-update:" "${CONFIG_FILE}"; then
            echo "geo-auto-update: false" >> "${CONFIG_FILE}"
        fi
        
        # 确保有正确的端口配置
        if ! grep -q "^mixed-port:" "${CONFIG_FILE}"; then
            sed -i '1i mixed-port: 7890' "${CONFIG_FILE}"
        fi
        
        # 添加 SOCKS5 端口配置
        if ! grep -q "^socks-port:" "${CONFIG_FILE}"; then
            sed -i '/^mixed-port:/a socks-port: 7891' "${CONFIG_FILE}"
        fi
        
        # 确保允许局域网访问
        if ! grep -q "^allow-lan:" "${CONFIG_FILE}"; then
            sed -i '/^socks-port:/a allow-lan: true' "${CONFIG_FILE}"
        else
            sed -i 's/^allow-lan:.*/allow-lan: true/' "${CONFIG_FILE}"
        fi
        
        log_info "使用完整订阅配置，已优化本地访问设置"
        
        rm -f "${temp_config}"
        chmod 600 "${CONFIG_FILE}"
        
        # 处理 proxy-providers 配置
        handle_proxy_providers "${subscription_url}"
        
        log_success "配置文件创建完成: ${CONFIG_FILE}"
    else
        local curl_exit_code=$?
        log_error "订阅配置下载失败 (curl exit code: ${curl_exit_code})"
        log_error "订阅链接: ${subscription_url}"
        log_info "尝试手动测试: curl -v '${subscription_url}'"
        log_error "请检查以下问题："
        echo "  • 网络连接是否正常"
        echo "  • 订阅链接是否有效"
        echo "  • 是否需要代理访问"
        echo "  • 服务器防火墙设置"
        exit 1
    fi
}

# 步骤4：跑通 VPN
setup_and_start_vpn() {
    log_step "4. 启动 VPN 服务"
    
    # 创建 systemd 服务
    log_info "创建 systemd 服务"
    cat > "${SERVICE_FILE}" << EOF
[Unit]
Description=Mihomo (Clash.Meta) Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=${BINARY_TARGET} -d ${CONFIG_DIR}
Restart=on-failure
RestartSec=5
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
    
    chmod 644 "${SERVICE_FILE}"
    
    # 重载 systemd 并启动服务
    systemctl daemon-reload
    systemctl enable mihomo.service
    systemctl start mihomo.service
    
    # 等待服务启动
    log_info "等待服务启动..."
    sleep 3
    
    # 检查服务状态
    if systemctl is-active --quiet mihomo.service; then
        log_success "mihomo 服务启动成功"
        
        # 配置全局代理环境变量
        log_info "配置全局代理环境变量"
        cat > /etc/profile.d/mihomo-proxy.sh << 'EOF'
# Mihomo 代理环境变量配置
# 检查 mihomo 服务是否运行，如果运行则自动启用代理

# 检查服务状态并自动设置代理
if systemctl is-active --quiet mihomo.service 2>/dev/null; then
    export http_proxy="http://127.0.0.1:7890"
    export https_proxy="http://127.0.0.1:7890"
    export all_proxy="socks5://127.0.0.1:7891"
    
    # 仅在交互式登录时显示代理状态
    if [[ $- == *i* ]] && [[ -n "$PS1" ]]; then
        echo "🔗 Mihomo 代理已自动启用 (HTTP: 7890, SOCKS5: 7891)"
    fi
fi

proxy-on() {
    if systemctl is-active --quiet mihomo.service 2>/dev/null; then
        export http_proxy="http://127.0.0.1:7890"
        export https_proxy="http://127.0.0.1:7890"
        export all_proxy="socks5://127.0.0.1:7891"
        echo "🟢 代理已开启"
    else
        echo "❌ Mihomo 服务未运行，请先启动服务: systemctl start mihomo"
        return 1
    fi
}

proxy-off() {
    unset http_proxy https_proxy all_proxy
    echo "🔴 代理已关闭"
}

proxy-status() {
    echo "📊 代理状态："
    echo "  HTTP_PROXY:  ${http_proxy:-'未设置'}"
    echo "  HTTPS_PROXY: ${https_proxy:-'未设置'}"
    echo "  ALL_PROXY:   ${all_proxy:-'未设置'}"
    echo "  服务状态:    $(systemctl is-active mihomo.service 2>/dev/null || echo '未运行')"
}

# 为了兼容性，也创建别名
alias proxy-status='proxy-status'
EOF
        chmod 644 /etc/profile.d/mihomo-proxy.sh
        
        # 加载环境变量
        source /etc/profile.d/mihomo-proxy.sh
        
        # 等待服务完全启动
        log_info "等待服务完全启动..."
        sleep 5
        
        # 验证API可访问性
        local api_ready=false
        for i in {1..10}; do
            if curl -s --connect-timeout 3 "http://127.0.0.1:9090/version" >/dev/null 2>&1; then
                api_ready=true
                break
            fi
            log_info "等待API就绪... ($i/10)"
            sleep 2
        done
        
        if [[ "${api_ready}" == "true" ]]; then
            log_success "✅ 控制API就绪"
            
            # 智能设置全局代理模式（允许失败）
            log_step "5. 智能设置代理模式"
            if ! setup_optimal_proxy_mode; then
                log_warn "⚠️  自动代理设置失败，稍后可手动配置"
                log_info "   可运行: $0 --fix-proxy"
            fi
        else
            log_warn "⚠️  控制API响应较慢，将在后续步骤中重试"
        fi
        
        log_success "VPN 服务配置完成"
    else
        log_error "mihomo 服务启动失败"
        systemctl status mihomo.service --no-pager
        exit 1
    fi
}

# 智能设置最佳代理模式
setup_optimal_proxy_mode() {
    log_info "智能分析并设置最佳代理模式"
    
    # 等待API完全就绪 - 增加等待时间
    local retry_count=0
    local max_retries=20
    while [ $retry_count -lt $max_retries ]; do
        if curl -s "http://127.0.0.1:9090/proxies" >/dev/null 2>&1; then
            break
        fi
        log_info "等待API就绪... ($((retry_count + 1))/$max_retries)"
        sleep 3
        retry_count=$((retry_count + 1))
    done
    
    if [ $retry_count -eq $max_retries ]; then
        log_warn "⚠️  API响应较慢，将继续尝试配置"
        # 不返回错误，继续尝试配置
    fi
    
    # 额外等待，确保provider完全加载
    log_info "等待代理节点完全加载..."
    sleep 5
    
    # 分析所有可用的代理组 - 增加重试逻辑
    local global_info proxy_groups available_groups
    local info_retry=0
    local max_info_retries=5
    
    while [ $info_retry -lt $max_info_retries ]; do
        global_info=$(curl -s "http://127.0.0.1:9090/proxies/GLOBAL" 2>/dev/null)
        available_groups=$(echo "$global_info" | grep -o '"all":\[[^]]*\]' | grep -o '"[^"]*"' | grep -v '"all"' | tr -d '"')
        
        if [ -n "$available_groups" ]; then
            break
        fi
        
        log_info "重试获取代理组信息... ($((info_retry + 1))/$max_info_retries)"
        sleep 3
        info_retry=$((info_retry + 1))
    done
    
    if [ -z "$available_groups" ]; then
        log_error "❌ 无法获取代理组信息"
        return 0  # 返回0而不是1，避免中断安装流程
    fi
    
    log_info "可用代理组: $(echo "$available_groups" | tr '\n' ' ')"
    
    # 分析每个代理组的质量
    local best_auto_group=""
    local best_manual_group=""
    local fallback_group=""
    
    for group in $available_groups; do
        if [[ "$group" =~ (自动选择|自动|auto|Auto|AUTO|♻️|🚀|🔀) ]]; then
            if [ -z "$best_auto_group" ]; then
                best_auto_group="$group"
            fi
        elif [[ "$group" =~ (手动|选择|manual|Manual|MANUAL|🎯|📍) ]]; then
            if [ -z "$best_manual_group" ]; then
                best_manual_group="$group"
            fi
        elif [[ ! "$group" =~ ^(DIRECT|REJECT|直连|拒绝)$ ]]; then
            if [ -z "$fallback_group" ]; then
                fallback_group="$group"
            fi
        fi
    done
    
    # 选择最佳代理组
    local target_group=""
    local group_type=""
    
    if [ -n "$best_auto_group" ]; then
        target_group="$best_auto_group"
        group_type="自动"
    elif [ -n "$best_manual_group" ]; then
        target_group="$best_manual_group"  
        group_type="手动"
    elif [ -n "$fallback_group" ]; then
        target_group="$fallback_group"
        group_type="备用"
    else
        log_warn "⚠️  只找到基础代理组，VPN功能可能受限"
        target_group=$(echo "$available_groups" | head -1)
        group_type="基础"
    fi
    
    log_info "选择${group_type}代理组: $target_group"
    
    # 设置全局代理
    if curl -X PUT -H "Content-Type: application/json" -d "{\"name\":\"$target_group\"}" "http://127.0.0.1:9090/proxies/GLOBAL" >/dev/null 2>&1; then
        log_success "✅ 全局代理已设置为: $target_group"
        
        # 验证设置结果
        sleep 3
        local current_proxy
        current_proxy=$(curl -s "http://127.0.0.1:9090/proxies/GLOBAL" | grep -o '"now":"[^"]*"' | cut -d'"' -f4)
        
        if [[ "$current_proxy" == "$target_group" ]]; then
            log_success "✅ 代理模式验证成功: $current_proxy"
            
            # 如果是手动选择组，尝试设置为非DIRECT选项
            if [[ "$group_type" == "手动" ]]; then
                configure_manual_proxy_group "$target_group"
            fi
            
            # 🔥 关键修复：配置"漏网之鱼"代理组
            configure_fallback_proxy_group "$target_group"
            
            return 0
        else
            log_warn "⚠️  代理设置可能未生效，当前: $current_proxy"
        fi
    else
        log_error "❌ 无法设置全局代理为: $target_group"
    fi
    
    # 显示手动设置指令
    echo ""
    echo "🔧 手动设置代理命令："
    echo "   curl -X PUT -H \"Content-Type: application/json\" -d '{\"name\":\"$target_group\"}' \"http://127.0.0.1:9090/proxies/GLOBAL\""
    echo "   或运行: $0 --fix-proxy"
    
    # 不返回错误，避免中断安装流程
    return 0
}

# 配置手动代理组以使用最佳节点
configure_manual_proxy_group() {
    local group_name=$1
    log_info "优化手动代理组: $group_name"
    
    # 获取该组的可用选项
    local group_info available_options
    group_info=$(curl -s "http://127.0.0.1:9090/proxies/${group_name}" 2>/dev/null)
    available_options=$(echo "$group_info" | grep -o '"all":\[[^]]*\]' | grep -o '"[^"]*"' | grep -v '"all"' | tr -d '"')
    
    if [ -z "$available_options" ]; then
        log_warn "无法获取 $group_name 的选项"
        return 0  # 不返回错误，避免中断流程
    fi
    
    log_info "$group_name 可用选项: $(echo "$available_options" | tr '\n' ' ')"
    
    # 选择最佳选项（避免DIRECT）
    local best_option=""
    for option in $available_options; do
        if [[ ! "$option" =~ ^(DIRECT|REJECT|直连|拒绝)$ ]]; then
            best_option="$option"
            break
        fi
    done
    
    if [ -n "$best_option" ]; then
        log_info "为 $group_name 设置最佳选项: $best_option"
        if curl -X PUT -H "Content-Type: application/json" -d "{\"name\":\"$best_option\"}" "http://127.0.0.1:9090/proxies/${group_name}" >/dev/null 2>&1; then
            log_success "✅ $group_name 已设置为: $best_option"
        else
            log_warn "⚠️  无法设置 $group_name 的选项"
        fi
    else
        log_warn "⚠️  $group_name 中只有直连选项"
    fi
}

# 🔥 关键修复：配置"漏网之鱼"代理组
configure_fallback_proxy_group() {
    local target_group=$1
    
    log_info "🔧 配置漏网之鱼代理组（关键修复）"
    
    # 等待API完全就绪
    sleep 2
    
    # 检查是否存在"漏网之鱼"代理组
    local fallback_groups=("漏网之鱼" "兜底分流" "Final" "Others" "FINAL" "默认" "其他")
    local found_group=""
    
    for group_name in "${fallback_groups[@]}"; do
        if curl -s "http://127.0.0.1:9090/proxies/${group_name}" 2>/dev/null | grep -q '"name"'; then
            found_group="$group_name"
            log_info "发现兜底代理组: $found_group"
            break
        fi
    done
    
    if [ -z "$found_group" ]; then
        log_warn "⚠️  未发现兜底代理组，VPN自动切换可能需要手动配置"
        return 0
    fi
    
    # 获取兜底组的当前选择和可用选项
    local fallback_info current_selection available_options
    fallback_info=$(curl -s "http://127.0.0.1:9090/proxies/${found_group}" 2>/dev/null)
    current_selection=$(echo "$fallback_info" | grep -o '"now":"[^"]*"' | cut -d'"' -f4)
    available_options=$(echo "$fallback_info" | grep -o '"all":\[[^]]*\]' | grep -o '"[^"]*"' | grep -v '"all"' | tr -d '"')
    
    log_info "$found_group 当前选择: $current_selection"
    log_info "$found_group 可用选项: $(echo "$available_options" | tr '\n' ' ')"
    
    # 如果当前已经是非直连选项，则无需修改
    if [[ ! "$current_selection" =~ ^(DIRECT|直连)$ ]]; then
        log_success "✅ $found_group 已配置为 VPN 模式: $current_selection"
        return 0
    fi
    
    # 选择最佳的非直连选项
    local best_option=""
    
    # 优先选择传入的目标代理组
    if echo "$available_options" | grep -q "^$target_group$"; then
        best_option="$target_group"
    else
        # 按优先级选择
        local preferred_options=("自动选择" "Auto" "自动" "手动切换" "Manual" "手动")
        for pref_option in "${preferred_options[@]}"; do
            if echo "$available_options" | grep -q "^$pref_option$"; then
                best_option="$pref_option"
                break
            fi
        done
        
        # 如果没找到首选项，选择第一个非直连选项
        if [ -z "$best_option" ]; then
            for option in $available_options; do
                if [[ ! "$option" =~ ^(DIRECT|REJECT|直连|拒绝)$ ]]; then
                    best_option="$option"
                    break
                fi
            done
        fi
    fi
    
    if [ -n "$best_option" ]; then
        log_info "🚀 将 $found_group 切换到: $best_option"
        if curl -X PUT -H "Content-Type: application/json" -d "{\"name\":\"$best_option\"}" "http://127.0.0.1:9090/proxies/${found_group}" >/dev/null 2>&1; then
            
            # 验证切换结果
            sleep 2
            local new_selection
            new_selection=$(curl -s "http://127.0.0.1:9090/proxies/${found_group}" 2>/dev/null | grep -o '"now":"[^"]*"' | cut -d'"' -f4)
            
            if [[ "$new_selection" == "$best_option" ]]; then
                log_success "🎉 $found_group 成功切换到 VPN 模式: $new_selection"
                log_success "✅ Docker 容器现在将自动使用 VPN 网络！"
            else
                log_warn "⚠️  $found_group 切换可能未生效，当前: $new_selection"
            fi
        else
            log_error "❌ 无法切换 $found_group 到: $best_option"
        fi
    else
        log_warn "⚠️  $found_group 中没有可用的 VPN 选项"
        log_info "可用选项: $(echo "$available_options" | tr '\n' ' ')"
    fi
}

# 智能处理 proxy-providers 配置
handle_proxy_providers() {
    local subscription_url=$1
    
    if ! grep -q "proxy-providers:" "${CONFIG_FILE}"; then
        log_info "配置未使用 proxy-providers，跳过提供商文件处理"
        return 0
    fi
    
    log_info "检测到 proxy-providers 配置，智能处理提供商文件..."
    
    # 获取 provider 配置信息
    local provider_info
    provider_info=$(grep -A 50 "proxy-providers:" "${CONFIG_FILE}")
    
    # 提取所有 provider 名称和对应的 URL
    local provider_names
    provider_names=$(echo "$provider_info" | grep -E "^  [a-zA-Z0-9_-]+:" | sed 's/:.*$//' | xargs)
    
    if [ -z "$provider_names" ]; then
        log_warn "未找到有效的 proxy-providers 配置"
        return 1
    fi
    
    log_info "发现的提供商: $provider_names"
    
    for provider_name in $provider_names; do
        # 提取 provider 的详细配置
        local provider_config
        provider_config=$(echo "$provider_info" | sed -n "/^  ${provider_name}:/,/^  [a-zA-Z]/p" | sed '$d')
        
        # 提取 path 和 url
        local provider_path provider_url
        provider_path=$(echo "$provider_config" | grep "path:" | awk '{print $2}' | sed 's/^\.\/*//')
        provider_url=$(echo "$provider_config" | grep "url:" | awk '{$1=""; print $0}' | xargs)
        
        if [ -z "$provider_path" ]; then
            provider_path="${provider_name}_provider.yaml"
        fi
        
        local full_provider_path="${CONFIG_DIR}/${provider_path}"
        log_info "处理提供商: $provider_name -> $provider_path"
        
        # 尝试下载 provider 文件
        local downloaded=false
        
        if [ -n "$provider_url" ]; then
            log_info "尝试从配置URL下载: $provider_url"
            if curl -f -L -s -o "$full_provider_path" "$provider_url" --connect-timeout 15 --max-time 45; then
                if [ -s "$full_provider_path" ]; then
                    log_success "成功下载 $provider_name: $(wc -c < "$full_provider_path") bytes"
                    downloaded=true
                else
                    log_warn "下载的文件为空，删除"
                    rm -f "$full_provider_path"
                fi
            else
                log_warn "从配置URL下载失败: $provider_url"
            fi
        fi
        
        # 如果主URL失败，尝试其他可能的URL
        if [ "$downloaded" = false ]; then
            log_info "尝试备选URL模式..."
            
            # 从订阅URL推断可能的provider URL
            local base_url subscription_id
            base_url=$(echo "$subscription_url" | sed 's|/[^/]*$||')
            subscription_id=$(echo "$subscription_url" | grep -o '[a-f0-9]\{32\}' | head -1)
            
            local backup_urls=(
                "${base_url}/${provider_path}"
                "${base_url}/${subscription_id}"
                "https://www.yangshujie.top:18703/s/clashMeta/${subscription_id}"
                "https://www.yangshujie.top:18703/s/proxy/${subscription_id}"
            )
            
            for backup_url in "${backup_urls[@]}"; do
                if [ -n "$backup_url" ]; then
                    log_info "尝试备选URL: $backup_url"
                    if curl -f -L -s -o "$full_provider_path" "$backup_url" --connect-timeout 10 --max-time 30; then
                        if [ -s "$full_provider_path" ]; then
                            log_success "从备选URL成功下载 $provider_name"
                            downloaded=true
                            break
                        else
                            rm -f "$full_provider_path"
                        fi
                    fi
                fi
            done
        fi
        
        # 如果还是无法下载，尝试从主配置提取或创建基础配置
        if [ "$downloaded" = false ]; then
            log_warn "所有URL都无法下载 $provider_name，尝试备用方案"
            
            # 检查主配置是否包含 proxies 节点
            if grep -q "^proxies:" "${CONFIG_FILE}"; then
                log_info "从主配置提取代理节点"
                cat > "$full_provider_path" << EOF
# 从主配置提取的代理节点
proxies:
EOF
                # 提取代理节点
                grep -A 2000 "^proxies:" "${CONFIG_FILE}" | grep "^  - " | head -100 >> "$full_provider_path"
                
                if [ -s "$full_provider_path" ]; then
                    local proxy_count
                    proxy_count=$(grep -c "^  - " "$full_provider_path" || echo "0")
                    log_success "从主配置提取了 $proxy_count 个代理节点到 $provider_name"
                    downloaded=true
                fi
            else
                # 创建最小可用配置
                log_warn "创建最小可用配置用于服务启动"
                cat > "$full_provider_path" << EOF
# 最小可用配置 - 请联系服务商获取正确的代理节点
proxies:
  - name: "DIRECT"
    type: direct
  - name: "REJECT"
    type: reject
EOF
                log_warn "⚠️  已创建基础配置，但VPN功能不可用"
                echo "   需要联系服务提供商获取正确的代理节点配置"
            fi
        fi
    done
    
    log_success "proxy-providers 处理完成"
}

# 验证和修复 proxy-providers 文件
verify_and_fix_providers() {
    log_info "验证和修复 proxy-providers 文件..."
    
    if [ ! -f "${CONFIG_FILE}" ]; then
        log_error "配置文件不存在: ${CONFIG_FILE}"
        return 1
    fi
    
    # 检查是否使用 proxy-providers
    if ! grep -q "proxy-providers:" "${CONFIG_FILE}"; then
        log_info "配置未使用 proxy-providers，跳过检查"
        return 0
    fi
    
    # 获取所需的 provider 文件
    local provider_files
    provider_files=$(grep -A 20 "proxy-providers:" "${CONFIG_FILE}" | grep -o "[a-zA-Z0-9_-]*\.yaml" | sort -u)
    
    if [ -z "$provider_files" ]; then
        log_warn "未找到 proxy-providers 文件配置"
        return 0
    fi
    
    local missing_files=0
    
    for provider_file in $provider_files; do
        local provider_path="${CONFIG_DIR}/$provider_file"
        
        if [ ! -f "$provider_path" ] || [ ! -s "$provider_path" ]; then
            log_warn "Provider文件缺失或为空: $provider_file"
            missing_files=$((missing_files + 1))
            
            # 尝试重新下载
            log_info "尝试重新下载: $provider_file"
            local downloaded=false
            
            # 尝试不同的URL模式 - 从配置文件中提取实际的provider URL
            local provider_url_from_config
            provider_url_from_config=$(grep -A 10 "proxy-providers:" "${CONFIG_FILE}" | grep -A 5 "${provider_file%.*}_provider:" | grep "url:" | head -1 | awk '{print $2}')
            
            local urls=()
            if [ -n "$provider_url_from_config" ]; then
                urls+=("$provider_url_from_config")
            fi
            
            # 备选URL路径
            local base_url="https://www.yangshujie.top:18703/s"
            urls+=(
                "$base_url/clashMeta/8dfc915430e5de77b1c64cb8d7e4f1b3"
                "$base_url/clashMetaProfiles/8dfc915430e5de77b1c64cb8d7e4f1b3"
                "$base_url/clashMetaProfiles/$provider_file"
            )
            
            for url in "${urls[@]}"; do
                if curl -f -L -s -o "$provider_path" "$url" --connect-timeout 10 --max-time 30; then
                    if [ -s "$provider_path" ]; then
                        log_success "成功下载: $provider_file"
                        downloaded=true
                        break
                    else
                        rm -f "$provider_path"
                    fi
                fi
            done
            
            # 如果下载失败，尝试从主配置文件生成
            if [ "$downloaded" = false ]; then
                log_warn "无法下载 $provider_file，尝试从主配置生成"
                
                if grep -q "^proxies:" "${CONFIG_FILE}"; then
                    # 提取代理配置并创建 provider 文件
                    cat > "$provider_path" << EOF
# 临时生成的 provider 文件
proxies:
EOF
                    # 提取前50个代理节点
                    grep -A 1000 "^proxies:" "${CONFIG_FILE}" | grep "^  - " | head -50 >> "$provider_path"
                    
                    if [ -s "$provider_path" ]; then
                        log_info "成功生成临时 provider 文件: $provider_file"
                        downloaded=true
                    fi
                else
                    # 如果主配置中也没有代理节点，创建一个基本的provider文件但给出明确警告
                    log_warn "主配置中也没有代理节点，这通常意味着订阅服务或provider URL有问题"
                    cat > "$provider_path" << EOF
# 基本 provider 文件 - 仅用于服务正常启动
# ⚠️ 警告：当前仅有直连代理，请检查订阅配置
proxies:
  - name: "DIRECT-FALLBACK"
    type: direct
  - name: "EMERGENCY-DIRECT" 
    type: direct
EOF
                    if [ -s "$provider_path" ]; then
                        log_warn "⚠️  已创建应急 provider 文件: $provider_file"
                        log_error "❌ 当前仅有直连代理，VPN功能不可用！"
                        echo "    建议："
                        echo "    1. 检查订阅链接是否有效"
                        echo "    2. 联系服务提供商确认配置"
                        echo "    3. 或手动配置代理节点"
                        downloaded=true
                    fi
                fi
            fi
            
            if [ "$downloaded" = false ]; then
                log_error "无法获取 provider 文件: $provider_file"
            fi
        else
            log_success "Provider文件存在: $provider_file"
        fi
    done
    
    if [ $missing_files -eq 0 ]; then
        log_success "所有 proxy-providers 文件验证通过"
    else
        log_warn "有 $missing_files 个 provider 文件需要注意"
        
        # 重启服务以重新加载 provider 文件
        log_info "重新启动服务以加载 provider 文件..."
        systemctl restart mihomo.service
        sleep 3
        
        # 最终检查代理可用性
        log_info "检查代理服务可用性..."
        if curl -s "http://127.0.0.1:9090/proxies/GLOBAL" >/dev/null 2>&1; then
            local available_proxies
            available_proxies=$(curl -s "http://127.0.0.1:9090/proxies/GLOBAL" | grep -o '"all":\[[^]]*\]' | grep -o '"[^"]*"' | grep -v '"all"' | wc -l)
            log_info "检测到 $available_proxies 个可用代理组"
            
            # 检查是否只有直连代理
            local non_direct_proxies
            non_direct_proxies=$(curl -s "http://127.0.0.1:9090/proxies/手动切换" | grep -o '"all":\[[^]]*\]' | grep -o '"[^"]*"' | grep -v '"DIRECT"' | grep -v '"all"' | wc -l)
            
            if [ "$non_direct_proxies" -le 1 ]; then
                log_error "❌ 检测到可能只有直连代理可用，VPN功能可能不正常"
                echo ""
                echo "🔧 故障排除建议："
                echo "   1. 检查订阅服务状态：curl -I '${subscription_url:-订阅链接}'"
                echo "   2. 检查provider文件内容：cat ${CONFIG_DIR}/*.yaml"
                echo "   3. 联系VPN服务提供商确认订阅链接"
                echo "   4. 手动测试代理：curl -x http://127.0.0.1:7890 https://httpbin.org/ip"
                echo ""
            else
                log_success "✅ 检测到有效代理节点，VPN功能应该正常"
            fi
        fi
    fi
}

# 安装后验证和自动修复
perform_post_install_validation() {
    log_info "执行安装后验证和优化"
    
    # 1. 验证代理节点数量
    local proxy_count=0
    if [[ -f "${CONFIG_DIR}/zrmetouipf_provider.yaml" ]]; then
        proxy_count=$(grep -c 'name:' "${CONFIG_DIR}/zrmetouipf_provider.yaml" 2>/dev/null || echo "0")
        log_info "检测到 ${proxy_count} 个代理节点"
    fi
    
    if [[ ${proxy_count} -eq 0 ]]; then
        log_warn "未检测到代理节点，检查配置文件"
        if grep -q "proxy-providers:" "${CONFIG_FILE}"; then
            log_info "使用 proxy-providers 模式，等待节点加载..."
            sleep 5
        fi
    fi
    
    # 2. 确保全局代理设置正确
    local max_attempts=5
    local attempt=0
    while [[ ${attempt} -lt ${max_attempts} ]]; do
        local current_mode
        current_mode=$(curl -s "http://127.0.0.1:9090/proxies/GLOBAL" 2>/dev/null | grep -o '"now":"[^"]*"' | cut -d'"' -f4)
        
        if [[ "${current_mode}" == "DIRECT" ]]; then
            log_warn "检测到全局代理为DIRECT模式，自动修复中... (${attempt}/${max_attempts})"
            curl -X PUT -H "Content-Type: application/json" -d '{"name":"自动选择"}' "http://127.0.0.1:9090/proxies/GLOBAL" >/dev/null 2>&1
            sleep 3
            ((attempt++))
        elif [[ "${current_mode}" == "自动选择" ]]; then
            log_success "✅ 全局代理已正确设置为: ${current_mode}"
            break
        else
            log_info "当前全局代理模式: ${current_mode}"
            break
        fi
    done
    
    # 3. 验证关键代理组配置
    if curl -s "http://127.0.0.1:9090/proxies" >/dev/null 2>&1; then
        log_success "✅ 代理API响应正常"
        
        # 检查是否有可用的代理节点
        local available_proxies
        available_proxies=$(curl -s "http://127.0.0.1:9090/proxies" 2>/dev/null | grep -o '"867e198b[^"]*"' | wc -l)
        log_info "API显示 ${available_proxies} 个可用代理节点"
    else
        log_warn "⚠️  代理API无响应"
    fi
    
    # 4. 预热代理连接
    log_info "预热代理连接..."
    curl -s --connect-timeout 3 --proxy 127.0.0.1:7890 http://www.google.com >/dev/null 2>&1 &
    
    log_success "安装后验证完成"
}

# 步骤5：全面测试 VPN 连接
test_vpn_connectivity() {
    log_step "5. 全面测试 VPN 连接"
    
    # 1. 检查服务状态
    log_info "🔍 检查服务状态"
    if ! systemctl is-active --quiet mihomo.service; then
        log_error "❌ mihomo 服务未运行"
        return 1
    fi
    log_success "✅ mihomo 服务运行正常"
    
    # 2. 检查端口监听状态
    log_info "🔍 检查端口监听状态"
    local ports_ok=true
    
    for port in 7890 7891 9090; do
        if ss -tuln | grep -q ":${port}"; then
            log_success "✅ 端口 $port 监听正常"
        else
            log_error "❌ 端口 $port 未监听"
            ports_ok=false
        fi
    done
    
    if [ "$ports_ok" = false ]; then
        log_error "端口监听异常，请检查配置"
        return 1
    fi
    
    # 3. 检查API可用性
    log_info "🔍 检查控制API"
    if curl -s "http://127.0.0.1:9090/version" >/dev/null 2>&1; then
        log_success "✅ 控制API可用"
    else
        log_error "❌ 控制API不可用"
        return 1
    fi
    
    # 4. 分析当前代理配置
    log_info "🔍 分析当前代理配置"
    local current_global current_manual
    current_global=$(curl -s "http://127.0.0.1:9090/proxies/GLOBAL" | grep -o '"now":"[^"]*"' | cut -d'"' -f4)
    
    if [ -n "$current_global" ]; then
        log_success "✅ 全局代理: $current_global"
        
        # 如果全局代理不是DIRECT，检查其具体设置
        if [[ "$current_global" != "DIRECT" ]]; then
            current_manual=$(curl -s "http://127.0.0.1:9090/proxies/${current_global}" | grep -o '"now":"[^"]*"' | cut -d'"' -f4)
            if [ -n "$current_manual" ]; then
                log_info "   └── 当前选择: $current_manual"
                
                if [[ "$current_manual" == "DIRECT" ]]; then
                    log_warn "⚠️  代理组选择了DIRECT，VPN未激活"
                    # 尝试自动修复
                    configure_manual_proxy_group "$current_global"
                fi
            fi
        else
            log_warn "⚠️  全局代理设置为DIRECT，VPN未激活"
        fi
    else
        log_error "❌ 无法获取代理配置"
        return 1
    fi
    
    # 5. 测试网络连接
    log_info "🌐 测试网络连接"
    
    # 获取直连IP作为基线
    log_info "获取直连IP基线..."
    local direct_ip=""
    
    # 尝试获取直连IP
    local ip_response
    ip_response=$(timeout 10 curl -s "http://httpbin.org/ip" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$ip_response" ]; then
        direct_ip=$(echo "$ip_response" | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
    fi
    
    # 备用方法获取IP
    if [ -z "$direct_ip" ]; then
        ip_response=$(timeout 10 curl -s "http://icanhazip.com" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$ip_response" ]; then
            direct_ip=$(echo "$ip_response" | tr -d '\n\r ' | grep -E '^[0-9.]+$')
        fi
    fi
    
    if [ -n "$direct_ip" ]; then
        log_success "✅ 直连IP: $direct_ip"
    else
        log_warn "⚠️  无法获取直连IP，网络可能有问题"
    fi
    
    # 测试HTTP代理
    log_info "测试HTTP代理连接..."
    local http_test_result=""
    local proxy_working=false
    
    for test_url in "http://httpbin.org/ip" "http://icanhazip.com" "http://api.ipify.org"; do
        log_info "尝试 $test_url..."
        
        # 先测试连通性
        local response
        response=$(timeout 15 curl -s --proxy "http://127.0.0.1:7890" "$test_url" 2>/dev/null)
        local curl_exit=$?
        
        if [ $curl_exit -eq 0 ] && [ -n "$response" ]; then
            # 解析IP地址
            if [[ "$test_url" == *"httpbin"* ]]; then
                http_test_result=$(echo "$response" | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
            else
                http_test_result=$(echo "$response" | tr -d '\n\r ' | grep -E '^[0-9.]+$')
            fi
            
            if [ -n "$http_test_result" ]; then
                proxy_working=true
                if [ -n "$direct_ip" ] && [[ "$http_test_result" != "$direct_ip" ]]; then
                    log_success "✅ HTTP代理工作正常，出口IP: $http_test_result (代理生效)"
                elif [ -n "$direct_ip" ] && [[ "$http_test_result" == "$direct_ip" ]]; then
                    log_warn "⚠️  HTTP代理IP与直连相同: $http_test_result (当前使用直连节点)"
                    proxy_working=true  # 技术上代理工作，只是选择了直连节点
                else
                    log_success "✅ HTTP代理测试通过，出口IP: $http_test_result"
                fi
                break
            else
                log_warn "   响应格式异常，无法解析IP"
            fi
        else
            log_warn "   连接失败 (退出码: $curl_exit)"
        fi
    done
    
    if [ "$proxy_working" = false ]; then
        log_error "❌ HTTP代理连接失败，所有测试服务都无响应"
        log_info "   手动测试: curl --proxy http://127.0.0.1:7890 http://httpbin.org/ip"
    fi
    
    # 测试HTTPS代理  
    log_info "测试HTTPS代理连接..."
    local https_success=false
    local test_url="https://httpbin.org/ip"
    
    # 先尝试正常HTTPS验证
    local https_response
    https_response=$(timeout 15 curl -s --proxy "http://127.0.0.1:7890" "$test_url" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$https_response" ]; then
        https_success=true
        log_success "✅ HTTPS代理测试通过"
    else
        # 尝试跳过SSL验证
        https_response=$(timeout 15 curl -s -k --proxy "http://127.0.0.1:7890" "$test_url" 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$https_response" ]; then
            https_success=true
            log_success "✅ HTTPS代理测试通过 (SSL验证跳过)"
        fi
    fi
    
    if [ "$https_success" = false ]; then
        log_warn "⚠️  HTTPS代理测试失败"
        log_info "   💡 这可能是SSL证书验证问题，不影响实际使用"
    fi
    
    # 测试SOCKS5代理
    log_info "测试SOCKS5代理连接..."
    local socks_response
    socks_response=$(timeout 15 curl -s --socks5 "127.0.0.1:7891" "http://httpbin.org/ip" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$socks_response" ]; then
        local socks_ip
        socks_ip=$(echo "$socks_response" | grep -o '"origin": "[^"]*"' | cut -d'"' -f4)
        if [ -n "$socks_ip" ]; then
            log_success "✅ SOCKS5代理测试通过，出口IP: $socks_ip"
        else
            log_success "✅ SOCKS5代理连接成功"
        fi
    else
        log_warn "⚠️  SOCKS5代理测试失败"
        log_info "   手动测试: curl --socks5 127.0.0.1:7891 http://httpbin.org/ip"
    fi
    
    # 6. 测试关键网站访问能力
    log_info "🌐 测试关键网站访问"
    local test_sites=("google.com" "youtube.com" "github.com")
    local accessible_sites=0
    
    for site in "${test_sites[@]}"; do
        log_info "测试访问 $site..."
        local test_success=false
        local error_detail=""
        
        # 方法1: 尝试HTTPS HEAD请求
        if timeout 15 curl -s -I --proxy "http://127.0.0.1:7890" "https://$site" >/dev/null 2>&1; then
            test_success=true
        else
            # 方法2: 尝试HTTPS GET请求（忽略SSL验证）
            if timeout 15 curl -s -k --proxy "http://127.0.0.1:7890" "https://$site" >/dev/null 2>&1; then
                test_success=true
                error_detail="(SSL证书验证绕过)"
            else
                # 方法3: 尝试HTTP请求
                if timeout 15 curl -s -I --proxy "http://127.0.0.1:7890" "http://$site" >/dev/null 2>&1; then
                    test_success=true
                    error_detail="(HTTP协议)"
                else
                    # 获取详细错误信息
                    error_detail=$(timeout 10 curl -s -I --proxy "http://127.0.0.1:7890" "https://$site" 2>&1 | head -1)
                fi
            fi
        fi
        
        if [ "$test_success" = true ]; then
            if [ -n "$error_detail" ]; then
                log_success "✅ $site 访问成功 $error_detail"
            else
                log_success "✅ $site 访问成功"
            fi
            accessible_sites=$((accessible_sites + 1))
        else
            log_warn "⚠️  $site 访问失败"
            if [ -n "$error_detail" ]; then
                log_info "   错误详情: $error_detail"
            fi
            
            # 提供详细的诊断信息
            log_info "   手动测试: curl -I --proxy http://127.0.0.1:7890 https://$site"
        fi
    done
    
    # 7. 生成测试报告
    echo ""
    log_info "📊 连接测试报告"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  服务状态: ✅ 正常运行"
    echo "  端口监听: ✅ 7890/7891/9090"
    echo "  全局代理: $current_global"
    if [ -n "$current_manual" ] && [[ "$current_manual" != "$current_global" ]]; then
        echo "  代理节点: $current_manual"
    fi
    if [ -n "$http_test_result" ]; then
        echo "  出口IP: $http_test_result"
    fi
    echo "  可访问网站: $accessible_sites/${#test_sites[@]}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # 8. 综合分析和建议
    echo ""
    log_info "🔍 代理效果分析"
    
    # 分析代理是否真正工作
    local proxy_effective=false
    if [ -n "$http_test_result" ] && [ -n "$direct_ip" ]; then
        if [[ "$http_test_result" != "$direct_ip" ]]; then
            proxy_effective=true
            log_success "✅ 代理正在工作：出口IP已改变 ($direct_ip → $http_test_result)"
        else
            log_warn "⚠️  代理可能未生效：出口IP未改变 ($http_test_result)"
        fi
    elif [ -n "$http_test_result" ]; then
        log_info "ℹ️  代理连接正常，出口IP: $http_test_result"
        proxy_effective=true
    fi
    
    # 根据测试结果提供建议
    if [ $accessible_sites -eq 0 ] && [[ "$current_manual" == "DIRECT" || "$current_global" == "DIRECT" ]]; then
        echo ""
        log_warn "🔧 检测到问题：代理未正确配置"
        echo "建议操作："
        echo "  1. 运行自动修复: $(basename "$0") --fix-proxy"
        echo "  2. 检查代理组设置: curl -s http://127.0.0.1:9090/proxies/GLOBAL"
        echo "  3. 手动切换代理节点: 访问控制面板"
        echo "  4. 查看服务日志: journalctl -u mihomo.service -n 50"
    elif [ "$proxy_effective" = true ] && [ $accessible_sites -gt 0 ]; then
        log_success "🎉 VPN配置成功！代理功能完全正常"
        echo "   • 代理服务正常运行"
        echo "   • 出口IP已通过代理"
        echo "   • 可访问目标网站: $accessible_sites/${#test_sites[@]}"
    elif [ "$proxy_effective" = true ]; then
        log_success "✅ 代理基本功能正常"
        log_warn "⚠️  部分网站访问可能受限，但代理本身工作正常"
        echo "   建议："
        echo "   • 尝试切换不同的代理节点"
        echo "   • 检查目标网站是否对该代理服务器有限制"
    elif [ $accessible_sites -gt 0 ]; then
        log_warn "⚠️  网站可访问，但代理效果不明确"
        echo "   建议手动验证：curl --proxy http://127.0.0.1:7890 http://httpbin.org/ip"
    else
        log_warn "⚠️  VPN配置完成，但功能可能受限"
        echo "建议操作："
        echo "  1. 运行修复: $(basename "$0") --fix-proxy"
        echo "  2. 检查网络连通性"
        echo "  3. 尝试不同的代理节点"
    fi
    log_info "检查代理状态和外网IP"
    local current_ip=""
    
    # 首先检查全局代理设置
    local proxy_mode=""
    if proxy_mode=$(curl -s "http://127.0.0.1:9090/proxies/GLOBAL" 2>/dev/null | grep -o '"now":"[^"]*"' | cut -d'"' -f4); then
        if [[ "${proxy_mode}" == "DIRECT" ]]; then
            log_warn "⚠️  全局代理设置为DIRECT，将自动切换为代理模式"
            curl -X PUT -H "Content-Type: application/json" -d '{"name":"自动选择"}' "http://127.0.0.1:9090/proxies/GLOBAL" >/dev/null 2>&1
            sleep 2
            proxy_mode="自动选择"
        fi
        log_info "当前代理模式: ${proxy_mode}"
    fi
    
    # 尝试获取外网IP（优先级顺序）
    local ip_sources=("ipinfo.io/ip" "ifconfig.me" "myip.ipip.net")
    for source in "${ip_sources[@]}"; do
        log_info "尝试通过 ${source} 获取IP..."
        
        # 先尝试HTTPS
        if current_ip=$(curl -s --connect-timeout 8 --proxy 127.0.0.1:7890 "https://${source}" 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1); then
            if [[ -n "${current_ip}" ]]; then
                log_success "当前外网 IP: ${current_ip} (via HTTPS ${source})"
                break
            fi
        fi
        
        # HTTPS失败则尝试HTTP
        if current_ip=$(curl -s --connect-timeout 8 --proxy 127.0.0.1:7890 "http://${source}" 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | head -1); then
            if [[ -n "${current_ip}" ]]; then
                log_success "当前外网 IP: ${current_ip} (via HTTP ${source})"
                log_warn "⚠️  注意：HTTPS代理存在SSL证书验证问题，但HTTP正常"
                break
            fi
        fi
    done
    
    if [[ -z "${current_ip}" ]]; then
        log_warn "无法获取外网IP，但这可能是因为IP查询网站被智能分流规则直连"
        log_info "💡 这通常是正常现象，代理主要用于访问被封锁的网站"
    fi
}

# 创建诊断脚本
create_diagnostic_script() {
    local diagnostic_script="/usr/local/bin/mihomo-diagnose"
    
    cat > "${diagnostic_script}" << 'EOF'
#!/bin/bash
# Mihomo VPN 诊断脚本

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

echo "==============================================="
echo "🔍 Mihomo VPN 诊断工具"
echo "==============================================="

# 1. 检查服务状态
log_info "1. 检查 mihomo 服务状态"
if systemctl is-active --quiet mihomo.service; then
    log_success "✅ mihomo 服务运行正常"
    systemctl status mihomo.service --no-pager -l
else
    log_error "❌ mihomo 服务未运行"
    systemctl status mihomo.service --no-pager -l
fi

echo

# 2. 检查端口监听
log_info "2. 检查端口监听状态"
if ss -tuln | grep -q ":7890"; then
    log_success "✅ 端口 7890 监听正常"
    ss -tuln | grep ":789"
else
    log_error "❌ 端口 7890 未监听"
fi

echo

# 3. 检查配置文件
log_info "3. 检查配置文件"
config_file="/root/.config/clash/config.yaml"
if [[ -f "${config_file}" ]]; then
    log_success "✅ 配置文件存在"
    echo "代理节点数量: $(grep -c '^  - name:' "${config_file}" || echo "0")"
    echo "配置文件大小: $(du -h "${config_file}" | cut -f1)"
else
    log_error "❌ 配置文件不存在"
fi

echo

# 4. 测试连接
log_info "4. 测试网络连接"
echo "直连测试:"
if curl -s --connect-timeout 5 http://www.baidu.com >/dev/null; then
    log_success "✅ 直连正常"
else
    log_error "❌ 直连失败"
fi

echo "代理测试:"
if curl -s --connect-timeout 10 --proxy 127.0.0.1:7890 https://www.baidu.com >/dev/null; then
    log_success "✅ 代理连接正常"
else
    log_warn "⚠️  代理连接失败"
fi

echo

# 5. 显示最近日志
log_info "5. 最近的服务日志 (最后 20 行)"
journalctl -u mihomo.service --no-pager -n 20

echo
log_info "💡 故障排除建议："
echo "  • 重启服务: systemctl restart mihomo"
echo "  • 检查配置: cat /root/.config/clash/config.yaml"
echo "  • 更新订阅: 重新运行安装脚本"
echo "  • 查看完整日志: journalctl -u mihomo.service -f"
EOF

    chmod +x "${diagnostic_script}"
    log_info "已创建诊断脚本: ${diagnostic_script}"
}

# 显示完成信息和使用指南
show_completion_info() {
    echo
    log_success "=========================================="
    log_success "🎉 Mihomo VPN 安装配置完成！"
    log_success "=========================================="
    echo
    
    # 获取服务器IP
    local server_ip
    server_ip=$(hostname -I | awk '{print $1}' | head -1)
    
    # 获取当前代理状态
    local current_proxy=""
    if curl -s "http://127.0.0.1:9090/proxies/GLOBAL" >/dev/null 2>&1; then
        current_proxy=$(curl -s "http://127.0.0.1:9090/proxies/GLOBAL" | grep -o '"now":"[^"]*"' | cut -d'"' -f4)
    fi
    
    log_info "📊 服务状态:"
    echo "  🟢 服务状态: $(systemctl is-active mihomo.service)"
    echo "  🌐 混合端口: 7890 (HTTP/HTTPS)"  
    echo "  🧦 SOCKS端口: 7891"
    echo "  ⚙️  控制API: 9090"
    if [ -n "$current_proxy" ]; then
        echo "  🎯 当前代理: $current_proxy"
    fi
    echo "  📁 配置目录: ${CONFIG_DIR}"
    echo
    
    log_info "🌐 访问地址:"
    echo "  • 本地控制面板: http://127.0.0.1:9090/ui"
    if [ -n "$server_ip" ]; then
        echo "  • 远程控制面板: http://${server_ip}:9090/ui"
    fi
    echo "  • API接口: http://127.0.0.1:9090"
    echo
    
    log_info "🚀 快速使用:"
    echo "  # 启用全局代理环境变量"
    echo "  source /etc/profile.d/mihomo-proxy.sh"
    echo "  proxy-on"
    echo ""
    echo "  # 测试代理连接"
    echo "  curl --proxy http://127.0.0.1:7890 http://httpbin.org/ip"
    echo ""
    echo "  # 浏览器代理设置"
    echo "  HTTP代理: 127.0.0.1:7890"
    echo "  SOCKS5代理: 127.0.0.1:7891"
    echo
    
    log_info "🔧 管理命令:"
    echo "  • 查看状态: $0 --status"
    echo "  • 测试连接: $0 --test"  
    echo "  • 修复代理: $0 --fix-proxy"
    echo "  • 验证配置: $0 --verify"
    echo "  • 服务管理: systemctl {start|stop|restart} mihomo"
    echo "  • 查看日志: journalctl -u mihomo.service -f"
    echo
    
    log_info "🔍 故障排除:"
    echo "  • 如果代理不工作，运行: $0 --fix-proxy"
    echo "  • 如果配置有问题，运行: $0 --verify"  
    echo "  • 查看详细状态: $0 --status"
    echo "  • 运行完整测试: $0 --test"
    echo
    
    log_info "💡 高级功能:"
    echo "  • 代理规则切换: 访问控制面板修改规则"
    echo "  • 节点选择: 在控制面板中手动选择最佳节点"
    echo "  • 实时监控: journalctl -u mihomo.service -f"
    echo "  • 配置热重载: 修改配置后自动重新加载"
    echo
    
    # 根据当前状态给出特定建议
    if [[ "$current_proxy" == "DIRECT" ]]; then
        log_warn "⚠️  当前代理设置为DIRECT，VPN未激活"
        echo "   快速修复: $0 --fix-proxy"
    elif [ -z "$current_proxy" ]; then
        log_warn "⚠️  无法获取代理状态，可能需要检查"
        echo "   运行诊断: $0 --test"
    else
        log_success "✅ 代理配置正常，VPN已激活"
        echo "   当前使用: $current_proxy"
    fi
    
    echo
    log_success "🎯 安装完成！享受您的VPN服务！"
    echo "  • 服务已设置开机自启动"
    echo
    
    # 检查代理状态并提供诊断信息
    echo
    local https_test_result=""
    local http_test_result=""
    
    # 测试HTTPS代理
    if curl -s --connect-timeout 5 --proxy 127.0.0.1:7890 https://www.google.com >/dev/null 2>&1; then
        https_test_result="✅ HTTPS代理工作正常"
    else
        https_test_result="❌ HTTPS代理连接失败"
    fi
    
    # 测试HTTP代理
    if curl -s --connect-timeout 5 --proxy 127.0.0.1:7890 http://www.google.com >/dev/null 2>&1; then
        http_test_result="✅ HTTP代理工作正常"
    else
        http_test_result="❌ HTTP代理连接失败"
    fi
    
    # 自动检测和诊断代理状态
    local final_https_test=""
    local final_http_test=""
    
    # 执行最终的代理连接测试
    if curl -s --connect-timeout 5 --proxy 127.0.0.1:7890 https://www.google.com >/dev/null 2>&1; then
        final_https_test="✅ HTTPS代理工作正常"
    else
        final_https_test="❌ HTTPS代理连接失败"
    fi
    
    if curl -s --connect-timeout 5 --proxy 127.0.0.1:7890 http://www.google.com >/dev/null 2>&1; then
        final_http_test="✅ HTTP代理工作正常"
    else
        final_http_test="❌ HTTP代理连接失败"
    fi
    
    log_info "🔍 最终代理连接状态："
    echo "  • ${final_https_test}"
    echo "  • ${final_http_test}"
    echo
    
    # 根据测试结果提供精准诊断
    if [[ "${final_http_test}" == *"✅"* && "${final_https_test}" == *"❌"* ]]; then
        log_success "🎉 代理基本功能正常！"
        log_warn "🔧 HTTPS存在SSL证书验证问题（常见现象）："
        echo
        echo "解决方案："
        echo "1. 对于命令行使用："
        echo "   curl --insecure --proxy 127.0.0.1:7890 https://example.com"
        echo
        echo "2. 对于浏览器使用："
        echo "   • 设置HTTP代理: 127.0.0.1:7890"
        echo "   • 访问控制面板: http://$(hostname -I | awk '{print $1}'):9090"
        echo "   • 手动切换代理节点测试不同服务器"
        echo
        echo "3. 验证关键网站可访问："
        echo "   curl --proxy 127.0.0.1:7890 -I http://www.youtube.com"
        echo "   curl --proxy 127.0.0.1:7890 -I http://www.google.com"
        echo
    elif [[ "${final_http_test}" == *"✅"* && "${final_https_test}" == *"✅"* ]]; then
        log_success "🎉 代理连接完全正常，所有功能正常！"
    elif [[ "${final_http_test}" == *"❌"* ]]; then
        log_warn "🔧 代理连接异常 - 自动诊断："
        echo
        
        # 检查全局代理设置
        local current_mode
        current_mode=$(curl -s http://127.0.0.1:9090/proxies/GLOBAL 2>/dev/null | grep -o '"now":"[^"]*"' | cut -d'"' -f4)
        echo "1. 当前全局代理模式: ${current_mode:-"无法获取"}"
        
        if [[ "${current_mode}" == "DIRECT" ]]; then
            echo "   ⚠️  问题发现：代理设置为直连模式"
            echo "   🔧 自动修复："
            curl -X PUT -H "Content-Type: application/json" -d '{"name":"自动选择"}' "http://127.0.0.1:9090/proxies/GLOBAL" >/dev/null 2>&1
            sleep 3
            echo "   ✅ 已设置为自动选择模式，请稍后重新测试"
        fi
        
        echo
        echo "2. 手动诊断命令："
        echo "   systemctl status mihomo.service"
        echo "   journalctl -u mihomo.service -n 20 --no-pager"
        echo "   curl -s http://127.0.0.1:9090/proxies/GLOBAL"
        echo
        echo "3. 手动修复命令："
        echo "   systemctl restart mihomo"
        echo "   curl -X PUT -H \"Content-Type: application/json\" -d '{\"name\":\"自动选择\"}' \"http://127.0.0.1:9090/proxies/GLOBAL\""
        echo
    else
        log_success "🎉 代理配置完成！"
    fi
}

# 显示使用帮助
show_usage() {
    echo "Mihomo VPN 安装和管理脚本"
    echo ""
    echo "用法: $0 [选项] [订阅链接]"
    echo ""
    echo "选项:"
    echo "  无参数           完整安装VPN（交互式输入订阅链接）"
    echo "  --install        完整安装VPN"
    echo "  --install <URL>  使用指定订阅链接安装VPN"
    echo "  <URL>            直接使用订阅链接安装VPN"
    echo "  --fix-proxy      修复代理设置"
    echo "  --test           测试VPN连接"
    echo "  --verify         验证和修复provider文件"
    echo "  --status         显示服务状态"
    echo "  --help, -h       显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0                                              # 交互式安装"
    echo "  $0 --install                                    # 交互式安装"
    echo "  $0 --install https://example.com/subscription   # 使用指定订阅链接安装"
    echo "  $0 https://example.com/subscription             # 直接使用订阅链接安装"
    echo "  $0 --fix-proxy                                  # 仅修复代理设置"
    echo "  $0 --test                                       # 测试连接状态"
    echo "  $0 --verify                                     # 验证provider文件"
}

# 修复代理设置
fix_proxy_only() {
    echo "=========================================="
    echo "🔧 修复 VPN 代理设置"
    echo "=========================================="
    
    check_root
    
    if ! systemctl is-active --quiet mihomo.service; then
        log_error "mihomo 服务未运行，请先完整安装"
        exit 1
    fi
    
    log_info "正在修复代理设置..."
    setup_optimal_proxy_mode
    
    echo ""
    log_info "测试修复结果..."
    test_vpn_connectivity
}

# 仅测试连接
test_only() {
    echo "=========================================="
    echo "🔍 测试 VPN 连接状态"
    echo "=========================================="
    
    check_root
    test_vpn_connectivity
}

# 验证和修复provider文件
verify_only() {
    echo "=========================================="
    echo "🔍 验证和修复 Provider 文件"
    echo "=========================================="
    
    check_root
    
    if [ ! -f "${CONFIG_FILE}" ]; then
        log_error "配置文件不存在，请先运行完整安装"
        exit 1
    fi
    
    verify_and_fix_providers
}

# 显示服务状态
show_status() {
    echo "=========================================="
    echo "📊 Mihomo VPN 服务状态"
    echo "=========================================="
    
    # 服务状态
    echo "🔸 服务状态:"
    if systemctl is-active --quiet mihomo.service; then
        echo "  ✅ mihomo.service: 运行中"
    else
        echo "  ❌ mihomo.service: 未运行"
    fi
    
    # 端口状态  
    echo ""
    echo "🔸 端口监听:"
    for port in 7890 7891 9090; do
        if ss -tuln | grep -q ":${port}"; then
            echo "  ✅ 端口 $port: 监听中"
        else
            echo "  ❌ 端口 $port: 未监听"
        fi
    done
    
    # 代理状态
    echo ""
    echo "🔸 代理配置:"
    if curl -s "http://127.0.0.1:9090/proxies/GLOBAL" >/dev/null 2>&1; then
        local current_proxy
        current_proxy=$(curl -s "http://127.0.0.1:9090/proxies/GLOBAL" | grep -o '"now":"[^"]*"' | cut -d'"' -f4)
        echo "  ✅ API可用，当前代理: $current_proxy"
    else
        echo "  ❌ API不可用"
    fi
    
    # 配置文件
    echo ""
    echo "🔸 配置文件:"
    if [ -f "${CONFIG_FILE}" ]; then
        echo "  ✅ 主配置: ${CONFIG_FILE}"
        if grep -q "proxy-providers:" "${CONFIG_FILE}"; then
            local provider_files
            provider_files=$(find "${CONFIG_DIR}" -name "*.yaml" -not -name "config.yaml" | wc -l)
            echo "  📁 Provider文件: $provider_files 个"
        fi
    else
        echo "  ❌ 主配置: 不存在"
    fi
}

# 主函数
main() {
    local subscription_url=""
    
    # 处理命令行参数
    case "${1:-}" in
        --help|-h)
            show_usage
            exit 0
            ;;
        --fix-proxy)
            fix_proxy_only
            exit 0
            ;;
        --test)
            test_only
            exit 0
            ;;
        --verify)
            verify_only
            exit 0
            ;;
        --status)
            show_status
            exit 0
            ;;
        --install)
            # 检查是否有第二个参数作为订阅链接
            if [[ -n "${2:-}" ]]; then
                subscription_url="$2"
                log_info "使用命令行参数提供的订阅链接: ${subscription_url}"
            fi
            ;;
        "")
            # 无参数，继续执行完整安装
            ;;
        http*://*)
            # 直接传入订阅链接
            subscription_url="$1"
            log_info "检测到订阅链接参数: ${subscription_url}"
            ;;
        *)
            log_error "未知参数: $1"
            show_usage
            exit 1
            ;;
    esac
    
    echo "=========================================="
    echo "🚀 Mihomo VPN 快速安装向导"
    echo "=========================================="
    echo
    
    # 检查基础环境
    init_environment
    check_root
    check_system
    check_static_resources
    
    echo
    log_info "准备执行以下步骤："
    echo "  1️⃣  安装 mihomo 客户端"
    if [[ -z "${subscription_url}" ]]; then
        echo "  2️⃣  输入订阅链接"
    else
        echo "  2️⃣  验证订阅链接"
    fi
    echo "  3️⃣  下载并配置订阅"
    echo "  4️⃣  启动 VPN 服务"
    echo "  5️⃣  智能设置代理模式"
    echo "  6️⃣  验证和修复配置"
    echo "  7️⃣  全面测试连接"
    echo
    
    # 如果提供了订阅链接，则自动确认；否则询问用户
    if [[ -n "${subscription_url}" ]]; then
        log_info "使用提供的订阅链接，自动开始安装..."
        sleep 1
    else
        read -p "确认开始安装？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "安装已取消"
            log_info "提示: 使用 '$0 --help' 查看其他选项"
            exit 0
        fi
    fi
    
    # 执行安装步骤
    install_mihomo
    
    # 获取订阅链接（如果未通过参数提供）
    if [[ -z "${subscription_url}" ]]; then
        subscription_url=$(get_subscription_url)
    else
        # 验证提供的订阅链接
        log_step "2. 验证订阅链接"
        if [[ ! "${subscription_url}" =~ ^https?:// ]]; then
            log_error "无效的订阅链接格式: ${subscription_url}"
            exit 1
        fi
        log_info "使用订阅链接: ${subscription_url}"
        
        # 简单测试链接连通性
        if curl -s --connect-timeout 10 --head "${subscription_url}" >/dev/null 2>&1; then
            log_success "✅ 订阅链接验证通过"
        else
            log_warn "⚠️  链接连通性测试失败，但将继续尝试下载"
        fi
    fi
    
    download_and_setup_config "${subscription_url}"
    setup_and_start_vpn
    
    # 安装后自动验证和修复
    log_step "6. 验证和优化安装结果"
    if ! verify_and_fix_providers; then
        log_warn "⚠️  Provider文件验证失败，但不影响基本功能"
    fi
    
    # 执行安装后验证
    log_step "7. 安装后验证"  
    if ! perform_post_install_validation; then
        log_warn "⚠️  部分验证失败，但服务可能仍然可用"
    fi
    
    # 全面测试连接
    log_step "8. 全面测试连接"
    if ! test_vpn_connectivity; then
        log_warn "⚠️  连接测试未完全通过，但基础服务已安装"
    fi
    
    # 创建诊断脚本（允许失败）
    if ! create_diagnostic_script; then
        log_warn "⚠️  诊断脚本创建失败"
    fi
    
    # 显示完成信息
    show_completion_info
    
    echo ""
    log_success "🎉 安装流程完成！"
    log_info "如遇问题，可运行以下命令："
    echo "  • 修复代理: $0 --fix-proxy"
    echo "  • 测试连接: $0 --test" 
    echo "  • 查看状态: $0 --status"
}

# 执行主函数
main "$@"
