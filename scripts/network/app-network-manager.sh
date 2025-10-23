#!/bin/bash

# 业务网络管理脚本
# 用于创建、删除和管理业务应用的 Docker 网络

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 日志函数
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

# 显示帮助信息
show_help() {
    cat << EOF
${GREEN}业务网络管理工具${NC}

${BLUE}用途:${NC}
    为业务应用创建独立的 Docker 网络,支持 bridge 和 overlay 两种模式

${BLUE}用法:${NC}
    $0 <命令> [参数]

${BLUE}命令:${NC}
    ${CYAN}create${NC}      创建业务网络
    ${CYAN}delete${NC}      删除业务网络
    ${CYAN}list${NC}        列出所有业务网络
    ${CYAN}inspect${NC}     查看网络详情
    ${CYAN}connect${NC}     将容器连接到网络
    ${CYAN}disconnect${NC}  断开容器与网络的连接
    ${CYAN}help${NC}        显示此帮助信息

${BLUE}创建网络参数:${NC}
    --name NAME         网络名称 (必需,建议格式: <app>-network)
    --driver DRIVER     网络驱动 (bridge/overlay,默认: bridge)
    --subnet SUBNET     子网地址 (可选,如: 172.21.0.0/16)
    --gateway GATEWAY   网关地址 (可选,如: 172.21.0.1)
    --internal          内部网络,不允许外网访问 (可选)
    --attachable        允许手动连接容器 (overlay 模式推荐)
    --encrypted         启用加密 (overlay 模式可选,影响性能)

${BLUE}示例:${NC}
    # 创建 bridge 网络 (单机部署)
    $0 create --name miniblog-network --driver bridge

    # 创建 bridge 网络并指定子网
    $0 create --name miniblog-network --driver bridge --subnet 172.21.0.0/16

    # 创建 overlay 网络 (跨主机部署)
    $0 create --name miniblog-network --driver overlay --attachable

    # 创建内部网络 (不允许外网访问)
    $0 create --name private-network --driver bridge --internal

    # 删除网络
    $0 delete --name miniblog-network

    # 列出所有业务网络
    $0 list

    # 查看网络详情
    $0 inspect --name miniblog-network

    # 将容器连接到网络
    $0 connect --name miniblog-network --container miniblog-app

    # 断开容器连接
    $0 disconnect --name miniblog-network --container miniblog-app

${BLUE}推荐配置:${NC}
    ${CYAN}单机部署:${NC}
        $0 create --name <app>-network --driver bridge

    ${CYAN}跨主机部署:${NC}
        $0 create --name <app>-network --driver overlay --attachable

    ${CYAN}隔离网络:${NC}
        $0 create --name <app>-network --driver bridge --internal

${BLUE}注意事项:${NC}
    - overlay 网络需要先初始化 Docker Swarm
    - 建议网络名称格式: <应用名>-network (如 miniblog-network)
    - 子网不要与 infra-network (172.20.0.0/16) 冲突
    - 推荐子网范围: 172.21.0.0/16, 172.22.0.0/16, ...
    - 业务网络通过 external 方式加入 infra-network 访问基础设施

EOF
}

# 检查 Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        error "Docker 未安装"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        error "Docker 服务未运行"
        exit 1
    fi
}

# 检查网络名称格式
validate_network_name() {
    local name="$1"
    
    if [[ ! "$name" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
        error "网络名称格式不正确"
        echo "  格式要求: 小写字母、数字、下划线、连字符,且以字母或数字开头"
        echo "  推荐格式: <app>-network (如 miniblog-network)"
        return 1
    fi
    
    if [[ ! "$name" =~ -network$ ]]; then
        warn "建议网络名称以 '-network' 结尾,如: ${name}-network"
    fi
    
    return 0
}

# 检查 Swarm 模式
check_swarm_mode() {
    if docker info 2>/dev/null | grep -q "Swarm: active"; then
        return 0
    else
        return 1
    fi
}

# 创建网络
create_network() {
    local network_name=""
    local driver="bridge"
    local subnet=""
    local gateway=""
    local internal="false"
    local attachable="false"
    local encrypted="false"
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --name)
                network_name="$2"
                shift 2
                ;;
            --driver)
                driver="$2"
                shift 2
                ;;
            --subnet)
                subnet="$2"
                shift 2
                ;;
            --gateway)
                gateway="$2"
                shift 2
                ;;
            --internal)
                internal="true"
                shift
                ;;
            --attachable)
                attachable="true"
                shift
                ;;
            --encrypted)
                encrypted="true"
                shift
                ;;
            *)
                error "未知参数: $1"
                return 1
                ;;
        esac
    done
    
    # 验证必需参数
    if [[ -z "$network_name" ]]; then
        error "缺少网络名称"
        echo "使用方式: $0 create --name <网络名称> [选项]"
        return 1
    fi
    
    # 验证网络名称
    validate_network_name "$network_name" || return 1
    
    # 验证驱动类型
    if [[ "$driver" != "bridge" && "$driver" != "overlay" ]]; then
        error "不支持的网络驱动: $driver"
        echo "支持的驱动: bridge, overlay"
        return 1
    fi
    
    # 检查网络是否已存在
    if docker network ls --format '{{.Name}}' | grep -q "^${network_name}$"; then
        warn "网络 ${network_name} 已存在"
        docker network inspect "$network_name" | grep -E "Name|Driver|Scope|Subnet"
        return 0
    fi
    
    # overlay 模式检查
    if [[ "$driver" == "overlay" ]]; then
        if ! check_swarm_mode; then
            error "overlay 网络需要 Docker Swarm 模式"
            echo ""
            info "请先初始化 Swarm:"
            echo "  sudo ./scripts/network/swarm-manager.sh init-manager"
            return 1
        fi
    fi
    
    log "创建网络: $network_name"
    echo "  驱动: $driver"
    [[ -n "$subnet" ]] && echo "  子网: $subnet"
    [[ -n "$gateway" ]] && echo "  网关: $gateway"
    [[ "$internal" == "true" ]] && echo "  内部网络: 是"
    [[ "$attachable" == "true" ]] && echo "  可附加: 是"
    [[ "$encrypted" == "true" ]] && echo "  加密: 是"
    echo
    
    # 构建 docker network create 命令
    local cmd="docker network create"
    cmd+=" --driver $driver"
    
    # 添加 IPAM 配置
    if [[ -n "$subnet" ]]; then
        cmd+=" --subnet $subnet"
    fi
    
    if [[ -n "$gateway" ]]; then
        cmd+=" --gateway $gateway"
    fi
    
    # 添加选项
    if [[ "$internal" == "true" ]]; then
        cmd+=" --internal"
    fi
    
    if [[ "$attachable" == "true" ]]; then
        cmd+=" --attachable"
    fi
    
    # overlay 特定选项
    if [[ "$driver" == "overlay" ]]; then
        cmd+=" --opt com.docker.network.driver.mtu=1450"
        if [[ "$encrypted" == "true" ]]; then
            cmd+=" --opt encrypted=true"
        fi
    fi
    
    # bridge 特定选项
    if [[ "$driver" == "bridge" ]]; then
        cmd+=" --opt com.docker.network.bridge.name=${network_name}"
        cmd+=" --opt com.docker.network.bridge.enable_icc=true"
    fi
    
    # 添加标签
    cmd+=" --label app.network=true"
    cmd+=" --label app.network.type=$driver"
    cmd+=" --label app.network.name=$network_name"
    
    # 添加网络名称
    cmd+=" $network_name"
    
    # 执行命令
    if eval "$cmd"; then
        success "网络 $network_name 创建成功!"
        echo
        docker network inspect "$network_name" | grep -E "Name|Driver|Scope|Subnet|Gateway|Internal"
        echo
        info "业务应用 docker-compose.yml 配置示例:"
        cat << YAML
---
networks:
  ${network_name}:
    external: true
    name: ${network_name}
  infra-network:
    external: true
    name: infra-network

services:
  app:
    image: your-app:latest
    networks:
      - ${network_name}    # 业务自己的网络
      - infra-network      # 访问基础设施服务
YAML
    else
        error "网络创建失败"
        return 1
    fi
}

# 删除网络
delete_network() {
    local network_name=""
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --name)
                network_name="$2"
                shift 2
                ;;
            *)
                error "未知参数: $1"
                return 1
                ;;
        esac
    done
    
    if [[ -z "$network_name" ]]; then
        error "缺少网络名称"
        echo "使用方式: $0 delete --name <网络名称>"
        return 1
    fi
    
    # 检查网络是否存在
    if ! docker network ls --format '{{.Name}}' | grep -q "^${network_name}$"; then
        warn "网络 ${network_name} 不存在"
        return 0
    fi
    
    # 检查是否有容器使用
    local containers=$(docker network inspect "$network_name" --format '{{range .Containers}}{{.Name}} {{end}}')
    if [[ -n "$containers" ]]; then
        warn "以下容器正在使用网络 ${network_name}:"
        echo "$containers"
        echo
        read -p "是否强制删除? (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            info "操作已取消"
            return 0
        fi
    fi
    
    log "删除网络: $network_name"
    
    if docker network rm "$network_name" 2>&1; then
        success "网络 $network_name 已删除"
    else
        error "网络删除失败"
        return 1
    fi
}

# 列出网络
list_networks() {
    log "业务网络列表:"
    echo
    
    # 列出所有带 app.network=true 标签的网络
    local app_networks=$(docker network ls --filter "label=app.network=true" --format "{{.Name}}")
    
    if [[ -z "$app_networks" ]]; then
        warn "暂无业务网络"
        echo
        info "创建业务网络:"
        echo "  $0 create --name <app>-network --driver bridge"
        return 0
    fi
    
    # 格式化输出
    printf "%-30s %-10s %-10s %-20s\n" "网络名称" "驱动" "范围" "子网"
    printf "%-30s %-10s %-10s %-20s\n" "----------" "----" "----" "----"
    
    while IFS= read -r network; do
        local driver=$(docker network inspect "$network" --format '{{.Driver}}')
        local scope=$(docker network inspect "$network" --format '{{.Scope}}')
        local subnet=$(docker network inspect "$network" --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}')
        
        printf "%-30s %-10s %-10s %-20s\n" "$network" "$driver" "$scope" "$subnet"
    done <<< "$app_networks"
    
    echo
    info "查看详情: $0 inspect --name <网络名称>"
}

# 查看网络详情
inspect_network() {
    local network_name=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --name)
                network_name="$2"
                shift 2
                ;;
            *)
                error "未知参数: $1"
                return 1
                ;;
        esac
    done
    
    if [[ -z "$network_name" ]]; then
        error "缺少网络名称"
        echo "使用方式: $0 inspect --name <网络名称>"
        return 1
    fi
    
    if ! docker network ls --format '{{.Name}}' | grep -q "^${network_name}$"; then
        error "网络 ${network_name} 不存在"
        return 1
    fi
    
    log "网络详情: $network_name"
    echo
    docker network inspect "$network_name"
}

# 连接容器到网络
connect_container() {
    local network_name=""
    local container_name=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --name)
                network_name="$2"
                shift 2
                ;;
            --container)
                container_name="$2"
                shift 2
                ;;
            *)
                error "未知参数: $1"
                return 1
                ;;
        esac
    done
    
    if [[ -z "$network_name" ]] || [[ -z "$container_name" ]]; then
        error "缺少参数"
        echo "使用方式: $0 connect --name <网络名称> --container <容器名称>"
        return 1
    fi
    
    log "连接容器 $container_name 到网络 $network_name"
    
    if docker network connect "$network_name" "$container_name" 2>&1; then
        success "连接成功"
    else
        error "连接失败"
        return 1
    fi
}

# 断开容器连接
disconnect_container() {
    local network_name=""
    local container_name=""
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --name)
                network_name="$2"
                shift 2
                ;;
            --container)
                container_name="$2"
                shift 2
                ;;
            *)
                error "未知参数: $1"
                return 1
                ;;
        esac
    done
    
    if [[ -z "$network_name" ]] || [[ -z "$container_name" ]]; then
        error "缺少参数"
        echo "使用方式: $0 disconnect --name <网络名称> --container <容器名称>"
        return 1
    fi
    
    log "断开容器 $container_name 与网络 $network_name 的连接"
    
    if docker network disconnect "$network_name" "$container_name" 2>&1; then
        success "断开成功"
    else
        error "断开失败"
        return 1
    fi
}

# 主函数
main() {
    local command="${1:-help}"
    
    case "$command" in
        create)
            check_docker
            shift
            create_network "$@"
            ;;
        delete|remove|rm)
            check_docker
            shift
            delete_network "$@"
            ;;
        list|ls)
            check_docker
            list_networks
            ;;
        inspect)
            check_docker
            shift
            inspect_network "$@"
            ;;
        connect)
            check_docker
            shift
            connect_container "$@"
            ;;
        disconnect)
            check_docker
            shift
            disconnect_container "$@"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            error "未知命令: $command"
            echo
            show_help
            exit 1
            ;;
    esac
}

main "$@"
