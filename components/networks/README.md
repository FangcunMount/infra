# 共享网络定义

## 概述

`infra-network` 是基础设施组件和业务容器共用的 `Docker Swarm overlay` 网络。

当前目标拓扑不是旧的双机互联，而是`四节点跨云 Swarm 基础网络层`：

- `serverA`：manager
- `serverB`：manager
- `serverD`：manager
- `serverC`：worker

这层网络只解决一件事：`让加入同一 overlay 的容器在四台机器之间继续使用容器名通信`。

## 网络参数

### infra-network

- 驱动：`overlay`
- 附着方式：`attachable`
- 子网：`172.20.0.0/24`
- MTU：`1450`
- 数据面加密：`enabled`

对应定义见 [docker-compose.yml](./docker-compose.yml)。

## 设计边界

- `infra-network` 依赖 `Swarm`，即使业务部署仍然使用 `docker compose up -d`。
- 只有连接到 `infra-network` 的容器，才能跨主机通过容器名发现彼此。
- 这不是 K8s，也不是完整的 Swarm service 编排。当前只是把 Swarm 用作跨主机网络层。

## 前置条件

### 1. 节点角色

推荐固定为：

- `serverA`：首个 manager
- `serverB`：额外 manager
- `serverD`：额外 manager
- `serverC`：worker

这样能让 `A/B` 留在云服务商 A，`D` 在云服务商 B 提供第三个 manager，多数派仍为奇数。

### 2. 固定互联地址

每台机器都要准备一组稳定的节点互联地址：

- `advertise-addr`：控制面地址
- `data-path-addr`：数据面地址

如果没有独立数据网卡，`data-path-addr` 可以先和 `advertise-addr` 相同。

### 3. 放通端口

四台机器之间必须互通：

- `2377/tcp`
- `7946/tcp`
- `7946/udp`
- `4789/udp`
- `IP protocol 50 (ESP)`，当 overlay 加密启用时

这些端口只应该向`四台 Swarm 节点彼此`开放，不要直接暴露给公网。

## 初始化顺序

### 1. 初始化首个 manager（serverA）

```bash
sudo ./scripts/01-network/swarm-manager.sh init-manager <serverA-advertise-ip> [serverA-data-ip]
```

### 2. 获取 join token

```bash
sudo ./scripts/01-network/swarm-manager.sh get-join-token
```

### 3. 将 serverB / serverD 加入为 manager

```bash
sudo ./scripts/01-network/swarm-manager.sh join-manager <serverA-ip> <manager-token> <node-advertise-ip> [node-data-ip]
```

### 4. 将 serverC 加入为 worker

```bash
sudo ./scripts/01-network/swarm-manager.sh init-worker <serverA-ip> <worker-token> <serverC-advertise-ip> [serverC-data-ip]
```

### 5. 在任一 manager 上创建 overlay 网络

```bash
sudo ./scripts/01-network/swarm-manager.sh create-network
```

或：

```bash
INFRA_BACKEND_SUBNET=172.20.0.0/24 \
INFRA_NETWORK_MTU=1450 \
INFRA_NETWORK_ENCRYPTED=true \
bash ./scripts/02-components/init-infrastructure.sh create
```

## 验证

### 查看节点

```bash
docker node ls
```

预期：

- `serverA/serverB/serverD` 为 `Reachable/Leader` 之一
- `serverC` 为 `worker`

### 查看网络 Peers

```bash
docker network inspect infra-network | grep -A4 Peers
```

预期应看到 4 个节点地址。

### 临时全局服务铺网

如果某个节点还没出现 overlay peer，可临时创建全局服务触发网络下发：

```bash
docker service create --mode global --name net-probe --network infra-network alpine sleep 1d
docker service rm net-probe
```

### 测试跨主机名字解析

在任一已接入 `infra-network` 的容器内：

```bash
docker exec <container> ping -c 2 mongo
docker exec <container> ping -c 2 nsqd
```

## 迁移注意事项

- 老文档中仍可能提到双机 `serverA/serverB`，但网络层现在以四节点拓扑为准。
- 业务编排是否改成四机部署，是下一层工作；本目录只维护网络基座。
- `infra-network` 的子网从 `172.20.0.0/16` 收敛到 `172.20.0.0/24`，相关信任网段配置也要同步更新。

## 故障定位

优先检查：

1. `docker node ls` 是否仍有多数 manager `Ready`
2. 四台机器之间是否只对白名单源开放了 Swarm 端口
3. `docker network inspect infra-network` 的 `Peers` 是否齐全
4. 节点初始化时是否显式使用了正确的 `advertise-addr` / `data-path-addr`

## 相关文件

- [components/networks/docker-compose.yml](./docker-compose.yml)
- [scripts/01-network/swarm-manager.sh](../../scripts/01-network/swarm-manager.sh)
- [scripts/02-components/init-infrastructure.sh](../../scripts/02-components/init-infrastructure.sh)
- [docs/network/architecture.md](../../docs/network/architecture.md)
- [docs/network/swarm-setup.md](../../docs/network/swarm-setup.md)
