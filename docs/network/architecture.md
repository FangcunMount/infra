# 网络架构

## 概述

本项目采用 **Docker Swarm Overlay 网络** 实现跨服务器容器通信。所有基础设施服务和业务应用通过统一的 `infra-network` 进行服务发现和通信。

## 网络拓扑 (v2.1 双机架构)

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                         Docker Swarm Cluster                              │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                    infra-network (overlay, attachable)               │ │
│  │                         172.20.0.0/16                                │ │
│  │                                                                      │ │
│  │   ServerA (2C4G)                    ServerB (2C2G)                  │ │
│  │   172.17.0.223                      10.0.0.22                       │ │
│  │   ┌─────────────────────┐          ┌─────────────────────┐         │ │
│  │   │ nginx      :80/443  │          │ nsqlookupd :4160/61 │         │ │
│  │   │ redis-cache:6379    │◀────────▶│ nsqd       :4150/51 │         │ │
│  │   │ mongo      :27017   │          │ nsqadmin   :4171    │         │ │
│  │   │                     │          │                     │         │ │
│  │   │ [业务应用可部署]    │          │ [业务应用可部署]    │         │ │
│  │   └─────────────────────┘          └─────────────────────┘         │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│                    [VXLAN Tunnel - Port 4789/UDP]                       │
└──────────────────────────────────────────────────────────────────────────┘

云服务（外部）:
  ├── 阿里云 RDS (MySQL)
```

## 核心网络: infra-network

### 基本配置

| 属性 | 值 | 说明 |
|------|-----|------|
| **网络名称** | `infra-network` | 统一的基础设施网络 |
| **驱动类型** | `overlay` | 支持跨主机通信 |
| **子网** | `172.20.0.0/16` | 65,534 个可用 IP |
| **网关** | `172.20.0.1` | 默认网关 |
| **MTU** | `1450` | Overlay 推荐值 |
| **Attachable** | `true` | 允许非 Swarm 服务连接 |

### 网络定义

```yaml
# components/networks/docker-compose.yml
networks:
  backend:
    name: infra-network
    driver: overlay
    attachable: true
    ipam:
      config:
        - subnet: 172.20.0.0/16
    driver_opts:
      com.docker.network.driver.mtu: "1450"
```

## 服务发现

### 服务地址表

所有服务通过 **容器名** 访问，无需记忆 IP 地址：

| 服务 | 容器名 | 端口 | 位置 | 访问示例 |
|------|--------|------|------|----------|
| **Nginx** | `nginx` | 80/443 | ServerA | `http://nginx` |
| **Redis** | `redis-cache` | 6379 | ServerA | `redis-cache:6379` |
| **MongoDB** | `mongo` | 27017 | ServerA | `mongo:27017` |
| **NSQLookupd** | `nsqlookupd` | 4160/4161 | ServerB | `nsqlookupd:4161` |
| **NSQd** | `nsqd` | 4150/4151 | ServerB | `nsqd:4150` |
| **NSQAdmin** | `nsqadmin` | 4171 | ServerB | `nsqadmin:4171` |

### 应用配置示例

```yaml
# 应用环境变量配置
environment:
  # Redis 单实例
  REDIS_HOST: redis-cache
  REDIS_PORT: 6379
  
  # 数据库 (本地 MongoDB)
  MONGO_HOST: mongo
  MONGO_PORT: 27017
  
  # 消息队列 (ServerB 的 NSQ)
  NSQ_NSQD_HOST: nsqd
  NSQ_NSQD_PORT: 4150
  NSQ_LOOKUPD_HOST: nsqlookupd
  NSQ_LOOKUPD_PORT: 4161
  
  # 云服务 (使用公网/内网地址)
  MYSQL_HOST: your-rds.mysql.rds.aliyuncs.com
```

---

## 应用部署网络配置

### 快速开始

业务应用只需加入 `infra-network` 即可访问所有基础设施服务。

#### 1. 最简配置

```yaml
# your-app/docker-compose.yml
services:
  your-app:
    image: your-app:latest
    networks:
      - infra-network

networks:
  infra-network:
    external: true
```

#### 2. 完整配置示例

```yaml
# your-app/docker-compose.yml
version: "3.8"

services:
  api:
    image: your-api:latest
    container_name: your-api
    restart: unless-stopped
    ports:
      - "8080:8080"
    environment:
      # 基础设施服务 (通过容器名访问)
      REDIS_HOST: redis-cache
      REDIS_PORT: 6379
      REDIS_PASSWORD: ${REDIS_APP_PASSWORD}
      
      MONGO_URI: mongodb://${MONGO_APP_USER}:${MONGO_APP_PASSWORD}@mongo:27017/${MONGO_DATABASE}?authSource=${MONGO_DATABASE}&replicaSet=rs0&directConnection=true
      
      NSQ_NSQD_ADDR: nsqd:4150
      NSQ_LOOKUPD_ADDR: nsqlookupd:4161
      MYSQL_HOST: ${MYSQL_HOST}
      MYSQL_PORT: ${MYSQL_PORT}
    networks:
      - infra-network
    labels:
      - "infra.app=your-api"
      - "infra.host=serverA"  # 或 serverB

networks:
  infra-network:
    external: true
```

#### 3. 多服务应用

```yaml
# your-app/docker-compose.yml
services:
  api:
    image: your-api:latest
    networks:
      - infra-network
      - app-internal  # 应用内部网络
    
  worker:
    image: your-worker:latest
    networks:
      - infra-network
      - app-internal
    
  scheduler:
    image: your-scheduler:latest
    networks:
      - app-internal  # 不需要直接访问基础设施

networks:
  infra-network:
    external: true
  app-internal:
    driver: bridge  # 应用内部使用 bridge 即可
```

### 部署到不同服务器

#### 部署到 ServerA

```yaml
# 适合需要低延迟访问 Redis/MongoDB 的服务
services:
  api:
    deploy:
      placement:
        constraints:
          - node.hostname == serverA
    networks:
      - infra-network
```

#### 部署到 ServerB

```yaml
# 适合消息消费者服务
services:
  consumer:
    deploy:
      placement:
        constraints:
          - node.hostname == serverB
    networks:
      - infra-network
```

#### 任意节点部署

```yaml
# 无状态服务可以部署到任意节点
services:
  stateless-api:
    # 不指定 placement，Swarm 自动调度
    networks:
      - infra-network
```

### Nginx 反向代理配置

将应用配置添加到 Nginx：

```nginx
# /data/apps/nginx-configs/your-app.conf
upstream your_app {
    server your-api:8080;  # 使用容器名
}

server {
    listen 80;
    server_name your-app.fangcunmount.cn;
    
    location / {
        proxy_pass http://your_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 验证网络连通性

```bash
# 进入应用容器
docker exec -it your-api sh

# 测试 Redis 连接
redis-cli -h redis-cache -p 6379 ping

# 测试 MongoDB 连接
mongosh --host mongo --port 27017 --eval "db.runCommand({ping:1})"

# 测试 NSQ 连接
curl http://nsqd:4151/ping
curl http://nsqlookupd:4161/ping
```

---

## 技术实现

### VXLAN 隧道

Overlay 网络使用 VXLAN (Virtual Extensible LAN) 技术实现跨主机通信：

```text
┌─────────────────────────────────────────────────┐
│  Container → Docker Bridge → VXLAN → Host NIC   │
│                                                 │
│  [容器IP] → [172.20.x.x] → [封装] → [物理IP]   │
└─────────────────────────────────────────────────┘
```

**工作原理**:

1. 容器发送数据包到网关 `172.20.0.1`
2. Docker 封装数据包为 VXLAN 格式
3. 通过 UDP 端口 4789 发送到目标主机
4. 目标主机解封装并转发到目标容器

---

## 端口暴露策略

### ServerA 端口

| 服务 | 端口 | 绑定地址 | 说明 |
|------|------|----------|------|
| Nginx | 80/443 | 0.0.0.0 | 公网访问 |
| Redis | 6379 | 0.0.0.0 | 内网优先 |
| MongoDB | 27017 | 127.0.0.1 | 仅本地 |

### ServerB 端口

| 服务 | 端口 | 绑定地址 | 说明 |
|------|------|----------|------|
| NSQLookupd | 4160/4161 | 0.0.0.0 | 内网访问 |
| NSQd | 4150/4151 | 0.0.0.0 | 内网访问 |
| NSQAdmin | 4171 | 127.0.0.1 | 仅本地 |

---

## 网络优化

### MTU 配置

```yaml
# Overlay 网络推荐 MTU
driver_opts:
  com.docker.network.driver.mtu: "1450"
```

- **1450**: 跨公网推荐（避免分片）
- **1500**: 内网标准
- **9000**: 支持 Jumbo Frame 的内网

## 前置要求

### Docker Swarm 初始化

Overlay 网络依赖 Docker Swarm：

```bash
# ServerA (管理节点)
docker swarm init --advertise-addr <ServerA_IP>

# ServerB (工作节点) - 使用 init 输出的 token
docker swarm join --token SWMTKN-xxx <ServerA_IP>:2377

# 验证集群
docker node ls
```

### 防火墙规则

必须开放以下端口：

| 端口 | 协议 | 用途 |
|------|------|------|
| 2377 | TCP | Swarm 管理 |
| 7946 | TCP/UDP | 节点发现 |
| 4789 | UDP | VXLAN 数据 |

```bash
# 防火墙配置示例
ufw allow 2377/tcp
ufw allow 7946/tcp
ufw allow 7946/udp
ufw allow 4789/udp
```

---

## 故障排查

### 服务无法通信

```bash
# 检查网络状态
docker network inspect infra-network

# 检查容器网络配置
docker inspect <container> | grep -A 10 Networks

# 测试 DNS 解析
docker exec <container> nslookup redis-cache
```

### 跨主机通信失败

```bash
# 检查 Swarm 状态
docker node ls

# 检查 VXLAN 端口
nc -zv <target_ip> 4789

# 重建网络
docker network rm infra-network
make init
```

---

## 常用命令

```bash
# 初始化网络和卷
make init

# 查看网络状态
docker network ls
docker network inspect infra-network

# 测试容器间连通性
docker exec redis-cache ping mongo

# 清理未使用的网络
docker network prune
```

---

## 相关文档

- [服务器架构](../server/architecture.md)
- [组件部署指南](../components/README.md)

---

**更新时间**: 2025-12-01  
**文档版本**: v2.1
