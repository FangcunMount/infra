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
COMPONENTS_DIR="${REPO_ROOT}/components"
ENV_DIR="${REPO_ROOT}/compose/env"
INIT_TARGET="${INIT_TARGET:-common}"  # common|serverA|serverB

# 默认环境
DEFAULT_ENV="dev"
ORIGINAL_ENVIRONMENT="${ENVIRONMENT:-}"
ENVIRONMENT="${DEFAULT_ENV}"

# 允许通过外部环境变量覆盖默认环境（与 Makefile 保持一致）
if [[ -n "${INFRA_ENV_TYPE:-}" ]]; then
    ENVIRONMENT="${INFRA_ENV_TYPE}"
elif [[ -n "${INFRA_ENV:-}" ]]; then
    ENVIRONMENT="${INFRA_ENV}"
elif [[ -n "$ORIGINAL_ENVIRONMENT" ]]; then
    ENVIRONMENT="$ORIGINAL_ENVIRONMENT"
elif [[ -n "${ENV:-}" ]]; then
    ENVIRONMENT="${ENV}"
fi

# 根据环境确定配置文件路径
# - prod 环境: 使用 serverA.env（默认）或 serverB.env
# - 其他环境: 使用 .env
get_env_file() {
    local server="${1:-A}"
    if [[ "$ENVIRONMENT" == "prod" ]]; then
        local server_upper="${server^^}"
        echo "${ENV_DIR}/prod/server${server_upper}.env"
    else
        echo "${ENV_DIR}/${ENVIRONMENT}/.env"
    fi
}

ENV_FILE="$(get_env_file)"

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
    local network_missing=true
    if docker network inspect infra-network >/dev/null 2>&1; then
        network_missing=false
    fi

    # 使用 init 脚本实际创建的卷名
    local volume_missing=false
    local required_volumes=()
    case "${INIT_TARGET}" in
        serverA)
            required_volumes=(
                infra_redis_cache
                infra_mongo_data
                infra_mongo_config
                infra_nginx_logs
            )
            ;;
        serverB)
            required_volumes=(
                infra_nsq_data
            )
            ;;
        *)
            required_volumes=(
                infra_redis_cache
                infra_mongo_data
                infra_mongo_config
                infra_nginx_logs
                infra_nsq_data
            )
            ;;
    esac
    for vol in "${required_volumes[@]}"; do
        if ! docker volume inspect "$vol" >/dev/null 2>&1; then
            volume_missing=true
            break
        fi
    done

    local is_manager=false
    if docker info 2>/dev/null | grep -q "Is Manager: true"; then
        is_manager=true
    fi

    if [[ "$network_missing" == true || "$volume_missing" == true ]]; then
        log_warn "基础设施不完整，正在初始化..."
        if [[ "$is_manager" == true ]]; then
            if ! "$infra_script" create; then
                log_error "基础设施创建失败"
                return 1
            fi
            log_success "基础设施初始化完成"
        else
            if [[ "$network_missing" == true ]]; then
                log_error "当前节点不是 Swarm Manager，且缺少 infra-network。请在 Manager 节点执行 make init 或 ${infra_script} create 后重试。"
                return 1
            else
                log_warn "当前节点不是 Swarm Manager，检测到部分卷缺失，跳过自动创建"
            fi
        fi
    else
        log_success "基础设施已就绪"
    fi
}

# 确保 Redis ACL 文件在启动前存在
ensure_redis_acl() {
    local redis_dir="${COMPONENTS_DIR}/redis"
    local acl_file="${redis_dir}/users.acl"
    local acl_script="${redis_dir}/generate-acl.sh"
    local env_file="$ENV_FILE"

    if [[ ! -d "$redis_dir" ]]; then
        log_warn "Redis 组件目录不存在，跳过 ACL 文件生成"
        return 0
    fi

    if [[ -d "$acl_file" ]]; then
        log_warn "检测到 users.acl 是目录（Docker 可能提前创建），正在删除..."
        rm -rf "$acl_file"
    fi

    if [[ ! -f "$acl_file" ]]; then
        touch "$acl_file"
        log_info "已创建空的 Redis ACL 文件"
    fi

    if [[ ! -f "$env_file" ]]; then
        log_warn "环境配置文件不存在: $env_file，无法生成 Redis ACL"
        log_warn "请先运行 make env-init 或指定正确的环境"
        return 0
    fi

    if [[ -f "$acl_script" ]]; then
        log_info "正在根据 ${ENVIRONMENT} 环境生成 Redis ACL 配置..."
        bash "$acl_script" "$env_file"
        log_success "Redis ACL 配置已生成"
    else
        log_warn "未找到 Redis ACL 生成脚本: $acl_script"
    fi
}

# 基础设施组件
INFRA_COMPONENTS=(
    "core"      # 网络和卷
    "nginx"     # 网关
    "storage"   # 数据库和缓存
    "nsq"       # 消息队列 (NSQ)
    "cicd"      # CI/CD
)

# 基础设施管理界面服务（可选）
MANAGEMENT_SERVICES=(
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
    nsq      - 消息服务 (nsq)
    cicd     - CI/CD 服务 (jenkins)
    all      - 所有基础设施

管理界面服务:
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
    $0 mgmt up mongo-express          # 启动 MongoDB 管理界面
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
            args+=("-f" "${COMPONENTS_DIR}/networks/docker-compose.yml")
            ;;
        "nginx")
            args+=("-f" "${COMPONENTS_DIR}/networks/docker-compose.yml")
            args+=("-f" "${COMPONENTS_DIR}/nginx/docker-compose.yml")
            ;;
        "storage")
            args+=("-f" "${COMPONENTS_DIR}/networks/docker-compose.yml")
            args+=("-f" "${COMPONENTS_DIR}/mysql/docker-compose.yml")
            args+=("-f" "${COMPONENTS_DIR}/redis/docker-compose.yml")
            args+=("-f" "${COMPONENTS_DIR}/mongo/docker-compose.yml")
            ;;
        "nsq")
            args+=("-f" "${COMPONENTS_DIR}/networks/docker-compose.yml")
            args+=("-f" "${COMPONENTS_DIR}/nsq/docker-compose.yml")
            ;;
        "cicd")
            args+=("-f" "${COMPONENTS_DIR}/networks/docker-compose.yml")
            args+=("-f" "${COMPONENTS_DIR}/jenkins/docker-compose.yml")
            ;;
        "all")
            args+=("-f" "${COMPONENTS_DIR}/networks/docker-compose.yml")
            args+=("-f" "${COMPONENTS_DIR}/nginx/docker-compose.yml")
            args+=("-f" "${COMPONENTS_DIR}/mysql/docker-compose.yml")
            args+=("-f" "${COMPONENTS_DIR}/redis/docker-compose.yml")
            args+=("-f" "${COMPONENTS_DIR}/mongo/docker-compose.yml")
            args+=("-f" "${COMPONENTS_DIR}/nsq/docker-compose.yml")
            args+=("-f" "${COMPONENTS_DIR}/jenkins/docker-compose.yml")
            ;;
        *)
            log_error "未知的基础设施组件: $component"
            log_info "可用组件: ${INFRA_COMPONENTS[*]} all"
            return 1
            ;;
    esac
    
    # 添加环境配置
    if [[ -f "$ENV_FILE" ]]; then
        args+=("--env-file" "$ENV_FILE")
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
    local redis_compose_file="${COMPONENTS_DIR}/redis/docker-compose.yml"
    local includes_redis=false
    for element in "${compose_files[@]}"; do
        if [[ "$element" == "$redis_compose_file" ]]; then
            includes_redis=true
            break
        fi
    done
    
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
                if [[ "$includes_redis" == true ]]; then
                    ensure_redis_acl
                fi
                $COMPOSE_CMD "${compose_files[@]}" up -d
            fi
            ;;
        "down")
            log_info "停止基础设施组件: $component"
            if [[ "$component" == "core" ]]; then
                # core 组件清理网络，但保留数据卷
                log_warn "清理网络 (保留数据卷)..."
                docker network rm infra-network 2>/dev/null || true
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
            # 自动拼接代理参数
            $COMPOSE_CMD "${compose_files[@]}" build \
                --build-arg http_proxy="$http_proxy" \
                --build-arg https_proxy="$https_proxy"
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
    
    # 管理界面服务定义在各自组件的 docker-compose.yml 中，使用 profiles 控制
    local compose_args=()
    compose_args+=("-f" "${COMPONENTS_DIR}/networks/docker-compose.yml")
    compose_args+=("-f" "${COMPONENTS_DIR}/mongo/docker-compose.yml")
    compose_args+=("-f" "${COMPONENTS_DIR}/redis/docker-compose.yml")
    compose_args+=("--profile" "management")
    
    # 添加环境配置
    if [[ -f "$ENV_FILE" ]]; then
        compose_args+=("--env-file" "$ENV_FILE")
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
