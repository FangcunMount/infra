#!/bin/bash

# 测试 setup-network.sh 中的静态文件检查逻辑
# 只运行 install_mihomo_binary 函数的静态文件检查部分

set -e

# 导入日志函数
log_info() { echo "[$(date '+%H:%M:%S')] ℹ️  $1"; }
log_success() { echo "[$(date '+%H:%M:%S')] ✅ $1"; }
log_warn() { echo "[$(date '+%H:%M:%S')] ⚠️  $1"; }
log_error() { echo "[$(date '+%H:%M:%S')] ❌ $1"; }
log_debug() { 
    if [[ "${DEBUG:-}" == "true" ]]; then
        echo "[$(date '+%H:%M:%S')] 🐛 $1"; 
    fi
}

# 模拟 install_mihomo_binary 函数中的静态文件检查部分
test_static_file_check() {
    echo "=== 测试 setup-network.sh 静态文件检查功能 ==="
    echo
    
    # 检测架构
    local arch=$(uname -m)
    case $arch in
        x86_64)
            arch="amd64"
            ;;
        aarch64|arm64)
            arch="arm64"
            ;;
        armv7l)
            arch="armv7"
            ;;
        *)
            log_error "不支持的架构: $arch"
            exit 1
            ;;
    esac
    
    log_info "系统架构: $arch"
    
    # 检查本地静态文件
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    local static_dir="$script_dir/static"
    local static_binary="$static_dir/mihomo-linux-$arch"
    
    log_info "检查本地静态文件..."
    log_info "静态文件目录: $static_dir"
    log_info "目标文件: mihomo-linux-$arch"
    
    # 列出 static 目录中的 mihomo 相关文件
    if [[ -d "$static_dir" ]]; then
        local mihomo_files
        mihomo_files=$(ls -la "$static_dir"/mihomo* 2>/dev/null || true)
        if [[ -n "$mihomo_files" ]]; then
            log_info "发现的 mihomo 文件:"
            echo "$mihomo_files" | while read -r line; do
                echo "  $line"
            done
        else
            log_info "static 目录中没有找到 mihomo 文件"
        fi
    else
        log_warn "静态文件目录不存在: $static_dir"
    fi
    
    echo
    
    # 优先使用本地静态文件
    if [[ -f "$static_binary" ]]; then
        log_success "✅ 找到本地静态二进制文件: $static_binary"
        
        # 检查文件大小
        local file_size
        file_size=$(stat -c%s "$static_binary" 2>/dev/null || stat -f%z "$static_binary" 2>/dev/null || echo "0")
        log_info "文件大小: $(( file_size / 1024 / 1024 )) MB"
        
        # 检查文件权限
        if [[ -x "$static_binary" ]]; then
            log_info "文件已具有执行权限"
        else
            log_info "文件需要添加执行权限"
        fi
        
        log_info "模拟：使用本地静态二进制文件..."
        log_success "✅ 本地静态文件检查通过"
        
        echo
        log_info "在实际运行中，此时会："
        echo "  1. 复制文件到临时目录"
        echo "  2. 设置执行权限" 
        echo "  3. 验证文件可执行性"
        echo "  4. 安装到系统目录"
        
    else
        log_warn "❌ 未找到本地静态二进制文件: $static_binary"
        
        # 提供详细的解决方案
        echo
        log_info "解决方案："
        echo "  方案1 - 使用预下载脚本（推荐）:"
        echo "    ./download-mihomo-binaries.sh"
        echo
        echo "  方案2 - 手动下载到 static 目录:"
        echo "    mkdir -p $static_dir"
        echo "    # 然后下载对应架构的文件到:"
        echo "    # $static_binary"
        echo
        echo "  方案3 - 在线下载（需要网络连接）"
        echo
        
        log_info "在实际运行中，此时会尝试从 GitHub 在线下载"
    fi
    
    echo
    echo "=== 静态文件检查测试完成 ==="
}

# 运行测试
export DEBUG=true
test_static_file_check