# 网络管理指南

## 概述

本文只覆盖当前推荐网络模型：

- `Docker Swarm` 负责跨主机基础网络层
- `infra-network` 是四节点共用的 attachable overlay
- 业务部署仍然可以继续使用 `docker compose up -d`

## 节点角色

| 节点 | 角色 | 说明 |
|------|------|------|
| `serverA` | manager | 首个 manager |
| `serverB` | manager | 第二个 manager |
| `serverD` | manager | 第三个 manager |
| `serverC` | worker | Mongo 所在节点 |

## 网络类型

| 网络名称 | 类型 | 子网 | 用途 |
|---------|------|------|------|
| `infra-network` | overlay | `172.20.0.0/24` | 基础设施共享网络 |
| `<app>-network` | bridge/overlay | `172.21+.0.0/24` | 业务应用专用网络 |

## 核心原则

### 单向依赖

```text
业务应用 ──→ infra-network ──→ 基础设施服务
```

- 基础设施组件只接 `infra-network`
- 业务应用接自己的业务网络，同时接 `infra-network`
- 跨主机依赖优先通过容器名，不直接依赖宿主机 IP

### 固定互联地址

每个节点都要显式使用：

- `advertise-addr`
- `data-path-addr`

如果没有独立数据网卡，`data-path-addr` 可先等于 `advertise-addr`。

### 防火墙白名单

以下端口只对白名单 Swarm 节点开放：

- `2377/tcp`
- `7946/tcp`
- `7946/udp`
- `4789/udp`
- `ESP (protocol 50)`，启用 overlay 加密时

## 常用命令

### 初始化首个 manager

```bash
make swarm-init SWARM_ADVERTISE_ADDR=<serverA-ip> SWARM_DATA_PATH_ADDR=<serverA-data-ip>
```

### 加入额外 manager

```bash
make swarm-join-manager \
  SWARM_MANAGER_IP=<serverA-ip> \
  SWARM_TOKEN=<manager-token> \
  SWARM_ADVERTISE_ADDR=<node-ip> \
  SWARM_DATA_PATH_ADDR=<node-data-ip>
```

### 加入 worker

```bash
make swarm-join-worker \
  SWARM_MANAGER_IP=<serverA-ip> \
  SWARM_TOKEN=<worker-token> \
  SWARM_ADVERTISE_ADDR=<serverC-ip> \
  SWARM_DATA_PATH_ADDR=<serverC-data-ip>
```

### 查看状态

```bash
make swarm-status
docker node ls
docker network inspect infra-network
```

### 创建基础网络

```bash
INFRA_BACKEND_SUBNET=172.20.0.0/24 \
INFRA_NETWORK_MTU=1450 \
INFRA_NETWORK_ENCRYPTED=true \
make init
```

## 网络创建参数

当前默认参数由 [scripts/02-components/init-infrastructure.sh](../../scripts/02-components/init-infrastructure.sh) 控制：

- `INFRA_BACKEND_SUBNET=172.20.0.0/24`
- `INFRA_BACKEND_GATEWAY=172.20.0.1`
- `INFRA_NETWORK_MTU=1450`
- `INFRA_NETWORK_DRIVER=overlay`
- `INFRA_NETWORK_ENCRYPTED=true`

## 应用接入方式

### 单服务接入

```yaml
services:
  your-app:
    image: your-app:latest
    networks:
      - app-network
      - infra-network

networks:
  app-network:
    driver: bridge
  infra-network:
    external: true
```

### 跨主机依赖示例

```yaml
environment:
  MONGO_HOST: mongo
  MONGO_PORT: 27017
  NSQ_NSQD_HOST: nsqd
  NSQ_LOOKUPD_HOST: nsqlookupd
```

只要目标容器也接入 `infra-network`，这些名字就能跨主机解析。

## 网络验证

### 1. 节点层

```bash
docker node ls
docker info | grep -A10 Swarm
```

### 2. overlay 层

```bash
docker network ls | grep infra-network
docker network inspect infra-network | grep -A4 Peers
```

### 3. 容器层

```bash
docker run --rm --network infra-network alpine ping -c 2 mongo
docker run --rm --network infra-network alpine ping -c 2 nsqd
```

### 4. 监控抓取层

```bash
docker exec prometheus wget -qO- http://qs-apiserver:8080/metrics | head
docker exec prometheus wget -qO- http://qs-worker:9092/metrics | head
```

## 常见问题

### 节点 join 失败

先检查：

1. `advertise-addr` 是否正确
2. `2377/tcp` 是否只对白名单节点放开
3. 是否误把公网漂移 IP 当成 swarm 地址

### `infra-network` 没有下发到某个节点

先看：

```bash
docker network inspect infra-network | grep -A4 Peers
```

必要时创建全局占位服务：

```bash
docker service create --mode global --name net-probe --network infra-network alpine sleep 1d
docker service rm net-probe
```

### 跨主机名字解析失败

通常只会是这几种原因：

1. 容器没接入 `infra-network`
2. 目标节点 overlay 没下发成功
3. 节点间 `7946/tcp+udp` / `4789/udp` 不通

### 跨云性能抖动

优先检查：

1. MTU 是否需要进一步下调
2. `data-path-addr` 是否显式配置
3. 是否启用了 overlay 加密
4. 云防火墙是否对 UDP/ESP 有限制

## 安全建议

- 不要把 `4789/udp` 暴露给公网任意来源
- manager 节点保持奇数
- Mongo 所在节点保持 worker
- 先验证 overlay 稳定，再迁移核心数据链路

## 相关文档

- [网络架构](./architecture.md)
- [Swarm 初始化与排障](./swarm-setup.md)
- [共享网络定义](../../components/networks/README.md)
