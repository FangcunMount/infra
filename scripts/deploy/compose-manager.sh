#!/usr/bin/env bash
set -euo pipefail

# ==========================================
# 分层 Docker Compose 管理脚本
# 用于管理基础设施和应用服务的部署
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
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_DIR="${REPO_ROOT}/compose"

# 默认环境
DEFAULT_ENV="dev"
ENVIRONMENT="${DEFAULT_ENV}"

# 基础设施组件
INFRA_COMPONENTS=(
    "core"      # 网络和卷
    "nginx"     # 网关
    "storage"   # 数据库和缓存
    "message"   # 消息队列
    "cicd"      # CI/CD
)

# 应用服务
APP_SERVICES=(
    "miniblog"
    "qs-api"
    "qs-collection"
    "qs-evaluation"
)

show_usage() {
    cat << EOF
用法: $0 [选项] <命令> [目标]

命令:
    infra <action> [component]  管理基础设施
    app <action> [service]      管理应用服务
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

应用服务:
    miniblog       - 博客应用
    qs-api         - QS API 服务
    qs-collection  - QS 采集服务
    qs-evaluation  - QS 评估服务
    all            - 所有应用

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
    $0 app up miniblog                # 启动博客应用
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
    
    local compose_args
    if ! compose_args=$(build_infra_compose_args "$component"); then
        return 1
    fi
    
    # 转换为数组
    readarray -t compose_files <<< "$compose_args"
    
    case "$action" in
        "up")
            log_info "启动基础设施组件: $component"
            $COMPOSE_CMD "${compose_files[@]}" up -d
            ;;
        "down")
            log_info "停止基础设施组件: $component"
            $COMPOSE_CMD "${compose_files[@]}" down
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

# 管理应用服务
manage_app() {
    local action="$1"
    local service="${2:-all}"
    
    log_step "管理应用服务: $action $service (环境: $ENVIRONMENT)"
    
    if [[ "$service" == "all" ]]; then
        for app in "${APP_SERVICES[@]}"; do
            manage_single_app "$action" "$app"
        done
    else
        manage_single_app "$action" "$service"
    fi
}

# 管理单个应用
manage_single_app() {
    local action="$1"
    local service="$2"
    
    local app_compose="${COMPOSE_DIR}/apps/${service}/docker-compose.yml"
    
    if [[ ! -f "$app_compose" ]]; then
        log_error "应用服务 $service 的 compose 文件不存在: $app_compose"
        return 1
    fi
    
    local compose_args=("-f" "$app_compose")
    
    # 添加环境配置
    if [[ -f "${COMPOSE_DIR}/env/${ENVIRONMENT}/.env" ]]; then
        compose_args+=("--env-file" "${COMPOSE_DIR}/env/${ENVIRONMENT}/.env")
    fi
    
    case "$action" in
        "up")
            log_info "启动应用服务: $service"
            $COMPOSE_CMD "${compose_args[@]}" up -d
            ;;
        "down")
            log_info "停止应用服务: $service"
            $COMPOSE_CMD "${compose_args[@]}" down
            ;;
        "restart")
            log_info "重启应用服务: $service"
            $COMPOSE_CMD "${compose_args[@]}" restart
            ;;
        "pull")
            log_info "拉取应用镜像: $service"
            $COMPOSE_CMD "${compose_args[@]}" pull
            ;;
        "build")
            log_info "构建应用镜像: $service"
            $COMPOSE_CMD "${compose_args[@]}" build
            ;;
        *)
            log_error "未知动作: $action"
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
    log_info "应用服务:"
    docker ps --filter "label=app.name" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "无运行的应用服务"
    
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
            app)
                if [[ $# -lt 2 ]]; then
                    log_error "app 命令需要指定动作"
                    show_usage
                    exit 1
                fi
                manage_app "$2" "${3:-all}"
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