#!/bin/bash

# SSL 证书管理工具
# 用途: 自动申请、部署和续期 SSL 证书

set -euo pipefail

# 脚本目录和配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
SSL_DIR="/data/ssl"
NGINX_CONTAINER="nginx"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

# 检查依赖
check_dependencies() {
    log "检查依赖工具..."
    
    # 检查 certbot
    if ! command -v certbot &> /dev/null; then
        error "certbot 未安装，正在安装..."
        sudo apt-get update
        sudo apt-get install -y certbot python3-certbot-nginx
    fi
    
    # 检查 Docker
    if ! command -v docker &> /dev/null; then
        error "Docker 未安装"
        exit 1
    fi
    
    # 检查 SSL 目录
    if [[ ! -d "$SSL_DIR" ]]; then
        log "创建 SSL 证书目录..."
        sudo mkdir -p "$SSL_DIR"/{certs,private,archive,renewal}
        sudo chown -R www:www "$SSL_DIR"
        sudo chmod 755 "$SSL_DIR"
        sudo chmod 700 "$SSL_DIR/private"
    fi
    
    success "依赖检查完成"
}

# 申请新证书
obtain_certificate() {
    local domain="$1"
    local email="${2:-admin@${domain}}"
    
    log "为域名 $domain 申请 SSL 证书..."
    
    # 停止 nginx 以释放 80 端口
    if docker ps | grep -q "$NGINX_CONTAINER"; then
        log "临时停止 Nginx 容器..."
        docker stop "$NGINX_CONTAINER" || true
    fi
    
    # 申请证书
    if certbot certonly \
        --standalone \
        --email "$email" \
        --agree-tos \
        --non-interactive \
        --domains "$domain" \
        --cert-path "$SSL_DIR/certs/${domain}.crt" \
        --key-path "$SSL_DIR/private/${domain}.key" \
        --config-dir "$SSL_DIR" \
        --work-dir "$SSL_DIR" \
        --logs-dir "/data/log/certbot"; then
        
        success "证书申请成功: $domain"
        
        # 复制证书到标准位置
        sudo cp "/etc/letsencrypt/live/${domain}/fullchain.pem" "$SSL_DIR/certs/${domain}.crt"
        sudo cp "/etc/letsencrypt/live/${domain}/privkey.pem" "$SSL_DIR/private/${domain}.key"
        sudo chown www:www "$SSL_DIR/certs/${domain}.crt" "$SSL_DIR/private/${domain}.key"
        sudo chmod 644 "$SSL_DIR/certs/${domain}.crt"
        sudo chmod 600 "$SSL_DIR/private/${domain}.key"
        
        # 重启 nginx
        log "重启 Nginx 容器..."
        cd "$INFRA_ROOT"
        make restart-nginx
        
        success "证书部署完成: $domain"
    else
        error "证书申请失败: $domain"
        
        # 重启 nginx（即使失败也要恢复服务）
        log "恢复 Nginx 容器..."
        cd "$INFRA_ROOT"
        make restart-nginx
        
        exit 1
    fi
}

# 续期证书
renew_certificates() {
    log "检查和续期所有证书..."
    
    # 停止 nginx
    if docker ps | grep -q "$NGINX_CONTAINER"; then
        log "临时停止 Nginx 容器..."
        docker stop "$NGINX_CONTAINER" || true
    fi
    
    # 续期所有证书
    if certbot renew \
        --config-dir "$SSL_DIR" \
        --work-dir "$SSL_DIR" \
        --logs-dir "/data/log/certbot" \
        --pre-hook "docker stop $NGINX_CONTAINER || true" \
        --post-hook "cd $INFRA_ROOT && make restart-nginx"; then
        
        success "证书续期检查完成"
    else
        warn "部分证书续期可能失败，请检查日志"
    fi
    
    # 确保 nginx 运行
    log "确保 Nginx 容器运行..."
    cd "$INFRA_ROOT"
    make restart-nginx
}

# 列出证书
list_certificates() {
    log "当前 SSL 证书列表:"
    echo
    
    if [[ -d "$SSL_DIR/certs" ]]; then
        for cert_file in "$SSL_DIR/certs"/*.crt; do
            if [[ -f "$cert_file" ]]; then
                local domain=$(basename "$cert_file" .crt)
                local expiry=$(openssl x509 -enddate -noout -in "$cert_file" | cut -d= -f2)
                echo "🔒 $domain"
                echo "   到期时间: $expiry"
                echo "   证书文件: $cert_file"
                echo "   私钥文件: $SSL_DIR/private/${domain}.key"
                echo
            fi
        done
    else
        warn "未找到证书目录"
    fi
}

# 删除证书
remove_certificate() {
    local domain="$1"
    
    warn "删除域名 $domain 的 SSL 证书..."
    
    # 删除 certbot 证书
    if certbot delete --cert-name "$domain" --config-dir "$SSL_DIR"; then
        success "Certbot 证书删除成功"
    fi
    
    # 删除本地文件
    sudo rm -f "$SSL_DIR/certs/${domain}.crt"
    sudo rm -f "$SSL_DIR/private/${domain}.key"
    
    success "证书文件删除完成: $domain"
}

# 生成 nginx SSL 配置模板
generate_ssl_config() {
    local domain="$1"
    local cert_file="$SSL_DIR/certs/${domain}.crt"
    local key_file="$SSL_DIR/private/${domain}.key"
    
    if [[ ! -f "$cert_file" ]] || [[ ! -f "$key_file" ]]; then
        error "证书文件不存在: $domain"
        exit 1
    fi
    
    cat << EOF
# SSL 配置 for $domain
# 生成时间: $(date)

server {
    listen 443 ssl http2;
    server_name $domain;
    
    # SSL 证书配置
    ssl_certificate /data/ssl/certs/${domain}.crt;
    ssl_certificate_key /data/ssl/private/${domain}.key;
    
    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-SHA256:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES256-SHA256:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA256:AES128-SHA:AES256-SHA:DES-CBC3-SHA;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 5m;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    # 其他安全头
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    
    # 应用配置在这里添加 location 块
    # ...
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name $domain;
    
    # Let's Encrypt 验证路径
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    # 其他请求重定向到 HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}
EOF
}

# 设置自动续期
setup_auto_renewal() {
    log "设置 SSL 证书自动续期..."
    
    # 创建续期脚本
    local renewal_script="/data/ssl/renew-certs.sh"
    cat > "$renewal_script" << 'EOF'
#!/bin/bash
# SSL 证书自动续期脚本

cd "$(dirname "$0")"
/home/www/workspace/infra/scripts/utils/ssl-manager.sh renew

# 记录续期日志
echo "$(date): 证书续期检查完成" >> /data/log/ssl/renewal.log
EOF
    
    sudo chmod +x "$renewal_script"
    sudo chown www:www "$renewal_script"
    
    # 添加到 crontab
    local crontab_line="0 2 * * 1 /data/ssl/renew-certs.sh"
    
    if ! crontab -l | grep -q "$renewal_script"; then
        (crontab -l 2>/dev/null; echo "$crontab_line") | crontab -
        success "自动续期任务已添加到 crontab"
    else
        success "自动续期任务已存在"
    fi
    
    # 创建日志目录
    sudo mkdir -p /data/log/ssl
    sudo chown -R www:www /data/log/ssl
}

# 显示帮助
show_help() {
    cat << EOF
SSL 证书管理工具

用法: $0 <command> [options]

命令:
  obtain <domain> [email]     申请新的 SSL 证书
  renew                       续期所有证书
  list                        列出所有证书
  remove <domain>             删除指定域名的证书
  config <domain>             生成 nginx SSL 配置模板
  setup-auto                  设置自动续期
  
示例:
  $0 obtain blog.example.com admin@example.com
  $0 renew
  $0 list
  $0 remove blog.example.com
  $0 config blog.example.com > /data/apps/nginx-configs/blog-ssl.conf
  $0 setup-auto

注意:
- 证书申请需要域名已解析到当前服务器
- 申请过程中会临时停止 nginx 服务
- 建议在维护窗口期间进行操作
EOF
}

# 主函数
main() {
    if [[ $# -eq 0 ]]; then
        show_help
        exit 1
    fi
    
    local command="$1"
    shift
    
    case "$command" in
        "obtain")
            if [[ $# -lt 1 ]]; then
                error "请指定域名"
                exit 1
            fi
            check_dependencies
            obtain_certificate "$@"
            ;;
        "renew")
            check_dependencies
            renew_certificates
            ;;
        "list")
            list_certificates
            ;;
        "remove")
            if [[ $# -ne 1 ]]; then
                error "请指定要删除的域名"
                exit 1
            fi
            remove_certificate "$1"
            ;;
        "config")
            if [[ $# -ne 1 ]]; then
                error "请指定域名"
                exit 1
            fi
            generate_ssl_config "$1"
            ;;
        "setup-auto")
            setup_auto_renewal
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            error "未知命令: $command"
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"