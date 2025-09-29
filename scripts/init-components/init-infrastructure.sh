#!/usr/bin/env bash
set -euo pipefail

# ==========================================
# 基础设施网络和卷初始化脚本
# 用于创建 Docker 网络和数据卷
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

# 脚本目录和项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# 环境变量配置
INFRA_DATA_ROOT="${INFRA_DATA_ROOT:-/data/infra}"
INFRA_FRONTEND_SUBNET="${INFRA_FRONTEND_SUBNET:-172.19.0.0/16}"
INFRA_FRONTEND_GATEWAY="${INFRA_FRONTEND_GATEWAY:-172.19.0.1}"
INFRA_BACKEND_SUBNET="${INFRA_BACKEND_SUBNET:-172.20.0.0/16}"
INFRA_BACKEND_GATEWAY="${INFRA_BACKEND_GATEWAY:-172.20.0.1}"
INFRA_NETWORK_MTU="${INFRA_NETWORK_MTU:-1500}"

# 用户配置
INFRA_USER="${INFRA_USER:-$USER}"
INFRA_GROUP="${INFRA_GROUP:-docker}"

# 验证配置
validate_config() {
    log_step "验证配置参数..."
    
    # 检查 Docker 是否运行
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker 未运行，请先启动 Docker 服务"
        return 1
    fi
    
    # 检查网络子网是否冲突
    if docker network ls --format '{{.Name}}' | grep -E '^(infra-frontend|infra-backend)$' >/dev/null; then
        log_warn "检测到已存在的 infra 网络，将跳过已存在的网络创建"
    fi
    
    # 验证子网格式
    if ! echo "${INFRA_FRONTEND_SUBNET}" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$'; then
        log_error "前端子网格式无效: ${INFRA_FRONTEND_SUBNET}"
        return 1
    fi
    
    if ! echo "${INFRA_BACKEND_SUBNET}" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$'; then
        log_error "后端子网格式无效: ${INFRA_BACKEND_SUBNET}"
        return 1
    fi
    
    # 显示当前配置
    log_info "当前配置:"
    echo "  数据根目录: ${INFRA_DATA_ROOT}"
    echo "  前端网络: ${INFRA_FRONTEND_SUBNET} (网关: ${INFRA_FRONTEND_GATEWAY})"
    echo "  后端网络: ${INFRA_BACKEND_SUBNET} (网关: ${INFRA_BACKEND_GATEWAY})"
    echo "  网络MTU: ${INFRA_NETWORK_MTU}"
    echo "  用户:组: ${INFRA_USER}:${INFRA_GROUP}"
    
    return 0
}

show_help() {
    cat << EOF
基础设施网络和卷初始化脚本

用法:
  $0 [选项] <操作>

操作:
  create     创建网络和数据卷
  remove     删除网络和数据卷  
  status     查看网络和卷状态
  reset      重置（删除后重新创建）

选项:
  --dry-run  仅显示命令，不实际执行
  --help     显示帮助信息

示例:
  $0 create              # 创建网络和卷
  $0 status              # 查看状态
  $0 reset               # 重置所有
  $0 --dry-run create    # 预览创建命令

环境变量:
  INFRA_DATA_ROOT        数据根目录 (默认: /data/infra)
  INFRA_FRONTEND_SUBNET  前端网络子网 (默认: 172.19.0.0/16)
  INFRA_BACKEND_SUBNET   后端网络子网 (默认: 172.20.0.0/16)
  INFRA_NETWORK_MTU      网络MTU大小 (默认: 1500)
  INFRA_USER             数据目录所有者 (默认: $USER)
  INFRA_GROUP            数据目录组 (默认: docker)
EOF
}

# 创建 Docker 网络
create_networks() {
    local dry_run=${1:-false}
    
    log_step "创建 Docker 网络..."
    
    # 前端网络（对外服务）
    local frontend_cmd="docker network create \\
  --driver bridge \\
  --subnet=${INFRA_FRONTEND_SUBNET} \\
  --gateway=${INFRA_FRONTEND_GATEWAY} \\
  --opt com.docker.network.bridge.name=infra-frontend \\
  --opt com.docker.network.bridge.enable_icc=false \\
  --opt com.docker.network.bridge.enable_ip_masquerade=true \\
  --opt com.docker.network.driver.mtu=${INFRA_NETWORK_MTU} \\
  --label 'network.zone=public' \\
  --label 'network.access=external' \\
  infra-frontend"
  
    # 后端网络（内部服务）
    local backend_cmd="docker network create \\
  --driver bridge \\
  --subnet=${INFRA_BACKEND_SUBNET} \\
  --gateway=${INFRA_BACKEND_GATEWAY} \\
  --opt com.docker.network.bridge.name=infra-backend \\
  --opt com.docker.network.bridge.enable_icc=true \\
  --opt com.docker.network.driver.mtu=${INFRA_NETWORK_MTU} \\
  --label 'network.zone=private' \\
  --label 'network.access=internal' \\
  infra-backend"
  
    if [[ "$dry_run" == "true" ]]; then
        echo "# 前端网络创建命令:"
        echo "$frontend_cmd"
        echo
        echo "# 后端网络创建命令:"
        echo "$backend_cmd"
        return 0
    fi
    
    # 检查网络是否已存在
    if docker network inspect infra-frontend >/dev/null 2>&1; then
        log_warn "前端网络 infra-frontend 已存在"
    else
        log_info "创建前端网络 infra-frontend..."
        eval "$frontend_cmd" || log_error "前端网络创建失败"
    fi
    
    if docker network inspect infra-backend >/dev/null 2>&1; then
        log_warn "后端网络 infra-backend 已存在"
    else
        log_info "创建后端网络 infra-backend..."
        eval "$backend_cmd" || log_error "后端网络创建失败"
    fi
}

# 创建数据卷
create_volumes() {
    local dry_run=${1:-false}
    
    log_step "创建数据持久化卷..."
    
    local volumes=(
        "infra_mysql_data:${INFRA_DATA_ROOT}/mysql/data"
        "infra_redis_data:${INFRA_DATA_ROOT}/redis/data"
        "infra_mongo_data:${INFRA_DATA_ROOT}/mongo/data"
        "infra_kafka_data:${INFRA_DATA_ROOT}/kafka/data"
        "infra_jenkins_data:${INFRA_DATA_ROOT}/jenkins/data"
        "infra_nginx_logs:${INFRA_DATA_ROOT}/nginx/logs"
        "infra_app_logs:${INFRA_DATA_ROOT}/logs"
    )
    
    # 创建数据目录
    if [[ "$dry_run" != "true" ]]; then
        log_info "创建数据目录: ${INFRA_DATA_ROOT}"
        sudo mkdir -p "${INFRA_DATA_ROOT}"/{mysql,redis,mongo,kafka,jenkins,nginx,logs}/{data,conf,logs} 2>/dev/null || true
        
        # 设置目录所有权，优先尝试 docker 组
        if getent group docker >/dev/null 2>&1; then
            sudo chown -R "${INFRA_USER}:${INFRA_GROUP}" "${INFRA_DATA_ROOT}" 2>/dev/null || \
            sudo chown -R "${INFRA_USER}:${INFRA_USER}" "${INFRA_DATA_ROOT}"
        else
            sudo chown -R "${INFRA_USER}:${INFRA_USER}" "${INFRA_DATA_ROOT}"
        fi
        
        sudo chmod -R 755 "${INFRA_DATA_ROOT}"
        log_success "数据目录创建完成: ${INFRA_DATA_ROOT}"
    fi
    
    for volume_def in "${volumes[@]}"; do
        local volume_name="${volume_def%%:*}"
        local mount_path="${volume_def##*:}"
        
        local volume_cmd="docker volume create \\
  --driver local \\
  --opt type=none \\
  --opt o=bind \\
  --opt device=${mount_path} \\
  ${volume_name}"
        
        if [[ "$dry_run" == "true" ]]; then
            echo "# 卷创建命令: $volume_name"
            echo "$volume_cmd"
            echo
            continue
        fi
        
        if docker volume inspect "$volume_name" >/dev/null 2>&1; then
            log_warn "数据卷 $volume_name 已存在"
        else
            log_info "创建数据卷: $volume_name -> $mount_path"
            # 确保挂载点目录存在
            sudo mkdir -p "$mount_path"
            eval "$volume_cmd" || log_warn "数据卷 $volume_name 创建失败，将使用 Docker 管理的卷"
        fi
    done
}

# 删除网络和卷
remove_infrastructure() {
    local dry_run=${1:-false}
    
    log_step "删除基础设施网络和卷..."
    
    local networks=("infra-frontend" "infra-backend")
    local volumes=("infra_mysql_data" "infra_redis_data" "infra_mongo_data" "infra_kafka_data" "infra_jenkins_data" "infra_nginx_logs" "infra_app_logs")
    
    if [[ "$dry_run" == "true" ]]; then
        echo "# 删除网络命令:"
        for network in "${networks[@]}"; do
            echo "docker network rm $network"
        done
        echo
        echo "# 删除卷命令:"
        for volume in "${volumes[@]}"; do
            echo "docker volume rm $volume"
        done
        return 0
    fi
    
    # 删除网络
    for network in "${networks[@]}"; do
        if docker network inspect "$network" >/dev/null 2>&1; then
            log_info "删除网络: $network"
            docker network rm "$network" || log_warn "网络 $network 删除失败"
        else
            log_info "网络 $network 不存在"
        fi
    done
    
    # 删除卷（谨慎操作）
    echo
    read -p "⚠️  确认删除所有数据卷？这将清除所有持久化数据！(y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        for volume in "${volumes[@]}"; do
            if docker volume inspect "$volume" >/dev/null 2>&1; then
                log_warn "删除数据卷: $volume"
                docker volume rm "$volume" || log_warn "数据卷 $volume 删除失败"
            else
                log_info "数据卷 $volume 不存在"
            fi
        done
    else
        log_info "取消删除数据卷操作"
    fi
}

# 查看状态
show_status() {
    log_step "基础设施网络和卷状态"
    
    echo
    log_info "🌐 Docker 网络:"
    if docker network ls --filter "name=infra-" --format "table {{.Name}}\t{{.Driver}}\t{{.Scope}}" | grep -q infra-; then
        docker network ls --filter "name=infra-" --format "table {{.Name}}\t{{.Driver}}\t{{.Scope}}"
    else
        echo "  ❌ 未找到 infra 相关网络"
    fi
    
    echo
    log_info "💾 数据卷:"
    if docker volume ls --filter "name=infra_" --format "table {{.Name}}\t{{.Driver}}\t{{.Mountpoint}}" | grep -q infra_; then
        docker volume ls --filter "name=infra_" --format "table {{.Name}}\t{{.Driver}}\t{{.Mountpoint}}"
    else
        echo "  ❌ 未找到 infra 相关数据卷"
    fi
    
    echo
    log_info "📁 数据目录: ${INFRA_DATA_ROOT}"
    if [[ -d "${INFRA_DATA_ROOT}" ]]; then
        du -sh "${INFRA_DATA_ROOT}"/* 2>/dev/null | head -10 || echo "  (目录为空)"
    else
        echo "  ❌ 数据目录 ${INFRA_DATA_ROOT} 不存在"
    fi
}

# 验证网络连通性
test_networks() {
    log_step "测试网络连通性..."
    
    # 测试前端网络
    if docker network inspect infra-frontend >/dev/null 2>&1; then
        log_info "测试前端网络连通性..."
        docker run --rm --network infra-frontend alpine ping -c 2 172.19.0.1 >/dev/null 2>&1 && \
            log_success "前端网络连通性正常" || log_warn "前端网络连通性异常"
    fi
    
    # 测试后端网络
    if docker network inspect infra-backend >/dev/null 2>&1; then
        log_info "测试后端网络连通性..."
        docker run --rm --network infra-backend alpine ping -c 2 172.20.0.1 >/dev/null 2>&1 && \
            log_success "后端网络连通性正常" || log_warn "后端网络连通性异常"
    fi
}

# 主函数
main() {
    local dry_run=false
    local operation=""
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                dry_run=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            create|remove|status|reset|test)
                operation="$1"
                shift
                ;;
            *)
                log_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    if [[ -z "$operation" ]]; then
        log_error "请指定操作: create|remove|status|reset|test"
        show_help
        exit 1
    fi
    
    # 对于需要 Docker 的操作，验证配置
    if [[ "$operation" != "status" ]] && [[ "$dry_run" != "true" ]]; then
        if ! validate_config; then
            exit 1
        fi
        echo
    fi
    
    case "$operation" in
        create)
            create_networks "$dry_run"
            create_volumes "$dry_run"
            if [[ "$dry_run" != "true" ]]; then
                log_success "基础设施网络和卷创建完成！"
                echo
                show_status
            fi
            ;;
        remove)
            remove_infrastructure "$dry_run"
            ;;
        status)
            show_status
            ;;
        test)
            test_networks
            ;;
        reset)
            log_warn "重置操作：先删除再重新创建"
            remove_infrastructure "$dry_run"
            if [[ "$dry_run" != "true" ]]; then
                echo
                log_info "等待 2 秒后重新创建..."
                sleep 2
                create_networks "$dry_run"
                create_volumes "$dry_run"
                log_success "基础设施重置完成！"
            fi
            ;;
    esac
}

main "$@"