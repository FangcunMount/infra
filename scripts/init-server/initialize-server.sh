#!/usr/bin/env bash
set -euo pipefail

# 服务器一键初始化脚本
# 执行顺序：init-users.sh → setup-network.sh → install-docker.sh

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

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

log_step() {
    echo -e "${CYAN}[STEP]${NC} $1"
}

# 检查脚本存在性
check_scripts() {
    local scripts=("init-users.sh" "setup-network.sh" "install-docker.sh")
    local missing=()
    
    for script in "${scripts[@]}"; do
        if [[ ! -f "$script" ]]; then
            missing+=("$script")
        fi
    done
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "缺少必要的脚本文件："
        for script in "${missing[@]}"; do
            echo "  - $script"
        done
        exit 1
    fi
}

# 检查权限
check_permissions() {
    if [[ ${EUID} -ne 0 ]]; then
        log_error "此脚本必须以 root 用户身份运行"
        echo "使用方法: sudo $0"
        exit 1
    fi
}

# 显示执行计划
show_plan() {
    echo "=========================================="
    echo "🚀 服务器初始化三步流程"
    echo "=========================================="
    echo
    echo "执行计划："
    echo "  1️⃣  用户和安全配置     (init-users.sh)"
    echo "  2️⃣  网络环境配置       (setup-network.sh)"
    echo "  3️⃣  Docker 环境安装    (install-docker.sh)"
    echo
    echo "预计用时：10-23 分钟"
    echo "=========================================="
    echo
}

# 执行步骤
execute_step() {
    local step_num=$1
    local step_name="$2"
    local script_name="$3"
    local description="$4"
    
    echo
    log_step "步骤 ${step_num}/3: $step_name"
    echo "描述: $description"
    echo "执行脚本: $script_name"
    echo
    
    read -p "继续执行此步骤？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_warn "用户跳过步骤 $step_num"
        return 1
    fi
    
    log_info "开始执行 $script_name..."
    
    if ./"$script_name"; then
        log_success "✅ 步骤 $step_num 完成: $step_name"
        return 0
    else
        log_error "❌ 步骤 $step_num 失败: $step_name"
        echo
        log_info "您可以："
        echo "  1. 检查错误信息并修复问题"
        echo "  2. 重新运行: sudo ./$script_name"
        echo "  3. 或继续执行后续步骤"
        return 1
    fi
}

# 验证步骤
verify_step() {
    local step_num=$1
    local step_name="$2"
    
    case $step_num in
        1)
            log_info "验证用户配置..."
            if systemctl is-active --quiet ssh 2>/dev/null; then
                log_success "SSH 服务正常"
            else
                log_warn "SSH 服务检查失败"
            fi
            ;;
        2)
            log_info "验证网络配置..."
            if systemctl is-active --quiet mihomo 2>/dev/null; then
                log_success "mihomo 服务正常"
                if netstat -tuln 2>/dev/null | grep -q ":7890 "; then
                    log_success "代理端口 7890 正常监听"
                fi
            else
                log_warn "网络服务检查失败"
            fi
            ;;
        3)
            log_info "验证 Docker 配置..."
            if systemctl is-active --quiet docker 2>/dev/null; then
                log_success "Docker 服务正常"
                if docker version >/dev/null 2>&1; then
                    log_success "Docker 命令可用"
                fi
            else
                log_warn "Docker 服务检查失败"
            fi
            ;;
    esac
}

# 显示完成信息
show_completion() {
    echo
    echo "=========================================="
    echo "🎉 服务器初始化完成！"
    echo "=========================================="
    echo
    echo "✅ 已完成的配置："
    echo "  • 用户和安全环境"
    echo "  • 网络代理服务"
    echo "  • Docker 容器环境"
    echo
    echo "🔧 管理命令："
    echo "  • 用户管理: sudo usermod, sudo passwd"
    echo "  • 网络管理: mihomo-control {start|stop|status}"
    echo "  • Docker 管理: docker {ps|images|run}"
    echo
    echo "🌐 服务端点："
    echo "  • SSH: 端口 22（如有配置）"
    echo "  • 代理服务: http://$(hostname -I | awk '{print $1}'):7890"
    echo "  • 管理面板: http://$(hostname -I | awk '{print $1}'):9090"
    echo
    echo "📚 更多信息请查看 SERVER_INITIALIZATION_FLOW.md"
    echo "=========================================="
}

# 主函数
main() {
    # 检查环境
    check_permissions
    check_scripts
    
    # 显示计划
    show_plan
    
    # 用户确认
    read -p "确认开始三步初始化流程？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "用户取消执行"
        exit 0
    fi
    
    # 记录开始时间
    local start_time=$(date +%s)
    
    # 执行三个步骤
    local completed_steps=0
    
    # 步骤1: 用户初始化
    if execute_step 1 "用户和安全配置" "init-users.sh" "创建用户、配置SSH、设置权限"; then
        verify_step 1 "用户配置"
        ((completed_steps++))
    fi
    
    # 步骤2: 网络配置
    if execute_step 2 "网络环境配置" "setup-network.sh" "安装mihomo、配置代理、优化网络"; then
        verify_step 2 "网络配置"
        ((completed_steps++))
    fi
    
    # 步骤3: Docker安装
    if execute_step 3 "Docker环境安装" "install-docker.sh" "安装Docker、配置服务、设置权限"; then
        verify_step 3 "Docker配置"
        ((completed_steps++))
    fi
    
    # 计算耗时
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local minutes=$((duration / 60))
    local seconds=$((duration % 60))
    
    echo
    log_info "执行统计："
    echo "  完成步骤: $completed_steps/3"
    echo "  总耗时: ${minutes}分${seconds}秒"
    
    if [[ $completed_steps -eq 3 ]]; then
        show_completion
    else
        echo
        log_warn "部分步骤未完成，请检查日志并手动执行剩余步骤"
    fi
}

# 执行主函数
main "$@"