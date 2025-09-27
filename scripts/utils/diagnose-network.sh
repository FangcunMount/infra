#!/usr/bin/env bash
# 网络环境诊断脚本
# 用于排查 setup-network.sh 运行中的问题

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[!]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

echo "========================================"
echo "网络环境诊断工具"
echo "========================================"
echo

# 检查基本权限
log_info "1. 检查运行权限"
if [[ ${EUID} -eq 0 ]]; then
    log_success "正在以 root 权限运行"
else
    log_error "需要 root 权限，请使用: sudo $0"
    echo "当前用户: $(whoami)"
fi

# 检查系统信息
log_info "2. 系统信息"
if [[ -f /etc/os-release ]]; then
    source /etc/os-release
    echo "  操作系统: ${PRETTY_NAME:-${ID}}"
    echo "  版本: ${VERSION_ID:-未知}"
    echo "  内核: $(uname -r)"
    echo "  架构: $(uname -m)"
else
    log_error "无法读取 /etc/os-release"
fi

# 检查磁盘空间
log_info "3. 磁盘空间"
df -h / | head -2

# 检查网络连接
log_info "4. 网络连接测试"
test_sites=("8.8.8.8" "114.114.114.114" "github.com" "docker.com")
for site in "${test_sites[@]}"; do
    if ping -c 1 -W 3 "$site" >/dev/null 2>&1; then
        log_success "连接到 $site: 正常"
    else
        log_error "连接到 $site: 失败"
    fi
done

# 检查 DNS 解析
log_info "5. DNS 解析测试"
if nslookup github.com >/dev/null 2>&1; then
    log_success "DNS 解析: 正常"
else
    log_error "DNS 解析: 失败"
    echo "  当前 DNS 服务器:"
    cat /etc/resolv.conf | grep nameserver || echo "  未找到 DNS 配置"
fi

# 检查必要工具
log_info "6. 必要工具检查"
tools=("curl" "wget" "python3" "docker" "systemctl")
for tool in "${tools[@]}"; do
    if command -v "$tool" >/dev/null 2>&1; then
        version=$($tool --version 2>/dev/null | head -1 || echo "已安装")
        log_success "$tool: $version"
    else
        log_warn "$tool: 未安装"
    fi
done

# 检查包管理器
log_info "7. 包管理器检查"
if command -v apt-get >/dev/null 2>&1; then
    log_success "apt-get: 可用"
    echo "  更新状态: $(apt list --upgradable 2>/dev/null | wc -l) 个包可更新"
elif command -v yum >/dev/null 2>&1; then
    log_success "yum: 可用"
elif command -v dnf >/dev/null 2>&1; then
    log_success "dnf: 可用"
else
    log_error "未找到支持的包管理器"
fi

# 检查 Docker 状态
log_info "8. Docker 服务状态"
if systemctl is-active --quiet docker 2>/dev/null; then
    log_success "Docker 服务: 运行中"
    docker_version=$(docker --version 2>/dev/null || echo "版本未知")
    echo "  版本: $docker_version"
elif systemctl status docker >/dev/null 2>&1; then
    log_warn "Docker 服务: 已安装但未运行"
    echo "  启动命令: systemctl start docker"
else
    log_warn "Docker 服务: 未安装"
    echo "  请先运行: sudo ./install-docker.sh"
fi

# 检查端口占用
log_info "9. 端口占用检查"
ports=("7890" "9090" "53")
for port in "${ports[@]}"; do
    if netstat -tln 2>/dev/null | grep -q ":$port " || ss -tln 2>/dev/null | grep -q ":$port "; then
        log_warn "端口 $port: 已被占用"
        process=$(netstat -tlnp 2>/dev/null | grep ":$port " | awk '{print $7}' || echo "未知进程")
        echo "  占用进程: $process"
    else
        log_success "端口 $port: 可用"
    fi
done

# 检查防火墙状态
log_info "10. 防火墙状态"
if command -v ufw >/dev/null 2>&1; then
    ufw_status=$(ufw status 2>/dev/null | head -1 || echo "状态未知")
    echo "  UFW: $ufw_status"
elif command -v firewall-cmd >/dev/null 2>&1; then
    if systemctl is-active --quiet firewalld; then
        log_info "  firewalld: 运行中"
    else
        log_info "  firewalld: 未运行"
    fi
elif command -v iptables >/dev/null 2>&1; then
    rules_count=$(iptables -L | wc -l 2>/dev/null || echo "0")
    echo "  iptables: $rules_count 条规则"
else
    log_info "  未检测到防火墙配置"
fi

echo
log_info "诊断完成！"
echo "如果发现问题，请根据上述信息进行修复后重新运行 setup-network.sh"