#!/usr/bin/env bash
#
# 宿主机系统调优脚本（通用版）
# 适用于运行 MongoDB、Redis 等数据库的服务器
#
# 用途：
# 1. 禁用透明大页（THP）
# 2. 设置 vm.swappiness=1
# 3. 提升网络连接队列
# 4. 提升文件描述符限制
# 5. 优化 TCP 参数
#
# 执行：sudo bash scripts/00-server/tune-host.sh
#

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "=========================================="
echo -e "${BLUE}宿主机系统调优 - 数据库优化${NC}"
echo "=========================================="

# 检查 root 权限
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}❌ 错误：此脚本需要 root 权限执行${NC}"
   echo "   请使用: sudo bash $0"
   exit 1
fi

# 检测操作系统
if [[ -f /etc/os-release ]]; then
    source /etc/os-release
    OS_NAME=$ID
    OS_VERSION=$VERSION_ID
    echo -e "${YELLOW}检测到系统: $PRETTY_NAME${NC}"
else
    OS_NAME="unknown"
fi

echo ""
read -p "继续执行系统调优？[y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 已取消"
    exit 0
fi

# 1. 禁用透明大页（THP）
echo ""
echo -e "${BLUE}📌 1. 禁用透明大页（Transparent Huge Pages）${NC}"
if [[ -f /sys/kernel/mm/transparent_hugepage/enabled ]]; then
    echo never > /sys/kernel/mm/transparent_hugepage/enabled
    echo never > /sys/kernel/mm/transparent_hugepage/defrag
    echo -e "   ${GREEN}✅ THP 已禁用（运行时）${NC}"
    
    # 永久生效：systemd 服务
    cat > /etc/systemd/system/disable-thp.service << 'EOF'
[Unit]
Description=Disable Transparent Huge Pages (THP)
DefaultDependencies=no
After=sysinit.target local-fs.target
Before=mongod.service redis.service

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'echo never > /sys/kernel/mm/transparent_hugepage/enabled && echo never > /sys/kernel/mm/transparent_hugepage/defrag'

[Install]
WantedBy=basic.target
EOF
    systemctl daemon-reload
    systemctl enable disable-thp.service --quiet 2>/dev/null || true
    echo -e "   ${GREEN}✅ THP 禁用服务已配置（开机自动执行）${NC}"
else
    echo -e "   ${YELLOW}⚠️  未找到 THP 配置文件，跳过${NC}"
fi

# 2. 配置 sysctl 参数
echo ""
echo -e "${BLUE}📌 2. 配置内核参数（sysctl）${NC}"

declare -A SYSCTL_PARAMS=(
    ["vm.swappiness"]="1"
    ["vm.overcommit_memory"]="1"
    ["net.core.somaxconn"]="65535"
    ["net.ipv4.tcp_max_syn_backlog"]="8192"
    ["net.ipv4.tcp_keepalive_time"]="300"
    ["net.ipv4.tcp_keepalive_intvl"]="30"
    ["net.ipv4.tcp_keepalive_probes"]="3"
)

for param in "${!SYSCTL_PARAMS[@]}"; do
    value="${SYSCTL_PARAMS[$param]}"
    sysctl -w "$param=$value" > /dev/null 2>&1 || true
    
    if ! grep -q "^$param" /etc/sysctl.conf; then
        echo "$param=$value" >> /etc/sysctl.conf
    else
        sed -i "s/^$param.*/$param=$value/" /etc/sysctl.conf
    fi
    
    echo -e "   ${GREEN}✅ $param = $value${NC}"
done

sysctl -p > /dev/null 2>&1 || true

# 3. 设置文件描述符限制
echo ""
echo -e "${BLUE}📌 3. 设置文件描述符限制 (ulimit)${NC}"

LIMITS_CONF="/etc/security/limits.conf"
NOFILE_LIMIT="100000"

if ! grep -q "# Database ulimit settings" "$LIMITS_CONF"; then
    cat >> "$LIMITS_CONF" << EOF

# Database ulimit settings (MongoDB, Redis)
* soft nofile $NOFILE_LIMIT
* hard nofile $NOFILE_LIMIT
root soft nofile $NOFILE_LIMIT
root hard nofile $NOFILE_LIMIT
EOF
    echo -e "   ${GREEN}✅ limits.conf 已更新${NC}"
else
    echo -e "   ${GREEN}✅ limits.conf 已包含配置${NC}"
fi

# 4. 优化进程数限制
echo ""
echo -e "${BLUE}📌 4. 优化进程数限制${NC}"

if ! grep -q "# Database nproc settings" "$LIMITS_CONF"; then
    cat >> "$LIMITS_CONF" << EOF

# Database nproc settings
* soft nproc 32768
* hard nproc 65536
EOF
    echo -e "   ${GREEN}✅ nproc 限制已设置${NC}"
else
    echo -e "   ${GREEN}✅ nproc 限制已包含${NC}"
fi

# 5. 禁用 SELinux（可选，如果影响 Docker）
if [[ "$OS_NAME" == "centos" ]] || [[ "$OS_NAME" == "rhel" ]]; then
    echo ""
    echo -e "${BLUE}📌 5. 检查 SELinux 状态${NC}"
    if command -v getenforce &> /dev/null; then
        SELINUX_STATUS=$(getenforce)
        if [[ "$SELINUX_STATUS" != "Disabled" ]]; then
            echo -e "   ${YELLOW}⚠️  SELinux 当前状态: $SELINUX_STATUS${NC}"
            echo -e "   ${YELLOW}   如果遇到权限问题，可以设置为 Permissive${NC}"
            # setenforce 0  # 临时禁用
            # sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config
        else
            echo -e "   ${GREEN}✅ SELinux 已禁用${NC}"
        fi
    fi
fi

# 6. 创建检查脚本
echo ""
echo -e "${BLUE}📌 6. 创建配置检查脚本${NC}"

cat > /usr/local/bin/check-db-tuning << 'CHECKSCRIPT'
#!/bin/bash
echo "=========================================="
echo "数据库宿主机调优状态检查"
echo "=========================================="
echo ""
echo "THP Enabled:           $(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || echo 'N/A')"
echo "THP Defrag:            $(cat /sys/kernel/mm/transparent_hugepage/defrag 2>/dev/null || echo 'N/A')"
echo "vm.swappiness:         $(sysctl -n vm.swappiness 2>/dev/null || echo 'N/A')"
echo "vm.overcommit_memory:  $(sysctl -n vm.overcommit_memory 2>/dev/null || echo 'N/A')"
echo "net.core.somaxconn:    $(sysctl -n net.core.somaxconn 2>/dev/null || echo 'N/A')"
echo "tcp_keepalive_time:    $(sysctl -n net.ipv4.tcp_keepalive_time 2>/dev/null || echo 'N/A')"
echo "ulimit -n (nofile):    $(ulimit -n)"
echo "ulimit -u (nproc):     $(ulimit -u)"
echo ""
CHECKSCRIPT

chmod +x /usr/local/bin/check-db-tuning
echo -e "   ${GREEN}✅ 检查脚本已创建: /usr/local/bin/check-db-tuning${NC}"

# 验证配置
echo ""
echo "=========================================="
echo -e "${GREEN}✅ 调优完成！当前配置：${NC}"
echo "=========================================="
/usr/local/bin/check-db-tuning

echo ""
echo -e "${YELLOW}📝 重要提示：${NC}"
echo -e "   1. ${YELLOW}部分配置需要重启 shell 会话才能生效${NC}"
echo -e "   2. ${YELLOW}建议重启服务器以确保所有配置生效${NC}"
echo -e "   3. 随时运行 ${BLUE}check-db-tuning${NC} 检查配置状态"
echo -e "   4. THP 禁用服务已配置为开机自动执行"
echo ""
echo -e "${GREEN}🚀 可以继续部署数据库容器了！${NC}"
echo ""
