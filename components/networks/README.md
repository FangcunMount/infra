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
- Tailscale underlay MTU：`1280`
- 容器 overlay 端点 MTU：约 `1230`（扣除约 50 字节 VXLAN 开销）
- Docker overlay 数据面加密：`disabled`
- 底层节点链路加密：`Tailscale`

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

每台机器都要先加入同一个 Tailscale tailnet，并准备一组稳定的节点互联地址：

- `advertise-addr`：控制面地址
- `data-path-addr`：数据面地址

当前推荐两者都使用本机 `tailscale ip -4`，不要使用公网 IP 或 Mihomo 代理出口 IP。

### 3. 放通端口

四台机器之间必须互通：

- `2377/tcp`
- `7946/tcp`
- `7946/udp`
- `4789/udp`
这些端口走 Tailscale 节点网络；云安全组不需要向公网开放 Swarm 端口。
Docker overlay 不再启用 `encrypted=true`，因此不依赖 `IP protocol 50 (ESP)`。

## 初始化顺序

### 1. 初始化首个 manager（serverA）

先在 serverA 上执行 `make tailscale-ip`，然后：

```bash
sudo ./scripts/01-network/swarm-manager.sh init-manager <serverA-ts-ip> <serverA-ts-ip>
```

### 2. 获取 join token

```bash
sudo ./scripts/01-network/swarm-manager.sh get-join-token
```

### 3. 将 serverB / serverD 加入为 manager

```bash
sudo ./scripts/01-network/swarm-manager.sh join-manager <serverA-ts-ip> <manager-token> <node-ts-ip> <node-ts-ip>
```

### 4. 将 serverC 加入为 worker

```bash
sudo ./scripts/01-network/swarm-manager.sh init-worker <serverA-ts-ip> <worker-token> <serverC-ts-ip> <serverC-ts-ip>
```

### 5. 在任一 manager 上创建 overlay 网络

```bash
sudo ./scripts/01-network/swarm-manager.sh create-network
```

或：

```bash
INFRA_BACKEND_SUBNET=172.20.0.0/24 \
INFRA_NETWORK_MTU=1280 \
INFRA_NETWORK_ENCRYPTED=false \
bash ./scripts/02-components/init-infrastructure.sh create
```

## 验证

先验证仓库中的 MTU 策略没有回退：

```bash
make network-mtu-policy-verify
```

在接入生产 overlay 的节点上验证实际网络。以 serverA 的 apiserver 到 Mongo 为例：

```bash
make network-mtu-verify \
  MTU_VERIFY_CONTAINER=qs-apiserver \
  MTU_VERIFY_TARGET=mongo
```

预期同时满足：

- `infra-network` driver MTU 为 `1280`
- `tailscale0` MTU 为 `1280`
- 容器端点 MTU 不大于 `1230`
- 到跨主机目标的 PMTU 不大于 `1230`

`infra-network` 已存在时，初始化脚本不会原地修改 MTU。Docker overlay
也不支持原地更新该选项，必须在维护窗口内保存容器 aliases、断开全部
旧端点、重建同名网络并按依赖顺序重连。不要在仍有容器挂载时直接运行
`docker network rm infra-network`。

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
