# 服务器初始化指南

> 完整的服务器环境配置指南，包括用户配置、Docker 安装和网络环境设置

## 📋 目录

- [概述](#概述)
- [用户环境配置](#用户环境配置)
- [Docker 环境配置](#docker-环境配置)
- [网络环境配置](#网络环境配置)
- [验证和测试](#验证和测试)

---

## 概述

### 初始化目标

完成以下环境配置：

- ✅ 创建应用用户和开发用户
- ✅ 配置 SSH 密钥认证和安全策略
- ✅ 安装 Docker Engine 和 Docker Compose
- ✅ 配置 Docker 网络和存储
- ✅ 设置网络代理（可选）

### 适用服务器

- **ServerA** (47.94.204.124) - 2C4G - Nginx + 存储服务
- **ServerB** (112.126.82.123) - 2C4G - NSQ + 计算服务

### 一键初始化

```bash
# 完整初始化（用户 + Docker + 网络）
sudo ./scripts/server/initialize.sh

# 分步执行
sudo ./scripts/server/init-users.sh      # 用户配置
sudo ./scripts/server/install-docker.sh   # Docker 安装
sudo ./scripts/network/setup.sh           # 网络配置（可选）
```

---

## 用户环境配置

### 用户角色设计

| 用户名 | 角色 | sudo 权限 | SSH 访问 | 工作目录 |
|--------|------|-----------|----------|----------|
| `www` | 应用管理 | ✅ | ✅ Ed25519 密钥 | `/home/www/workspace` |
| `yangshujie` | 开发用户 | ✅ | ❌ | `/home/yangshujie/workspace` |
| `root` | 系统管理 | ✅ 完全 | ✅ 配置 | `/root/workspace` |

### 自动化配置

```bash
# 执行用户初始化脚本
sudo ./scripts/server/init-users.sh
```

**脚本会自动完成**：

- 创建 `www` 和 `yangshujie` 用户
- 生成 SSH Ed25519 密钥对
- 配置 sudo 权限（无密码）
- 设置工作目录和环境变量
- 配置 Docker 别名和快捷命令

### SSH 密钥配置

```bash
# www 用户的 SSH 密钥
/home/www/.ssh/id_ed25519           # 私钥
/home/www/.ssh/id_ed25519.pub       # 公钥
/home/www/.ssh/config               # SSH 配置（GitHub）

# 查看公钥（添加到 GitHub）
sudo cat /home/www/.ssh/id_ed25519.pub
```

### 环境变量

所有用户的 `.bashrc` 已配置：

- Docker 管理别名 (`dps`, `dimg`, `dlog` 等)
- systemctl 快捷命令 (`sc-status`, `sc-start` 等)
- 自动进入 `workspace` 目录
- 彩色提示符和 Git 状态显示

---

## Docker 环境配置

### Docker 版本

- **Docker Engine**: 最新稳定版（通过官方源安装）
- **Docker Compose**: V2（集成在 Docker CLI 中）

### 自动化安装

```bash
# 执行 Docker 安装脚本
sudo ./scripts/server/install-docker.sh
```

**脚本会自动完成**：

- 添加 Docker 官方 APT 源
- 安装 Docker Engine 和 containerd
- 配置 Docker daemon（镜像加速、日志限制）
- 将 `www` 用户添加到 docker 组
- 启动并启用 Docker 服务

### Docker 配置

配置文件：`/etc/docker/daemon.json`

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "live-restore": true,
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}
```

**关键配置说明**：

- `log-opts`: 限制日志文件大小，防止磁盘占满
- `storage-driver`: 使用 overlay2 存储驱动（性能最优）
- `live-restore`: 容器在 Docker daemon 重启时保持运行
- `registry-mirrors`: 使用国内镜像加速拉取

### Docker 数据目录

```bash
# 默认数据目录
/var/lib/docker/

# 如果磁盘空间紧张，可以移动到独立磁盘
# 参考：scripts/server/install-docker.sh 中的数据目录迁移部分
```

### 验证安装

```bash
# 检查 Docker 版本
docker --version
docker compose version

# 测试 Docker 运行
docker run hello-world

# 检查 Docker 服务状态
systemctl status docker

# 查看 Docker 信息
docker info
```

---

## 网络环境配置

### 网络配置概述

基础设施使用 Docker Overlay 网络实现跨主机通信：

- **网络名称**: `infra-network`
- **网络驱动**: overlay
- **子网**: 172.20.0.0/16
- **网关**: 172.20.0.1

### 网络初始化

```bash
# 使用 Makefile 初始化网络
make network-init

# 或使用脚本直接初始化
./scripts/components/init-infrastructure.sh create
```

### 代理配置（可选）

如果服务器需要通过代理访问外网：

```bash
# 配置网络代理
sudo ./scripts/network/setup.sh

# 或手动配置 mihomo
sudo systemctl start mihomo
sudo systemctl enable mihomo
```

**代理功能**：

- TUN 模式全局代理
- 自动分流（国内直连、国外代理）
- Web 管理界面：<http://localhost:9090>

### 防火墙配置

```bash
# 开放基础设施端口
sudo ufw allow 80/tcp        # Nginx HTTP
sudo ufw allow 443/tcp       # Nginx HTTPS
sudo ufw allow 3306/tcp      # MySQL
sudo ufw allow 6379/tcp      # Redis Cache
sudo ufw allow 6380/tcp      # Redis Auth
sudo ufw allow 27017/tcp     # MongoDB
sudo ufw allow 4150:4171/tcp # NSQ 服务端口

# 启用防火墙
sudo ufw enable
```

---

## 验证和测试

### 用户配置验证

```bash
# 切换到 www 用户
sudo su - www

# 验证工作目录
pwd  # 应该在 /home/www/workspace

# 验证 Docker 权限
docker ps  # 应该可以无 sudo 执行

# 验证 SSH 密钥
ls -la ~/.ssh/  # 应该有 id_ed25519 和 id_ed25519.pub

# 退出 www 用户
exit
```

### Docker 配置验证

```bash
# Docker 版本
docker --version  # Docker version 24.x.x 或更高

# Docker Compose 版本
docker compose version  # Docker Compose version v2.x.x 或更高

# Docker 服务状态
systemctl status docker  # 应该显示 active (running)

# Docker 信息
docker info | grep -E "Storage Driver|Logging Driver"
# 应该显示：
# Storage Driver: overlay2
# Logging Driver: json-file
```

### 网络配置验证

```bash
# 检查 Docker 网络
docker network ls | grep infra-network

# 检查 Swarm 状态
docker node ls  # 应该显示当前节点

# 测试网络连接
ping -c 3 8.8.8.8  # 测试外网连接
```

### 完整性测试

```bash
# 运行测试容器
docker run -d --name test-nginx --network infra-network nginx:alpine

# 检查容器状态
docker ps | grep test-nginx

# 测试网络通信
docker exec test-nginx ping -c 3 www.baidu.com

# 清理测试容器
docker rm -f test-nginx
```

---

## 常见问题

### Q1: Docker 拉取镜像很慢

**解决方案**：

```bash
# 检查镜像加速配置
cat /etc/docker/daemon.json

# 重启 Docker 服务
sudo systemctl restart docker

# 或配置代理（如果有）
sudo ./scripts/network/setup.sh
```

### Q2: www 用户无法执行 docker 命令

**解决方案**：

```bash
# 将用户添加到 docker 组
sudo usermod -aG docker www

# 用户需要重新登录才能生效
# 或使用 newgrp 命令
newgrp docker
```

### Q3: SSH 密钥认证失败

**解决方案**：

```bash
# 检查 SSH 密钥权限
sudo chmod 700 /home/www/.ssh
sudo chmod 600 /home/www/.ssh/id_ed25519
sudo chmod 644 /home/www/.ssh/id_ed25519.pub
sudo chown -R www:www /home/www/.ssh

# 重新生成密钥（如果需要）
sudo -u www ssh-keygen -t ed25519 -C "www@server" -f /home/www/.ssh/id_ed25519 -N ""
```

### Q4: 网络初始化失败

**解决方案**：

```bash
# 检查 Swarm 状态
docker swarm init

# 如果已经初始化，重新创建网络
docker network rm infra-network
docker network create --driver overlay --attachable \
  --subnet 172.20.0.0/16 --gateway 172.20.0.1 \
  infra-network
```

---

## 安全建议

### SSH 安全

1. **禁用密码登录**（仅允许密钥认证）
2. **修改 SSH 端口**（避免暴力破解）
3. **配置 fail2ban**（防止暴力破解）
4. **定期轮换 SSH 密钥**

### Docker 安全

1. **限制容器资源**（CPU、内存）
2. **使用最小权限原则**
3. **定期更新 Docker 和镜像**
4. **启用 Docker Content Trust**

### 网络安全

1. **配置防火墙规则**
2. **使用 SSL/TLS 加密**
3. **限制服务端口访问**
4. **启用入侵检测系统**

---

## 下一步

初始化完成后，可以继续：

1. 📦 [部署基础设施服务](../components/) - 安装 Nginx、MySQL、Redis 等
2. 🌐 [配置网络环境](../network/management.md) - Docker Swarm、VPN 等
3. 🔧 使用 `make help` 查看所有可用命令

---

**相关脚本**：

- `scripts/server/initialize.sh` - 完整初始化
- `scripts/server/init-users.sh` - 用户配置
- `scripts/server/install-docker.sh` - Docker 安装
- `scripts/network/setup.sh` - 网络代理配置

**最后更新**: 2025年10月24日
