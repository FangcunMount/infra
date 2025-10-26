#!/bin/bash

# 应用 Nginx 配置管理脚本
# 用于管理应用项目的 nginx 配置文件

# 配置目录
APPS_CONFIG_DIR="/data/apps/nginx-configs"
NGINX_CONTAINER="nginx"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_debug() { echo -e "${BLUE}[DEBUG]${NC} $1"; }

# 显示帮助信息
show_help() {
    echo "应用 Nginx 配置管理工具"
    echo ""
    echo "用法:"
    echo "  $0 deploy <app-name> <config-file>  - 部署应用配置"
    echo "  $0 remove <app-name>               - 移除应用配置"
    echo "  $0 list                           - 列出所有应用配置"
    echo "  $0 reload                         - 重载 nginx 配置"
    echo "  $0 test                           - 测试 nginx 配置"
    echo ""
    echo "示例:"
    echo "  $0 deploy blog ./nginx/blog.conf"
    echo "  $0 remove blog"
    echo "  $0 list"
    echo "  $0 reload"
}

# 确保配置目录存在
ensure_config_dir() {
    if [ ! -d "$APPS_CONFIG_DIR" ]; then
        log_info "创建应用配置目录: $APPS_CONFIG_DIR"
        sudo mkdir -p "$APPS_CONFIG_DIR"
        sudo chown www:www "$APPS_CONFIG_DIR"
        sudo chmod 755 "$APPS_CONFIG_DIR"
    fi
}

# 部署应用配置
deploy_config() {
    local app_name="$1"
    local config_file="$2"
    
    if [ -z "$app_name" ] || [ -z "$config_file" ]; then
        log_error "请提供应用名称和配置文件路径"
        show_help
        return 1
    fi
    # 确保目标配置目录存在（后续可能会从该目录查找文件）
    ensure_config_dir

    # 如果传入的第二个参数不是一个现有文件，尝试在常见位置查找
    if [ ! -f "$config_file" ]; then
        # 1) /data/apps/nginx-configs/<name>.conf
        if [ -f "$APPS_CONFIG_DIR/${config_file}.conf" ]; then
            config_file="$APPS_CONFIG_DIR/${config_file}.conf"
        # 2) 当前工作目录 <name>.conf
        elif [ -f "${PWD}/${config_file}.conf" ]; then
            config_file="${PWD}/${config_file}.conf"
        # 3) components/nginx/conf.d/apps/<name>.conf （仓库示例位置）
        elif [ -f "$SCRIPT_DIR/../components/nginx/conf.d/apps/${config_file}.conf" ]; then
            config_file="$SCRIPT_DIR/../components/nginx/conf.d/apps/${config_file}.conf"
        # 4) components/nginx/conf.d/<name>.conf
        elif [ -f "$SCRIPT_DIR/../components/nginx/conf.d/${config_file}.conf" ]; then
            config_file="$SCRIPT_DIR/../components/nginx/conf.d/${config_file}.conf"
        else
            log_error "配置文件不存在: $config_file"
            return 1
        fi
    fi
    
    local target_file="$APPS_CONFIG_DIR/${app_name}.conf"
    
    log_info "部署 $app_name 配置..."
    log_debug "源文件: $config_file"
    log_debug "目标文件: $target_file"
    
    # 复制配置文件
    sudo cp "$config_file" "$target_file"
    sudo chown www:www "$target_file"
    sudo chmod 644 "$target_file"
    
    # 测试配置
    if test_nginx_config; then
        # 重载配置
        reload_nginx
        log_info "✅ $app_name 配置部署成功"
    else
        log_error "❌ 配置文件有误，回滚操作"
        sudo rm -f "$target_file"
        return 1
    fi
}

# 移除应用配置
remove_config() {
    local app_name="$1"
    
    if [ -z "$app_name" ]; then
        log_error "请提供应用名称"
        return 1
    fi
    
    local target_file="$APPS_CONFIG_DIR/${app_name}.conf"
    
    if [ ! -f "$target_file" ]; then
        log_warn "应用配置不存在: $app_name"
        return 0
    fi
    
    log_info "移除 $app_name 配置..."
    sudo rm -f "$target_file"
    
    # 重载配置
    reload_nginx
    log_info "✅ $app_name 配置已移除"
}

# 列出所有应用配置
list_configs() {
    log_info "📋 已部署的应用配置:"
    
    if [ ! -d "$APPS_CONFIG_DIR" ]; then
        echo "  无配置目录"
        return 0
    fi
    
    local count=0
    for file in "$APPS_CONFIG_DIR"/*.conf; do
        if [ -f "$file" ]; then
            local app_name=$(basename "$file" .conf)
            local file_size=$(ls -lh "$file" | awk '{print $5}')
            local mod_time=$(ls -l "$file" | awk '{print $6, $7, $8}')
            echo "  - $app_name ($file_size, 修改时间: $mod_time)"
            count=$((count + 1))
        fi
    done
    
    if [ $count -eq 0 ]; then
        echo "  无已部署的配置"
    fi
}

# 测试 nginx 配置
test_nginx_config() {
    if command -v docker >/dev/null 2>&1; then
        docker exec "$NGINX_CONTAINER" nginx -t 2>/dev/null
    else
        log_warn "Docker 不可用，跳过配置测试"
        return 0
    fi
}

# 重载 nginx 配置
reload_nginx() {
    log_info "🔄 重载 nginx 配置..."
    
    if command -v docker >/dev/null 2>&1; then
        if docker exec "$NGINX_CONTAINER" nginx -s reload 2>/dev/null; then
            log_info "✅ nginx 配置已重载"
        else
            log_error "❌ nginx 配置重载失败"
            return 1
        fi
    else
        log_warn "Docker 不可用，请手动重载 nginx"
    fi
}

# 主函数
main() {
    case "${1:-}" in
        "deploy")
            deploy_config "$2" "$3"
            ;;
        "remove")
            remove_config "$2"
            ;;
        "list"|"ls")
            list_configs
            ;;
        "test")
            test_nginx_config && log_info "✅ nginx 配置测试通过"
            ;;
        "reload")
            reload_nginx
            ;;
        "help"|"-h"|"--help"|"")
            show_help
            ;;
        *)
            log_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"