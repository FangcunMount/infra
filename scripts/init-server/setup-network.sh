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
STATIC_DIR="${REPO_ROOT}/static"

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
    
    if [[ ! -d "${STATIC_DIR}" ]]; then
        log_error "未找到 static 目录: ${STATIC_DIR}"
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
        
        # 确保允许局域网访问
        if ! grep -q "^allow-lan:" "${CONFIG_FILE}"; then
            sed -i '/^mixed-port:/a allow-lan: true' "${CONFIG_FILE}"
        else
            sed -i 's/^allow-lan:.*/allow-lan: true/' "${CONFIG_FILE}"
        fi
        
        log_info "使用完整订阅配置，已优化本地访问设置"
        
        rm -f "${temp_config}"
        chmod 600 "${CONFIG_FILE}"
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
            
            # 自动设置全局代理为自动选择模式（而不是默认的DIRECT）
            log_info "设置全局代理为代理模式"
            if curl -X PUT -H "Content-Type: application/json" -d '{"name":"自动选择"}' "http://127.0.0.1:9090/proxies/GLOBAL" >/dev/null 2>&1; then
                log_success "✅ 全局代理已设置为自动选择模式"
                
                # 验证代理设置是否生效
                sleep 2
                local proxy_mode
                proxy_mode=$(curl -s "http://127.0.0.1:9090/proxies/GLOBAL" 2>/dev/null | grep -o '"now":"[^"]*"' | cut -d'"' -f4)
                if [[ "${proxy_mode}" == "自动选择" ]]; then
                    log_success "✅ 代理模式设置验证成功: ${proxy_mode}"
                else
                    log_warn "⚠️  代理模式可能未完全生效，当前: ${proxy_mode}"
                fi
            else
                log_warn "⚠️  无法自动设置全局代理，稍后请手动设置"
                echo "   手动设置命令: curl -X PUT -H \"Content-Type: application/json\" -d '{\"name\":\"自动选择\"}' \"http://127.0.0.1:9090/proxies/GLOBAL\""
            fi
        else
            log_error "❌ 控制API无法访问，代理可能有问题"
        fi
        
        log_success "VPN 服务配置完成"
    else
        log_error "mihomo 服务启动失败"
        systemctl status mihomo.service --no-pager
        exit 1
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

# 步骤5：测试 VPN 连接
test_vpn_connectivity() {
    log_step "5. 测试 VPN 连接"
    
    # 检查端口监听
    log_info "检查端口监听状态"
    if ss -tuln | grep -q ":7890"; then
        log_success "代理端口 7890 监听正常"
    else
        log_error "代理端口 7890 未监听"
        return 1
    fi
    
    # 测试内网连接（直连）
    log_info "测试内网连接（直连）"
    if curl -s --connect-timeout 5 http://www.baidu.com > /dev/null; then
        log_success "✅ 内网直连测试通过"
    else
        log_warn "⚠️  内网直连测试失败"
    fi
    
    # 测试代理连接 - 分别测试 HTTP 和 HTTPS 协议
    log_info "测试代理连接"
    
    # 测试 HTTP 代理
    log_info "测试 HTTP 协议代理..."
    if curl -s --connect-timeout 10 --proxy 127.0.0.1:7890 http://www.google.com > /dev/null 2>&1; then
        log_success "✅ HTTP 代理测试通过"
        local http_proxy_ok=true
    else
        log_warn "⚠️  HTTP 代理测试失败"
        local http_proxy_ok=false
    fi
    
    # 测试 HTTPS 代理
    log_info "测试 HTTPS 协议代理..."
    if curl -s --connect-timeout 10 --proxy 127.0.0.1:7890 https://www.google.com > /dev/null 2>&1; then
        log_success "✅ HTTPS 代理测试通过"
        local https_proxy_ok=true
    else
        log_warn "⚠️  HTTPS 代理测试失败（可能是SSL证书问题）"
        local https_proxy_ok=false
        
        # 如果HTTP成功但HTTPS失败，提供SSL解决方案
        if [[ "${http_proxy_ok}" == "true" ]]; then
            log_info "💡 HTTP代理正常，HTTPS问题可能是SSL证书验证"
            echo "   解决方案: curl --insecure --proxy 127.0.0.1:7890 https://site.com"
        fi
    fi
    
    # 测试关键网站访问
    log_info "测试关键网站访问..."
    if curl -s --connect-timeout 10 --proxy 127.0.0.1:7890 -I https://www.youtube.com > /dev/null 2>&1; then
        log_success "✅ YouTube访问测试通过"
    elif curl -s --connect-timeout 10 --proxy 127.0.0.1:7890 -I http://www.youtube.com > /dev/null 2>&1; then
        log_success "✅ YouTube访问测试通过（HTTP）"
    else
        log_warn "⚠️  YouTube访问测试失败"
    fi
    
    # 显示代理状态和IP信息
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

# 显示完成信息
show_completion_info() {
    echo
    log_success "=========================================="
    log_success "🎉 VPN 安装配置完成！"
    log_success "=========================================="
    echo
    
    log_info "服务信息:"
    echo "  • 混合端口: 7890 (HTTP/HTTPS)"
    echo "  • SOCKS端口: 7891"
    echo "  • 控制面板: http://127.0.0.1:9090"
    echo "  • 配置文件: ${CONFIG_FILE}"
    echo "  • 服务状态: systemctl status mihomo"
    echo
    
    log_info "使用方法:"
    echo "  • 启用代理: source /etc/profile.d/mihomo-proxy.sh && proxy-on"
    echo "  • 禁用代理: proxy-off"
    echo "  • 查看状态: proxy-status"
    echo "  • 服务管理: systemctl {start|stop|restart|status} mihomo"
    echo
    
    log_info "测试命令:"
    echo "  • 测试直连: curl -I http://www.baidu.com"
    echo "  • 测试HTTP代理: curl --proxy 127.0.0.1:7890 http://www.google.com"
    echo "  • 测试HTTPS代理: curl --insecure --proxy 127.0.0.1:7890 https://www.google.com"
    echo "  • 快速验证: curl --proxy 127.0.0.1:7890 -I http://www.youtube.com"
    echo "  • 查看代理状态: curl -s http://127.0.0.1:9090/proxies/GLOBAL | grep now"
    echo
    
    log_info "诊断工具:"
    echo "  • 运行诊断: mihomo-diagnose"
    echo "  • 查看日志: journalctl -u mihomo.service -f"
    echo "  • 重启服务: systemctl restart mihomo"
    echo
    
    log_warn "注意事项:"
    echo "  • 所有用户登录后会自动检测并启用代理"
    echo "  • 代理仅在 mihomo 服务运行时自动生效"
    echo "  • 如需修改配置，编辑 ${CONFIG_FILE} 后重启服务"
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

# 主函数
main() {
    echo "=========================================="
    echo "🚀 Mihomo VPN 快速安装向导"
    echo "=========================================="
    echo
    
    # 检查基础环境
    check_root
    check_system
    check_static_resources
    
    echo
    log_info "准备执行以下步骤："
    echo "  1️⃣  安装 mihomo 客户端"
    echo "  2️⃣  输入订阅链接"
    echo "  3️⃣  下载并配置订阅"
    echo "  4️⃣  启动 VPN 服务"
    echo "  5️⃣  测试网络连接"
    echo
    
    read -p "确认开始安装？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "安装已取消"
        exit 0
    fi
    
    # 执行安装步骤
    install_mihomo
    
    local subscription_url
    subscription_url=$(get_subscription_url)
    
    download_and_setup_config "${subscription_url}"
    setup_and_start_vpn
    
    # 安装后自动验证和修复
    log_step "验证和优化安装结果"
    perform_post_install_validation
    
    test_vpn_connectivity
    
    # 创建诊断脚本
    create_diagnostic_script
    
    show_completion_info
}

# 执行主函数
main "$@"
