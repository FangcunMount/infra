#!/bin/bash

# mihomo 网络代理诊断和修复脚本
# 用于诊断 setup-network.sh 安装后的网络代理问题

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "========================================"
echo "    Mihomo 网络代理诊断工具"
echo "========================================"
echo

# 检查系统状态
check_system_status() {
    log_info "检查系统状态..."

    # 检查 mihomo 二进制文件
    if [[ -f "/usr/local/bin/mihomo" ]]; then
        log_success "✅ mihomo 二进制文件存在"
        /usr/local/bin/mihomo -v
    else
        log_error "❌ mihomo 二进制文件不存在"
        return 1
    fi

    # 检查配置目录
    if [[ -d "/opt/mihomo" ]]; then
        log_success "✅ mihomo 配置目录存在"
        ls -la /opt/mihomo/
    else
        log_error "❌ mihomo 配置目录不存在: /opt/mihomo"
        return 1
    fi

    # 检查配置文件
    if [[ -f "/opt/mihomo/config/config.yaml" ]]; then
        log_success "✅ 配置文件存在"
        head -10 /opt/mihomo/config/config.yaml
    else
        log_error "❌ 配置文件不存在: /opt/mihomo/config/config.yaml"
        return 1
    fi

    # 检查地理数据文件
    if [[ -f "/opt/mihomo/data/GeoSite.dat" && -f "/opt/mihomo/data/GeoIP.metadb" ]]; then
        log_success "✅ 地理数据文件存在"
    else
        log_warn "⚠️  地理数据文件缺失"
    fi

    # 检查 systemd 服务
    if systemctl is-active --quiet mihomo.service 2>/dev/null; then
        log_success "✅ mihomo 服务正在运行"
        systemctl status mihomo.service --no-pager -l | head -10
    else
        log_error "❌ mihomo 服务未运行"
        return 1
    fi

    # 检查全局代理环境变量
    if [[ -f "/etc/profile.d/mihomo-proxy.sh" ]]; then
        log_success "✅ 全局代理脚本存在"
        cat /etc/profile.d/mihomo-proxy.sh
    else
        log_warn "⚠️  全局代理脚本不存在"
    fi

    # 检查环境变量
    if env | grep -q "http_proxy\|https_proxy"; then
        log_success "✅ 代理环境变量已设置"
        env | grep -i proxy
    else
        log_warn "⚠️  代理环境变量未设置"
    fi
}

# 修复配置问题
fix_configuration() {
    log_info "开始修复配置..."

    # 创建必要的目录
    log_info "创建配置目录..."
    mkdir -p /opt/mihomo/config
    mkdir -p /opt/mihomo/data

    # 设置权限
    chown -R mihomo:mihomo /opt/mihomo 2>/dev/null || true
    chmod -R 755 /opt/mihomo

    # 创建基础配置文件（如果不存在）
    if [[ ! -f "/opt/mihomo/config/config.yaml" ]]; then
        log_info "创建基础配置文件..."
        cat > /opt/mihomo/config/config.yaml << 'EOF'
# Mihomo 基础配置文件
mixed-port: 7890
allow-lan: true
bind-address: "*"
mode: rule
log-level: info
ipv6: true

# DNS 配置
dns:
  enable: true
  listen: 0.0.0.0:53
  default-nameserver:
    - 8.8.8.8
    - 1.1.1.1
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  nameserver:
    - https://dns.alidns.com/dns-query
    - https://doh.pub/dns-query

# 代理配置（需要根据实际情况修改）
proxies: []

# 规则配置
rules:
  - MATCH,DIRECT
EOF
        log_success "基础配置文件已创建"
    fi

    # 重新加载服务
    log_info "重新加载 systemd 服务..."
    systemctl daemon-reload

    # 重启服务
    log_info "重启 mihomo 服务..."
    systemctl restart mihomo.service

    # 等待服务启动
    sleep 3

    if systemctl is-active --quiet mihomo.service; then
        log_success "✅ mihomo 服务重启成功"
    else
        log_error "❌ mihomo 服务重启失败"
        systemctl status mihomo.service --no-pager
        return 1
    fi
}

# 设置全局代理
setup_global_proxy() {
    log_info "设置全局代理环境变量..."

    # 创建代理脚本
    cat > /etc/profile.d/mihomo-proxy.sh << 'EOF'
#!/bin/bash
# Mihomo 全局代理环境变量

export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"
export ftp_proxy="http://127.0.0.1:7890"
export no_proxy="localhost,127.0.0.1,::1"

# Docker 代理
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
EOF

    chmod +x /etc/profile.d/mihomo-proxy.sh
    log_success "全局代理脚本已创建"

    # 立即应用环境变量
    source /etc/profile.d/mihomo-proxy.sh
    log_success "环境变量已应用到当前会话"
}

# 测试网络连接
test_network() {
    log_info "测试网络连接..."

    # 测试本地代理端口
    if nc -z 127.0.0.1 7890 2>/dev/null; then
        log_success "✅ 本地代理端口 7890 可访问"
    else
        log_error "❌ 本地代理端口 7890 不可访问"
        return 1
    fi

    # 测试代理连接
    log_info "测试代理连接..."
    if curl -s --connect-timeout 5 --max-time 10 -x http://127.0.0.1:7890 https://httpbin.org/ip >/dev/null; then
        log_success "✅ 代理连接正常"
    else
        log_warn "⚠️  代理连接测试失败，可能需要配置代理节点"
    fi

    # 测试 DNS
    log_info "测试 DNS 解析..."
    if nslookup github.com 127.0.0.1 >/dev/null 2>&1; then
        log_success "✅ DNS 解析正常"
    else
        log_warn "⚠️  DNS 解析测试失败"
    fi
}

# 主函数
main() {
    echo "选择操作："
    echo "1) 诊断当前状态"
    echo "2) 修复配置问题"
    echo "3) 设置全局代理"
    echo "4) 测试网络连接"
    echo "5) 完整修复（2+3+4）"
    echo

    read -p "请选择 (1-5): " choice

    case $choice in
        1)
            check_system_status
            ;;
        2)
            fix_configuration
            ;;
        3)
            setup_global_proxy
            ;;
        4)
            test_network
            ;;
        5)
            log_info "执行完整修复..."
            fix_configuration
            setup_global_proxy
            test_network
            log_success "完整修复完成！"
            ;;
        *)
            log_error "无效选择"
            exit 1
            ;;
    esac

    echo
    log_info "操作完成。如仍有问题，请检查 mihomo 日志："
    echo "  journalctl -u mihomo.service -f"
    echo
    log_info "常用管理命令："
    echo "  systemctl status mihomo.service    # 查看服务状态"
    echo "  systemctl restart mihomo.service  # 重启服务"
    echo "  curl -x http://127.0.0.1:7890 https://httpbin.org/ip  # 测试代理"
}

main "$@"