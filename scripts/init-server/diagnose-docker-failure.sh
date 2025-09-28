#!/bin/bash

# Docker 服务启动失败诊断脚本
# 用于分析 Docker 服务无法启动的原因

set -euo pipefail

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo "========================================"
echo "🔧 Docker 服务启动失败诊断"
echo "========================================"

# 检查 Docker 服务状态
log_info "检查 Docker 服务状态..."
systemctl status docker.service --no-pager -l || true

echo
echo "========================================"

# 查看 Docker 服务日志
log_info "查看 Docker 服务启动日志（最近20条）..."
journalctl -xeu docker.service -n 20 --no-pager || true

echo
echo "========================================"

# 检查 Docker daemon 配置文件
log_info "检查 Docker daemon 配置文件..."
if [[ -f /etc/docker/daemon.json ]]; then
    log_info "Docker daemon 配置文件存在: /etc/docker/daemon.json"
    echo "配置文件内容:"
    cat /etc/docker/daemon.json
    
    # 验证 JSON 语法
    if command -v jq >/dev/null 2>&1; then
        if jq . /etc/docker/daemon.json >/dev/null 2>&1; then
            log_success "✅ JSON 语法正确"
        else
            log_error "❌ JSON 语法错误"
            echo "JSON 语法检查："
            jq . /etc/docker/daemon.json || true
        fi
    else
        log_warn "⚠️  jq 未安装，无法验证 JSON 语法"
        log_info "可以使用 python3 验证："
        python3 -m json.tool /etc/docker/daemon.json >/dev/null 2>&1 && log_success "✅ JSON 语法正确" || log_error "❌ JSON 语法错误"
    fi
else
    log_warn "⚠️  Docker daemon 配置文件不存在"
fi

echo
echo "========================================"

# 检查 systemd 配置
log_info "检查 Docker systemd 配置..."
if [[ -d /etc/systemd/system/docker.service.d ]]; then
    log_info "systemd 覆盖配置目录存在"
    for conf_file in /etc/systemd/system/docker.service.d/*.conf; do
        if [[ -f "$conf_file" ]]; then
            log_info "配置文件: $conf_file"
            cat "$conf_file"
        fi
    done
else
    log_info "无 systemd 覆盖配置"
fi

echo
echo "========================================"

# 检查端口占用
log_info "检查端口占用情况..."
if command -v netstat >/dev/null 2>&1; then
    log_info "检查常见 Docker 端口占用..."
    netstat -tlnp | grep -E ':(2375|2376|2377)' || log_info "Docker 管理端口未被占用"
else
    log_warn "⚠️  netstat 不可用，跳过端口检查"
fi

echo
echo "========================================"

# 检查存储驱动
log_info "检查存储相关配置..."
if [[ -d /var/lib/docker ]]; then
    log_info "Docker 数据目录存在: /var/lib/docker"
    log_info "目录权限: $(ls -ld /var/lib/docker)"
    log_info "磁盘使用情况:"
    df -h /var/lib/docker
else
    log_warn "⚠️  Docker 数据目录不存在"
fi

echo
echo "========================================"

# 检查进程冲突
log_info "检查进程冲突..."
if pgrep dockerd >/dev/null 2>&1; then
    log_warn "⚠️  发现 dockerd 进程仍在运行"
    ps aux | grep dockerd | grep -v grep
fi

if pgrep containerd >/dev/null 2>&1; then
    log_info "containerd 进程运行中（正常）"
else
    log_warn "⚠️  containerd 进程未运行"
fi

echo
echo "========================================"

# 检查内核模块
log_info "检查内核模块..."
required_modules=("overlay" "br_netfilter")
for module in "${required_modules[@]}"; do
    if lsmod | grep -q "$module"; then
        log_success "✅ 内核模块 $module 已加载"
    else
        log_warn "⚠️  内核模块 $module 未加载"
        log_info "尝试加载: modprobe $module"
        modprobe "$module" 2>/dev/null && log_success "✅ $module 模块加载成功" || log_error "❌ $module 模块加载失败"
    fi
done

echo
echo "========================================"

# 检查 cgroup
log_info "检查 cgroup 配置..."
if [[ -d /sys/fs/cgroup ]]; then
    log_info "cgroup 文件系统可用"
    if mount | grep -q cgroup2; then
        log_info "使用 cgroup v2"
    else
        log_info "使用 cgroup v1"
    fi
else
    log_error "❌ cgroup 文件系统不可用"
fi

echo
echo "========================================"
log_info "💡 常见解决方案："
echo

echo "1. 📋 配置文件问题："
echo "   • 备份配置: cp /etc/docker/daemon.json /etc/docker/daemon.json.bak"
echo "   • 重置配置: echo '{}' > /etc/docker/daemon.json"
echo "   • 重启服务: systemctl restart docker"

echo
echo "2. 🔄 服务冲突："
echo "   • 停止所有 Docker 进程: pkill dockerd"
echo "   • 重新加载配置: systemctl daemon-reload"
echo "   • 启动服务: systemctl start docker"

echo
echo "3. 🗂️ 权限问题："
echo "   • 检查目录权限: ls -la /var/lib/docker"
echo "   • 重置权限: chown -R root:root /var/lib/docker"
echo "   • 重新启动: systemctl restart docker"

echo
echo "4. 🧹 完全重置："
echo "   • 停止服务: systemctl stop docker"
echo "   • 清理数据: rm -rf /var/lib/docker"
echo "   • 重新启动: systemctl start docker"

echo
echo "5. 📝 手动启动测试："
echo "   • 停止服务: systemctl stop docker"
echo "   • 手动启动: dockerd --debug"
echo "   • 查看详细错误信息"

echo
log_info "🔧 自动修复尝试："

# 尝试修复 JSON 配置
if [[ -f /etc/docker/daemon.json ]]; then
    if ! python3 -m json.tool /etc/docker/daemon.json >/dev/null 2>&1; then
        log_warn "⚠️  检测到 JSON 语法错误，尝试修复..."
        cp /etc/docker/daemon.json /etc/docker/daemon.json.error
        echo '{}' > /etc/docker/daemon.json
        log_info "已重置配置文件，原文件备份为 daemon.json.error"
    fi
fi

# 重新加载 systemd 配置
systemctl daemon-reload

# 尝试启动 Docker 服务
log_info "尝试重新启动 Docker 服务..."
if systemctl start docker; then
    log_success "✅ Docker 服务启动成功"
    systemctl status docker --no-pager -l
else
    log_error "❌ Docker 服务仍然无法启动"
    log_info "请根据上述诊断信息手动排查问题"
fi

echo
log_info "诊断完成！"