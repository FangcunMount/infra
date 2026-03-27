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
    echo "  $0 deploy <app-name> <config-file>             - 部署现有配置文件"
    echo "  $0 deploy <app-name> <domain> <port> [ssl]    - 按域名端口自动生成并部署配置"
    echo "  $0 remove <app-name>               - 移除应用配置"
    echo "  $0 list                           - 列出所有应用配置"
    echo "  $0 reload                         - 重载 nginx 配置"
    echo "  $0 test                           - 测试 nginx 配置"
    echo ""
    echo "示例:"
    echo "  $0 deploy blog ./nginx/blog.conf"
    echo "  $0 deploy iam iam.fangcunmount.cn 8080 yes"
    echo "  $0 deploy qs qs.fangcunmount.cn 8081 no"
    echo "  $0 remove blog"
    echo "  $0 list"
    echo "  $0 reload"
}

# 生成应用配置（临时文件）
generate_config_file() {
    local app_name="$1"
    local domain="$2"
    local port="$3"
    local ssl_enabled="${4:-no}"
    local tmp_file

    tmp_file="$(mktemp "/tmp/nginx-${app_name}-XXXXXX.conf")"

    if [[ "$ssl_enabled" == "yes" || "$ssl_enabled" == "true" ]]; then
        cat > "$tmp_file" << EOF
upstream ${app_name}_backend {
    server ${app_name}:${port};
}

server {
    listen 443 ssl http2;
    server_name ${domain};

    ssl_certificate /data/ssl/certs/${domain}.crt;
    ssl_certificate_key /data/ssl/private/${domain}.key;

    location / {
        proxy_pass http://${app_name}_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}

server {
    listen 80;
    server_name ${domain};
    return 301 https://\$server_name\$request_uri;
}
EOF
    else
        cat > "$tmp_file" << EOF
upstream ${app_name}_backend {
    server ${app_name}:${port};
}

server {
    listen 80;
    server_name ${domain};

    location / {
        proxy_pass http://${app_name}_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    fi

    echo "$tmp_file"
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
    local arg2="$2"
    local arg3="${3:-}"
    local arg4="${4:-no}"
    local config_file=""
    local generated_config_file=""
    
    if [ -z "$app_name" ] || [ -z "$arg2" ]; then
        log_error "请提供应用名称及配置参数"
        show_help
        return 1
    fi
    # 确保目标配置目录存在（后续可能会从该目录查找文件）
    ensure_config_dir

    # 模式1：deploy <app-name> <config-file>
    if [ -f "$arg2" ]; then
        config_file="$arg2"
    # 模式2：deploy <app-name> <domain> <port> [ssl]
    elif [ -n "$arg3" ]; then
        generated_config_file="$(generate_config_file "$app_name" "$arg2" "$arg3" "$arg4")"
        config_file="$generated_config_file"
    else
        # 兼容：第二个参数是配置名（不带 .conf）
        config_file="$arg2"
        if [ -f "$APPS_CONFIG_DIR/${config_file}.conf" ]; then
            config_file="$APPS_CONFIG_DIR/${config_file}.conf"
        elif [ -f "${PWD}/${config_file}.conf" ]; then
            config_file="${PWD}/${config_file}.conf"
        else
            log_error "未找到配置文件，或缺少 <port> 参数: $arg2"
            show_help
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

    # 清理自动生成的临时文件
    if [ -n "$generated_config_file" ] && [ -f "$generated_config_file" ]; then
        rm -f "$generated_config_file"
    fi
    
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
            local config_name=$(basename "$file" .conf)
            local app_name="-"
            local upstream_name
            local file_size=$(ls -lh "$file" | awk '{print $5}')
            local mod_time=$(ls -l "$file" | awk '{print $6, $7, $8}')

            # 优先从 upstream 推断应用名（例如 upstream iam_backend -> iam）
            upstream_name=$(awk '/^[[:space:]]*upstream[[:space:]]+/ {print $2; exit}' "$file" 2>/dev/null || true)
            upstream_name="${upstream_name%;}"
            if [[ -n "$upstream_name" ]]; then
                app_name="${upstream_name%_backend}"
            fi

            echo "  - 配置: ${config_name} (app: ${app_name}, ${file_size}, 修改时间: ${mod_time})"
            count=$((count + 1))
        fi
    done
    
    if [ $count -eq 0 ]; then
        echo "  无已部署的配置"
    fi
}

# 测试 nginx 配置
test_nginx_config() {
    if ! command -v docker >/dev/null 2>&1; then
        log_warn "Docker 不可用，跳过配置测试"
        return 0
    fi

    # 在容器内运行 nginx -t，捕获输出以便在出错时显示（便于诊断）
    local out
    if out=$(docker exec "$NGINX_CONTAINER" nginx -t 2>&1); then
        log_info "✅ nginx 配置测试通过"
        return 0
    else
        log_error "nginx 配置测试失败，输出如下："
        echo "$out"
        return 1
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
            deploy_config "$2" "$3" "$4" "$5"
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