# Docker Swarm 跨主机部署指南

## 🎯 部署架构

```text
ServerA (管理节点)                    ServerB (工作节点)
├── Redis                            ├── NSQ (nsqlookupd, nsqd, nsqadmin)
├── MongoDB                          └── 业务应用
├── 业务应用
└── Swarm Manager

         ↕ Docker Swarm Overlay Network (infra-network)
    容器间通过服务名直接通信，无需配置 IP
```

---

## 🚀 快速开始（5分钟部署）

### ServerA (管理节点) - 192.168.1.100

```bash
# 1. 初始化 Swarm
make swarm-init ADVERTISE_ADDR=192.168.1.100

# 2. 创建 overlay 网络
make swarm-network

# 3. 启动基础设施服务
make install
make up
```

### ServerB (工作节点) - 192.168.1.101

```bash
# 1. 加入 Swarm 集群
make swarm-join MANAGER_IP=192.168.1.100

# 2. 验证节点状态（在 ServerA 执行）
make swarm-status
make swarm-nodes
```

### 验证部署

```bash
# ServerA 上验证
docker network ls | grep infra-network
docker ps

# ServerB 上验证
docker network ls | grep infra-network

# 测试跨主机通信
docker exec <container-on-serverA> ping <container-on-serverB>
```

---

## 📋 详细部署步骤

### 阶段 1: 准备工作

#### 1.1 检查网络互通

```bash
# 在 ServerA 上
ping <ServerB-IP>

# 在 ServerB 上
ping <ServerA-IP>
```

#### 1.2 开放 Swarm 端口

在**两台服务器**上执行：

```bash
# 使用脚本自动配置
bash scripts/network/swarm-manager.sh init-manager --advertise-addr <YOUR-IP>

# 或手动配置防火墙
sudo ufw allow 2377/tcp    # 集群管理
sudo ufw allow 7946/tcp    # 节点通信
sudo ufw allow 7946/udp    # 节点通信
sudo ufw allow 4789/udp    # overlay网络
sudo ufw reload
```

### 阶段 2: 初始化 Swarm 集群

#### 2.1 ServerA 初始化管理节点

```bash
# 方式1: 使用 Makefile
make swarm-init ADVERTISE_ADDR=192.168.1.100

# 方式2: 使用脚本
bash scripts/network/swarm-manager.sh init-manager --advertise-addr 192.168.1.100

# 方式3: 直接使用 Docker
docker swarm init --advertise-addr 192.168.1.100
```

初始化成功后会显示：

```text
✅ Swarm 集群初始化成功！

管理节点 Token:
SWMTKN-1-xxxxx-manager-token-xxxxx

工作节点 Token:
SWMTKN-1-xxxxx-worker-token-xxxxx

请在其他节点上运行以下命令加入集群:
make swarm-join MANAGER_IP=192.168.1.100
```

#### 2.2 ServerB 加入集群

```bash
# 方式1: 使用 Makefile
make swarm-join MANAGER_IP=192.168.1.100

# 方式2: 使用脚本
bash scripts/network/swarm-manager.sh init-worker --manager-ip 192.168.1.100
```

### 阶段 3: 创建 Overlay 网络

#### 3.1 创建基础设施网络

在 **ServerA（管理节点）** 上执行：

```bash
# 方式1: 使用 Makefile
make swarm-network

# 方式2: 使用 compose（推荐）
cd compose/base
docker-compose -f docker-compose.yml up -d
```

这会创建名为 `infra-network` 的 overlay 网络，配置：

- Driver: overlay
- Subnet: 172.20.0.0/16
- Gateway: 172.20.0.1
- Attachable: true（允许独立容器附加）
- MTU: 1450（适配大部分网络环境）

#### 3.2 验证网络

```bash
# ServerA 上查看
docker network ls | grep infra-network

# ServerB 上查看（overlay 网络会自动同步）
docker network ls | grep infra-network

# 查看网络详情
docker network inspect infra-network
```

### 阶段 4: 部署服务

#### 4.1 ServerA 部署存储服务

```bash
# 安装服务
make install-mysql
make install-redis  
make install-mongo

# 启动服务
make up-storage

# 验证
docker ps
```

#### 4.2 ServerB 部署消息服务

```bash
# 确保已加入 Swarm 集群
make swarm-status

# 安装服务
make install-nsq

# 启动服务
make up-message

# 验证
docker ps
```

#### 4.3 测试跨主机通信

```bash
# 在 ServerA 的容器中
docker exec mysql ping redis           # ✅ 同主机通信
docker exec mysql ping nsqd            # ✅ 跨主机通信

# 在 ServerB 的容器中  
docker exec nsqd ping mysql            # ✅ 跨主机通信
docker exec nsqd ping redis            # ✅ 跨主机通信
```

---

## 🔧 管理命令

### 查看集群状态

```bash
# 查看整体状态
make swarm-status

# 列出所有节点
make swarm-nodes

# 查看节点详情
docker node inspect <NODE-ID>
```

### 节点管理

```bash
# 提升工作节点为管理节点
docker node promote <NODE-ID>

# 降级管理节点为工作节点
docker node demote <NODE-ID>

# 设置节点可用性
docker node update --availability active <NODE-ID>
docker node update --availability pause <NODE-ID>
docker node update --availability drain <NODE-ID>
```

### 离开集群

```bash
# 工作节点离开
make swarm-leave

# 管理节点强制离开
docker swarm leave --force
```

---

## ⚠️ 注意事项

### 1. 网络驱动选择

- **单主机**: 使用 `bridge` 驱动（性能更好）
- **跨主机**: 必须使用 `overlay` 驱动

### 2. 端口冲突

确保两台服务器上不要部署相同端口的服务：

- ServerA: MySQL(3306), Redis(6379), MongoDB(27017)
- ServerB: NSQ(4150,4151,4160,4161,4171)

### 3. 数据持久化

overlay 网络不影响数据卷，数据仍然存储在各自主机上：

```yaml
volumes:
  mysql-data:
    driver: local  # 本地存储，不跨主机
```

### 4. 服务发现

容器间通过**服务名**通信，而非 IP：

```bash
# ✅ 正确
redis://redis:6379
mongodb://mongo:27017

# ❌ 错误（IP 可能变化）
redis://172.20.0.10:6379
```

### 5. 高可用性

生产环境建议：

- 至少 3 个管理节点（保证高可用）
- 工作节点按需扩展
- 关键服务配置副本

```bash
# 添加第三个管理节点
make swarm-join MANAGER_IP=192.168.1.100 NODE_TYPE=manager
```

---

## 🔍 故障排查

### 问题 1: 节点无法加入集群

**症状**: `Error response from daemon: rpc error`

**解决**:

```bash
# 1. 检查防火墙
sudo ufw status

# 2. 检查端口是否开放
nc -zv <MANAGER-IP> 2377

# 3. 检查管理节点状态
docker node ls

# 4. 重新获取 token
docker swarm join-token worker
```

### 问题 2: 容器无法跨主机通信

**症状**: `ping: bad address`

**解决**:

```bash
# 1. 确认网络存在
docker network ls | grep infra-network

# 2. 确认容器已连接到网络
docker network inspect infra-network

# 3. 检查 UDP 4789 端口
sudo ufw allow 4789/udp

# 4. 检查 MTU 设置
ip link show
```

### 问题 3: Overlay 网络未同步到工作节点

**症状**: ServerB 上看不到 infra-network

**解决**:

```bash
# 1. 确认节点已加入集群
docker node ls

# 2. 重启 Docker 服务
sudo systemctl restart docker

# 3. 在工作节点上手动拉取网络（启动使用该网络的容器）
docker run -d --network infra-network alpine sleep 3600
```

### 问题 4: 管理节点宕机

**症状**: 集群无法管理

**解决**:

```bash
# 如果有多个管理节点，会自动选举新 Leader
docker node ls

# 如果只有一个管理节点，需要恢复该节点
# 或在工作节点上强制初始化新集群（会丢失原集群信息）
docker swarm init --force-new-cluster
```

---

## 📊 监控和日志

### 查看服务日志

```bash
# 查看特定服务日志
make logs SERVICE=mysql
make logs SERVICE=redis

# 实时跟踪日志
docker logs -f <container-name>
```

### 监控资源使用

```bash
# 查看容器资源占用
docker stats

# 查看节点资源
docker node inspect <NODE-ID> --format '{{.Status.State}}'
```

---

## 🎯 最佳实践

### 1. 标签管理

为节点打标签，便于服务调度：

```bash
# 标记存储节点
docker node update --label-add type=storage serverA

# 标记计算节点
docker node update --label-add type=compute serverB

# 部署时使用约束
docker service create --constraint 'node.labels.type==storage' ...
```

### 2. 网络隔离

不同环境使用不同网络：

```bash
# 生产环境
make app-network-create NAME=prod-network DRIVER=overlay

# 测试环境
make app-network-create NAME=test-network DRIVER=overlay
```

### 3. 健康检查

为服务配置健康检查：

```yaml
healthcheck:
  test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
  interval: 10s
  timeout: 5s
  retries: 3
```

### 4. 定期备份

定期备份管理节点配置：

```bash
# 备份 Swarm 配置
docker swarm ca > swarm-ca.pem
```

---

## 📚 相关资源

- 网络管理完整指南: `docs/网络管理/网络管理完整指南.md`
- Swarm 官方文档: <https://docs.docker.com/engine/swarm/>
- Overlay 网络文档: <https://docs.docker.com/network/overlay/>

---

**快速帮助**: 运行 `make help` 查看所有可用命令
