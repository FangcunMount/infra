#!/bin/bash

# 测试 setup-network.sh 可重复执行功能
# 此脚本用于验证脚本的状态检查逻辑

set -e

echo "=== 测试 setup-network.sh 可重复执行功能 ==="
echo

# 只导入状态检查函数，不运行主脚本
# 提取状态检查函数定义
check_mihomo_installed() {
    [[ -f "/usr/local/bin/mihomo" ]] && /usr/local/bin/mihomo -v >/dev/null 2>&1
}

check_directories_setup() {
    [[ -d "/opt/mihomo" ]] && [[ -d "/opt/mihomo/config" ]] && [[ -d "/opt/mihomo/data" ]]
}

check_geodata_downloaded() {
    [[ -f "/opt/mihomo/data/GeoSite.dat" ]] && [[ -f "/opt/mihomo/data/GeoIP.metadb" ]]
}

check_base_config_created() {
    [[ -f "/opt/mihomo/config/config.yaml" ]]
}

check_systemd_service_setup() {
    systemctl list-units --all --type=service | grep -q mihomo.service
}

check_mihomo_service_running() {
    systemctl is-active --quiet mihomo.service 2>/dev/null
}

check_global_proxy_setup() {
    [[ -f "/etc/profile.d/mihomo-proxy.sh" ]] || [[ -f "/etc/environment" ]] && grep -q "http_proxy" /etc/environment
}

check_management_scripts_created() {
    [[ -f "/usr/local/bin/mihomo-control" ]] && [[ -f "/usr/local/bin/diagnose-network.sh" ]]
}

echo "测试状态检查函数："
echo

# 测试 mihomo 安装检查
echo "1. 检查 mihomo 是否已安装..."
if check_mihomo_installed; then
    echo "   ✅ mihomo 已安装"
else
    echo "   ❌ mihomo 未安装"
fi

# 测试目录检查
echo "2. 检查配置目录是否已创建..."
if check_directories_setup; then
    echo "   ✅ 配置目录已创建"
else
    echo "   ❌ 配置目录未创建"
fi

# 测试地理数据检查
echo "3. 检查地理数据文件是否已下载..."
if check_geodata_downloaded; then
    echo "   ✅ 地理数据文件已下载"
else
    echo "   ❌ 地理数据文件未下载"
fi

# 测试基础配置检查
echo "4. 检查基础配置文件是否已创建..."
if check_base_config_created; then
    echo "   ✅ 基础配置文件已创建"
else
    echo "   ❌ 基础配置文件未创建"
fi

# 测试 systemd 服务检查
echo "5. 检查 systemd 服务是否已配置..."
if check_systemd_service_setup; then
    echo "   ✅ systemd 服务已配置"
else
    echo "   ❌ systemd 服务未配置"
fi

# 测试服务运行检查
echo "6. 检查 mihomo 服务是否正在运行..."
if check_mihomo_service_running; then
    echo "   ✅ mihomo 服务正在运行"
else
    echo "   ❌ mihomo 服务未运行"
fi

# 测试全局代理检查
echo "7. 检查全局代理是否已配置..."
if check_global_proxy_setup; then
    echo "   ✅ 全局代理已配置"
else
    echo "   ❌ 全局代理未配置"
fi

# 测试管理脚本检查
echo "8. 检查管理脚本是否已创建..."
if check_management_scripts_created; then
    echo "   ✅ 管理脚本已创建"
else
    echo "   ❌ 管理脚本未创建"
fi

echo
echo "=== 状态检查完成 ==="
echo
echo "说明："
echo "- 如果所有检查都显示 ❌，说明系统是干净的，可以完整运行安装"
echo "- 如果某些检查显示 ✅，说明对应组件已安装，脚本会跳过这些步骤"
echo "- 这是可重复执行脚本的设计目标：只执行必要的步骤"