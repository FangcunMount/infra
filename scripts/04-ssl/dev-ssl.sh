#!/bin/bash

# 开发环境 SSL 证书生成脚本（自签名）
# 用于本地/内网开发环境的 HTTPS 访问

set -euo pipefail

DOMAIN="${1:-localhost}"
SSL_DIR="${SSL_DIR:-${INFRA_DATA_ROOT:-/data/infra}/ssl/web}"
DAYS="${DAYS:-365}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

require_openssl() {
    if ! command -v openssl >/dev/null 2>&1; then
        log_error "openssl 未安装，请先安装 openssl"
        exit 1
    fi
}

create_directories() {
    log_info "创建证书目录: $SSL_DIR"
    mkdir -p "$SSL_DIR"
}

generate_self_signed_cert() {
    local domain="$1"
    local cert_file="$SSL_DIR/${domain}.crt"
    local key_file="$SSL_DIR/${domain}.key"
    
    if [[ -f "$cert_file" && "${2:-}" != "force" ]]; then
        log_warn "证书已存在: $cert_file"
        log_warn "如需重新生成，请使用 'force' 参数"
        exit 1
    fi
    
    log_info "为域名 '$domain' 生成自签名证书（有效期 $DAYS 天）..."
    
    # 生成自签名证书
    openssl req -x509 -nodes -days "$DAYS" \
        -newkey rsa:2048 \
        -keyout "$key_file" \
        -out "$cert_file" \
        -subj "/C=CN/ST=Shanghai/L=Shanghai/O=Dev/OU=Development/CN=${domain}" \
        -addext "subjectAltName=DNS:${domain},DNS:*.${domain},DNS:localhost,IP:127.0.0.1,IP:::1"
    
    # 设置权限
    chmod 600 "$key_file"
    chmod 644 "$cert_file"
    
    log_info "✅ 证书生成完成:"
    echo "   📄 证书: $cert_file"
    echo "   🔑 私钥: $key_file"
    echo ""
    
    # 显示证书信息
    log_info "证书详情:"
    openssl x509 -in "$cert_file" -noout -subject -issuer -dates -ext subjectAltName
    echo ""
    
    log_warn "⚠️  这是自签名证书，浏览器会显示安全警告"
    log_warn "   开发环境可以忽略，或在浏览器中手动信任此证书"
    echo ""
    log_info "💡 如需消除浏览器警告，建议使用 mkcert:"
    echo "   brew install mkcert  # macOS"
    echo "   mkcert -install"
    echo "   mkcert $domain"
}

verify_cert() {
    local domain="$1"
    local cert_file="$SSL_DIR/${domain}.crt"
    
    if [[ ! -f "$cert_file" ]]; then
        log_error "证书不存在: $cert_file"
        exit 1
    fi
    
    log_info "验证证书: $domain"
    openssl x509 -in "$cert_file" -noout -text
}

list_certs() {
    log_info "开发环境证书列表 ($SSL_DIR):"
    echo ""
    
    if [[ ! -d "$SSL_DIR" ]]; then
        log_warn "证书目录不存在: $SSL_DIR"
        return
    fi
    
    local found=0
    for cert in "$SSL_DIR"/*.crt; do
        [[ -f "$cert" ]] || continue
        found=1
        local domain=$(basename "$cert" .crt)
        echo "📄 $domain"
        openssl x509 -in "$cert" -noout -subject -dates -ext subjectAltName 2>/dev/null | sed 's/^/   /'
        echo ""
    done
    
    if [[ $found -eq 0 ]]; then
        log_warn "未找到任何证书"
    fi
}

remove_cert() {
    local domain="$1"
    local cert_file="$SSL_DIR/${domain}.crt"
    local key_file="$SSL_DIR/${domain}.key"
    
    if [[ ! -f "$cert_file" && ! -f "$key_file" ]]; then
        log_warn "证书不存在: $domain"
        exit 1
    fi
    
    log_warn "删除证书: $domain"
    rm -f "$cert_file" "$key_file"
    log_info "✅ 证书已删除"
}

print_help() {
    cat <<EOF
开发环境 SSL 证书生成工具（自签名）

用法: $0 [command] [options]

命令:
    generate <domain>      生成自签名证书（默认命令）
    force <domain>         强制重新生成证书
    verify <domain>        验证并显示证书详情
    list                   列出所有证书
    remove <domain>        删除指定证书
    help                   显示帮助

参数:
    <domain>               域名，默认 localhost

环境变量:
    SSL_DIR                证书输出目录，默认 /data/infra/ssl/web
    INFRA_DATA_ROOT        影响 SSL_DIR 默认值
    DAYS                   证书有效期（天），默认 365

示例:
    # 生成 localhost 证书
    $0 generate localhost
    
    # 生成自定义域名证书（支持通配符）
    $0 generate dev.local
    $0 generate api.internal
    
    # 列出所有证书
    $0 list
    
    # 强制重新生成
    $0 force dev.local
    
    # 删除证书
    $0 remove dev.local

说明:
    - 自签名证书适用于开发/测试环境
    - 浏览器会显示安全警告，但不影响功能
    - 证书包含 SAN：域名、通配符、localhost、127.0.0.1
    - 生产环境请使用 ssl-manager.sh 申请 Let's Encrypt 证书
EOF
}

main() {
    require_openssl
    
    case "${1:-generate}" in
        generate)
            create_directories
            generate_self_signed_cert "${2:-localhost}"
            ;;
        force)
            if [[ -z "${2:-}" ]]; then
                log_error "请指定域名"
                echo "用法: $0 force <domain>"
                exit 1
            fi
            create_directories
            generate_self_signed_cert "$2" "force"
            ;;
        verify)
            if [[ -z "${2:-}" ]]; then
                log_error "请指定域名"
                echo "用法: $0 verify <domain>"
                exit 1
            fi
            verify_cert "$2"
            ;;
        list)
            list_certs
            ;;
        remove)
            if [[ -z "${2:-}" ]]; then
                log_error "请指定域名"
                echo "用法: $0 remove <domain>"
                exit 1
            fi
            remove_cert "$2"
            ;;
        help|--help|-h)
            print_help
            ;;
        *)
            # 如果第一个参数不是命令，当作域名处理
            if [[ ! "$1" =~ ^- ]]; then
                create_directories
                generate_self_signed_cert "$1"
            else
                log_error "未知命令: $1"
                print_help
                exit 1
            fi
            ;;
    esac
}

main "$@"
