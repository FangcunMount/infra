# 网络管理参考

本文不是建网操作手册。当前唯一的建网主流程是：

- [Tailscale + 四节点 Swarm 初始化与排障](./swarm-setup.md)

如果要从零初始化 serverA/serverB/serverC/serverD，请按 `swarm-setup.md` 执行，不要从本文复制初始化命令。

## 当前网络模型

```text
Tailscale underlay
        ↓
Docker Swarm advertise/data-path 使用 Tailscale IP
        ↓
infra-network attachable overlay
```

关键约束：

- `serverA/serverB/serverD` 是 Swarm manager。
- `serverC` 是 Swarm worker，专门承载 MongoDB。
- `INFRA_NETWORK_ENCRYPTED=false`，Docker overlay 不启用 ESP。
- 节点链路加密由 Tailscale 承担。
- Mihomo 只作为应用代理，不应劫持 `100.64.0.0/10`。

## 日常检查

### Tailscale

```bash
tailscale status
tailscale ip -4
tailscale ping <peer-ts-ip>
sudo make tailscale-check
```

### Swarm

```bash
docker node ls
docker info | grep -A10 Swarm
```

### infra-network

```bash
docker network ls | grep infra-network
docker network inspect infra-network | grep -A4 Peers
```

### 容器名解析

```bash
docker run --rm --network infra-network alpine ping -c 2 mongo
docker run --rm --network infra-network alpine ping -c 2 nsqd
```

## 常见故障定位

### 节点 join 失败

优先检查：

- `tailscale status` 是否能看到所有节点。
- `tailscale ping <peer-ts-ip>` 是否成功。
- `advertise-addr` / `data-path-addr` 是否使用了 `tailscale ip -4`。
- 当前节点是否残留 `Swarm: pending`，如有先执行 `docker swarm leave --force`。

### infra-network 没有下发到某个节点

先看 peer：

```bash
docker network inspect infra-network | grep -A4 Peers
```

必要时创建全局占位服务触发网络下发：

```bash
docker service create --mode global --name net-probe --network infra-network alpine sleep 1d
docker service rm net-probe
```

### 跨主机容器名解析失败

通常只会是这几类原因：

- 容器没接入 `infra-network`。
- 目标节点 overlay peer 没下发成功。
- Swarm 使用了公网 IP 或错误网卡 IP，而不是 Tailscale IP。
- Mihomo TUN 劫持了 `100.64.0.0/10`。

## 相关文档

- [网络架构](./architecture.md)
- [Tailscale + 四节点 Swarm 初始化与排障](./swarm-setup.md)
- [共享网络定义](../../components/networks/README.md)
