#!/bin/bash
# Mihomo VPN 完全卸载脚本
# 用于清理所有 mihomo 相关配置，恢复默认网络环境

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $*"; }

# 配置常量
readonly BINARY_TARGET="/usr/local/bin/mihomo"
readonly CONFIG_DIR="/root/.config/clash"
readonly SERVICE_FILE="/etc/systemd/system/mihomo.service"
readonly PROXY_PROFILE="/etc/profile.d/mihomo-proxy.sh"
readonly DIAGNOSTIC_SCRIPT="/usr/local/bin/mihomo-diagnose"

# 检查是否为root用户
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "此脚本需要root权限运行"
        log_info "请使用: sudo $0"
        exit 1
    fi
}

# 显示当前状态
show_current_status() {
    log_step "检查当前 VPN 安装状态"
    
    echo "🔍 当前系统状态："
    
    # 检查服务状态
    if systemctl is-enabled --quiet mihomo.service 2>/dev/null; then
        local service_status=$(systemctl is-active mihomo.service 2>/dev/null || echo "inactive")
        echo "  • 系统服务: 已安装 (${service_status})"
    else
        echo "  • 系统服务: 未安装"
    fi
    
    # 检查二进制文件
    if [[ -f "${BINARY_TARGET}" ]]; then
        local version=$(${BINARY_TARGET} -v 2>/dev/null | head -1 || echo "无法获取版本")
        echo "  • 二进制文件: 已安装 (${version})"
    else
        echo "  • 二进制文件: 未安装"
    fi
    
    # 检查配置目录
    if [[ -d "${CONFIG_DIR}" ]]; then
        local config_files=$(find "${CONFIG_DIR}" -type f 2>/dev/null | wc -l)
        echo "  • 配置目录: 存在 (${config_files} 个文件)"
    else
        echo "  • 配置目录: 不存在"
    fi
    
    # 检查全局代理配置
    if [[ -f "${PROXY_PROFILE}" ]]; then
        echo "  • 全局代理配置: 已安装"
    else
        echo "  • 全局代理配置: 未安装"
    fi
    
    # 检查当前代理环境变量
    if [[ -n "${http_proxy:-}" ]] || [[ -n "${https_proxy:-}" ]]; then
        echo "  • 当前代理状态: 已启用"
        echo "    - HTTP_PROXY: ${http_proxy:-'未设置'}"
        echo "    - HTTPS_PROXY: ${https_proxy:-'未设置'}"
    else
        echo "  • 当前代理状态: 未启用"
    fi
    
    echo
}

# 停止并禁用服务
stop_and_disable_service() {
    log_step "1. 停止并禁用 mihomo 服务"
    
    if systemctl is-active --quiet mihomo.service 2>/dev/null; then
        log_info "停止 mihomo 服务..."
        systemctl stop mihomo.service
        log_success "✅ 服务已停止"
    else
        log_info "服务未运行，跳过停止操作"
    fi
    
    if systemctl is-enabled --quiet mihomo.service 2>/dev/null; then
        log_info "禁用 mihomo 服务自启动..."
        systemctl disable mihomo.service
        log_success "✅ 服务自启动已禁用"
    else
        log_info "服务未设置自启动，跳过禁用操作"
    fi
}

# 删除服务文件
remove_service_file() {
    log_step "2. 删除 systemd 服务文件"
    
    if [[ -f "${SERVICE_FILE}" ]]; then
        log_info "删除服务文件: ${SERVICE_FILE}"
        rm -f "${SERVICE_FILE}"
        
        log_info "重载 systemd daemon..."
        systemctl daemon-reload
        systemctl reset-failed mihomo.service 2>/dev/null || true
        
        log_success "✅ 服务文件已删除"
    else
        log_info "服务文件不存在，跳过删除"
    fi
}

# 删除二进制文件
remove_binary() {
    log_step "3. 删除 mihomo 二进制文件"
    
    if [[ -f "${BINARY_TARGET}" ]]; then
        log_info "删除二进制文件: ${BINARY_TARGET}"
        rm -f "${BINARY_TARGET}"
        log_success "✅ 二进制文件已删除"
    else
        log_info "二进制文件不存在，跳过删除"
    fi
}

# 删除配置文件
remove_config_files() {
    log_step "4. 删除配置文件和目录"
    
    if [[ -d "${CONFIG_DIR}" ]]; then
        log_info "删除配置目录: ${CONFIG_DIR}"
        
        # 备份配置文件（可选）
        read -p "是否备份配置文件到 /tmp？(y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            local backup_dir="/tmp/mihomo-config-backup-$(date +%Y%m%d-%H%M%S)"
            mkdir -p "${backup_dir}"
            cp -r "${CONFIG_DIR}"/* "${backup_dir}/" 2>/dev/null || true
            log_success "✅ 配置已备份到: ${backup_dir}"
        fi
        
        rm -rf "${CONFIG_DIR}"
        log_success "✅ 配置目录已删除"
    else
        log_info "配置目录不存在，跳过删除"
    fi
}

# 删除全局代理配置
remove_global_proxy() {
    log_step "5. 删除全局代理配置"
    
    if [[ -f "${PROXY_PROFILE}" ]]; then
        log_info "删除全局代理配置: ${PROXY_PROFILE}"
        rm -f "${PROXY_PROFILE}"
        log_success "✅ 全局代理配置已删除"
    else
        log_info "全局代理配置不存在，跳过删除"
    fi
}

# 清理环境变量
clean_environment_variables() {
    log_step "6. 清理当前会话的代理环境变量"
    
    # 清理当前会话的代理变量
    unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY 2>/dev/null || true
    
    log_info "清理当前会话的代理环境变量"
    log_success "✅ 环境变量已清理"
    
    # 提示用户重新登录
    log_warn "注意：需要重新登录终端以完全清除所有用户的代理环境变量"
}

# 删除诊断脚本
remove_diagnostic_tools() {
    log_step "7. 删除诊断和管理工具"
    
    local tools=("${DIAGNOSTIC_SCRIPT}" "/usr/local/bin/mihomo-diagnose" "/root/mihomo-ssl-diagnose.sh" "/root/verify-proxy.sh")
    
    for tool in "${tools[@]}"; do
        if [[ -f "${tool}" ]]; then
            log_info "删除工具: ${tool}"
            rm -f "${tool}"
        fi
    done
    
    log_success "✅ 诊断工具已删除"
}

# 清理网络配置残留
clean_network_residuals() {
    log_step "8. 清理网络配置残留"
    
    # 检查并清理可能的 iptables 规则（如果有的话）
    log_info "检查防火墙规则..."
    
    # 清理可能的端口占用
    local ports=("7890" "7891" "9090")
    for port in "${ports[@]}"; do
        if ss -tuln | grep -q ":${port}"; then
            log_warn "端口 ${port} 仍被占用，可能需要手动检查"
        fi
    done
    
    log_success "✅ 网络残留检查完成"
}

# 验证卸载结果
verify_uninstall() {
    log_step "9. 验证卸载结果"
    
    local issues=()
    
    # 检查服务
    if systemctl is-enabled --quiet mihomo.service 2>/dev/null || systemctl is-active --quiet mihomo.service 2>/dev/null; then
        issues+=("systemd 服务仍然存在")
    fi
    
    # 检查二进制文件
    if [[ -f "${BINARY_TARGET}" ]]; then
        issues+=("二进制文件仍然存在")
    fi
    
    # 检查配置目录
    if [[ -d "${CONFIG_DIR}" ]]; then
        issues+=("配置目录仍然存在")
    fi
    
    # 检查代理配置
    if [[ -f "${PROXY_PROFILE}" ]]; then
        issues+=("全局代理配置仍然存在")
    fi
    
    # 检查端口占用
    if ss -tuln | grep -q ":7890\|:7891\|:9090"; then
        issues+=("相关端口仍被占用")
    fi
    
    if [[ ${#issues[@]} -eq 0 ]]; then
        log_success "✅ 卸载验证通过！所有 mihomo 组件已完全删除"
        return 0
    else
        log_warn "⚠️  发现以下问题："
        for issue in "${issues[@]}"; do
            echo "  • ${issue}"
        done
        return 1
    fi
}

# 显示卸载完成信息
show_completion_info() {
    echo
    log_success "=========================================="
    log_success "🎯 Mihomo VPN 卸载完成！"
    log_success "=========================================="
    echo
    
    log_info "已删除的组件:"
    echo "  ✅ Mihomo 服务和自启动配置"
    echo "  ✅ 二进制文件 (/usr/local/bin/mihomo)"
    echo "  ✅ 配置文件和目录 (/root/.config/clash)"
    echo "  ✅ 全局代理环境变量配置"
    echo "  ✅ 诊断和管理工具"
    echo
    
    log_info "网络环境状态:"
    echo "  🔄 系统已恢复到默认网络配置"
    echo "  🌐 所有网络流量现在直接连接"
    echo "  🔓 代理环境变量已清除"
    echo
    
    log_warn "重要提醒:"
    echo "  • 请重新登录终端以确保环境变量完全清除"
    echo "  • 如果有备份配置文件，请检查 /tmp 目录"
    echo "  • 现在可以重新运行安装脚本进行全新安装"
    echo
    
    log_info "验证卸载："
    echo "  • 检查服务: systemctl status mihomo"
    echo "  • 检查进程: ps aux | grep mihomo"
    echo "  • 检查端口: ss -tuln | grep '7890\\|7891\\|9090'"
    echo "  • 检查网络: curl -I http://www.google.com"
    echo
    
    if verify_uninstall; then
        log_success "🎉 系统已完全清理，可以进行重新安装！"
    else
        log_warn "🔧 部分清理可能需要手动处理，请检查上述问题。"
    fi
}

# 主函数
main() {
    echo "=========================================="
    echo "🗑️  Mihomo VPN 完全卸载工具"
    echo "=========================================="
    echo
    
    # 检查权限
    check_root
    
    # 显示当前状态
    show_current_status
    
    # 确认卸载
    echo "⚠️  警告：此操作将完全删除所有 Mihomo VPN 相关配置！"
    echo
    read -p "确认继续卸载？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "卸载已取消"
        exit 0
    fi
    
    echo
    log_info "开始执行卸载流程..."
    echo
    
    # 执行卸载步骤
    stop_and_disable_service
    remove_service_file
    remove_binary
    remove_config_files
    remove_global_proxy
    clean_environment_variables
    remove_diagnostic_tools
    clean_network_residuals
    
    # 显示完成信息
    show_completion_info
}

# 捕获错误
trap 'log_error "卸载过程中发生错误，请检查上述输出"; exit 1' ERR

# 执行主函数
main "$@"