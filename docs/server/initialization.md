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

- 创建并维护 `root`、`yangshujie`、`deploy`、`www` 四类 Linux 身份
- 配置 `deploy` 的 CI/CD 受限 sudo 与可选 SSH 公钥
- 安装 Docker Engine 和 Docker Compose
- 执行宿主机基础参数调优
- 可选安装 VPN/Mihomo 代理

### 适用服务器

- **ServerA** - `4C8G` - `nginx + qs-apiserver + qs-collection-server`
- **ServerB** - `2C2G` - `IAM`
- **ServerC** - `4C4G` - `mongodb`
- **ServerD** - `4C4G` - `qs-worker + operating + nsq + prometheus + grafana`

当前 Swarm 角色约定：

- `serverA`：manager
- `serverB`：manager
- `serverD`：manager
- `serverC`：worker

### 一键初始化

```bash
# 交互式完整初始化（推荐）
sudo bash scripts/00-server/initialize.sh

# 分步执行
sudo bash scripts/00-server/init-users.sh           # 用户配置
sudo bash scripts/00-server/install-docker.sh        # Docker 安装
sudo bash scripts/00-server/tune-host.sh             # 宿主机调优
sudo bash scripts/00-server/setup-deploy-ssh.sh "$CI_PUBLIC_KEY"
sudo bash scripts/01-network/vpn-setup.sh            # VPN/Mihomo（可选）

# Makefile 入口
make server-init
```

---

## 用户环境配置

### 用户角色设计

| 用户名 | 角色 | sudo 权限 | SSH/登录 | 工作目录 |
|--------|------|-----------|----------|----------|
| `root` | 系统引导和紧急维护 | 完全权限 | 默认存在，不日常使用 | `/root/workspace` |
| `yangshujie` | 人工运维用户 | `sudo` / `wheel` | 可登录 | `/home/yangshujie/workspace` |
| `deploy` | CI/CD 部署用户 | `/etc/sudoers.d/deploy-cicd` 最小白名单 | 密码锁定，仅 SSH key | `/home/deploy/workspace` |
| `www` | 业务运行时 UID/GID | 无 | `nologin`，不可登录 | `/var/www` |

### 自动化配置

```bash
# 执行用户初始化脚本
sudo bash scripts/00-server/init-users.sh
```

**脚本会自动完成**：

- 维护 `root` 的 `/root/workspace`、`/root/bin` 和基础 `.bashrc`
- 创建/更新 `yangshujie`，加入 sudo/wheel 管理组，不加入 docker 组
- 创建/更新 `deploy`，锁定密码，写入最小 sudoers 白名单
- 创建/更新 `www`，设置为 `nologin`，不加入 sudo/docker 组
- 创建 `/var/www`、`/srv/apps`、`/var/log/apps`、`/data/infra`、`/data/logs`
- 写入 `/opt/infra/.env` 的 `WWW_UID/WWW_GID` 和 `APP_UID/APP_GID`，默认固定为 `2000:2000`

### `/data` 挂载目录约定

| 宿主机路径 | 属主建议 | 用途 |
|-----------|----------|------|
| `/data/apps/nginx-configs` | `www:www` | Nginx 应用反向代理配置 |
| `/data/image/qrcode` | `www:www`，父目录 `/data/image` 可保持 `root:root 0777` | qs-apiserver 二维码本地兼容目录 |
| `/data/infra/mongo/conf/{mongod.conf,init-mongo.js}` | `www:www` | MongoDB 配置与首次初始化脚本 |
| `/data/infra/mongo/data` | `www:www` | MongoDB 数据目录 |
| `/data/infra/mongo/config/replset.key` | `999:999 0400` | MongoDB 副本集 keyFile |
| `/data/infra/nsq/{nsqlookupd.conf,nsqd.conf,nsqadmin.conf}` | `root:root` | NSQ 配置文件 |
| `/data/infra/nsq/data` | `root:root` | NSQ 数据目录 |
| `/data/infra/ssl/grpc/{ca,server,clients}` | `www:www` | gRPC mTLS 证书目录 |
| `/data/logs/nginx` | `www:www` | Nginx 容器日志 |
| `/data/logs/qs-server/*` | `WWW_UID:WWW_GID` | QS 三件套日志 |
| `/data/logs/iam` | `WWW_UID:WWW_GID` | IAM 日志 |
| `/data/ops/iam-keys` | `WWW_UID:WWW_GID`，父目录 `/data/ops` 可保持 `root:root` | IAM JWKS 持久化密钥 |
| `/data/ssl/{certs,private}` | `www:www` | 仅 serverA Nginx 与 qs-apiserver 需要的公网 TLS 证书 |

基础组件 Compose 直接 bind mount 上述目录，不再依赖 Docker named volume。历史遗留的 `infra_nginx_logs`、`infra_mongo_data`、`infra_nsq_data` 只在 destroy/cleanup 命令中作为兼容清理项保留。

### deploy SSH 密钥配置

```bash
# 本地生成 CI/CD 专用密钥，不在服务器生成私钥
ssh-keygen -t ed25519 -C "github-actions@deploy" -f ~/.ssh/deploy_key

# 在服务器配置 deploy 受限 SSH 入口
sudo bash scripts/00-server/setup-deploy-ssh.sh "$(cat ~/.ssh/deploy_key.pub)"
```

`setup-deploy-ssh.sh` 会把公钥写入 `/home/deploy/.ssh/authorized_keys`，禁用 PTY、Agent 转发、X11 转发和端口转发，但不会使用 `command=` 强制入口。当前 GitHub Actions 使用 `scp-action` + `ssh-action`，如果强制 `deployctl` 会拦截 tar/scp 和多行部署脚本。

四台机器建议使用相同的运行时 UID/GID：

```bash
sudo RUNTIME_UID=2000 RUNTIME_GID=2000 bash scripts/00-server/init-users.sh
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
sudo bash scripts/00-server/install-docker.sh
```

**脚本会自动完成**：

- 添加 Docker 官方 APT 源
- 安装 Docker Engine 和 containerd
- 配置 Docker daemon（镜像加速、日志限制）
- 不自动将任何业务用户加入 docker 组；运维使用 `sudo docker`
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
# 参考：scripts/00-server/install-docker.sh 中的数据目录迁移部分
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
- **子网**: 172.20.0.0/24
- **网关**: 172.20.0.1

### 网络初始化

```bash
# 使用 Makefile 初始化网络
make init ENV=prod INIT_TARGET=serverA

# 或使用脚本直接初始化
bash scripts/02-components/init-infrastructure.sh create
```

### 代理配置（可选）

如果服务器需要通过代理访问外网：

```bash
# 配置网络代理
sudo bash scripts/01-network/vpn-setup.sh

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
# 开放公网入口（仅 serverA）
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 四节点 Swarm / overlay 端口走 Tailscale underlay，不对公网开放。
# 如使用 UFW 且 tailscale0 入站被拦截，可只允许 tailscale0：
sudo ufw allow in on tailscale0

# 如果你明确要在主机防火墙上细化规则，以下端口仅允许 tailscale0/四台 Tailscale IP 互通：
sudo ufw allow 2377/tcp
sudo ufw allow 7946/tcp
sudo ufw allow 7946/udp
sudo ufw allow 4789/udp

# NSQ 端口（仅在 serverD 对受信任节点开放）
sudo ufw allow 4150:4171/tcp

# MongoDB 不建议对公网开放 27017
# 如需运维访问，优先使用 SSH 隧道到 serverC 的 127.0.0.1:27017

# 启用防火墙
sudo ufw enable
```

---

## 验证和测试

### 用户配置验证

```bash
# 验证四类用户都存在
id root
id yangshujie
id deploy
id www

# www 必须不可登录
getent passwd www | cut -d: -f7

# deploy 不加入 docker/sudo 组，只通过 sudoers 白名单执行 CI/CD 命令
groups deploy
sudo -l -U deploy

# 四台机器的 WWW_UID/WWW_GID 必须一致，并与 GitHub Secrets 一致
grep -E '^(RUNTIME_USER|RUNTIME_GROUP|WWW_UID|WWW_GID|APP_UID|APP_GID)=' /opt/infra/.env
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
sudo bash scripts/01-network/vpn-setup.sh
```

### Q2: www 用户无法执行 docker 命令

**解决方案**：

```bash
# 这是预期行为。www 是 nologin 运行时用户，不应该执行 docker 命令。
# 人工运维使用 yangshujie + sudo docker；CI/CD 使用 deploy + 受限 sudo。
sudo docker ps
```

### Q3: deploy SSH 密钥认证失败

**解决方案**：

```bash
# 检查 SSH 密钥权限
sudo chmod 700 /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys
sudo chown -R deploy:deploy /home/deploy/.ssh

# 重新配置 CI/CD 公钥
sudo bash scripts/00-server/setup-deploy-ssh.sh "$(cat ~/.ssh/deploy_key.pub)"
```

### Q4: 网络初始化失败

**解决方案**：

```bash
# 检查 Swarm 状态
docker swarm init

# 如果已经初始化，重新创建网络
docker network rm infra-network
docker network create --driver overlay --attachable \
  --subnet 172.20.0.0/24 --gateway 172.20.0.1 \
  --opt com.docker.network.driver.mtu=1280 \
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
2. 🌐 [配置 Tailscale + Swarm 网络](../network/swarm-setup.md) - 按主流程建立跨云容器网络
3. 🔧 使用 `make help` 查看所有可用命令

---

**相关脚本**：

- `scripts/00-server/initialize.sh` - 交互式 Linux 初始化
- `scripts/00-server/init-users.sh` - 用户配置
- `scripts/00-server/install-docker.sh` - Docker 安装
- `scripts/00-server/tune-host.sh` - 宿主机参数调优
- `scripts/01-network/vpn-setup.sh` - VPN/Mihomo 代理配置

**最后更新**: 2026年4月26日
