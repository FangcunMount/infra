# 服务器初始化 - Docker 安装配置

> 🐳 安装和配置企业级 Docker 环境，包括 Docker Engine 和 Docker Compose

## 🎯 Docker 配置目标

- 安装最新稳定版 Docker Engine
- 配置 Docker Compose V2
- 优化 Docker 性能和安全设置
- 设置 Docker 镜像仓库和加速
- 配置容器运行环境和资源限制

## 🐳 Docker 架构设计

### Docker 环境结构

```
┌─────────────────────────────────────────────────┐
│                Docker Engine                    │
│  ┌─────────────────────────────────────────────┐│
│  │           容器运行时                        ││
│  │  ┌─────────────┐  ┌─────────────────────┐  ││
│  │  │   网络管理   │  │      存储管理       │  ││
│  │  │  • bridge   │  │   • 数据卷          │  ││
│  │  │  • overlay  │  │   • 绑定挂载        │  ││
│  │  │  • macvlan  │  │   • tmpfs          │  ││
│  │  └─────────────┘  └─────────────────────┘  ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
                      │
┌─────────────────────────────────────────────────┐
│             Docker Compose                      │
│  ┌─────────────────────────────────────────────┐│
│  │            服务编排                         ││
│  │  • 多容器应用管理                           ││
│  │  • 网络和存储编排                          ││
│  │  • 环境变量管理                           ││
│  │  • 健康检查和重启                         ││
│  └─────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
                      │
┌─────────────────────────────────────────────────┐
│               基础设施容器                       │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ │
│  │MySQL │ │Redis │ │Mongo │ │Kafka │ │Nginx │ │
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ │
└─────────────────────────────────────────────────┘
```

## 🚀 自动化安装

### 一键 Docker 安装

```bash
# 执行 Docker 自动安装脚本
sudo ./scripts/init-server/install-docker.sh

# 脚本会自动完成：
# ✅ 卸载旧版本 Docker
# ✅ 配置 Docker 官方软件源
# ✅ 安装最新版 Docker Engine
# ✅ 安装 Docker Compose V2
# ✅ 配置用户权限和组
# ✅ 优化 Docker 性能配置
# ✅ 设置开机自启动
```

### 检查安装结果

```bash
# 验证 Docker 安装
docker --version
docker compose version

# 测试 Docker 功能
sudo docker run hello-world

# 查看 Docker 信息
docker system info
```

## 🔧 手动安装步骤

### 步骤 1: 卸载旧版本

```bash
# 卸载旧版本 Docker
sudo apt-get remove -y docker docker-engine docker.io containerd runc docker-compose

# 清理旧配置
sudo rm -rf /var/lib/docker
sudo rm -rf /etc/docker
```

### 步骤 2: 安装依赖和GPG密钥

```bash
# 更新软件包索引
sudo apt-get update

# 安装必要依赖
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    apt-transport-https \
    software-properties-common

# 添加 Docker 官方 GPG 密钥
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 设置 Docker 软件源
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

### 步骤 3: 安装 Docker Engine

```bash
# 更新软件包索引
sudo apt-get update

# 安装 Docker Engine
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 启动 Docker 服务
sudo systemctl start docker
sudo systemctl enable docker

# 验证安装
sudo docker run hello-world
```

### 步骤 4: 配置用户权限

```bash
# 将用户添加到 docker 组
sudo usermod -aG docker $USER
sudo usermod -aG docker admin
sudo usermod -aG docker deploy

# 应用组权限变更（需要重新登录）
newgrp docker

# 验证无 sudo 运行
docker ps
```

### 步骤 5: 安装 Docker Compose V2

```bash
# Docker Compose Plugin 已包含在 Docker Engine 中
# 验证 Docker Compose V2
docker compose version

# 创建 docker-compose 别名（兼容性）
sudo tee /usr/local/bin/docker-compose << 'EOF'
#!/bin/bash
exec docker compose "$@"
EOF

sudo chmod +x /usr/local/bin/docker-compose

# 验证别名
docker-compose version
```

## ⚙️ Docker 配置优化

### Docker Daemon 配置

```bash
# 创建 Docker daemon 配置文件
sudo mkdir -p /etc/docker

sudo tee /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "registry-mirrors": [
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com"
  ],
  "storage-driver": "overlay2",
  "storage-opts": [
    "overlay2.override_kernel_check=true"
  ],
  "default-ulimits": {
    "nofile": {
      "Hard": 64000,
      "Name": "nofile",
      "Soft": 64000
    }
  },
  "live-restore": true,
  "userland-proxy": false,
  "experimental": false,
  "metrics-addr": "127.0.0.1:9323",
  "max-concurrent-downloads": 10,
  "max-concurrent-uploads": 5,
  "default-address-pools": [
    {
      "base": "172.17.0.0/12",
      "size": 24
    },
    {
      "base": "192.168.0.0/16", 
      "size": 24
    }
  ]
}
EOF

# 重启 Docker 服务使配置生效
sudo systemctl restart docker
```

### 系统资源优化

```bash
# 创建 Docker 系统优化配置
sudo tee /etc/sysctl.d/99-docker-optimization.conf << 'EOF'
# Docker 容器优化
vm.max_map_count = 262144
fs.may_detach_mounts = 1

# 网络优化
net.ipv4.ip_forward = 1
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1

# 内存管理优化
vm.overcommit_memory = 1
vm.swappiness = 1
EOF

# 应用系统配置
sudo sysctl -p /etc/sysctl.d/99-docker-optimization.conf

# 加载内核模块
sudo modprobe overlay
sudo modprobe br_netfilter

# 设置开机自动加载
echo 'overlay' | sudo tee -a /etc/modules
echo 'br_netfilter' | sudo tee -a /etc/modules
```

### systemd 服务优化

```bash
# 创建 Docker 服务优化配置
sudo mkdir -p /etc/systemd/system/docker.service.d

sudo tee /etc/systemd/system/docker.service.d/override.conf << 'EOF'
[Service]
# 限制日志大小
Environment="DOCKER_OPTS=--log-opt max-size=10m --log-opt max-file=3"

# 调整 OOM 分数
OOMScoreAdjust=-500

# 增加文件句柄限制
LimitNOFILE=1048576
LimitNPROC=1048576

# 内存和 CPU 限制
MemoryLimit=8G
CPUQuota=400%
EOF

# 重新加载 systemd 配置
sudo systemctl daemon-reload
sudo systemctl restart docker
```

## 🔐 Docker 安全配置

### 容器安全设置

```bash
# 创建 Docker 安全配置
sudo tee -a /etc/docker/daemon.json << 'EOF'
{
  "icc": false,
  "userland-proxy": false,
  "no-new-privileges": true,
  "seccomp-profile": "/etc/docker/seccomp-profile.json",
  "apparmor-profile": "docker-default"
}
EOF
```

### 用户命名空间隔离

```bash
# 启用用户命名空间重映射
sudo tee -a /etc/docker/daemon.json << 'EOF'
{
  "userns-remap": "default"
}
EOF

# 创建 dockremap 用户
sudo useradd dockremap
sudo echo 'dockremap:165536:65536' | sudo tee -a /etc/subuid
sudo echo 'dockremap:165536:65536' | sudo tee -a /etc/subgid
```

### Docker Socket 安全

```bash
# 设置 Docker socket 权限
sudo chmod 660 /var/run/docker.sock
sudo chown root:docker /var/run/docker.sock

# 创建 Docker 访问审计
sudo tee /etc/audit/rules.d/docker.rules << 'EOF'
-w /usr/bin/docker -p wa -k docker
-w /var/lib/docker -p wa -k docker
-w /etc/docker -p wa -k docker
-w /lib/systemd/system/docker.service -p wa -k docker
-w /var/run/docker.sock -p wa -k docker
EOF

# 重启 auditd 服务
sudo systemctl restart auditd
```

## 📊 Docker 监控配置

### 启用 Docker 指标

```bash
# 验证指标端点
curl http://127.0.0.1:9323/metrics

# 安装 Docker 监控工具
docker run -d \
  --name docker-stats \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -p 8080:8080 \
  dockersamples/visualizer
```

### 容器资源监控

```bash
# 查看容器资源使用情况
docker stats

# 查看系统资源使用
docker system df
docker system events

# 清理未使用的资源
docker system prune -f
docker image prune -f
docker container prune -f
docker volume prune -f
```

## 🗂️ Docker 数据管理

### 数据目录配置

```bash
# 创建 Docker 数据目录
sudo mkdir -p /opt/docker-data

# 停止 Docker 服务
sudo systemctl stop docker

# 移动现有数据（如果有）
sudo mv /var/lib/docker /opt/docker-data/

# 更新 Docker 配置
sudo tee -a /etc/docker/daemon.json << 'EOF'
{
  "data-root": "/opt/docker-data"
}
EOF

# 重启 Docker 服务
sudo systemctl start docker
```

### 日志管理

```bash
# 配置日志轮转
sudo tee /etc/logrotate.d/docker << 'EOF'
/var/lib/docker/containers/*/*.log {
    rotate 7
    daily
    compress
    size=1M
    missingok
    delaycompress
    copytruncate
}
EOF

# 清理容器日志
sudo find /var/lib/docker/containers/ -name "*.log" -exec truncate -s 0 {} \;
```

## 📋 验证检查清单

### ✅ Docker 安装验证

```bash
# 检查 Docker 版本
docker --version | grep -q "Docker version" && echo "✅ Docker 安装成功" || echo "❌ Docker 安装失败"

# 检查 Docker Compose
docker compose version | grep -q "Docker Compose version" && echo "✅ Docker Compose 安装成功" || echo "❌ Docker Compose 安装失败"

# 检查 Docker 服务状态
sudo systemctl is-active docker | grep -q "active" && echo "✅ Docker 服务运行中" || echo "❌ Docker 服务未运行"

# 测试 Docker 功能
docker run --rm hello-world >/dev/null 2>&1 && echo "✅ Docker 功能正常" || echo "❌ Docker 功能异常"
```

### ✅ 用户权限验证

```bash
# 检查用户组
groups | grep -q docker && echo "✅ 用户已加入 docker 组" || echo "❌ 用户未加入 docker 组"

# 测试无 sudo 执行
docker ps >/dev/null 2>&1 && echo "✅ 无需 sudo 执行 docker 命令" || echo "❌ 需要 sudo 权限"

# 检查 socket 权限
ls -l /var/run/docker.sock | grep -q "docker" && echo "✅ Docker socket 权限正确" || echo "❌ Docker socket 权限错误"
```

### ✅ 配置优化验证

```bash
# 检查 daemon 配置
docker info | grep -q "Registry Mirrors" && echo "✅ 镜像加速配置生效" || echo "❌ 镜像加速配置未生效"

# 检查存储驱动
docker info | grep -q "overlay2" && echo "✅ 存储驱动优化生效" || echo "❌ 存储驱动未优化"

# 检查系统参数
sysctl net.ipv4.ip_forward | grep -q "1" && echo "✅ IP 转发已启用" || echo "❌ IP 转发未启用"
```

## 🚨 故障排除

### Docker 服务问题

```bash
# 问题 1: Docker 服务启动失败
sudo systemctl status docker -l
sudo journalctl -u docker -f

# 检查配置文件语法
sudo dockerd --validate

# 重置 Docker 配置
sudo systemctl stop docker
sudo mv /etc/docker/daemon.json /etc/docker/daemon.json.backup
sudo systemctl start docker
```

### 权限问题

```bash
# 问题 2: Permission denied
# 检查用户组
id $USER | grep docker

# 重新添加用户到组
sudo usermod -aG docker $USER
newgrp docker

# 检查 socket 权限
sudo chown root:docker /var/run/docker.sock
sudo chmod 660 /var/run/docker.sock
```

### 网络问题

```bash
# 问题 3: 容器网络连接失败
# 检查网络配置
docker network ls
docker network inspect bridge

# 重置网络
docker network prune -f
sudo systemctl restart docker

# 检查防火墙规则
sudo iptables -L DOCKER-USER
```

### 存储问题

```bash
# 问题 4: 磁盘空间不足
# 清理未使用资源
docker system prune -a -f

# 检查磁盘使用
docker system df
df -h /var/lib/docker

# 移动 Docker 数据目录
sudo systemctl stop docker
sudo mv /var/lib/docker /opt/docker-data/
# 更新 daemon.json 中的 data-root 配置
sudo systemctl start docker
```

## 🎯 最佳实践

### 镜像管理

```bash
# 定期清理
#!/bin/bash
# 每周执行的清理脚本
docker image prune -f
docker container prune -f
docker volume prune -f
docker network prune -f

# 清理悬空镜像
docker images --filter "dangling=true" -q | xargs -r docker rmi
```

### 资源限制

```bash
# 为生产容器设置资源限制
docker run -d \
  --name my-app \
  --memory="1g" \
  --cpus="1.5" \
  --restart=unless-stopped \
  my-image
```

### 健康检查

```bash
# 容器健康检查示例
docker run -d \
  --name my-service \
  --health-cmd="curl -f http://localhost:8080/health || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  my-service-image
```

## 🔄 下一步

Docker 环境配置完成后，请继续进行：

1. [🔧 网络&基础卷](服务器组件--网络&基础卷.md) - 创建 Docker 网络和数据卷
2. [🗄️ 存储服务](服务器组件--存储服务(MySQL_Redis_MongoDB).md) - 部署数据库服务

---

> 💡 **Docker 运维提醒**:
> - 定期更新 Docker 版本和安全补丁
> - 监控容器资源使用和性能指标
> - 定期清理未使用的镜像和容器
> - 备份重要的数据卷和配置文件
> - 保持镜像仓库的安全和更新