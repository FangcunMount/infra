#!/bin/bash

# SSL 证书管理工具
# 用途: 自动申请、部署和续期 SSL 证书

set -euo pipefail

# 脚本目录和配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
SSL_DIR="/data/ssl"
NGINX_CONTAINER="nginx"
ALIYUN_CREDENTIALS="$HOME/.secrets/aliyun.ini"

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
        if command -v yum &> /dev/null; then
            # CentOS/RHEL
            sudo yum install -y certbot
        elif command -v apt-get &> /dev/null; then
            # Debian/Ubuntu
            sudo apt-get update
            sudo apt-get install -y certbot
        else
            error "无法确定包管理器，请手动安装 certbot"
            exit 1
        fi
    fi
    
    # 检查 certbot-dns-aliyun 插件
    if ! python3 -c "import certbot_dns_aliyun" &> /dev/null; then
        warn "certbot-dns-aliyun 插件未安装，正在安装..."
        
        # Ubuntu 24.04+ 需要 --break-system-packages 标志
        if sudo pip3 install certbot-dns-aliyun --break-system-packages 2>/dev/null; then
            success "插件安装成功"
        elif sudo pip3 install certbot-dns-aliyun 2>/dev/null; then
            success "插件安装成功"
        else
            error "插件安装失败"
            echo
            warn "请尝试以下方式之一："
            echo "1. 使用 --break-system-packages 标志:"
            echo "   sudo pip3 install certbot-dns-aliyun --break-system-packages"
            echo
            echo "2. 使用 pipx (推荐):"
            echo "   sudo apt install pipx"
            echo "   pipx install certbot-dns-aliyun"
            echo
            exit 1
        fi
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

# 检查阿里云凭证
check_aliyun_credentials() {
    if [[ ! -f "$ALIYUN_CREDENTIALS" ]]; then
        error "阿里云凭证文件不存在: $ALIYUN_CREDENTIALS"
        echo
        warn "请按以下步骤创建阿里云 DNS API 凭证文件："
        echo
        echo "1. 创建凭证目录："
        echo "   mkdir -p ~/.secrets"
        echo
        echo "2. 创建凭证文件："
        echo "   cat > ~/.secrets/aliyun.ini << EOF"
        echo "dns_aliyun_access_key = YOUR_ACCESS_KEY_ID"
        echo "dns_aliyun_access_key_secret = YOUR_ACCESS_KEY_SECRET"
        echo "EOF"
        echo
        echo "3. 设置安全权限："
        echo "   chmod 600 ~/.secrets/aliyun.ini"
        echo
        echo "获取 AccessKey："
        echo "  https://ram.console.aliyun.com/users"
        echo "  需要授予权限: AliyunDNSFullAccess"
        echo
        exit 1
    fi
    
    # 检查凭证文件权限
    local perms=$(stat -c %a "$ALIYUN_CREDENTIALS" 2>/dev/null || stat -f %Lp "$ALIYUN_CREDENTIALS" 2>/dev/null)
    if [[ "$perms" != "600" ]]; then
        warn "凭证文件权限不安全，正在修正..."
        chmod 600 "$ALIYUN_CREDENTIALS"
    fi
    
    success "阿里云凭证检查通过"
}

# 申请通配符证书（使用阿里云 DNS API）
obtain_wildcard_certificate() {
    local domain="$1"
    local email="${2:-admin@${domain}}"
    
    log "为域名 $domain 申请通配符 SSL 证书..."
    log "域名范围: $domain 和 *.${domain}"
    
    # 检查阿里云凭证
    check_aliyun_credentials
    
    # 使用 DNS 验证申请证书（无需停止 nginx）
    if certbot certonly \
        --authenticator dns-aliyun \
        --dns-aliyun-credentials "$ALIYUN_CREDENTIALS" \
        --email "$email" \
        --agree-tos \
        --non-interactive \
        -d "$domain" \
        -d "*.${domain}" \
        --cert-name "$domain" \
        --config-dir /etc/letsencrypt \
        --work-dir /var/lib/letsencrypt \
        --logs-dir /var/log/letsencrypt; then
        
        success "证书申请成功: $domain + *.${domain}"
        
        # 确保 SSL 目录存在
        log "准备证书存储目录..."
        sudo mkdir -p "$SSL_DIR"/{certs,private}
        sudo chown -R www:www "$SSL_DIR" 2>/dev/null || sudo chown -R root:root "$SSL_DIR"
        sudo chmod 755 "$SSL_DIR"
        sudo chmod 755 "$SSL_DIR/certs"
        sudo chmod 700 "$SSL_DIR/private"
        
        # 复制证书到标准位置
        log "复制证书到 $SSL_DIR..."
        sudo cp "/etc/letsencrypt/live/${domain}/fullchain.pem" "$SSL_DIR/certs/${domain}.crt"
        sudo cp "/etc/letsencrypt/live/${domain}/privkey.pem" "$SSL_DIR/private/${domain}.key"
        
        # 设置权限
        if id www &>/dev/null; then
            sudo chown www:www "$SSL_DIR/certs/${domain}.crt" "$SSL_DIR/private/${domain}.key"
        else
            sudo chown root:root "$SSL_DIR/certs/${domain}.crt" "$SSL_DIR/private/${domain}.key"
        fi
        sudo chmod 644 "$SSL_DIR/certs/${domain}.crt"
        sudo chmod 600 "$SSL_DIR/private/${domain}.key"
        
        # 重启 nginx 使证书生效
        log "重新加载 Nginx 配置..."
        if docker ps | grep -q "$NGINX_CONTAINER"; then
            docker exec "$NGINX_CONTAINER" nginx -s reload || {
                warn "Nginx 重载失败，尝试重启容器..."
                docker restart "$NGINX_CONTAINER"
            }
        fi
        
        success "证书部署完成: $domain"
        log "证书覆盖范围:"
        log "  ✅ $domain"
        log "  ✅ *.${domain} (所有子域名)"
        log "证书文件:"
        log "  📄 证书: $SSL_DIR/certs/${domain}.crt"
        log "  🔑 私钥: $SSL_DIR/private/${domain}.key"
    else
        error "证书申请失败: $domain"
        exit 1
    fi
}

# 申请新证书（单域名，HTTP 验证）
obtain_certificate() {
    local domain="$1"
    local email="${2:-admin@${domain}}"
    
    log "为域名 $domain 申请 SSL 证书（单域名）..."
    
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
        --cert-name "$domain" \
        --config-dir /etc/letsencrypt \
        --work-dir /var/lib/letsencrypt \
        --logs-dir /var/log/letsencrypt; then
        
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
        make restart-nginx || docker start "$NGINX_CONTAINER"
        
        success "证书部署完成: $domain"
    else
        error "证书申请失败: $domain"
        
        # 重启 nginx（即使失败也要恢复服务）
        log "恢复 Nginx 容器..."
        cd "$INFRA_ROOT"
        make restart-nginx || docker start "$NGINX_CONTAINER"
        
        exit 1
    fi
}

# 续期证书
renew_certificates() {
    log "检查和续期所有证书..."
    
    # DNS 验证的证书无需停止 nginx
    # 直接续期
    if certbot renew \
        --config-dir /etc/letsencrypt \
        --work-dir /var/lib/letsencrypt \
        --logs-dir /var/log/letsencrypt \
        --post-hook "docker exec $NGINX_CONTAINER nginx -s reload || docker restart $NGINX_CONTAINER"; then
        
        success "证书续期检查完成"
        
        # 同步证书到 SSL 目录
        log "同步证书到 $SSL_DIR..."
        for cert_dir in /etc/letsencrypt/live/*/; do
            if [[ -d "$cert_dir" ]]; then
                local domain=$(basename "$cert_dir")
                if [[ "$domain" != "README" ]]; then
                    sudo cp "${cert_dir}fullchain.pem" "$SSL_DIR/certs/${domain}.crt"
                    sudo cp "${cert_dir}privkey.pem" "$SSL_DIR/private/${domain}.key"
                    sudo chown www:www "$SSL_DIR/certs/${domain}.crt" "$SSL_DIR/private/${domain}.key"
                    sudo chmod 644 "$SSL_DIR/certs/${domain}.crt"
                    sudo chmod 600 "$SSL_DIR/private/${domain}.key"
                fi
            fi
        done
    else
        warn "部分证书续期可能失败，请检查日志"
    fi
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

# 导入外部证书（如阿里云证书）
import_certificate() {
    local domain="$1"
    local cert_path="$2"
    local key_path="$3"
    
    if [[ -z "$domain" ]] || [[ -z "$cert_path" ]] || [[ -z "$key_path" ]]; then
        error "用法: import <domain> <cert_file> <key_file>"
        exit 1
    fi
    
    if [[ ! -f "$cert_path" ]]; then
        error "证书文件不存在: $cert_path"
        exit 1
    fi
    
    if [[ ! -f "$key_path" ]]; then
        error "私钥文件不存在: $key_path"
        exit 1
    fi
    
    log "导入域名 $domain 的 SSL 证书..."
    
    # 验证证书
    if ! openssl x509 -in "$cert_path" -text -noout >/dev/null 2>&1; then
        error "无效的证书文件: $cert_path"
        exit 1
    fi
    
    if ! openssl rsa -in "$key_path" -check -noout >/dev/null 2>&1; then
        error "无效的私钥文件: $key_path"
        exit 1
    fi
    
    # 复制到标准位置
    sudo cp "$cert_path" "$SSL_DIR/certs/${domain}.crt"
    sudo cp "$key_path" "$SSL_DIR/private/${domain}.key"
    
    # 设置权限
    sudo chown www:www "$SSL_DIR/certs/${domain}.crt" "$SSL_DIR/private/${domain}.key"
    sudo chmod 644 "$SSL_DIR/certs/${domain}.crt"
    sudo chmod 600 "$SSL_DIR/private/${domain}.key"
    
    success "证书导入成功: $domain"
    
    # 显示证书信息
    local expiry=$(openssl x509 -enddate -noout -in "$SSL_DIR/certs/${domain}.crt" | cut -d= -f2)
    log "证书到期时间: $expiry"
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
    
    # 创建日志目录
    log "创建日志目录..."
    sudo mkdir -p /data/log/ssl /data/ssl
    sudo chown -R root:root /data/log/ssl /data/ssl 2>/dev/null || true
    
    # 创建续期脚本
    local renewal_script="/data/ssl/renew-certs.sh"
    log "创建续期脚本: $renewal_script"
    
    cat > "$renewal_script" << 'EOF'
#!/bin/bash
# SSL 证书自动续期脚本
# 每周一凌晨 2:00 自动运行

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INFRA_ROOT="/opt/infra"

# 记录开始时间
echo "========================================" >> /data/log/ssl/renewal.log
echo "$(date): 开始检查证书续期" >> /data/log/ssl/renewal.log

# 执行续期
cd "$INFRA_ROOT"
"$INFRA_ROOT/scripts/tools/ssl-manager.sh" renew >> /data/log/ssl/renewal.log 2>&1

# 记录完成时间
echo "$(date): 证书续期检查完成" >> /data/log/ssl/renewal.log
echo "========================================" >> /data/log/ssl/renewal.log
EOF
    
    sudo chmod +x "$renewal_script"
    
    # 添加到 crontab
    local crontab_line="0 2 * * 1 $renewal_script"
    
    log "检查现有 crontab 任务..."
    if crontab -l 2>/dev/null | grep -q "$renewal_script"; then
        warn "自动续期任务已存在，跳过添加"
        log "现有任务:"
        crontab -l 2>/dev/null | grep ssl
    else
        log "添加自动续期任务到 crontab..."
        (crontab -l 2>/dev/null || echo "") | grep -v "^$" | cat - <(echo "$crontab_line") | crontab -
        success "✅ 自动续期任务已添加到 crontab"
    fi
    
    echo
    success "🎉 自动续期配置完成！"
    echo
    log "配置详情:"
    log "  📅 运行时间: 每周一凌晨 2:00"
    log "  📜 续期脚本: $renewal_script"
    log "  📝 日志文件: /data/log/ssl/renewal.log"
    echo
    log "查看当前 crontab 任务:"
    crontab -l 2>/dev/null | grep -v "^#" | grep -v "^$" || echo "  (空)"
    echo
    log "💡 提示:"
    log "  - 证书到期前 30 天会自动续期"
    log "  - 手动测试续期: certbot renew --dry-run"
    log "  - 查看续期日志: tail -f /data/log/ssl/renewal.log"
}

# 显示帮助
show_help() {
    cat << EOF
SSL 证书管理工具

用法: $0 <command> [options]

命令:
  wildcard <domain> [email]   申请通配符证书 (*.domain + domain) - 使用阿里云 DNS API
  obtain <domain> [email]     申请单域名证书 - 使用 HTTP 验证
  import <domain> <cert> <key> 导入外部证书（如阿里云证书）
  renew                       续期所有证书
  list                        列出所有证书
  remove <domain>             删除指定域名的证书
  config <domain>             生成 nginx SSL 配置模板
  setup-auto                  设置自动续期
  setup-aliyun                设置阿里云 DNS API 凭证
  
示例:
  # 申请通配符证书（推荐）
  $0 wildcard yangshujie.com yshujie@163.com
  
  # 申请单域名证书
  $0 obtain blog.example.com admin@example.com
  
  # 导入外部证书
  $0 import blog.example.com ./blog.crt ./blog.key
  
  # 续期所有证书
  $0 renew
  
  # 列出所有证书
  $0 list
  
  # 删除证书
  $0 remove blog.example.com
  
  # 生成 nginx 配置
  $0 config blog.example.com > /data/apps/nginx-configs/blog-ssl.conf
  
  # 设置自动续期
  $0 setup-auto

证书类型对比:
  通配符证书 (wildcard):
    ✅ 覆盖主域名和所有子域名: example.com, *.example.com
    ✅ 无需停止 nginx (DNS 验证)
    ✅ 需要阿里云 DNS API 凭证
    ✅ 推荐用于生产环境
  
  单域名证书 (obtain):
    ✅ 仅覆盖指定域名: example.com
    ⚠️  需要临时停止 nginx (HTTP 验证)
    ✅ 无需额外配置
    ✅ 适合测试或单一域名场景

阿里云 DNS API 配置:
  1. 获取 AccessKey: https://ram.console.aliyun.com/users
  2. 授予权限: AliyunDNSFullAccess
  3. 运行: $0 setup-aliyun
  
注意:
- 通配符证书申请需要先配置阿里云 DNS API 凭证
- 域名必须在阿里云 DNS 解析
- 证书有效期 90 天，建议配置自动续期
EOF
}

# 设置阿里云凭证（交互式）
setup_aliyun_credentials() {
    log "设置阿里云 DNS API 凭证..."
    echo
    
    # 创建凭证目录
    mkdir -p "$HOME/.secrets"
    
    # 交互式输入
    echo "请输入阿里云 AccessKey 信息："
    echo "（可从 https://ram.console.aliyun.com/users 获取）"
    echo
    
    read -p "AccessKey ID: " access_key_id
    read -sp "AccessKey Secret: " access_key_secret
    echo
    echo
    
    if [[ -z "$access_key_id" ]] || [[ -z "$access_key_secret" ]]; then
        error "AccessKey 不能为空"
        exit 1
    fi
    
    # 创建凭证文件
    cat > "$ALIYUN_CREDENTIALS" << EOF
# 阿里云 DNS API 凭证
# 用于 Let's Encrypt 通配符证书申请
# 创建时间: $(date)

dns_aliyun_access_key = ${access_key_id}
dns_aliyun_access_key_secret = ${access_key_secret}
EOF
    
    # 设置安全权限
    chmod 600 "$ALIYUN_CREDENTIALS"
    
    success "阿里云凭证配置完成: $ALIYUN_CREDENTIALS"
    log "文件权限已设置为 600（仅所有者可读写）"
    echo
    log "现在可以使用以下命令申请通配符证书："
    echo "  $0 wildcard your-domain.com your-email@example.com"
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
        "wildcard")
            if [[ $# -lt 1 ]]; then
                error "请指定域名"
                echo "用法: $0 wildcard <domain> [email]"
                exit 1
            fi
            check_dependencies
            obtain_wildcard_certificate "$@"
            ;;
        "obtain")
            if [[ $# -lt 1 ]]; then
                error "请指定域名"
                echo "用法: $0 obtain <domain> [email]"
                exit 1
            fi
            check_dependencies
            obtain_certificate "$@"
            ;;
        "import")
            if [[ $# -ne 3 ]]; then
                error "请指定域名、证书文件和私钥文件"
                error "用法: $0 import <domain> <cert_file> <key_file>"
                exit 1
            fi
            import_certificate "$@"
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
        "setup-aliyun")
            setup_aliyun_credentials
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