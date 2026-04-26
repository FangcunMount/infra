# 四节点跨云 Swarm 初始化与排障

本文记录当前推荐的 `Swarm + attachable overlay` 基础网络层初始化方式。

## 目标拓扑

- `serverA`：manager
- `serverB`：manager
- `serverD`：manager
- `serverC`：worker

说明：

- `serverA/serverB` 位于云服务商 A
- `serverC/serverD` 位于云服务商 B
- `serverC` 运行 MongoDB，保持 `worker` 角色，避免叠加控制面

## 关键原则

1. 每个节点都要显式指定 `--advertise-addr`
2. 跨云场景建议显式指定 `--data-path-addr`
3. 只有 manager 节点创建 `infra-network`
4. `infra-network` 默认启用 overlay 数据面加密
5. Swarm 端口只能对白名单节点开放

## 必需端口

四台机器之间放通：

- `2377/tcp`
- `7946/tcp`
- `7946/udp`
- `4789/udp`
- `IP protocol 50 (ESP)`，当 overlay 加密启用时

## 初始化步骤

### 1. 安装 Docker（四台）

```bash
sudo make server-install-docker
docker --version
docker compose version
```

### 2. 在 serverA 初始化首个 manager

```bash
sudo ./scripts/01-network/swarm-manager.sh init-manager <serverA-advertise-ip> [serverA-data-ip]
```

例如：

```bash
sudo ./scripts/01-network/swarm-manager.sh init-manager 10.10.0.11 10.10.0.11
```

### 3. 获取 join token

```bash
sudo ./scripts/01-network/swarm-manager.sh get-join-token
```

会同时输出：

- worker token
- manager token

### 4. 将 serverB 加入为 manager

```bash
sudo ./scripts/01-network/swarm-manager.sh join-manager <serverA-ip> <manager-token> <serverB-advertise-ip> [serverB-data-ip]
```

### 5. 将 serverD 加入为 manager

```bash
sudo ./scripts/01-network/swarm-manager.sh join-manager <serverA-ip> <manager-token> <serverD-advertise-ip> [serverD-data-ip]
```

### 6. 将 serverC 加入为 worker

```bash
sudo ./scripts/01-network/swarm-manager.sh init-worker <serverA-ip> <worker-token> <serverC-advertise-ip> [serverC-data-ip]
```

### 7. 确认 manager 多数派

在任一 manager 上：

```bash
docker node ls
```

预期：

- `serverA/serverB/serverD` 都是 `Manager`
- 至少 2 个 manager 处于 `Reachable` / `Leader`
- `serverC` 为 `Ready` 的 `Worker`

### 8. 创建基础网络

在任一 manager 上：

```bash
sudo ./scripts/01-network/swarm-manager.sh create-network
```

或使用初始化脚本：

```bash
INFRA_BACKEND_SUBNET=172.20.0.0/24 \
INFRA_NETWORK_MTU=1450 \
INFRA_NETWORK_ENCRYPTED=true \
bash ./scripts/02-components/init-infrastructure.sh create
```

### 9. 确认网络 peer

```bash
docker network inspect infra-network | grep -A4 Peers
```

应该看到 4 个节点。

如果 worker 上还没看到网络，可临时创建全局服务触发网络下发：

```bash
docker service create --mode global --name net-probe --network infra-network alpine sleep 1d
docker service rm net-probe
```

## attachable overlay 的用法

当前仓库不是用 `docker stack deploy` 管业务，而是继续在每台机器上执行：

```bash
docker compose up -d
```

只要容器加入了同一个外部 `infra-network`，它们仍可以跨主机通过容器名互访。

例如：

- `mongo:27017`
- `nsqd:4150`
- `qs-apiserver:8080`

## 验证命令

### 节点状态

```bash
docker node ls
docker info | grep -A10 Swarm
```

### 网络状态

```bash
docker network ls | grep infra-network
docker network inspect infra-network
```

### 跨主机探测

```bash
docker run --rm --network infra-network alpine ping -c 2 mongo
docker run --rm --network infra-network alpine ping -c 2 nsqd
```

## 常见问题

### 1. 某个节点 join 失败

优先检查：

- `advertise-addr` 是否填成了错误出口 IP
- `2377/tcp` 是否只对白名单节点开放
- 云防火墙 / 安全组是否同时放行 `7946/tcp+udp`、`4789/udp`

### 2. `infra-network` 在 worker 上看不到

先检查：

```bash
docker network inspect infra-network | grep -A4 Peers
```

如果 peer 不全，先创建 `net-probe` 全局服务触发下发。

### 3. overlay 能建但容器互访不稳定

优先排查：

- MTU 是否需要进一步下调
- 跨云网络是否对 UDP / ESP 有限制
- `data-path-addr` 是否显式绑定到了错误接口

### 4. 单个 manager 掉线后无法管理集群

这是旧双机或单 manager 模式常见问题。
当前方案要求 `A/B/D` 三个 manager，就是为了避免这个点。

## 迁移建议

如果你现在已经有旧双机 Swarm：

1. 先在低峰期把 `serverB/serverD` 加入为 manager
2. 再加入 `serverC` 为 worker
3. 确认 `docker node ls` 稳定
4. 再重建 `infra-network`
5. 最后让 `serverC/serverD` 上的容器接入该网络

不要在跨云节点尚未稳定之前，直接把 Mongo 切到新的跨机访问路径。
