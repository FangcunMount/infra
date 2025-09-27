#!/usr/bin/env bash
set -euo pipefail

# 下载 mihomo 二进制文件到 static 目录
# 支持多架构：amd64, arm64, armv7

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATIC_DIR="$SCRIPT_DIR/../../static"
TEMP_DIR="/tmp/mihomo-download"

log() { echo "[$(date '+%H:%M:%S')] $1"; }

# 创建目录
mkdir -p "$STATIC_DIR"
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"
cd "$TEMP_DIR"

echo "=== 下载 mihomo 二进制文件 ==="
echo

# 获取最新版本
log "获取最新版本信息..."
LATEST_VERSION=$(curl -s "https://api.github.com/repos/MetaCubeX/mihomo/releases/latest" | grep '"tag_name"' | cut -d'"' -f4)
if [[ -z "$LATEST_VERSION" ]]; then
    echo "❌ 无法获取最新版本信息"
    exit 1
fi

log "最新版本: $LATEST_VERSION"
echo

# 下载多架构版本
architectures=("amd64" "arm64" "armv7")

for arch in "${architectures[@]}"; do
    log "下载 $arch 架构..."
    
    filename="mihomo-linux-$arch-$LATEST_VERSION.gz"
    download_url="https://github.com/MetaCubeX/mihomo/releases/latest/download/$filename"
    
    if curl -fL "$download_url" -o "$filename"; then
        log "✅ 下载成功: $filename"
        
        # 解压
        gunzip "$filename"
        extracted_name="mihomo-linux-$arch-$LATEST_VERSION"
        target_name="mihomo-linux-$arch"
        
        # 移动到 static 目录
        if [[ -f "$extracted_name" ]]; then
            mv "$extracted_name" "$STATIC_DIR/$target_name"
            chmod +x "$STATIC_DIR/$target_name"
            log "✅ 已保存到: $STATIC_DIR/$target_name"
        else
            log "❌ 解压失败: $extracted_name"
        fi
    else
        log "❌ 下载失败: $filename"
    fi
    echo
done

# 清理临时目录
cd /
rm -rf "$TEMP_DIR"

echo "=== 下载完成 ==="
echo "文件位置: $STATIC_DIR"
ls -la "$STATIC_DIR"/mihomo-* 2>/dev/null || echo "没有找到 mihomo 文件"
echo

echo "现在可以在内网环境中使用这些二进制文件了！"