#!/bin/bash

# 测试静态文件检查功能
# 此脚本用于验证 setup-network.sh 中的静态文件检查逻辑

set -e

echo "=== 测试静态文件检查功能 ==="
echo

# 获取脚本目录
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
static_dir="$script_dir/static"

echo "项目根目录: $script_dir"
echo "静态文件目录: $static_dir"
echo

# 检测系统架构
arch=$(uname -m)
case $arch in
    x86_64)
        arch="amd64"
        ;;
    aarch64|arm64)
        arch="arm64"
        ;;
    *)
        echo "不支持的架构: $arch"
        exit 1
        ;;
esac

echo "检测架构: $arch"
target_file="mihomo-linux-$arch"
target_path="$static_dir/$target_file"
echo "目标文件: $target_file"
echo "目标路径: $target_path"
echo

# 测试场景1：static 目录不存在
echo "--- 测试场景1：static 目录不存在 ---"
if [[ -d "$static_dir" ]]; then
    echo "static 目录存在"
else
    echo "static 目录不存在，这是正常情况"
fi
echo

# 测试场景2：static 目录存在但为空
echo "--- 测试场景2：检查 static 目录内容 ---"
if [[ -d "$static_dir" ]]; then
    echo "static 目录内容:"
    if ls -la "$static_dir" 2>/dev/null; then
        echo
        echo "mihomo 相关文件:"
        ls -la "$static_dir"/mihomo* 2>/dev/null || echo "  未找到 mihomo 文件"
    else
        echo "  目录为空或无法访问"
    fi
else
    echo "static 目录不存在"
fi
echo

# 测试场景3：检查目标文件
echo "--- 测试场景3：检查目标文件 ---"
if [[ -f "$target_path" ]]; then
    echo "✅ 找到目标文件: $target_path"
    
    # 文件大小
    file_size=$(stat -c%s "$target_path" 2>/dev/null || stat -f%z "$target_path" 2>/dev/null || echo "0")
    file_size_mb=$((file_size / 1024 / 1024))
    echo "文件大小: ${file_size_mb}MB (${file_size} bytes)"
    
    # 文件权限
    if [[ -x "$target_path" ]]; then
        echo "✅ 文件具有执行权限"
    else
        echo "⚠️  文件需要添加执行权限"
    fi
    
    # 文件详细信息
    echo "文件详细信息:"
    ls -la "$target_path"
else
    echo "❌ 未找到目标文件: $target_path"
fi
echo

# 建议操作
echo "--- 建议操作 ---"
if [[ ! -d "$static_dir" ]]; then
    echo "1. 创建 static 目录:"
    echo "   mkdir -p $static_dir"
    echo
fi

if [[ ! -f "$target_path" ]]; then
    echo "2. 下载 mihomo 二进制文件:"
    echo "   ./download-mihomo-binaries.sh"
    echo
    echo "3. 或者手动下载到:"
    echo "   $target_path"
    echo
fi

echo "4. 测试 setup-network.sh 脚本:"
echo "   # 设置测试模式（不实际安装）"
echo "   export DEBUG=true"
echo "   ./setup-network.sh"
echo

echo "=== 测试完成 ==="