#!/bin/bash

# gRPC mTLS 证书生成脚本（开发/测试用）
# 默认输出到 /data/infra/ssl/grpc，可通过 CERT_DIR 覆盖

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${CERT_DIR:-${INFRA_DATA_ROOT:-/data/infra}/ssl/grpc}"
CERT_OWNER="${CERT_OWNER:-$((id -u ubuntu >/dev/null 2>&1 && echo ubuntu) || id -un 2>/dev/null || true)}"
CERT_GROUP="${CERT_GROUP:-$((id -u ubuntu >/dev/null 2>&1 && echo ubuntu) || id -gn 2>/dev/null || true)}"

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
    log_info "创建目录: $CERT_DIR/{ca,server,clients}"
    mkdir -p "$CERT_DIR/ca" "$CERT_DIR/server" "$CERT_DIR/clients"
}

generate_root_ca() {
    log_info "生成 Root CA..."
    openssl genrsa -out "$CERT_DIR/ca/root-ca.key" 4096
    openssl req -x509 -new -nodes \
        -key "$CERT_DIR/ca/root-ca.key" \
        -sha256 -days 3650 \
        -out "$CERT_DIR/ca/root-ca.crt" \
        -subj "/C=CN/ST=Shanghai/L=Shanghai/O=Infra/OU=IAM/CN=IAM Root CA (Dev)"
}

generate_intermediate_ca() {
    log_info "生成 Intermediate CA..."
    openssl genrsa -out "$CERT_DIR/ca/intermediate-ca.key" 4096
    openssl req -new \
        -key "$CERT_DIR/ca/intermediate-ca.key" \
        -out "$CERT_DIR/ca/intermediate-ca.csr" \
        -subj "/C=CN/ST=Shanghai/L=Shanghai/O=Infra/OU=IAM/CN=IAM Intermediate CA (Dev)"

    cat > "$CERT_DIR/ca/intermediate-ca.ext" <<EOF
basicConstraints = critical, CA:TRUE, pathlen:0
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always, issuer
EOF

    openssl x509 -req \
        -in "$CERT_DIR/ca/intermediate-ca.csr" \
        -CA "$CERT_DIR/ca/root-ca.crt" \
        -CAkey "$CERT_DIR/ca/root-ca.key" \
        -CAcreateserial \
        -out "$CERT_DIR/ca/intermediate-ca.crt" \
        -days 1825 -sha256 \
        -extfile "$CERT_DIR/ca/intermediate-ca.ext"

    cat "$CERT_DIR/ca/intermediate-ca.crt" "$CERT_DIR/ca/root-ca.crt" > "$CERT_DIR/ca/ca-chain.crt"
    rm -f "$CERT_DIR/ca/intermediate-ca.csr" "$CERT_DIR/ca/intermediate-ca.ext"
}

generate_server_cert() {
    local service_name="${1:-iam-grpc}"
    local ou="${2:-IAM}"
    local cn="${service_name}.svc"
    local alt_dns="${3:-${service_name}.internal.example.com}"
    
    log_info "生成服务端证书: $service_name"
    openssl genrsa -out "$CERT_DIR/server/${service_name}.key" 2048
    openssl req -new \
        -key "$CERT_DIR/server/${service_name}.key" \
        -out "$CERT_DIR/server/${service_name}.csr" \
        -subj "/C=CN/ST=Shanghai/L=Shanghai/O=Infra/OU=${ou}/CN=${cn}"

    cat > "$CERT_DIR/server/${service_name}.ext" <<EOF
basicConstraints = CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid, issuer
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${cn}
DNS.2 = ${alt_dns}
DNS.3 = localhost
DNS.4 = ${service_name}
IP.1 = 127.0.0.1
IP.2 = ::1
EOF

    openssl x509 -req \
        -in "$CERT_DIR/server/${service_name}.csr" \
        -CA "$CERT_DIR/ca/intermediate-ca.crt" \
        -CAkey "$CERT_DIR/ca/intermediate-ca.key" \
        -CAcreateserial \
        -out "$CERT_DIR/server/${service_name}.crt" \
        -days 365 -sha256 \
        -extfile "$CERT_DIR/server/${service_name}.ext"

    cat "$CERT_DIR/server/${service_name}.crt" "$CERT_DIR/ca/intermediate-ca.crt" > "$CERT_DIR/server/${service_name}-fullchain.crt"
    rm -f "$CERT_DIR/server/${service_name}.csr" "$CERT_DIR/server/${service_name}.ext"
}

generate_client_cert() {
    local service_name=$1
    local ou=$2
    local cn="${service_name}.svc"

    log_info "生成客户端证书: $service_name"
    openssl genrsa -out "$CERT_DIR/clients/${service_name}.key" 2048
    openssl req -new \
        -key "$CERT_DIR/clients/${service_name}.key" \
        -out "$CERT_DIR/clients/${service_name}.csr" \
        -subj "/C=CN/ST=Shanghai/L=Shanghai/O=Infra/OU=${ou}/CN=${cn}"

    cat > "$CERT_DIR/clients/${service_name}.ext" <<EOF
basicConstraints = CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid, issuer
subjectAltName = DNS:${cn}
EOF

    openssl x509 -req \
        -in "$CERT_DIR/clients/${service_name}.csr" \
        -CA "$CERT_DIR/ca/intermediate-ca.crt" \
        -CAkey "$CERT_DIR/ca/intermediate-ca.key" \
        -CAcreateserial \
        -out "$CERT_DIR/clients/${service_name}.crt" \
        -days 365 -sha256 \
        -extfile "$CERT_DIR/clients/${service_name}.ext"

    rm -f "$CERT_DIR/clients/${service_name}.csr" "$CERT_DIR/clients/${service_name}.ext"
}

verify_certificates() {
    log_info "验证证书..."
    
    for cert in "$CERT_DIR"/server/*.crt; do
        [[ -f "$cert" ]] && [[ "$cert" != *"-fullchain.crt" ]] || continue
        if openssl verify -CAfile "$CERT_DIR/ca/ca-chain.crt" "$cert" >/dev/null 2>&1; then
            log_info "✅ 服务端证书有效: $(basename "$cert")"
        else
            log_error "❌ 服务端证书验证失败: $(basename "$cert")"
        fi
    done

    for cert in "$CERT_DIR"/clients/*.crt; do
        [[ -f "$cert" ]] || continue
        if openssl verify -CAfile "$CERT_DIR/ca/ca-chain.crt" "$cert" >/dev/null 2>&1; then
            log_info "✅ 客户端证书有效: $(basename "$cert")"
        else
            log_error "❌ 客户端证书验证失败: $(basename "$cert")"
        fi
    done
}

show_cert_info() {
    local cert_file=$1
    log_info "证书信息: $cert_file"
    openssl x509 -in "$cert_file" -noout -subject -issuer -dates -ext subjectAltName 2>/dev/null || true
    echo ""
}

set_permissions() {
    # keys 600, crt/fullchain 644, then chown if可用
    find "$CERT_DIR" -type f -name "*.key" -exec chmod 600 {} +
    find "$CERT_DIR" -type f \( -name "*.crt" -o -name "*fullchain.crt" -o -name "*.pem" \) -exec chmod 644 {} +

    if [[ -n "$CERT_OWNER" || -n "$CERT_GROUP" ]]; then
        local target=""
        if [[ -n "$CERT_OWNER" && -n "$CERT_GROUP" ]]; then
            target="${CERT_OWNER}:${CERT_GROUP}"
        elif [[ -n "$CERT_OWNER" ]]; then
            target="${CERT_OWNER}"
        else
            target=":${CERT_GROUP}"
        fi

        if command -v chown >/dev/null 2>&1; then
            chown -R "$target" "$CERT_DIR" 2>/dev/null || log_warn "chown 失败，可能权限不足（忽略）"
        fi
    fi
}

generate_ca_only() {
    require_openssl
    create_directories

    if [[ -f "$CERT_DIR/ca/root-ca.crt" && "${1:-}" != "force" ]]; then
        log_warn "CA 证书已存在，使用 'force' 参数重新生成"
        exit 1
    fi

    log_info "=== 开始生成 CA 证书 ==="
    generate_root_ca
    generate_intermediate_ca
    set_permissions
    log_info "CA 证书生成完成，路径: $CERT_DIR/ca"
}

generate_server_only() {
    local service_name="${1:-}"
    local ou="${2:-IAM}"
    local alt_dns="${3:-}"
    
    if [[ -z "$service_name" ]]; then
        log_error "请指定服务名称"
        echo "用法: $0 generate-server <service_name> [ou] [alt_dns]"
        echo "示例: $0 generate-server iam-grpc IAM iam-grpc.internal.example.com"
        exit 1
    fi
    
    require_openssl
    
    if [[ ! -f "$CERT_DIR/ca/intermediate-ca.crt" ]]; then
        log_error "CA 证书不存在，请先运行: $0 generate-ca"
        exit 1
    fi
    
    mkdir -p "$CERT_DIR/server"
    log_info "=== 为服务 '$service_name' 生成服务端证书 ==="
    generate_server_cert "$service_name" "$ou" "$alt_dns"
    
    if openssl verify -CAfile "$CERT_DIR/ca/ca-chain.crt" "$CERT_DIR/server/${service_name}.crt" >/dev/null 2>&1; then
        log_info "✅ 服务端证书验证成功"
    else
        log_error "❌ 服务端证书验证失败"
        exit 1
    fi
    
    set_permissions
    log_info "服务端证书生成完成: $CERT_DIR/server/${service_name}.*"
}

generate_all() {
    require_openssl
    create_directories

    if [[ -f "$CERT_DIR/ca/root-ca.crt" && "${1:-}" != "force" ]]; then
        log_warn "证书已存在，使用 'force' 参数重新生成"
        exit 1
    fi

    log_info "=== 开始生成 gRPC mTLS 证书（开发/测试） ==="
    generate_root_ca
    generate_intermediate_ca
    generate_server_cert "iam-grpc" "IAM" "iam-grpc.internal.example.com"
    generate_client_cert "qs" "QS"
    generate_client_cert "admin" "Admin"
    generate_client_cert "ops" "Ops"
    verify_certificates
    set_permissions
    log_info "证书生成完成，路径: $CERT_DIR"
}

clean_all() {
    log_warn "删除证书目录: $CERT_DIR"
    rm -rf "$CERT_DIR/ca" "$CERT_DIR/server" "$CERT_DIR/clients"
}

clean_ca() {
    log_warn "删除 CA 证书: $CERT_DIR/ca"
    rm -rf "$CERT_DIR/ca"
}

clean_server_cert() {
    local service_name="$1"
    local removed=0
    for file in "$CERT_DIR/server/${service_name}.key" \
                "$CERT_DIR/server/${service_name}.crt" \
                "$CERT_DIR/server/${service_name}-fullchain.crt"; do
        if [[ -f "$file" ]]; then
            rm -f "$file"
            log_info "删除服务端证书文件: $file"
            removed=1
        fi
    done
    if [[ $removed -eq 0 ]]; then
        log_warn "未找到服务端证书: $service_name"
    fi
}

clean_client_cert() {
    local service_name="$1"
    local removed=0
    for file in "$CERT_DIR/clients/${service_name}.key" \
                "$CERT_DIR/clients/${service_name}.crt"; do
        if [[ -f "$file" ]]; then
            rm -f "$file"
            log_info "删除客户端证书文件: $file"
            removed=1
        fi
    done
    if [[ $removed -eq 0 ]]; then
        log_warn "未找到客户端证书: $service_name"
    fi
}

clean_target() {
    local scope="${1:-all}"
    local name="${2:-}"

    case "$scope" in
        all) clean_all ;;
        ca) clean_ca ;;
        server)
            if [[ -z "$name" ]]; then
                log_error "请提供服务端证书名称: $0 clean server <name>"
                exit 1
            fi
            clean_server_cert "$name"
            ;;
        client)
            if [[ -z "$name" ]]; then
                log_error "请提供客户端证书名称: $0 clean client <name>"
                exit 1
            fi
            clean_client_cert "$name"
            ;;
        *)
            log_error "未知 clean 范围: $scope，可选 all|ca|server|client"
            exit 1
            ;;
    esac
}

print_help() {
    cat <<EOF
gRPC mTLS 证书生成工具

用法: $0 [command] [options]

命令:
    generate-ca                生成 Root CA 和 Intermediate CA
    generate-server <name> [ou] [alt_dns]  生成服务端证书
        <name>      服务名称（必需）
        [ou]        组织单元，默认 IAM
        [alt_dns]   额外的 DNS 名称（可选）
        
    generate               生成所有证书（CA + 默认服务端 + 客户端）
    force                  强制重新生成所有证书
    clean [scope] [name]   删除证书（scope: all|ca|server|client）
    verify                 验证证书有效性
    info                   查看证书信息
    help                   显示帮助

示例:
    # 1. 生成 CA 证书
    $0 generate-ca
    
    # 2. 为不同服务生成证书
    $0 generate-server iam-grpc IAM iam-grpc.internal.example.com
    $0 generate-server user-api User user-api.internal.example.com
    $0 generate-server order-api Order
    
    # 3. 生成所有证书（一键）
    $0 generate

    # 4. 按需清理证书
    $0 clean all
    $0 clean ca
    $0 clean server iam-grpc
    $0 clean client qs

环境变量:
    CERT_DIR        证书输出目录，默认 ${CERT_DIR}
    INFRA_DATA_ROOT 影响 CERT_DIR 默认值
    CERT_OWNER      证书文件 chown 用户（默认 ubuntu，如不存在则当前用户）
    CERT_GROUP      证书文件 chown 用户组（默认 ubuntu，如不存在则当前组）
EOF
}

main() {
    case "${1:-generate}" in
        generate-ca) generate_ca_only "${2:-}" ;;
        generate-server) shift; generate_server_only "$@" ;;
        generate) generate_all ;;
        force) clean_all; generate_all force ;;
        clean) shift; clean_target "$@" ;;
        verify) verify_certificates ;;
        info)
            while IFS= read -r cert; do
                show_cert_info "$cert"
            done < <(find "$CERT_DIR" -type f -name "*.crt" 2>/dev/null)
            ;;
        help|--help|-h) print_help ;;
        *) log_error "未知命令: $1"; print_help; exit 1 ;;
    esac
}

main "$@"
