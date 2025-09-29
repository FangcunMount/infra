#!/bin/bash

# 初始化应用配置目录
# 确保 /data/apps/nginx-configs 目录存在并设置正确权限

APPS_CONFIG_DIR="/data/apps/nginx-configs"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# 创建应用配置目录
create_apps_config_dir() {
    log_info "初始化应用配置目录..."
    
    if [ ! -d "$APPS_CONFIG_DIR" ]; then
        log_info "创建目录: $APPS_CONFIG_DIR"
        sudo mkdir -p "$APPS_CONFIG_DIR"
    fi
    
    # 设置权限
    sudo chown www:www "$APPS_CONFIG_DIR"
    sudo chmod 755 "$APPS_CONFIG_DIR"
    
    # 创建说明文件
    cat > /tmp/apps-nginx-configs-readme.txt << 'EOF'
# 应用 Nginx 配置目录

此目录由 infra 项目管理，用于存放应用项目的 nginx 配置文件。

## 文件来源
- 应用项目通过部署脚本将配置文件复制到此目录
- 配置文件会被自动挂载到 nginx 容器的 /etc/nginx/conf.d/apps/ 目录

## 管理命令
- 部署配置: make app-deploy APP=blog CONFIG=./nginx/blog.conf
- 移除配置: make app-remove APP=blog  
- 列出配置: make app-list
- 重载配置: make nginx-reload

## 注意事项
- 请勿手动修改此目录中的文件
- 所有配置变更都应通过 infra 项目的管理工具进行
EOF
    
    sudo cp /tmp/apps-nginx-configs-readme.txt "$APPS_CONFIG_DIR/README.txt"
    sudo chown www:www "$APPS_CONFIG_DIR/README.txt"
    sudo chmod 644 "$APPS_CONFIG_DIR/README.txt"
    rm /tmp/apps-nginx-configs-readme.txt
    
    log_info "✅ 应用配置目录初始化完成"
    log_info "目录位置: $APPS_CONFIG_DIR"
    log_info "权限设置: www:www 755"
}

main() {
    create_apps_config_dir
}

main "$@"