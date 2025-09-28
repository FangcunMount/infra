#!/bin/bash
# Mihomo VPN 详细诊断脚本
# 专门排查 SSL_ERROR_SYSCALL 等代理连接问题

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $*"; }

CONFIG_FILE="/root/.config/clash/config.yaml"
CONTROL_URL="http://127.0.0.1:9090"

echo "=========================================="
echo "🔍 Mihomo SSL/代理连接诊断工具"
echo "=========================================="

# 1. 基础服务检查
log_step "1. 基础服务状态检查"
echo "检查 mihomo 服务状态..."
if systemctl is-active --quiet mihomo.service; then
    log_success "✅ mihomo 服务运行正常"
else
    log_error "❌ mihomo 服务未运行"
    exit 1
fi

echo "检查端口监听..."
if ss -tuln | grep -q ":7890"; then
    log_success "✅ HTTP 代理端口 7890 监听正常"
else
    log_error "❌ HTTP 代理端口 7890 未监听"
fi

if ss -tuln | grep -q ":7891"; then
    log_success "✅ SOCKS5 代理端口 7891 监听正常"
else
    log_error "❌ SOCKS5 代理端口 7891 未监听"
fi

if ss -tuln | grep -q ":9090"; then
    log_success "✅ 控制 API 端口 9090 监听正常"
else
    log_warn "⚠️  控制 API 端口 9090 未监听"
fi

echo

# 2. 配置文件分析
log_step "2. 配置文件分析"
if [[ -f "${CONFIG_FILE}" ]]; then
    log_info "配置文件存在: ${CONFIG_FILE}"
    
    # 统计代理节点数量
    proxy_count=$(grep -c '^  - name:' "${CONFIG_FILE}" 2>/dev/null || echo "0")
    log_info "代理节点数量: ${proxy_count}"
    
    # 显示前几个代理节点
    if [[ ${proxy_count} -gt 0 ]]; then
        echo "前5个代理节点:"
        grep -A1 '^  - name:' "${CONFIG_FILE}" | head -10 | while read line; do
            echo "    $line"
        done
    else
        log_error "❌ 未找到任何代理节点配置"
    fi
    
    # 检查代理组配置
    echo
    log_info "代理组配置:"
    if grep -q "proxy-groups:" "${CONFIG_FILE}"; then
        grep -A5 "proxy-groups:" "${CONFIG_FILE}" | head -10 | while read line; do
            echo "    $line"
        done
    else
        log_error "❌ 未找到代理组配置"
    fi
    
else
    log_error "❌ 配置文件不存在"
    exit 1
fi

echo

# 3. API 状态检查
log_step "3. Mihomo API 状态检查"
if curl -s --connect-timeout 5 "${CONTROL_URL}/version" >/dev/null 2>&1; then
    log_success "✅ 控制 API 可访问"
    
    # 获取当前选中的代理
    echo "当前代理选择:"
    if command -v jq >/dev/null 2>&1; then
        curl -s "${CONTROL_URL}/proxies" 2>/dev/null | jq -r '.proxies.GLOBAL.now // "未知"' | head -1 | while read proxy; do
            echo "    当前全局代理: $proxy"
        done
    else
        log_warn "未安装 jq，无法解析 API 响应"
    fi
    
    # 检查连接统计
    echo "连接统计:"
    curl -s "${CONTROL_URL}/traffic" 2>/dev/null | head -1 | while read traffic; do
        echo "    流量信息: $traffic"
    done
    
else
    log_warn "⚠️  控制 API 无法访问"
fi

echo

# 4. 网络连接测试
log_step "4. 详细网络连接测试"

# 4.1 直连测试
echo "4.1 直连测试 (不使用代理):"
test_sites=("www.baidu.com" "www.qq.com")
for site in "${test_sites[@]}"; do
    if curl -s --connect-timeout 5 "http://${site}" >/dev/null 2>&1; then
        log_success "✅ 直连 ${site} - 成功"
    else
        log_error "❌ 直连 ${site} - 失败"
    fi
done

echo

# 4.2 HTTP 代理测试
echo "4.2 HTTP 代理测试 (端口 7890):"
test_sites=("www.baidu.com" "www.google.com" "ifconfig.me")
for site in "${test_sites[@]}"; do
    echo -n "  测试 ${site}... "
    
    # HTTP 测试
    if curl -s --connect-timeout 10 --max-time 30 --proxy "127.0.0.1:7890" "http://${site}" >/dev/null 2>&1; then
        echo -e "${GREEN}HTTP-OK${NC}"
    else
        echo -e "${RED}HTTP-FAIL${NC}"
    fi
    
    # HTTPS 测试
    echo -n "  测试 ${site} (HTTPS)... "
    if curl -s --connect-timeout 10 --max-time 30 --proxy "127.0.0.1:7890" "https://${site}" >/dev/null 2>&1; then
        echo -e "${GREEN}HTTPS-OK${NC}"
    else
        # 获取详细错误信息
        error_info=$(curl --connect-timeout 10 --max-time 30 --proxy "127.0.0.1:7890" "https://${site}" 2>&1 | grep -o 'curl: ([0-9]*) .*' || echo "未知错误")
        echo -e "${RED}HTTPS-FAIL${NC} - ${error_info}"
    fi
done

echo

# 4.3 SOCKS5 代理测试
echo "4.3 SOCKS5 代理测试 (端口 7891):"
test_sites=("www.baidu.com" "www.google.com" "ifconfig.me")
for site in "${test_sites[@]}"; do
    echo -n "  测试 ${site} (SOCKS5)... "
    if curl -s --connect-timeout 10 --max-time 30 --socks5 "127.0.0.1:7891" "https://${site}" >/dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        error_info=$(curl --connect-timeout 10 --max-time 30 --socks5 "127.0.0.1:7891" "https://${site}" 2>&1 | grep -o 'curl: ([0-9]*) .*' || echo "未知错误")
        echo -e "${RED}FAIL${NC} - ${error_info}"
    fi
done

echo

# 5. SSL 详细诊断
log_step "5. SSL 连接详细诊断"
echo "测试不同的 SSL 配置..."

# 5.1 测试不同的 TLS 版本
echo "5.1 测试 TLS 版本兼容性:"
tls_versions=("--tlsv1.2" "--tlsv1.3")
for tls_ver in "${tls_versions[@]}"; do
    echo -n "  Google.com ${tls_ver}... "
    if curl -s --connect-timeout 10 ${tls_ver} --proxy "127.0.0.1:7890" "https://www.google.com" >/dev/null 2>&1; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAIL${NC}"
    fi
done

# 5.2 测试忽略 SSL 证书验证
echo "5.2 测试忽略 SSL 验证:"
echo -n "  Google.com (忽略SSL验证)... "
if curl -s --connect-timeout 10 --insecure --proxy "127.0.0.1:7890" "https://www.google.com" >/dev/null 2>&1; then
    echo -e "${GREEN}OK${NC} - 可能是证书验证问题"
else
    echo -e "${RED}FAIL${NC} - 不是证书问题"
fi

echo

# 6. 代理节点连通性测试
log_step "6. 代理节点连通性测试"
if [[ -f "${CONFIG_FILE}" ]]; then
    echo "解析配置文件中的代理服务器..."
    
    # 提取前几个代理节点的服务器地址
    grep -A10 '^  - name:' "${CONFIG_FILE}" | grep -E 'server:|port:' | head -10 | while read line; do
        if [[ "$line" =~ server:\ *([^\ ]+) ]]; then
            server="${BASH_REMATCH[1]}"
            echo -n "  测试代理服务器 ${server}... "
            
            # 测试服务器连通性
            if ping -c 1 -W 3 "$server" >/dev/null 2>&1; then
                echo -e "${GREEN}PING-OK${NC}"
            else
                echo -e "${RED}PING-FAIL${NC}"
            fi
        fi
    done
fi

echo

# 7. 系统网络配置检查
log_step "7. 系统网络配置检查"
echo "DNS 配置:"
cat /etc/resolv.conf | grep nameserver | head -3

echo
echo "路由表 (默认路由):"
ip route | grep default

echo
echo "防火墙状态:"
if command -v ufw >/dev/null 2>&1; then
    ufw status
else
    echo "UFW 未安装"
fi

echo

# 8. 建议和解决方案
log_step "8. 问题诊断和建议"
echo
log_warn "🔧 SSL_ERROR_SYSCALL 问题可能的原因和解决方案:"
echo
echo "1. 代理节点问题:"
echo "   - 节点服务器可能被封锁或不稳定"
echo "   - 尝试切换到其他节点"
echo "   - 检查订阅是否需要更新"
echo
echo "2. 网络干扰/DPI 检测:"
echo "   - 尝试使用 SOCKS5 代理而不是 HTTP 代理"
echo "   - 考虑启用混淆或伪装功能"
echo
echo "3. SSL/TLS 配置问题:"
echo "   - 尝试不同的 TLS 版本"
echo "   - 检查是否需要证书验证"
echo
echo "4. 系统配置问题:"
echo "   - 检查系统时间是否正确"
echo "   - 确认 DNS 解析正常"
echo "   - 检查防火墙规则"
echo

log_info "💡 立即尝试的解决方案:"
echo "# 1. 重启 mihomo 服务"
echo "systemctl restart mihomo && sleep 3"
echo
echo "# 2. 尝试使用 SOCKS5 代理"
echo "curl --socks5 127.0.0.1:7891 https://www.google.com"
echo
echo "# 3. 测试忽略 SSL 验证"
echo "curl --insecure --proxy 127.0.0.1:7890 https://www.google.com"
echo
echo "# 4. 检查服务日志"
echo "journalctl -u mihomo.service -n 50 --no-pager"
echo
echo "# 5. 手动切换代理节点 (如果有控制面板)"
echo "curl -X PUT ${CONTROL_URL}/proxies/GLOBAL -d '{\"name\":\"其他节点名称\"}'"

echo
log_info "诊断完成！请根据上述结果进行相应的调整。"