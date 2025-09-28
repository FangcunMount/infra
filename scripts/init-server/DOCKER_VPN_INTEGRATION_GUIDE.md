# Docker VPN 集成安装指南

## 概述

`install-docker.sh` 脚本已增强支持 VPN 网络环境集成。当检测到 Mihomo VPN 服务运行时，会自动配置 Docker 使用 VPN 代理网络，确保容器拉取镜像和网络访问都通过 VPN 进行。

## 功能特性

### 🔍 自动检测
- 自动检测 Mihomo VPN 服务状态
- 检查代理端口可用性 (HTTP: 7890, SOCKS5: 7891)
- 测试 VPN 网络连通性

### ⚙️ Docker 配置
- **Docker Hub 镜像加速器**: 配置多个可靠的国内镜像源提高拉取速度
- **Docker Hub 认证**: 可选配置 Docker Hub 登录以获得更高拉取配额
- **Docker Daemon 代理配置**: 配置 Docker daemon 使用 VPN 代理拉取镜像
- **Systemd 服务代理**: 配置 Docker systemd 服务的代理环境变量
- **优化配置**: 日志轮转、存储驱动、Cgroup 等标准优化

### 🛠️ 辅助工具
- **docker-vpn**: 强制使用 VPN 环境运行 Docker 命令
- **docker-compose-vpn**: 强制使用 VPN 环境运行 Docker Compose
- **test-docker-vpn.sh**: VPN 集成测试脚本
- **test-docker-users.sh**: 用户权限测试脚本

### 👥 用户权限管理
- **root 用户配置**: 确保 root 用户具有 Docker 访问权限
- **www 用户配置**: 自动检测并配置现有 www 用户的 Docker 权限
- **用户组管理**: 自动将用户添加到 docker 组
- **目录权限设置**: 配置用户级 Docker 配置目录

## 安装使用

### 前提条件

1. **操作系统支持**:
   - Ubuntu/Debian 系列
   - CentOS/RHEL/Rocky/AlmaLinux 系列
   - Fedora

2. **系统资源**:
   - 至少 2GB 可用磁盘空间
   - 推荐 1GB 以上内存

3. **VPN 服务** (可选):
   - Mihomo VPN 服务已安装并运行
   - 代理端口 7890 (HTTP) 和 7891 (SOCKS5) 可用

### 安装步骤

1. **运行安装脚本**:
   ```bash
   sudo ./install-docker.sh
   ```

2. **自动处理**:
   - 检测操作系统和 VPN 环境
   - 安装 Docker Engine 和相关组件
   - 配置 VPN 代理（如果可用）
   - 创建辅助脚本和测试工具

3. **验证安装**:
   ```bash
   # 基本验证
   docker --version
   docker compose version
   
   # VPN 集成测试
   sudo ./test-docker-vpn.sh
   ```

## 配置文件

### Docker Daemon 配置
文件位置: `/etc/docker/daemon.json`

**无 VPN 配置**:
```json
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2",
    "exec-opts": ["native.cgroupdriver=systemd"],
    "live-restore": true,
    "userland-proxy": false,
    "experimental": false,
    "ipv6": false,
    "icc": true,
    "default-ulimits": {
        "nofile": {
            "Name": "nofile",
            "Hard": 64000,
            "Soft": 64000
        }
    },
    "registry-mirrors": [
        "https://docker.m.daocloud.io",
        "https://dockerproxy.com",
        "https://docker.mirrors.ustc.edu.cn",
        "https://docker.nju.edu.cn"
    ]
}
```

**VPN 代理配置**:
```json
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2",
    "exec-opts": ["native.cgroupdriver=systemd"],
    "live-restore": true,
    "userland-proxy": false,
    "experimental": false,
    "ipv6": false,
    "icc": true,
    "default-ulimits": {
        "nofile": {
            "Name": "nofile",
            "Hard": 64000,
            "Soft": 64000
        }
    },
    "registry-mirrors": [
        "https://docker.io"
    ],
    "proxies": {
        "default": {
            "httpProxy": "http://127.0.0.1:7890",
            "httpsProxy": "http://127.0.0.1:7890",
            "noProxy": "localhost,127.0.0.0/8,::1"
        }
    }
}
```

### Systemd 代理配置
文件位置: `/etc/systemd/system/docker.service.d/proxy.conf`

```ini
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
Environment="NO_PROXY=localhost,127.0.0.0/8,::1"
```

## 使用方法

### 基本使用
安装完成后，Docker 会自动使用 VPN 网络（如果可用）：

```bash
# 拉取镜像（通过 VPN）
docker pull nginx

# 运行容器（通过 VPN）
docker run -d --name web nginx

# 使用 Docker Compose
docker compose up -d
```

### 辅助命令

**docker-vpn**: 强制使用 VPN 环境
```bash
# 强制通过 VPN 运行容器
docker-vpn run --rm alpine/curl curl https://www.google.com

# 强制通过 VPN 拉取镜像
docker-vpn pull ubuntu:latest
```

**docker-compose-vpn**: 强制使用 VPN 环境运行 Compose
```bash
# 强制通过 VPN 运行 Compose 项目
docker-compose-vpn up -d

# 强制通过 VPN 构建镜像
docker-compose-vpn build
```

### 测试验证

**运行集成测试**:
```bash
sudo ./test-docker-vpn.sh
```

**用户权限测试**:
```bash
sudo ./test-docker-users.sh
```

**手动验证网络**:
```bash
# 测试直连网络
docker run --rm --env http_proxy= --env https_proxy= alpine/curl curl -s http://httpbin.org/ip

# 测试 VPN 网络
docker run --rm alpine/curl curl -s http://httpbin.org/ip

# 测试 VPN 访问
docker run --rm alpine/curl curl -s https://www.google.com
```

## 网络行为

### 有 VPN 环境
- **镜像拉取**: 通过 VPN 代理进行
- **容器网络**: 默认通过 VPN 代理
- **构建过程**: 通过 VPN 代理下载依赖

### 无 VPN 环境
- **直连模式**: 所有网络访问直接连接
- **标准配置**: 使用 Docker 默认网络配置
- **可后续升级**: 启动 VPN 后重新运行安装脚本即可启用代理

## 故障排除

### VPN 检测失败
```bash
# 检查 Mihomo 服务状态
systemctl status mihomo

# 检查代理端口
nc -z 127.0.0.1 7890
nc -z 127.0.0.1 7891

# 测试代理连接
curl --proxy http://127.0.0.1:7890 https://www.google.com
```

### Docker 代理问题
```bash
# 检查 Docker daemon 配置
cat /etc/docker/daemon.json

# 检查 systemd 代理配置
cat /etc/systemd/system/docker.service.d/proxy.conf

# 重启 Docker 服务
systemctl restart docker

# 查看 Docker 系统信息
docker system info
```

### 网络连接问题
```bash
# 查看 Docker 网络
docker network ls

# 测试容器网络
docker run --rm alpine/curl curl -v https://www.google.com

# 检查代理环境变量
docker run --rm alpine env | grep -i proxy
```

## 升级和维护

### 从直连升级到 VPN
1. 安装并启动 Mihomo VPN 服务
2. 重新运行 `install-docker.sh` 脚本
3. 脚本会自动检测并配置 VPN 代理

### 禁用 VPN 代理
1. 停止 Mihomo 服务: `systemctl stop mihomo`
2. 删除代理配置:
   ```bash
   # 删除 daemon 代理配置
   sudo jq 'del(.proxies)' /etc/docker/daemon.json > /tmp/daemon.json
   sudo mv /tmp/daemon.json /etc/docker/daemon.json
   
   # 删除 systemd 代理配置
   sudo rm -f /etc/systemd/system/docker.service.d/proxy.conf
   
   # 重启 Docker
   sudo systemctl daemon-reload
   sudo systemctl restart docker
   ```

### 更新配置
```bash
# 重新检测和配置（保持现有 Docker 安装）
sudo ./install-docker.sh
```

## 安全考虑

- **代理认证**: 当前配置不包含代理认证，适用于本地 VPN 代理
- **网络隔离**: 容器仍可访问本地网络（127.0.0.0/8）
- **日志管理**: 配置了日志轮转避免磁盘占用过大
- **权限管理**: 建议将用户添加到 docker 组而非使用 sudo

## 相关文档

- [setup-network.sh VPN 安装指南](./SETUP_NETWORK_GUIDE.md)
- [VPN 快速参考](./QUICK_REFERENCE.md)
- [服务器初始化流程](../../docs/SERVER_INITIALIZATION_FLOW.md)