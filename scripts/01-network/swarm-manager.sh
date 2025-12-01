#!/bin/bash

# Docker Swarm 集群管理脚本
# 用于初始化和管理跨主机 Docker Swarm 集群

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
${GREEN}Docker Swarm 集群管理工具${NC}

${BLUE}用法:${NC}
    $0 <命令> [参数]

${BLUE}命令:${NC}
    ${CYAN}init-manager${NC}           初始化 Swarm 管理节点 (在 ServerA 执行)
    ${CYAN}init-worker${NC}            初始化 Swarm 工作节点 (在 ServerB 执行)
    ${CYAN}get-join-token${NC}         获取工作节点加入令牌
    ${CYAN}status${NC}                 查看 Swarm 集群状态
    ${CYAN}list-nodes${NC}             列出所有节点
    ${CYAN}create-network${NC}         创建 overlay 网络
    ${CYAN}remove-network${NC}         删除 overlay 网络
    ${CYAN}leave${NC}                  离开 Swarm 集群
    ${CYAN}test${NC}                   测试跨主机网络连通性
    ${CYAN}help${NC}                   显示此帮助信息

${BLUE}示例:${NC}
    # 在 ServerA 上初始化管理节点
    sudo $0 init-manager

    # 获取加入令牌 (在 ServerA 上)
    sudo $0 get-join-token

    # 在 ServerB 上加入集群 (使用上面获取的令牌)
    sudo $0 init-worker <manager-ip> <join-token>

    # 查看集群状态
    sudo $0 status

    # 创建 overlay 网络
    sudo $0 create-network

${BLUE}注意事项:${NC}
    - 需要 root 权限执行
    - 确保防火墙开放以下端口:
      * TCP 2377 (集群管理)
      * TCP/UDP 7946 (节点通信)
      * UDP 4789 (overlay 网络)
    - 建议在内网环境使用

EOF
}

# 检查是否为 root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "此脚本需要 root 权限执行"
        echo "请使用: sudo $0 $@"
        exit 1
    fi
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

# 检查防火墙端口
check_firewall() {
    log "检查 Swarm 所需端口..."
    
    local required_ports=(
        "2377/tcp"  # 集群管理
        "7946/tcp"  # 节点通信
        "7946/udp"  # 节点通信
        "4789/udp"  # overlay 网络
    )
    
    warn "请确保以下端口已开放:"
    for port in "${required_ports[@]}"; do
        echo "  - $port"
    done
    
    echo
    info "如需开放端口,执行以下命令:"
    echo "  sudo ufw allow 2377/tcp"
    echo "  sudo ufw allow 7946/tcp"
    echo "  sudo ufw allow 7946/udp"
    echo "  sudo ufw allow 4789/udp"
    echo
}

# 初始化管理节点
init_manager() {
    log "初始化 Docker Swarm 管理节点..."
    
    # 检查是否已在 swarm 中
    if docker info 2>/dev/null | grep -q "Swarm: active"; then
        warn "此节点已在 Swarm 集群中"
        docker node ls
        return 0
    fi
    
    check_firewall
    
    # 获取本机 IP (优先内网 IP)
    local host_ip=$(hostname -I | awk '{print $1}')
    
    log "使用 IP 地址: $host_ip"
    log "正在初始化 Swarm..."
    
    if docker swarm init --advertise-addr "$host_ip" 2>&1; then
        success "Swarm 管理节点初始化成功!"
        echo
        info "节点信息:"
        docker node ls
        echo
        success "请在工作节点上执行以下命令加入集群:"
        echo
        docker swarm join-token worker | grep "docker swarm join"
        echo
    else
        error "Swarm 初始化失败"
        exit 1
    fi
}

# 获取加入令牌
get_join_token() {
    log "获取 Swarm 加入令牌..."
    
    if ! docker info 2>/dev/null | grep -q "Swarm: active"; then
        error "此节点不是 Swarm 管理节点"
        exit 1
    fi
    
    echo
    echo "${GREEN}=== Worker 节点加入命令 ===${NC}"
    docker swarm join-token worker
    echo
    echo "${GREEN}=== Manager 节点加入命令 ===${NC}"
    docker swarm join-token manager
    echo
}

# 初始化工作节点
init_worker() {
    local manager_ip="$1"
    local join_token="$2"
    
    if [[ -z "$manager_ip" ]] || [[ -z "$join_token" ]]; then
        error "用法: $0 init-worker <manager-ip> <join-token>"
        echo
        echo "示例:"
        echo "  sudo $0 init-worker 192.168.1.100 SWMTKN-1-xxx"
        exit 1
    fi
    
    log "加入 Docker Swarm 集群..."
    
    # 检查是否已在 swarm 中
    if docker info 2>/dev/null | grep -q "Swarm: active"; then
        warn "此节点已在 Swarm 集群中"
        return 0
    fi
    
    check_firewall
    
    if docker swarm join --token "$join_token" "${manager_ip}:2377" 2>&1; then
        success "成功加入 Swarm 集群!"
        echo
        docker info | grep -A 5 "Swarm:"
    else
        error "加入集群失败"
        exit 1
    fi
}

# 查看集群状态
show_status() {
    log "Docker Swarm 集群状态:"
    echo
    
    if ! docker info 2>/dev/null | grep -q "Swarm: active"; then
        warn "此节点不在 Swarm 集群中"
        echo
        info "运行以下命令初始化:"
        echo "  sudo $0 init-manager    # 管理节点"
        echo "  sudo $0 init-worker     # 工作节点"
        return 1
    fi
    
    docker info | grep -A 10 "Swarm:"
    echo
}

# 列出节点
list_nodes() {
    log "Swarm 集群节点列表:"
    echo
    
    if ! docker info 2>/dev/null | grep -q "Swarm: active"; then
        error "此节点不在 Swarm 集群中"
        exit 1
    fi
    
    docker node ls 2>/dev/null || {
        warn "只有管理节点可以查看节点列表"
        return 1
    }
}

# 创建 overlay 网络
create_network() {
    log "创建 infra-network overlay 网络..."
    
    if ! docker info 2>/dev/null | grep -q "Swarm: active"; then
        error "此节点不在 Swarm 集群中,请先初始化 Swarm"
        exit 1
    fi
    
    # 检查网络是否已存在
    if docker network ls | grep -q "infra-network"; then
        warn "网络 infra-network 已存在"
        docker network inspect infra-network | grep -E "Name|Driver|Scope|Subnet"
        return 0
    fi
    
    # 创建 overlay 网络
    if docker network create \
        --driver overlay \
        --subnet 172.20.0.0/16 \
        --attachable \
        --opt com.docker.network.driver.mtu=1450 \
        --label infra.network=backend \
        --label infra.purpose=internal-services \
        --label infra.network.type=overlay \
        infra-network; then
        
        success "Overlay 网络创建成功!"
        echo
        docker network inspect infra-network | grep -E "Name|Driver|Scope|Subnet"
    else
        error "网络创建失败"
        exit 1
    fi
}

# 删除网络
remove_network() {
    log "删除 infra-network overlay 网络..."
    
    if docker network ls | grep -q "infra-network"; then
        docker network rm infra-network && success "网络已删除"
    else
        warn "网络不存在"
    fi
}

# 离开集群
leave_swarm() {
    log "离开 Docker Swarm 集群..."
    
    if ! docker info 2>/dev/null | grep -q "Swarm: active"; then
        warn "此节点不在 Swarm 集群中"
        return 0
    fi
    
    read -p "确认离开 Swarm 集群? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        warn "操作已取消"
        return 0
    fi
    
    if docker swarm leave --force 2>&1; then
        success "已离开 Swarm 集群"
    else
        error "离开集群失败"
        exit 1
    fi
}

# 测试网络
test_network() {
    log "测试跨主机网络连通性..."
    echo
    
    if ! docker network ls | grep -q "infra-network"; then
        error "网络 infra-network 不存在"
        exit 1
    fi
    
    # 启动测试容器
    log "在 infra-network 网络中启动测试容器..."
    
    local test_name="swarm-test-$(date +%s)"
    
    docker run -d \
        --name "$test_name" \
        --network infra-network \
        alpine sleep 300
    
    success "测试容器已启动: $test_name"
    
    local container_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$test_name")
    
    echo
    info "容器信息:"
    echo "  名称: $test_name"
    echo "  IP: $container_ip"
    echo "  网络: infra-network"
    echo
    info "请在另一台服务器上运行相同命令,然后互相 ping 测试"
    echo "  docker exec $test_name ping <对方容器IP>"
    echo
    warn "测试完成后执行以下命令清理:"
    echo "  docker rm -f $test_name"
}

# 主函数
main() {
    local command="${1:-help}"
    
    case "$command" in
        init-manager)
            check_root "$@"
            check_docker
            init_manager
            ;;
        init-worker)
            check_root "$@"
            check_docker
            shift
            init_worker "$@"
            ;;
        get-join-token|join-token)
            check_root "$@"
            check_docker
            get_join_token
            ;;
        status)
            check_docker
            show_status
            ;;
        list-nodes|nodes)
            check_docker
            list_nodes
            ;;
        create-network)
            check_root "$@"
            check_docker
            create_network
            ;;
        remove-network)
            check_root "$@"
            check_docker
            remove_network
            ;;
        leave)
            check_root "$@"
            check_docker
            leave_swarm
            ;;
        test)
            check_root "$@"
            check_docker
            test_network
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
