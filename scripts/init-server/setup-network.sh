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
    log_step "2. 输入订阅链接"
    
    local subscription_url=""
    while [[ -z "${subscription_url}" ]]; do
        echo
        read -rp "请输入 Clash 订阅链接: " subscription_url
        if [[ -z "${subscription_url}" ]]; then
            log_warn "订阅链接不能为空，请重新输入"
        elif [[ ! "${subscription_url}" =~ ^https?:// ]]; then
            log_warn "请输入有效的 HTTP/HTTPS 链接"
            subscription_url=""
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
    local temp_config="/tmp/mihomo_config.yaml"
    
    if curl -fsSL -o "${temp_config}" "${subscription_url}"; then
        log_success "订阅配置下载成功"
        
        # 修改配置，禁用自动更新
        log_info "调整配置参数"
        cat > "${CONFIG_FILE}" << EOF
# 基础配置
mixed-port: 7890
socks-port: 7891
allow-lan: true
mode: rule
log-level: info
external-controller: 127.0.0.1:9090
secret: ""

# DNS 配置
dns:
  enable: true
  listen: 0.0.0.0:1053
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  nameserver:
    - 223.5.5.5
    - 114.114.114.114

# 禁用自动更新（使用本地文件）
geo-auto-update: false
geox-url:
  geoip: ""
  geosite: ""
  mmdb: ""

EOF
        
        # 提取订阅配置中的节点和规则部分
        if grep -q "proxies:" "${temp_config}"; then
            log_info "提取代理节点配置"
            sed -n '/^proxies:/,$p' "${temp_config}" >> "${CONFIG_FILE}"
        else
            log_error "订阅配置格式异常，未找到 proxies 配置"
            exit 1
        fi
        
        rm -f "${temp_config}"
        chmod 600 "${CONFIG_FILE}"
        log_success "配置文件创建完成: ${CONFIG_FILE}"
    else
        log_error "订阅配置下载失败"
        log_error "请检查网络连接或订阅链接是否正确"
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
# Mihomo 代理环境变量
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"
export all_proxy="socks5://127.0.0.1:7891"

proxy-on() {
    export http_proxy="http://127.0.0.1:7890"
    export https_proxy="http://127.0.0.1:7890"
    export all_proxy="socks5://127.0.0.1:7891"
    echo "🟢 代理已开启"
}

proxy-off() {
    unset http_proxy https_proxy all_proxy
    echo "🔴 代理已关闭"
}

proxy-status() {
    if [[ -n "${http_proxy:-}" ]]; then
        echo "当前代理: $http_proxy"
    else
        echo "代理未开启"
    fi
}
EOF
        chmod 644 /etc/profile.d/mihomo-proxy.sh
        
        # 加载环境变量
        source /etc/profile.d/mihomo-proxy.sh
        log_success "VPN 服务配置完成"
    else
        log_error "mihomo 服务启动失败"
        systemctl status mihomo.service --no-pager
        exit 1
    fi
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
    
    # 测试外网连接（通过代理）
    log_info "测试外网连接（通过代理）"
    
    # 测试 HTTP 代理
    if curl -s --connect-timeout 10 --proxy 127.0.0.1:7890 https://www.google.com > /dev/null; then
        log_success "✅ HTTP 代理测试通过 - 可访问外网"
    else
        log_warn "⚠️  HTTP 代理测试失败"
    fi
    
    # 测试 SOCKS5 代理
    if curl -s --connect-timeout 10 --socks5 127.0.0.1:7891 https://ifconfig.me > /dev/null; then
        log_success "✅ SOCKS5 代理测试通过"
    else
        log_warn "⚠️  SOCKS5 代理测试失败"
    fi
    
    # 显示当前 IP
    log_info "检查当前外网 IP"
    local current_ip
    if current_ip=$(curl -s --connect-timeout 10 --proxy 127.0.0.1:7890 https://ifconfig.me 2>/dev/null); then
        log_success "当前外网 IP: ${current_ip}"
    else
        log_warn "无法获取外网 IP，可能代理配置有问题"
    fi
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
    echo "  • 测试代理: curl --proxy 127.0.0.1:7890 https://www.google.com"
    echo "  • 查看外网IP: curl --proxy 127.0.0.1:7890 https://ifconfig.me"
    echo
    
    log_warn "注意事项:"
    echo "  • 重新登录终端以应用环境变量"
    echo "  • 如需修改配置，编辑 ${CONFIG_FILE} 后重启服务"
    echo "  • 服务已设置开机自启动"
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
    test_vpn_connectivity
    
    show_completion_info
}

# 执行主函数
main "$@"
