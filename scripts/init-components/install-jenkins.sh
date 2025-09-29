#!/bin/bash

# =================================================================
# Jenkins CI/CD 平台安装脚本
# =================================================================
# 功能：在 Docker 环境中安装和配置 Jenkins
# 特性：Configuration as Code、预装插件、Docker 集成
# 作者：Infrastructure Team
# 版本：2.0
# =================================================================

set -euo pipefail

# =================================================================
# 全局配置
# =================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# 服务配置
SERVICE_NAME="jenkins"
DOCKER_IMAGE="jenkins/jenkins:lts"

# 目录配置
DATA_ROOT="/data"
JENKINS_HOME="$DATA_ROOT/jenkins"
LOG_DIR="$DATA_ROOT/logs/jenkins"

# 默认配置
DEFAULT_ENV="prod"
DEFAULT_HTTP_PORT="8080"
DEFAULT_AGENT_PORT="50000"
DEFAULT_MEMORY="1024m"

# =================================================================
# 工具函数
# =================================================================

# 颜色输出
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# 显示帮助信息
show_help() {
    cat << 'EOF'
Jenkins 安装脚本

用法:
    ./install-jenkins.sh [选项]

选项:
    -h, --help          显示帮助信息
    --env ENV           环境类型 (dev/prod，默认: prod)
    --port PORT         HTTP 端口 (默认: 8080)
    --memory MEM        内存限制 (默认: 1024m)
    --dry-run           预览模式，不实际执行
    --config-only       仅生成配置，不启动服务
    --start-only        仅启动服务，跳过配置生成
    --status            检查服务状态
    --logs              查看服务日志
    --stop              停止服务
    --restart           重启服务

示例:
    ./install-jenkins.sh                    # 标准安装
    ./install-jenkins.sh --env dev          # 开发环境
    ./install-jenkins.sh --port 9080        # 自定义端口
    ./install-jenkins.sh --dry-run          # 预览安装
    ./install-jenkins.sh --status           # 检查状态

EOF
}

# 检测 Docker Compose 命令
detect_docker_compose() {
    if docker compose version &>/dev/null; then
        echo "docker compose"
    elif command -v "docker-compose" &>/dev/null; then
        echo "docker-compose"
    else
        log_error "未找到 Docker Compose，请先安装 Docker"
        exit 1
    fi
}

# 生成安全密码
generate_password() {
    local length=${1:-16}
    openssl rand -base64 32 | tr -d "=+/" | head -c "$length"
}

# 检查端口占用
check_port() {
    local port=$1
    if command -v ss &>/dev/null; then
        ss -tuln | grep -q ":$port "
    elif command -v netstat &>/dev/null; then
        netstat -tuln | grep -q ":$port "
    else
        return 0  # 无法检查，假设端口可用
    fi
}

# =================================================================
# 前置条件检查
# =================================================================

check_requirements() {
    log_info "检查系统要求..."
    
    local errors=0
    
    # 检查 Docker
    if ! command -v docker &>/dev/null; then
        log_error "Docker 未安装"
        ((errors++))
    elif ! docker info &>/dev/null; then
        log_error "Docker 服务未运行"
        ((errors++))
    fi
    
    # 检查磁盘空间 (至少 2GB)
    local available_gb
    available_gb=$(df "$DATA_ROOT" 2>/dev/null | awk 'NR==2 {printf "%.1f", $4/1024/1024}' || echo "0")
    if (( $(echo "$available_gb < 2.0" | bc -l 2>/dev/null || echo 0) )); then
        log_warn "可用磁盘空间: ${available_gb}GB (建议至少 2GB)"
    fi
    
    # 检查端口占用
    if check_port "$HTTP_PORT"; then
        log_error "端口 $HTTP_PORT 已被占用"
        ((errors++))
    fi
    
    if check_port "$AGENT_PORT"; then
        log_error "端口 $AGENT_PORT 已被占用"
        ((errors++))
    fi
    
    # 检查权限
    if [[ ! -w "$(dirname "$DATA_ROOT")" ]] && ! sudo -n true 2>/dev/null; then
        log_error "需要 sudo 权限创建数据目录"
        ((errors++))
    fi
    
    if [[ $errors -gt 0 ]]; then
        log_error "前置条件检查失败，请解决以上问题"
        exit 1
    fi
    
    log_success "系统要求检查通过"
}

# =================================================================
# 目录和权限管理
# =================================================================

setup_directories() {
    log_info "设置目录结构..."
    
    local directories=(
        "$JENKINS_HOME"
        "$JENKINS_HOME/jenkins_home"
        "$JENKINS_HOME/casc_configs"
        "$LOG_DIR"
    )
    
    for dir in "${directories[@]}"; do
        if [[ ! -d "$dir" ]]; then
            sudo mkdir -p "$dir"
            log_info "创建目录: $dir"
        fi
    done
    
    # 设置权限 (Jenkins 容器使用 UID 1000)
    sudo chown -R 1000:1000 "$JENKINS_HOME" "$LOG_DIR"
    sudo chmod -R 755 "$JENKINS_HOME" "$LOG_DIR"
    
    log_success "目录设置完成"
}

# =================================================================
# 配置文件生成
# =================================================================

generate_env_config() {
    log_info "生成环境配置..."
    
    local env_dir="$PROJECT_ROOT/compose/env/$ENVIRONMENT"
    local env_file="$env_dir/.env"
    
    # 确保环境目录存在
    mkdir -p "$env_dir"
    
    # 检查是否已有 Jenkins 配置
    if grep -q "JENKINS_ADMIN_PASSWORD=" "$env_file" 2>/dev/null; then
        log_info "Jenkins 配置已存在，跳过生成"
        return 0
    fi
    
    # 生成管理员密码
    local admin_password
    admin_password=$(generate_password 16)
    
    # 添加 Jenkins 配置
    cat >> "$env_file" << EOF

# =================================================================
# Jenkins Configuration - Generated $(date)
# =================================================================
JENKINS_HTTP_PORT=$HTTP_PORT
JENKINS_AGENT_PORT=$AGENT_PORT
JENKINS_VERSION=lts
JENKINS_MEMORY=$MEMORY

# 管理员配置
JENKINS_ADMIN_USER=admin
JENKINS_ADMIN_PASSWORD=$admin_password

# JVM 配置
JAVA_OPTS=-Djenkins.install.runSetupWizard=false -Xmx$MEMORY -Xms256m

# Jenkins 配置
JENKINS_OPTS=--httpPort=$HTTP_PORT --logfile=/data/log/jenkins/jenkins.log
CASC_JENKINS_CONFIG=/var/jenkins_home/casc_configs/jenkins.yaml

EOF
    
    log_success "环境配置已生成: $env_file"
    log_info "管理员密码: $admin_password"
    
    # 存储密码供后续显示
    ADMIN_PASSWORD="$admin_password"
}

copy_config_files() {
    log_info "复制配置文件..."
    
    local source_dir="$PROJECT_ROOT/components/jenkins"
    local dest_configs="$JENKINS_HOME/casc_configs"
    local dest_home="$JENKINS_HOME/jenkins_home"
    
    # 复制 CasC 配置
    if [[ -f "$source_dir/jenkins.yaml" ]]; then
        sudo cp "$source_dir/jenkins.yaml" "$dest_configs/"
        log_info "复制 Jenkins CasC 配置"
    else
        log_warn "未找到 CasC 配置文件: $source_dir/jenkins.yaml"
    fi
    
    # 复制插件列表
    if [[ -f "$source_dir/plugins.txt" ]]; then
        sudo cp "$source_dir/plugins.txt" "$dest_home/"
        log_info "复制插件预安装列表"
    else
        log_warn "未找到插件列表: $source_dir/plugins.txt"
    fi
    
    # 设置文件权限
    sudo chown -R 1000:1000 "$dest_configs" "$dest_home"
    
    log_success "配置文件复制完成"
}

# =================================================================
# 服务管理
# =================================================================

start_jenkins() {
    log_info "启动 Jenkins 服务..."
    
    local env_file="$PROJECT_ROOT/compose/env/$ENVIRONMENT/.env"
    local compose_cmd
    compose_cmd=$(detect_docker_compose)
    
    cd "$PROJECT_ROOT"
    
    # 启动服务
    $compose_cmd \
        -f compose/base/docker-compose.yml \
        -f components/jenkins/override.yml \
        --env-file "$env_file" \
        up -d jenkins
    
    log_info "等待 Jenkins 启动..."
    
    # 等待服务就绪
    local max_wait=180
    local wait_time=0
    
    while [[ $wait_time -lt $max_wait ]]; do
        if curl -sf "http://localhost:$HTTP_PORT/login" >/dev/null 2>&1; then
            log_success "Jenkins 启动成功"
            return 0
        fi
        
        sleep 5
        wait_time=$((wait_time + 5))
        echo -n "."
    done
    
    echo
    log_error "Jenkins 启动超时"
    return 1
}

stop_jenkins() {
    log_info "停止 Jenkins 服务..."
    
    local env_file="$PROJECT_ROOT/compose/env/$ENVIRONMENT/.env"
    local compose_cmd
    compose_cmd=$(detect_docker_compose)
    
    cd "$PROJECT_ROOT"
    
    $compose_cmd \
        -f compose/base/docker-compose.yml \
        -f components/jenkins/override.yml \
        --env-file "$env_file" \
        down jenkins
    
    log_success "Jenkins 已停止"
}

restart_jenkins() {
    log_info "重启 Jenkins 服务..."
    
    local env_file="$PROJECT_ROOT/compose/env/$ENVIRONMENT/.env"
    local compose_cmd
    compose_cmd=$(detect_docker_compose)
    
    cd "$PROJECT_ROOT"
    
    $compose_cmd \
        -f compose/base/docker-compose.yml \
        -f components/jenkins/override.yml \
        --env-file "$env_file" \
        restart jenkins
    
    log_success "Jenkins 已重启"
}

check_status() {
    log_info "检查 Jenkins 状态..."
    
    # 检查容器状态
    if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "jenkins.*Up"; then
        log_success "✓ Jenkins 容器运行中"
        
        # 检查服务可访问性
        if curl -sf "http://localhost:$HTTP_PORT/login" >/dev/null 2>&1; then
            log_success "✓ Jenkins Web 界面可访问"
        else
            log_warn "△ Jenkins Web 界面无法访问"
        fi
        
        # 显示资源使用
        local stats
        stats=$(docker stats jenkins --no-stream --format "{{.CPUPerc}} {{.MemUsage}}" 2>/dev/null || echo "N/A")
        if [[ "$stats" != "N/A" ]]; then
            log_info "资源使用: CPU $stats"
        fi
        
        return 0
    else
        log_error "✗ Jenkins 容器未运行"
        return 1
    fi
}

show_logs() {
    log_info "显示 Jenkins 日志..."
    
    local env_file="$PROJECT_ROOT/compose/env/$ENVIRONMENT/.env"
    local compose_cmd
    compose_cmd=$(detect_docker_compose)
    
    cd "$PROJECT_ROOT"
    
    $compose_cmd \
        -f compose/base/docker-compose.yml \
        -f components/jenkins/override.yml \
        --env-file "$env_file" \
        logs -f jenkins
}

# =================================================================
# 信息显示
# =================================================================

show_access_info() {
    cat << EOF

🎉 Jenkins 安装完成！

📋 访问信息:
   Web 界面: http://localhost:$HTTP_PORT
   Agent 端口: localhost:$AGENT_PORT

🔐 管理员账户:
   用户名: admin
   密码: ${ADMIN_PASSWORD:-请查看环境配置文件}

🚀 功能特性:
   • Configuration as Code (CasC) 自动配置
   • 预装60+常用插件 (Git, Docker, Pipeline等)
   • Docker 集成支持 (可在流水线中使用 Docker)
   • 安全配置 (禁用匿名访问，默认管理员账户)
   • 日志集中管理

📖 使用建议:
   1. 首次登录后修改管理员密码
   2. 配置构建节点 (如需要)
   3. 创建第一个流水线作业
   4. 定期备份 Jenkins 配置

🔧 管理命令:
   查看状态: $0 --status
   查看日志: $0 --logs
   重启服务: $0 --restart
   停止服务: $0 --stop

EOF
}

# =================================================================
# 主程序
# =================================================================

main() {
    # 默认参数
    local ENVIRONMENT="$DEFAULT_ENV"
    local HTTP_PORT="$DEFAULT_HTTP_PORT"
    local AGENT_PORT="$DEFAULT_AGENT_PORT"
    local MEMORY="$DEFAULT_MEMORY"
    local DRY_RUN=false
    local CONFIG_ONLY=false
    local START_ONLY=false
    local ACTION=""
    
    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            --env)
                ENVIRONMENT="$2"
                shift 2
                ;;
            --port)
                HTTP_PORT="$2"
                shift 2
                ;;
            --memory)
                MEMORY="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --config-only)
                CONFIG_ONLY=true
                shift
                ;;
            --start-only)
                START_ONLY=true
                shift
                ;;
            --status)
                ACTION="status"
                shift
                ;;
            --logs)
                ACTION="logs"
                shift
                ;;
            --stop)
                ACTION="stop"
                shift
                ;;
            --restart)
                ACTION="restart"
                shift
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 设置 Agent 端口 (HTTP端口 + 41920)
    AGENT_PORT=$((HTTP_PORT + 41920))
    
    # 执行指定操作
    case "$ACTION" in
        status)
            check_status
            exit $?
            ;;
        logs)
            show_logs
            exit 0
            ;;
        stop)
            stop_jenkins
            exit 0
            ;;
        restart)
            restart_jenkins
            exit 0
            ;;
    esac
    
    # 预览模式
    if [[ "$DRY_RUN" == true ]]; then
        cat << EOF
🔍 预览模式 - 将执行以下操作:

环境配置:
  环境: $ENVIRONMENT
  HTTP端口: $HTTP_PORT  
  Agent端口: $AGENT_PORT
  内存限制: $MEMORY

操作步骤:
  1. 检查系统要求
  2. 创建目录结构: $JENKINS_HOME
EOF
        if [[ "$START_ONLY" != true ]]; then
            echo "  3. 生成环境配置文件"
            echo "  4. 复制 Jenkins 配置文件"
        fi
        if [[ "$CONFIG_ONLY" != true ]]; then
            echo "  5. 启动 Jenkins Docker 容器"
            echo "  6. 等待服务就绪"
        fi
        exit 0
    fi
    
    # 主安装流程
    log_info "开始 Jenkins 安装 (环境: $ENVIRONMENT, 端口: $HTTP_PORT)"
    
    check_requirements
    
    if [[ "$START_ONLY" != true ]]; then
        setup_directories
        generate_env_config
        copy_config_files
    fi
    
    if [[ "$CONFIG_ONLY" != true ]]; then
        if start_jenkins && check_status; then
            show_access_info
        else
            log_error "Jenkins 安装失败，请检查日志"
            exit 1
        fi
    else
        log_success "Jenkins 配置生成完成"
    fi
}

# 执行主程序
main "$@"