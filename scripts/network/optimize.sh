#!/bin/bash

# Docker 网络优化应用脚本
# 将现有的 Docker 组件配置应用网络安全优化

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
    --apply-jenkins     仅应用 Jenkins 网络优化
    --apply-network     仅应用网络配置优化
    --revert           回滚到优化前的配置
    --dry-run          预览模式，不实际修改文件
    --status           检查当前网络配置状态

功能:
    • 将 Jenkins 配置为通过 Nginx 代理访问
    • 设置后端网络为内部网络（增强安全性）
    • 配置 Nginx 代理规则
    • 备份原有配置

优化内容:
    1. Jenkins Web 端口通过 Nginx 代理（移除直接端口映射）
    2. 后端网络设置为 internal=true
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

# 创建备份
create_backup() {
    log_info "创建配置备份..."
    
    mkdir -p "$BACKUP_DIR"
    
    # 备份相关配置文件
    local files=(
        "components/jenkins/override.yml"
        "components/nginx/conf.d"
        "compose/base/docker-compose.yml"
    )
    
    for file in "${files[@]}"; do
        local src="$PROJECT_ROOT/$file"
        if [[ -e "$src" ]]; then
            local dest="$BACKUP_DIR/$(dirname "$file")"
            mkdir -p "$dest"
            cp -r "$src" "$dest/"
            log_info "备份: $file"
        fi
    done
    
    # 创建备份信息文件
    cat > "$BACKUP_DIR/backup_info.txt" << EOF
Docker 网络优化配置备份
备份时间: $(date)
备份目录: $BACKUP_DIR
脚本版本: $0

备份内容:
- Jenkins Override 配置
- Nginx 配置目录
- Docker Compose 基础配置

恢复方法:
cd "$PROJECT_ROOT"
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
    
    echo -e "\n=== Jenkins 端口配置 ==="
    if grep -q "8080:8080" "$PROJECT_ROOT/components/jenkins/override.yml" 2>/dev/null; then
        log_warn "△ Jenkins 8080 端口直接暴露（未优化）"
    else
        log_success "✓ Jenkins 8080 端口已移除直接映射"
    fi
    
    echo -e "\n=== Nginx 代理配置 ==="
    if [[ -f "$PROJECT_ROOT/components/nginx/conf.d/jenkins.conf" ]]; then
        log_success "✓ Jenkins Nginx 代理配置存在"
    else
        log_warn "△ Jenkins Nginx 代理配置不存在"
    fi
    
    echo -e "\n=== 网络安全配置 ==="
    if grep -q "internal: true" "$PROJECT_ROOT/compose/base/docker-compose.yml" 2>/dev/null; then
        log_success "✓ 后端网络已设置为内部网络"
    else
        log_warn "△ 后端网络未设置为内部网络"
    fi
}

# 应用 Jenkins 网络优化
apply_jenkins_optimization() {
    log_info "应用 Jenkins 网络优化..."
    
    local jenkins_override="$PROJECT_ROOT/components/jenkins/override.yml"
    local jenkins_optimized="$PROJECT_ROOT/components/jenkins/override-optimized.yml"
    
    if [[ -f "$jenkins_optimized" ]]; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "预览: 将替换 Jenkins override 配置"
            echo "  源文件: $jenkins_optimized"
            echo "  目标文件: $jenkins_override"
        else
            cp "$jenkins_optimized" "$jenkins_override"
            log_success "✓ Jenkins 配置已优化（移除直接端口映射）"
        fi
    else
        log_error "优化配置文件不存在: $jenkins_optimized"
        return 1
    fi
    
    # 确保 Nginx 代理配置存在
    local jenkins_nginx_conf="$PROJECT_ROOT/components/nginx/conf.d/jenkins.conf"
    if [[ -f "$jenkins_nginx_conf" ]]; then
        log_success "✓ Jenkins Nginx 代理配置已存在"
    else
        log_warn "△ Jenkins Nginx 代理配置不存在，请检查是否已创建"
    fi
}

# 应用网络配置优化
apply_network_optimization() {
    log_info "应用网络配置优化..."
    
    local base_compose="$PROJECT_ROOT/compose/base/docker-compose.yml"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "预览: 将修改网络配置"
        echo "  文件: $base_compose"
        echo "  修改: 设置 backend 网络为 internal: true"
    else
        # 修改 backend 网络为内部网络
        if grep -q "internal: false" "$base_compose"; then
            sed -i.bak 's/internal: false/internal: true/' "$base_compose"
            log_success "✓ 后端网络已设置为内部网络"
        elif ! grep -q "internal:" "$base_compose"; then
            # 在 backend 网络配置中添加 internal: true
            sed -i.bak '/name: infra-backend/a\    internal: true' "$base_compose"
            log_success "✓ 后端网络已设置为内部网络"
        else
            log_info "后端网络配置无需修改"
        fi
    fi
}

# 重启相关服务
restart_services() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "预览: 将重启以下服务"
        echo "  - Jenkins"
        echo "  - Nginx"
        return 0
    fi
    
    log_info "重启相关服务以应用网络配置..."
    
    cd "$PROJECT_ROOT"
    
    # 检查服务是否运行
    if docker-compose ps | grep -q "jenkins"; then
        log_info "重启 Jenkins 服务..."
        docker-compose restart jenkins
    fi
    
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
    if docker network inspect infra-backend --format '{{.Internal}}' 2>/dev/null | grep -q "true"; then
        log_success "✓ 后端网络已设置为内部网络"
    else
        log_warn "△ 后端网络内部设置需要确认"
    fi
    
    # 检查 Jenkins 访问
    if curl -s -f "http://localhost/nginx-health" >/dev/null 2>&1; then
        log_success "✓ Nginx 代理服务可访问"
        
        # 测试 Jenkins 代理
        if curl -s -k "https://jenkins.local/login" >/dev/null 2>&1; then
            log_success "✓ Jenkins 通过 Nginx 代理可访问"
        else
            log_warn "△ Jenkins 代理访问需要确认（可能需要配置 hosts）"
        fi
    else
        log_warn "△ Nginx 服务状态需要确认"
    fi
}

# 显示访问信息
show_access_info() {
    cat << EOF

=== 网络优化后的访问信息 ===

Jenkins CI/CD 平台:
  - HTTPS: https://jenkins.local (推荐)
  - HTTP:  http://jenkins.local (自动重定向到 HTTPS)
  - Agent: localhost:50000 (构建节点连接)

配置要求:
  1. 在 /etc/hosts 中添加: 127.0.0.1 jenkins.local
  2. 确保 SSL 证书配置正确
  3. 防火墙允许 443 和 50000 端口

安全提升:
  ✓ Jenkins Web 界面通过 HTTPS 访问
  ✓ 后端服务完全隔离（无法直接从外部访问）
  ✓ SSL 终结在 Nginx 层统一处理
  ✓ 访问日志和安全头部统一管理

故障排除:
  - 检查服务状态: docker-compose ps
  - 查看 Nginx 日志: docker-compose logs nginx
  - 查看 Jenkins 日志: docker-compose logs jenkins
  - 测试代理配置: curl -k https://jenkins.local/login

EOF
}

# 主函数
main() {
    local backup_first=false
    local apply_jenkins_only=false
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
            --apply-jenkins)
                apply_jenkins_only=true
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
    
    if [[ "$apply_jenkins_only" == true ]]; then
        apply_jenkins_optimization
    elif [[ "$apply_network_only" == true ]]; then
        apply_network_optimization
    else
        # 完整优化
        apply_jenkins_optimization
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