#!/bin/bash

# 更新静态地理数据文件脚本
# 用于定期更新 mihomo 所需的地理数据文件

set -euo pipefail

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATIC_DIR="$SCRIPT_DIR/static"

# 颜色输出函数
log_info() {
    echo -e "\033[34m[INFO]\033[0m $*"
}

log_success() {
    echo -e "\033[32m[SUCCESS]\033[0m $*"
}

log_warn() {
    echo -e "\033[33m[WARN]\033[0m $*"
}

log_error() {
    echo -e "\033[31m[ERROR]\033[0m $*"
}

log_step() {
    echo -e "\n\033[36m[STEP]\033[0m $*"
}

# 检查网络连接
check_network() {
    log_step "检查网络连接..."
    
    if ! curl -s --connect-timeout 5 --max-time 10 "https://api.github.com" >/dev/null; then
        log_error "无法连接到 GitHub，请检查网络连接"
        exit 1
    fi
    
    log_success "网络连接正常"
}

# 创建静态目录
create_static_dir() {
    if [[ ! -d "$STATIC_DIR" ]]; then
        log_info "创建静态文件目录: $STATIC_DIR"
        mkdir -p "$STATIC_DIR"
    fi
}

# 备份现有文件
backup_existing_files() {
    local backup_needed=false
    
    if [[ -f "$STATIC_DIR/GeoSite.dat" ]] || [[ -f "$STATIC_DIR/GeoIP.metadb" ]]; then
        backup_needed=true
    fi
    
    if [[ "$backup_needed" == "true" ]]; then
        log_step "备份现有文件..."
        local backup_dir="$STATIC_DIR/backup-$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$backup_dir"
        
        if [[ -f "$STATIC_DIR/GeoSite.dat" ]]; then
            cp "$STATIC_DIR/GeoSite.dat" "$backup_dir/"
            log_info "已备份 GeoSite.dat"
        fi
        
        if [[ -f "$STATIC_DIR/GeoIP.metadb" ]]; then
            cp "$STATIC_DIR/GeoIP.metadb" "$backup_dir/"
            log_info "已备份 GeoIP.metadb"
        fi
        
        log_success "文件备份完成: $backup_dir"
    fi
}

# 下载文件函数
download_file() {
    local filename="$1"
    local url="$2"
    local output_path="$STATIC_DIR/$filename"
    
    log_info "下载 $filename..."
    log_info "URL: $url"
    
    # 使用临时文件下载
    local temp_file="${output_path}.tmp"
    
    if curl -L --connect-timeout 10 --max-time 300 --retry 3 --retry-delay 2 \
       --progress-bar --output "$temp_file" "$url"; then
        
        # 验证文件大小
        local file_size
        file_size=$(stat -c%s "$temp_file" 2>/dev/null || stat -f%z "$temp_file" 2>/dev/null || echo "0")
        
        if [[ "$file_size" -gt 10000 ]]; then  # 至少10KB
            mv "$temp_file" "$output_path"
            log_success "✅ $filename 下载完成 (${file_size} bytes)"
            return 0
        else
            log_error "下载的文件过小，可能下载失败"
            rm -f "$temp_file"
            return 1
        fi
    else
        log_error "下载失败: $filename"
        rm -f "$temp_file"
        return 1
    fi
}

# 下载地理数据文件
download_geodata_files() {
    log_step "下载地理数据文件..."
    
    # 定义下载源
    local geosite_urls=(
        "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat"
        "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geosite.dat"
        "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/release/geosite.dat"
    )
    
    local geoip_urls=(
        "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.metadb"
        "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.metadb"
        "https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/release/geoip.metadb"
    )
    
    # 下载 GeoSite.dat
    local geosite_success=false
    for url in "${geosite_urls[@]}"; do
        if download_file "GeoSite.dat" "$url"; then
            geosite_success=true
            break
        else
            log_warn "从 $url 下载失败，尝试下一个源..."
        fi
    done
    
    if [[ "$geosite_success" != "true" ]]; then
        log_error "GeoSite.dat 从所有源下载失败"
        return 1
    fi
    
    # 下载 GeoIP.metadb
    local geoip_success=false
    for url in "${geoip_urls[@]}"; do
        if download_file "GeoIP.metadb" "$url"; then
            geoip_success=true
            break
        else
            log_warn "从 $url 下载失败，尝试下一个源..."
        fi
    done
    
    if [[ "$geoip_success" != "true" ]]; then
        log_error "GeoIP.metadb 从所有源下载失败"
        return 1
    fi
    
    log_success "所有地理数据文件下载完成"
}

# 验证文件
verify_files() {
    log_step "验证下载的文件..."
    
    local files=("GeoSite.dat" "GeoIP.metadb")
    local all_valid=true
    
    for file in "${files[@]}"; do
        local file_path="$STATIC_DIR/$file"
        
        if [[ ! -f "$file_path" ]]; then
            log_error "文件不存在: $file"
            all_valid=false
            continue
        fi
        
        local file_size
        file_size=$(stat -c%s "$file_path" 2>/dev/null || stat -f%z "$file_path" 2>/dev/null || echo "0")
        
        if [[ "$file_size" -lt 10000 ]]; then
            log_error "文件过小: $file ($file_size bytes)"
            all_valid=false
        else
            log_success "✅ $file 验证通过 ($file_size bytes)"
        fi
    done
    
    if [[ "$all_valid" != "true" ]]; then
        log_error "文件验证失败"
        return 1
    fi
    
    log_success "所有文件验证通过"
}

# 设置文件权限
set_permissions() {
    log_step "设置文件权限..."
    
    chmod 644 "$STATIC_DIR"/*.dat "$STATIC_DIR"/*.metadb 2>/dev/null || true
    
    log_success "文件权限设置完成"
}

# 显示完成信息
show_completion_info() {
    echo
    log_success "=========================================="
    log_success "静态文件更新完成！"
    log_success "=========================================="
    echo
    log_info "文件位置: $STATIC_DIR"
    echo
    ls -lh "$STATIC_DIR"/*.dat "$STATIC_DIR"/*.metadb 2>/dev/null || true
    echo
    log_info "使用说明："
    echo "  1. 这些文件将被 setup-network.sh 自动使用"
    echo "  2. 适用于内网和外网环境部署"
    echo "  3. 建议定期运行此脚本更新文件"
    echo
    log_info "下次更新："
    echo "  ./scripts/update-static-files.sh"
}

# 主函数
main() {
    log_info "=========================================="
    log_info "静态地理数据文件更新脚本"
    log_info "执行时间: $(date)"
    log_info "=========================================="
    
    # 用户确认
    echo
    log_warn "此脚本将下载最新的地理数据文件："
    echo "  • GeoSite.dat - 域名分流规则数据库"
    echo "  • GeoIP.metadb - IP地址地理位置数据库"
    echo
    echo "文件将保存到: $STATIC_DIR"
    echo
    
    read -p "确认继续？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "用户取消操作"
        exit 0
    fi
    
    # 执行更新步骤
    check_network
    create_static_dir
    backup_existing_files
    download_geodata_files
    verify_files
    set_permissions
    show_completion_info
    
    log_success "静态文件更新任务完成！"
}

# 执行主函数
main "$@"