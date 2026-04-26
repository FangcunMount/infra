# Tailscale + 四节点 Swarm 初始化与排障

本文记录当前推荐的基础网络层初始化方式：

```text
Tailscale 加密节点网络
        ↓
Docker Swarm advertise/data-path 使用 Tailscale IP
        ↓
infra-network attachable overlay，Docker overlay encryption 关闭
```

这样应用侧仍然使用容器名访问，例如 `mongo:27017`、`nsqd:4150`、`qs-apiserver:9090`，但跨云节点链路由 Tailscale 加密，不再依赖云安全组支持 `ESP / IP protocol 50`。

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

1. 四台机器先加入同一个 Tailscale tailnet。
2. `--advertise-addr` 和 `--data-path-addr` 都使用本机 `tailscale ip -4`。
3. `infra-network` 只在 manager 上创建。
4. `INFRA_NETWORK_ENCRYPTED=false`，不要启用 Docker encrypted overlay。
5. Mihomo 继续作为应用代理，不要让 Mihomo TUN 劫持 `100.64.0.0/10`。

## Tailscale 与 Mihomo 边界

两者可以共存，但职责必须分开：

- Tailscale：节点互联网络，用于 Swarm control/data path。
- Mihomo：应用代理，用于 Docker 拉镜像、命令行访问外网等。

如果 Mihomo 开启 TUN/透明代理，配置里应确保这些流量直连：

```yaml
rules:
  - IP-CIDR,100.64.0.0/10,DIRECT,no-resolve
  - IP-CIDR,100.100.100.100/32,DIRECT,no-resolve
  - DOMAIN-SUFFIX,ts.net,DIRECT
  - DOMAIN-SUFFIX,tailscale.com,DIRECT
```

Tailscale 推荐启动参数：

```bash
tailscale up \
  --hostname=<server-name> \
  --accept-dns=false \
  --accept-routes=false \
  --ssh=false
```

`accept-dns=false` 避免接管系统 DNS；`accept-routes=false` 避免接受 exit-node/subnet-route 导致默认路由变化。

## 必需端口

云安全组不再需要对公网开放 Swarm 端口。Swarm 端口应只在 Tailscale 节点网络内通信：

- `2377/tcp`
- `7946/tcp`
- `7946/udp`
- `4789/udp`

不再需要 `IP protocol 50 (ESP)`，因为 Docker overlay encryption 关闭，底层链路由 Tailscale 加密。

## 初始化步骤

### 1. 安装 Docker（四台）

```bash
sudo make server-install-docker
docker --version
docker compose version
```

### 2. 安装并启动 Tailscale（四台）

交互式登录：

```bash
sudo make tailscale-install
sudo make tailscale-up TAILSCALE_HOSTNAME=serverA
```

使用 auth key 非交互登录：

```bash
sudo make tailscale-install
sudo make tailscale-up \
  TAILSCALE_HOSTNAME=serverA \
  TAILSCALE_AUTH_KEY=tskey-auth-xxx
```

每台机器把 `TAILSCALE_HOSTNAME` 分别设为 `serverA/serverB/serverC/serverD`。

### 3. 获取每台机器的 Tailscale IP

在每台机器上：

```bash
make tailscale-ip
sudo make tailscale-check
```

记录结果，例如：

```text
serverA 100.x.x.11
serverB 100.x.x.12
serverC 100.x.x.13
serverD 100.x.x.14
```

同步更新 `compose/env/prod/*.env` 里的 `NODE_A_IP`、`NODE_B_IP`、`NODE_C_IP`、`NODE_D_IP`。

### 4. 在 serverA 初始化首个 manager

```bash
sudo ./scripts/01-network/swarm-manager.sh init-manager <serverA-ts-ip> <serverA-ts-ip>
```

或：

```bash
make swarm-init \
  SWARM_ADVERTISE_ADDR=<serverA-ts-ip> \
  SWARM_DATA_PATH_ADDR=<serverA-ts-ip>
```

### 5. 获取 join token

在任一 manager 上：

```bash
sudo ./scripts/01-network/swarm-manager.sh get-join-token
```

会同时输出：

- worker token
- manager token

不要把 token 写入文档或聊天记录；泄露后执行 `docker swarm join-token --rotate manager` / `worker` 轮换。

### 6. 将 serverB 加入为 manager

```bash
sudo ./scripts/01-network/swarm-manager.sh join-manager \
  <serverA-ts-ip> \
  <manager-token> \
  <serverB-ts-ip> \
  <serverB-ts-ip>
```

### 7. 将 serverD 加入为 manager

```bash
sudo ./scripts/01-network/swarm-manager.sh join-manager \
  <serverA-ts-ip> \
  <manager-token> \
  <serverD-ts-ip> \
  <serverD-ts-ip>
```

### 8. 将 serverC 加入为 worker

```bash
sudo ./scripts/01-network/swarm-manager.sh init-worker \
  <serverA-ts-ip> \
  <worker-token> \
  <serverC-ts-ip> \
  <serverC-ts-ip>
```

### 9. 确认 manager 多数派

在任一 manager 上：

```bash
docker node ls
```

预期：

- `serverA/serverB/serverD` 都是 `Manager`
- 至少 2 个 manager 处于 `Reachable` / `Leader`
- `serverC` 为 `Ready` 的 `Worker`

### 10. 创建基础网络

在任一 manager 上：

```bash
INFRA_NETWORK_ENCRYPTED=false \
sudo ./scripts/01-network/swarm-manager.sh create-network
```

或使用初始化脚本：

```bash
INFRA_BACKEND_SUBNET=172.20.0.0/24 \
INFRA_NETWORK_MTU=1450 \
INFRA_NETWORK_ENCRYPTED=false \
bash ./scripts/02-components/init-infrastructure.sh create
```

## attachable overlay 的用法

当前仓库不是用 `docker stack deploy` 管业务，而是继续在每台机器上执行：

```bash
docker compose up -d
```

只要容器加入同一个外部 `infra-network`，它们仍可以跨主机通过容器名互访。

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

### Tailscale 连通性

```bash
tailscale ping <serverB-ts-ip>
tailscale ping <serverC-ts-ip>
tailscale ping <serverD-ts-ip>
```

### 跨主机探测

```bash
docker run --rm --network infra-network alpine ping -c 2 mongo
docker run --rm --network infra-network alpine ping -c 2 nsqd
```

如果 worker 上还没看到网络，可临时创建全局服务触发网络下发：

```bash
docker service create --mode global --name net-probe --network infra-network alpine sleep 1d
docker service rm net-probe
```

## 常见问题

### 1. 某个节点 join 失败

优先检查：

- `tailscale status` 是否能看到所有节点
- `tailscale ping <peer-ts-ip>` 是否成功
- `advertise-addr` 是否填成了公网 IP 或 Mihomo 代理出口 IP
- 当前节点是否还处于 `Swarm: pending`，如是先 `docker swarm leave --force`

### 2. `infra-network` 在 worker 上看不到

先检查：

```bash
docker network inspect infra-network | grep -A4 Peers
```

如果 peer 不全，先创建 `net-probe` 全局服务触发下发。

### 3. overlay 能建但容器互访不稳定

优先排查：

- MTU 是否需要从 `1450` 进一步下调到 `1400` 或 `1280`
- Mihomo TUN 是否劫持 `100.64.0.0/10`
- `data-path-addr` 是否显式绑定到了错误接口
- 是否误开了 `INFRA_NETWORK_ENCRYPTED=true` 导致重新依赖 ESP

### 4. 单个 manager 掉线后无法管理集群

这是旧双机或单 manager 模式常见问题。
当前方案要求 `A/B/D` 三个 manager，就是为了避免这个点。

## 迁移建议

如果你现在已经有旧公网 IP Swarm：

1. 低峰期备份当前 token 和节点信息。
2. 每台机器先加入 Tailscale，确认 `tailscale ping` 互通。
3. 如节点已用公网 IP 加入 Swarm，逐台 `docker swarm leave --force` 后用 Tailscale IP 重新加入。
4. 确认 `docker node ls` 稳定。
5. 删除并重建 `infra-network`，确保 `INFRA_NETWORK_ENCRYPTED=false`。
6. 最后让 `serverC/serverD` 上的容器接入该网络。

不要在跨云节点尚未稳定之前，直接把 Mongo 切到新的跨机访问路径。
