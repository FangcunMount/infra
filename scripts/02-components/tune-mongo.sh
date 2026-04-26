#!/usr/bin/env bash
#
# MongoDB 系统调优脚本（宿主机执行）
# 适用于 ServerC (4C/4G) 单机 Mongo 生产环境
#
# 用途：
# 1. 禁用透明大页（THP） - MongoDB WiredTiger 不推荐使用 THP
# 2. 设置 vm.swappiness=1 - 最小化 swap 使用
# 3. 提升网络连接队列 - net.core.somaxconn=65535
# 4. 提升文件描述符限制 - nofile=100000
#
# 执行：sudo bash scripts/components/tune-mongo.sh
#

set -euo pipefail

echo "=========================================="
echo "MongoDB 系统调优 - ServerC (4C/4G)"
echo "=========================================="

# 检查 root 权限
if [[ $EUID -ne 0 ]]; then
   echo "❌ 错误：此脚本需要 root 权限执行"
   echo "   请使用: sudo bash $0"
   exit 1
fi

# 1. 禁用透明大页（THP）
echo ""
echo "📌 1. 禁用透明大页（Transparent Huge Pages）..."
if [[ -f /sys/kernel/mm/transparent_hugepage/enabled ]]; then
    echo never > /sys/kernel/mm/transparent_hugepage/enabled
    echo never > /sys/kernel/mm/transparent_hugepage/defrag
    echo "   ✅ THP 已禁用（运行时）"
    
    # 永久生效：添加到 rc.local 或 systemd
    if [[ ! -f /etc/systemd/system/disable-thp.service ]]; then
        cat > /etc/systemd/system/disable-thp.service << 'EOF'
[Unit]
Description=Disable Transparent Huge Pages (THP)
DefaultDependencies=no
After=sysinit.target local-fs.target
Before=mongod.service

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo never > /sys/kernel/mm/transparent_hugepage/enabled && echo never > /sys/kernel/mm/transparent_hugepage/defrag'

[Install]
WantedBy=basic.target
EOF
        systemctl daemon-reload
        systemctl enable disable-thp.service
        echo "   ✅ THP 禁用服务已配置（开机自动执行）"
    fi
else
    echo "   ⚠️  未找到 THP 配置文件，跳过"
fi

# 2. 设置 vm.swappiness
echo ""
echo "📌 2. 设置 vm.swappiness=1 （最小化 swap 使用）..."
sysctl -w vm.swappiness=1 > /dev/null
if ! grep -q "^vm.swappiness" /etc/sysctl.conf; then
    echo "vm.swappiness=1" >> /etc/sysctl.conf
fi
echo "   ✅ vm.swappiness=1 （当前值：$(sysctl -n vm.swappiness)）"

# 3. 提升网络连接队列
echo ""
echo "📌 3. 设置 net.core.somaxconn=65535..."
sysctl -w net.core.somaxconn=65535 > /dev/null
if ! grep -q "^net.core.somaxconn" /etc/sysctl.conf; then
    echo "net.core.somaxconn=65535" >> /etc/sysctl.conf
fi
echo "   ✅ net.core.somaxconn=65535 （当前值：$(sysctl -n net.core.somaxconn)）"

# 4. 设置 TCP keepalive（减少僵尸连接）
echo ""
echo "📌 4. 优化 TCP keepalive 参数..."
sysctl -w net.ipv4.tcp_keepalive_time=300 > /dev/null
sysctl -w net.ipv4.tcp_keepalive_intvl=30 > /dev/null
sysctl -w net.ipv4.tcp_keepalive_probes=3 > /dev/null

for param in tcp_keepalive_time tcp_keepalive_intvl tcp_keepalive_probes; do
    if ! grep -q "^net.ipv4.$param" /etc/sysctl.conf; then
        case $param in
            tcp_keepalive_time) echo "net.ipv4.$param=300" >> /etc/sysctl.conf ;;
            tcp_keepalive_intvl) echo "net.ipv4.$param=30" >> /etc/sysctl.conf ;;
            tcp_keepalive_probes) echo "net.ipv4.$param=3" >> /etc/sysctl.conf ;;
        esac
    fi
done
echo "   ✅ TCP keepalive 参数已优化"

# 5. 提升文件描述符限制
echo ""
echo "📌 5. 设置文件描述符限制 (nofile=100000)..."
if ! grep -q "^* soft nofile 100000" /etc/security/limits.conf; then
    cat >> /etc/security/limits.conf << 'EOF'

# MongoDB 文件描述符限制
* soft nofile 100000
* hard nofile 100000
mongod soft nofile 100000
mongod hard nofile 100000
EOF
    echo "   ✅ limits.conf 已更新（重启后生效）"
else
    echo "   ✅ limits.conf 已包含配置"
fi

# 当前会话立即生效
ulimit -n 100000 2>/dev/null || echo "   ⚠️  当前 shell 无法设置 ulimit（需重新登录）"

# 6. 应用所有 sysctl 配置
echo ""
echo "📌 6. 应用所有 sysctl 配置..."
sysctl -p > /dev/null 2>&1 || true
echo "   ✅ sysctl 配置已应用"

# 验证配置
echo ""
echo "=========================================="
echo "✅ 调优完成！当前配置："
echo "=========================================="
echo "THP Enabled:           $(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || echo 'N/A')"
echo "THP Defrag:            $(cat /sys/kernel/mm/transparent_hugepage/defrag 2>/dev/null || echo 'N/A')"
echo "vm.swappiness:         $(sysctl -n vm.swappiness)"
echo "net.core.somaxconn:    $(sysctl -n net.core.somaxconn)"
echo "tcp_keepalive_time:    $(sysctl -n net.ipv4.tcp_keepalive_time)"
echo "nofile (current):      $(ulimit -n)"
echo ""
echo "📝 注意事项："
echo "   1. THP 禁用已通过 systemd 服务配置，开机自动生效"
echo "   2. sysctl 参数已写入 /etc/sysctl.conf，重启后自动应用"
echo "   3. nofile 限制需重新登录 shell 才能在当前用户会话生效"
echo "   4. Docker 容器会继承宿主机的内核参数（THP、sysctl 等）"
echo ""
echo "🚀 建议重启 MongoDB 容器以应用所有优化："
echo "   cd /path/to/infra/components/mongo"
echo "   docker compose down && docker compose up -d"
echo ""
