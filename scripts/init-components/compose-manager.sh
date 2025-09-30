#!/usr/bin/env bash
set -euo pipefail

# ================== 代理环境变量（如需禁用请注释） ==================
export http_proxy="http://127.0.0.1:7890"
export https_proxy="http://127.0.0.1:7890"
export all_proxy="socks5://127.0.0.1:7891"
# ======================================================================
# ==========================================
# 基础设施组件管理脚本
# 用于管理已安装基础设施服务的生命周期
# 配合 install-components.sh 使用
# ==========================================

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
COMPOSE_DIR="${REPO_ROOT}/compose"

# 默认环境
DEFAULT_ENV="dev"
ENVIRONMENT="${DEFAULT_ENV}"

# 确保基础设施就绪
ensure_infrastructure() {
    log_info "检查基础设施状态..."
    
    local infra_script="$SCRIPT_DIR/init-infrastructure.sh"
    
    # 检查基础设施脚本是否存在
    if [[ ! -f "$infra_script" ]]; then
        log_error "基础设施脚本不存在: $infra_script"
        return 1
    fi
    
    # 检查网络和卷是否已创建
    if ! docker network inspect infra-frontend infra-backend >/dev/null 2>&1 || \
       ! docker volume inspect infra_mysql_data infra_redis_data >/dev/null 2>&1; then
        
        log_warn "基础设施不完整，正在初始化..."
        
        if ! "$infra_script" create; then
            log_error "基础设施创建失败"
            return 1
        fi
        
        log_success "基础设施初始化完成"
    else
        log_success "基础设施已就绪"
    fi
}

# 基础设施组件
INFRA_COMPONENTS=(
    "core"      # 网络和卷
    "nginx"     # 网关
    "storage"   # 数据库和缓存
    "message"   # 消息队列
    "cicd"      # CI/CD
)

# 基础设施管理界面服务（可选）
MANAGEMENT_SERVICES=(
    "kafka-ui"
    "mongo-express"
    "redis-commander"
)

show_usage() {
    cat << EOF
用法: $0 [选项] <命令> [目标]

命令:
    infra <action> [component]  管理基础设施
    mgmt <action> [service]     管理基础设施管理界面
    status                      查看服务状态
    logs [service]              查看日志
    cleanup                     清理停止的容器

基础设施组件:
    core     - 核心网络和卷
    nginx    - 网关服务
    storage  - 存储服务 (mysql, redis, mongo)
    message  - 消息服务 (kafka)
    cicd     - CI/CD 服务 (jenkins)
    all      - 所有基础设施

管理界面服务:
    kafka-ui       - Kafka 管理界面
    mongo-express  - MongoDB 管理界面
    redis-commander - Redis 管理界面
    all            - 所有管理界面

动作:
    up       - 启动服务
    down     - 停止服务
    restart  - 重启服务
    pull     - 拉取镜像
    build    - 构建镜像

选项:
    -e, --env ENV       设置环境 (dev|staging|prod，默认: ${DEFAULT_ENV})
    -d, --detach        后台运行
    -f, --force         强制操作
    -v, --verbose       详细输出
    -h, --help          显示此帮助

示例:
    $0 infra up all                    # 启动所有基础设施
    $0 infra up storage               # 仅启动存储服务
    $0 mgmt up kafka-ui               # 启动 Kafka 管理界面
    $0 -e prod infra up all           # 生产环境启动基础设施
    $0 status                         # 查看所有服务状态
    $0 logs nginx                     # 查看 nginx 日志
EOF
}

# 检查 Docker Compose 命令
detect_compose_cmd() {
    if command -v "docker" >/dev/null && docker compose version >/dev/null 2>&1; then
        echo "docker compose"
    elif command -v "docker-compose" >/dev/null; then
        echo "docker-compose"
    else
        log_error "未找到 docker compose 或 docker-compose 命令"
        exit 1
    fi
}

COMPOSE_CMD=$(detect_compose_cmd)

# 构建基础设施 compose 文件参数
build_infra_compose_args() {
    local component="$1"
    local args=()
    
    case "$component" in
        "core")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.yml")
            ;;
        "nginx")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.yml")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.nginx.yml")
            ;;
        "storage")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.yml")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.storage.yml")
            ;;
        "message")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.yml")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.message.yml")
            ;;
        "cicd")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.yml")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.cicd.yml")
            ;;
        "all")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.yml")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.nginx.yml")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.storage.yml")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.message.yml")
            args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.cicd.yml")
            ;;
        *)
            log_error "未知的基础设施组件: $component"
            log_info "可用组件: ${INFRA_COMPONENTS[*]} all"
            return 1
            ;;
    esac
    
    # 添加环境配置
    if [[ -f "${COMPOSE_DIR}/env/${ENVIRONMENT}/.env" ]]; then
        args+=("--env-file" "${COMPOSE_DIR}/env/${ENVIRONMENT}/.env")
    fi
    
    if [[ -f "${COMPOSE_DIR}/env/${ENVIRONMENT}/override.yml" ]]; then
        args+=("-f" "${COMPOSE_DIR}/env/${ENVIRONMENT}/override.yml")
    fi
    
    printf '%s\n' "${args[@]}"
}

# 管理基础设施
manage_infra() {
    local action="$1"
    local component="${2:-all}"
    
    log_step "管理基础设施: $action $component (环境: $ENVIRONMENT)"
    
    # 检查基础设施状态
    if [[ "$action" == "up" && "$component" != "core" ]]; then
        ensure_infrastructure
    fi
    
    local compose_args
    if ! compose_args=$(build_infra_compose_args "$component"); then
        return 1
    fi
    
    # 转换为数组
    readarray -t compose_files <<< "$compose_args"
    
    case "$action" in
        "up")
            log_info "启动基础设施组件: $component"
            if [[ "$component" == "core" ]]; then
                # core 组件只创建网络和卷，不启动服务
                log_info "创建基础网络和数据卷..."
                $COMPOSE_CMD "${compose_files[@]}" config --volumes 2>/dev/null | while read -r volume; do
                    if [[ -n "$volume" ]]; then
                        docker volume create "$volume" 2>/dev/null || true
                    fi
                done
                $COMPOSE_CMD "${compose_files[@]}" config --services 2>/dev/null || true
                log_success "基础网络和卷创建完成"
            else
                $COMPOSE_CMD "${compose_files[@]}" up -d
            fi
            ;;
        "down")
            log_info "停止基础设施组件: $component"
            if [[ "$component" == "core" ]]; then
                # core 组件清理网络，但保留数据卷
                log_warn "清理网络 (保留数据卷)..."
                docker network rm infra-frontend infra-backend 2>/dev/null || true
                log_success "核心组件停止完成"
            else
                $COMPOSE_CMD "${compose_files[@]}" down
            fi
            ;;
        "restart")
            log_info "重启基础设施组件: $component"
            $COMPOSE_CMD "${compose_files[@]}" restart
            ;;
        "pull")
            log_info "拉取基础设施镜像: $component"
            $COMPOSE_CMD "${compose_files[@]}" pull
            ;;
        "build")
            log_info "构建基础设施镜像: $component"
            $COMPOSE_CMD "${compose_files[@]}" build
            ;;
        *)
            log_error "未知动作: $action"
            return 1
            ;;
    esac
}

# 管理基础设施管理界面
manage_management_ui() {
    local action="$1"
    local service="${2:-all}"
    
    log_step "管理基础设施管理界面: $action $service (环境: $ENVIRONMENT)"
    
    if [[ "$service" == "all" ]]; then
        for mgmt in "${MANAGEMENT_SERVICES[@]}"; do
            manage_single_management_ui "$action" "$mgmt"
        done
    else
        manage_single_management_ui "$action" "$service"
    fi
}

# 管理单个管理界面服务
manage_single_management_ui() {
    local action="$1"
    local service="$2"
    
    # 管理界面服务通常在 message.yml 中定义，使用 profiles 控制
    local compose_args=()
    compose_args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.yml")
    compose_args+=("-f" "${COMPOSE_DIR}/infra/docker-compose.message.yml")
    compose_args+=("--profile" "management")
    
    # 添加环境配置
    if [[ -f "${COMPOSE_DIR}/env/${ENVIRONMENT}/.env" ]]; then
        compose_args+=("--env-file" "${COMPOSE_DIR}/env/${ENVIRONMENT}/.env")
    fi
    
    case "$action" in
        "up")
            log_info "启动管理界面服务: $service"
            $COMPOSE_CMD "${compose_args[@]}" up -d "$service"
            ;;
        "down")
            log_info "停止管理界面服务: $service"
            $COMPOSE_CMD "${compose_args[@]}" stop "$service"
            ;;
        "restart")
            log_info "重启管理界面服务: $service"
            $COMPOSE_CMD "${compose_args[@]}" restart "$service"
            ;;
        *)
            log_error "管理界面服务不支持动作: $action"
            return 1
            ;;
    esac
}

# 查看服务状态
show_status() {
    log_step "服务状态概览"
    
    echo
    log_info "基础设施服务:"
    docker ps --filter "label=infra.service" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "无运行的基础设施服务"
    
    echo
    log_info "管理界面服务:"
    docker ps --filter "label=infra.category=management" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "无运行的管理界面服务"
    
    echo
    log_info "网络:"
    docker network ls --filter "name=infra-" --format "table {{.Name}}\t{{.Driver}}\t{{.Scope}}" 2>/dev/null || echo "无 infra 网络"
}

# 查看日志
show_logs() {
    local service="${1:-}"
    
    if [[ -z "$service" ]]; then
        log_info "查看所有服务日志 (最近 50 行)"
        docker logs --tail=50 $(docker ps -q) 2>/dev/null || log_warn "没有运行的容器"
    else
        log_info "查看 $service 服务日志"
        docker logs -f --tail=100 "$service" 2>/dev/null || log_error "服务 $service 不存在或未运行"
    fi
}

# 清理资源
cleanup() {
    log_step "清理停止的容器和未使用的网络"
    
    log_info "清理停止的容器..."
    docker container prune -f
    
    log_info "清理未使用的网络..."
    docker network prune -f
    
    log_info "清理未使用的卷..."
    docker volume prune -f
    
    log_success "清理完成"
}

# 解析命令行参数
main() {
    local detach=false
    local force=false
    local verbose=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -e|--env)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -d|--detach)
                detach=true
                shift
                ;;
            -f|--force)
                force=true
                shift
                ;;
            -v|--verbose)
                verbose=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            infra)
                if [[ $# -lt 2 ]]; then
                    log_error "infra 命令需要指定动作"
                    show_usage
                    exit 1
                fi
                manage_infra "$2" "${3:-all}"
                exit $?
                ;;
            mgmt)
                if [[ $# -lt 2 ]]; then
                    log_error "mgmt 命令需要指定动作"
                    show_usage
                    exit 1
                fi
                manage_management_ui "$2" "${3:-all}"
                exit $?
                ;;
            status)
                show_status
                exit 0
                ;;
            logs)
                show_logs "${2:-}"
                exit 0
                ;;
            cleanup)
                cleanup
                exit 0
                ;;
            *)
                log_error "未知命令: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # 如果没有提供命令，显示帮助
    show_usage
    exit 1
}

main "$@"