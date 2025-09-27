#!/bin/bash

# 静态文件功能测试脚本
# 测试 setup-network.sh 中的静态文件检测和使用逻辑

set -euo pipefail

# 颜色输出函数
log_info() { echo -e "\033[34m[INFO]\033[0m $*"; }
log_success() { echo -e "\033[32m[SUCCESS]\033[0m $*"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $*"; }
log_error() { echo -e "\033[31m[ERROR]\033[0m $*"; }

# 获取项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATIC_DIR="$PROJECT_ROOT/static"
TEST_DATA_DIR="/tmp/mihomo_test_data"

log_info "=========================================="
log_info "setup-network.sh 静态文件功能测试"
log_info "=========================================="
echo

# 1. 测试静态文件检测
log_info "1. 测试静态文件检测逻辑"
echo "项目根目录: $PROJECT_ROOT"
echo "静态文件目录: $STATIC_DIR"

# 检查静态文件是否存在
if [[ -d "$STATIC_DIR" ]]; then
    log_success "✅ 静态文件目录存在"
    ls -lh "$STATIC_DIR"
    echo
    
    # 检查具体文件
    files_found=0
    
    if [[ -f "$STATIC_DIR/geosite.dat" ]]; then
        size=$(stat -f%z "$STATIC_DIR/geosite.dat" 2>/dev/null || echo "0")
        log_success "✅ geosite.dat 存在 (${size} bytes)"
        files_found=$((files_found + 1))
    fi
    
    if [[ -f "$STATIC_DIR/geoip.metadb" ]]; then
        size=$(stat -f%z "$STATIC_DIR/geoip.metadb" 2>/dev/null || echo "0")
        log_success "✅ geoip.metadb 存在 (${size} bytes)"
        files_found=$((files_found + 1))
    fi
    
    if [[ $files_found -eq 2 ]]; then
        log_success "✅ 所有必需的静态文件都存在"
    else
        log_warn "⚠️  缺少 $((2 - files_found)) 个静态文件"
    fi
else
    log_error "❌ 静态文件目录不存在"
fi

echo

# 2. 测试文件复制逻辑
log_info "2. 测试文件复制逻辑"

# 创建测试目录
mkdir -p "$TEST_DATA_DIR"
log_info "创建测试目录: $TEST_DATA_DIR"

# 模拟复制操作
if [[ -f "$STATIC_DIR/geosite.dat" ]] && [[ -f "$STATIC_DIR/geoip.metadb" ]]; then
    log_info "测试复制静态文件..."
    
    # 复制 geosite.dat
    if cp "$STATIC_DIR/geosite.dat" "$TEST_DATA_DIR/GeoSite.dat" 2>/dev/null; then
        log_success "✅ GeoSite.dat 复制成功"
    else
        log_error "❌ GeoSite.dat 复制失败"
    fi
    
    # 复制 geoip.metadb
    if cp "$STATIC_DIR/geoip.metadb" "$TEST_DATA_DIR/GeoIP.metadb" 2>/dev/null; then
        log_success "✅ GeoIP.metadb 复制成功"
    else
        log_error "❌ GeoIP.metadb 复制失败"
    fi
    
    # 验证复制结果
    echo
    log_info "复制后的文件:"
    ls -lh "$TEST_DATA_DIR/"
    
else
    log_warn "⚠️  静态文件不完整，跳过复制测试"
fi

echo

# 3. 测试路径检测逻辑（模拟 init-server 子目录调用）
log_info "3. 测试子目录路径检测"

# 模拟从 scripts/init-server/ 目录调用
cd "$PROJECT_ROOT/scripts/init-server"

# 模拟 setup-network.sh 中的路径检测逻辑
script_dir="$(cd ../.. && pwd)"
static_dir="$script_dir/static"

echo "当前工作目录: $(pwd)"
echo "脚本检测的项目根目录: $script_dir"
echo "静态文件目录: $static_dir"

if [[ "$script_dir" == "$PROJECT_ROOT" ]]; then
    log_success "✅ 路径检测正确"
else
    log_error "❌ 路径检测错误"
    echo "  预期: $PROJECT_ROOT"
    echo "  实际: $script_dir"
fi

echo

# 4. 测试文件名大小写处理
log_info "4. 测试文件名大小写处理"

# 检查大写文件名
if [[ -f "$static_dir/GeoSite.dat" ]] || [[ -f "$static_dir/geosite.dat" ]]; then
    log_success "✅ GeoSite 文件检测正常（支持大小写）"
else
    log_error "❌ GeoSite 文件检测失败"
fi

if [[ -f "$static_dir/GeoIP.metadb" ]] || [[ -f "$static_dir/geoip.metadb" ]]; then
    log_success "✅ GeoIP 文件检测正常（支持大小写）"
else
    log_error "❌ GeoIP 文件检测失败"
fi

echo

# 5. 清理测试环境
log_info "5. 清理测试环境"
rm -rf "$TEST_DATA_DIR"
log_success "✅ 测试环境清理完成"

echo
log_info "=========================================="
log_success "静态文件功能测试完成！"
log_info "=========================================="

# 返回原始目录
cd "$PROJECT_ROOT"