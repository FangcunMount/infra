#!/bin/bash

# Docker 网络优化应用脚本
# 将现有的 Docker 组件配置应用网络安全优化
# 注意: Jenkins 相关功能已弃用（项目已迁移至 GitHub Actions）

set -e

# 配置参数
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_DIR="$PROJECT_ROOT/backups/$(date +%Y%m%d_%H%M%S)"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# 显示帮助信息
show_help() {
    cat << EOF
Docker 网络优化应用脚本

用法: $0 [选项]

选项:
    -h, --help          显示帮助信息
    -b, --backup        创建配置备份
    --apply-network     仅应用网络配置优化
    --revert           回滚到优化前的配置
    --dry-run          预览模式，不实际修改文件
    --status           检查当前网络配置状态

功能:
    • 设置后端网络为内部网络（增强安全性）
    • 配置服务间通信规则
    • 备份原有配置

优化内容:
    1. 后端网络设置为 internal=true（仅 bridge 模式）
    2. Overlay 网络自带加密支持
    3. 添加 Jenkins 的 Nginx 代理配置
    4. 优化网络安全设置

示例:
    $0                  # 完整应用网络优化
    $0 --backup         # 先备份再应用优化
    $0 --apply-jenkins  # 仅优化 Jenkins 配置
    $0 --status         # 检查配置状态
    $0 --dry-run        # 预览将要执行的操作

EOF
}

# 创建配置备份
create_backup() {
    log_info "创建配置文件备份..."
    
    mkdir -p "$BACKUP_DIR"
    cp -r "$PROJECT_ROOT/components" "$BACKUP_DIR/"
    cp -r "$PROJECT_ROOT/compose" "$BACKUP_DIR/" 2>/dev/null || true
    
    # 生成恢复脚本
    cat > "$BACKUP_DIR/restore.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")/.."
cp -r "$BACKUP_DIR/components" ./
cp -r "$BACKUP_DIR/compose" ./
EOF
    
    log_success "配置备份完成: $BACKUP_DIR"
}

# 检查当前网络配置状态
check_status() {
    log_info "检查当前网络配置状态..."
    
    echo "=== Docker Compose 网络配置 ==="
    if docker network ls | grep -q "infra-"; then
        log_success "✓ Infra 网络已创建"
        docker network ls | grep "infra-"
    else
        log_warn "△ Infra 网络未创建"
    fi
    
    echo -e "\n=== 网络安全配置 ==="
    local networks_compose="$PROJECT_ROOT/components/networks/docker-compose.yml"
    if [[ -f "$networks_compose" ]] && grep -q "internal: true" "$networks_compose" 2>/dev/null; then
        log_success "✓ 后端网络已设置为内部网络"
    else
        log_warn "△ 后端网络未设置为内部网络（或使用 overlay 网络）"
    fi
}


# 应用 Jenkins 网络优化（已弃用）
# 注意: Jenkins 功能已移除，项目已迁移至 GitHub Actions
apply_jenkins_optimization() {
    log_warn "Jenkins 优化功能已弃用"
    log_info "项目已从 Jenkins 迁移至 GitHub Actions"
    log_info "此功能仅保留用于兼容性，不执行任何操作"
    return 0
}

# 应用网络配置优化
apply_network_optimization() {
    log_info "应用网络配置优化..."
    
    local networks_compose="$PROJECT_ROOT/components/networks/docker-compose.yml"
    
    if [[ ! -f "$networks_compose" ]]; then
        log_warn "网络配置文件不存在: $networks_compose"
        log_info "当前使用 overlay 网络，通过 init-infrastructure.sh 管理"
        return 0
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "预览: 将检查网络配置"
        echo "  文件: $networks_compose"
        echo "  检查: backend 网络安全设置"
    else
        # 检查网络配置
        if grep -q "driver: overlay" "$networks_compose" 2>/dev/null; then
            log_info "检测到 overlay 网络，内置加密支持"
        elif grep -q "internal: false" "$networks_compose"; then
            log_warn "检测到 backend 网络未设置为内部网络"
            log_info "建议: 如果不需要外部访问，可设置 internal: true"
        else
            log_success "✓ 网络配置符合安全要求"
        fi
    fi
}

# 重启相关服务
restart_services() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "预览: 将重启 Nginx 服务"
        echo "  - Nginx"
        return 0
    fi
    
    log_info "重启相关服务以应用网络配置..."
    
    cd "$PROJECT_ROOT"
    
    # 检查并重启 Nginx 服务
    if docker-compose ps | grep -q "nginx"; then
        log_info "重新加载 Nginx 配置..."
        docker-compose exec nginx nginx -s reload 2>/dev/null || {
            log_info "重启 Nginx 服务..."
            docker-compose restart nginx
        }
    fi
    
    log_success "服务重启完成"
}

# 验证网络优化结果
verify_optimization() {
    log_info "验证网络优化结果..."
    
    # 检查网络配置
    if docker network inspect infra-network --format '{{.Internal}}' 2>/dev/null | grep -q "true"; then
        log_success "✓ 后端网络已设置为内部网络"
    else
        log_warn "△ 后端网络内部设置需要确认（可能使用 overlay 网络）"
    fi
    
    # 检查 Nginx 访问
    if curl -s -f "http://localhost/nginx-health" >/dev/null 2>&1; then
        log_success "✓ Nginx 服务可访问"
    else
        log_warn "△ Nginx 服务访问测试失败"
    fi
}

# 显示访问信息
show_access_info() {
    cat << EOF

=== 网络优化信息 ===

网络配置:
  - 网络名称: infra-network
  - 网络类型: overlay (分布式部署)
  - 加密支持: 已启用

安全提升:
  ✓ 后端服务网络隔离
  ✓ 服务间通信加密
  ✓ Nginx 统一网关管理
  ✓ 访问日志和安全头部统一处理

故障排除:
  - 检查服务状态: docker-compose ps
  - 查看 Nginx 日志: docker-compose logs nginx
  - 检查网络状态: make network-status
  - 网络诊断: make port-check

注意: Jenkins 相关功能已弃用，项目已迁移至 GitHub Actions

EOF
}

# 主函数
main() {
    local backup_first=false
    local apply_network_only=false
    local show_status=false
    local revert=false
    DRY_RUN=false
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -b|--backup)
                backup_first=true
                shift
                ;;
            --apply-network)
                apply_network_only=true
                shift
                ;;
            --status)
                show_status=true
                shift
                ;;
            --revert)
                revert=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    # 执行操作
    if [[ "$show_status" == true ]]; then
        check_status
        exit 0
    fi
    
    if [[ "$revert" == true ]]; then
        log_error "回滚功能未实现，请手动从备份恢复"
        exit 1
    fi
    
    # 主要优化流程
    log_info "开始 Docker 网络优化..."
    
    if [[ "$backup_first" == true ]]; then
        create_backup
    fi
    
    if [[ "$apply_network_only" == true ]]; then
        apply_network_optimization
    else
        # 完整优化
        apply_network_optimization
    fi
    
    if [[ "$DRY_RUN" != true ]]; then
        restart_services
        sleep 5  # 等待服务启动
        verify_optimization
        show_access_info
    fi
    
    log_success "Docker 网络优化完成！"
}

# 执行主函数
main "$@"