# 网络架构

## 概述

本项目当前采用 `Tailscale underlay + Docker Swarm attachable overlay` 作为跨主机基础网络层。

目标不是把所有业务切到 `docker stack`，而是：

- 保留现有按机器 `docker compose up -d` 的部署方式
- 让不同主机上的容器继续通过`容器名`互相访问
- 在跨云场景下，为 Mongo / NSQ / 业务容器提供统一的容器网络平面
- 通过 Tailscale 承载节点互联加密，避免云安全组无法放行 ESP/IP protocol 50 的问题

## 当前目标拓扑

### 节点角色

| 节点 | 云厂商 | Swarm 角色 | 说明 |
|------|--------|------------|------|
| `serverA` | A | manager | 首个 manager |
| `serverB` | A | manager | 第二个 manager |
| `serverD` | B | manager | 第三个 manager |
| `serverC` | B | worker | Mongo 所在节点 |

### 设计理由

- manager 数量保持奇数，满足多数派
- `serverA/serverB` 留在云 A，避免 manager 过度偏向云 B
- `serverC` 跑 Mongo，只承担 worker，降低控制面和状态服务耦合

## infra-network

### 网络参数

| 属性 | 值 |
|------|-----|
| 网络名称 | `infra-network` |
| 驱动 | `overlay` |
| 附着方式 | `attachable` |
| 子网 | `172.20.0.0/24` |
| 网关 | `172.20.0.1` |
| Tailscale underlay MTU | `1280` |
| 容器 overlay 端点 MTU | 约 `1230` |
| Docker overlay 数据面加密 | `disabled` |
| 节点链路加密 | `Tailscale` |

定义见 [components/networks/docker-compose.yml](../../components/networks/docker-compose.yml)。

### 为什么继续用 attachable overlay

因为你当前业务部署模型仍然是：

```bash
docker compose up -d
```

而不是：

```bash
docker stack deploy
```

`attachable overlay` 允许：

- Swarm service 连接网络
- 普通 Compose 启动的 standalone 容器也连接网络

这样你可以在不整体切换运行时的前提下，先统一跨主机网络层。

## 网络拓扑

```text
                               Docker Swarm Cluster

 ┌──────────────────────────────────────────────────────────────────────────┐
 │        infra-network (overlay, attachable; Tailscale underlay)          │
 │                 172.20.0.0/24 / underlay 1280 / endpoint 1230         │
 │                                                                          │
 │  Cloud A                                         Cloud B                 │
 │                                                                          │
 │  serverA (manager)                               serverC (worker)        │
 │  serverB (manager)                               serverD (manager)       │
 │                                                                          │
 │  nginx / qs-apiserver                            mongo / qs-worker       │
 │  qs-collection / iam                             qs-worker / nsq / ops   │
 │                                                                          │
 │  Containers attached to infra-network continue to resolve each other     │
 │  by container name across hosts, for example: mongo, nsqd, qs-apiserver │
 └──────────────────────────────────────────────────────────────────────────┘

 Control plane:
   - TCP 2377

 Node discovery:
   - TCP/UDP 7946

 Overlay data plane over Tailscale:
   - UDP 4789 on tailscale0
   - no Docker ESP dependency because INFRA_NETWORK_ENCRYPTED=false
```

## 控制面与数据面

Docker 官方区分两类流量：

- 控制/管理面流量
- 应用数据面流量

在当前方案里：

- `--advertise-addr` 用于控制面
- `--data-path-addr` 用于 overlay 数据面

当前推荐 `advertise-addr` 和 `data-path-addr` 都使用本机 `tailscale ip -4` 输出的地址。

## 服务发现

### 跨主机仍使用容器名

当容器都接入 `infra-network` 后，可以继续使用：

- `mongo:27017`
- `nsqd:4150`
- `qs-apiserver:8080`
- `iam-apiserver:8080`

这正是当前方案相对主机级 VPN 的主要收益。

### 适用范围

- 同一 overlay 上的容器：可以用容器名
- 不在 overlay 上的主机进程：不能用容器名
- 没接入 `infra-network` 的容器：不能跨机依赖容器名

## 安全边界

### 端口暴露原则

Swarm 端口不要对公网全开。当前推荐通过 Tailscale 节点网络互通：

- `2377/tcp`
- `7946/tcp`
- `7946/udp`
- `4789/udp`
- 不需要 `ESP (protocol 50)`，因为 Docker overlay encryption 关闭，底层由 Tailscale 加密

### 为什么关闭 Docker overlay 加密

云安全组通常只能配置 TCP/UDP/ICMP/GRE，不能稳定放行 Docker encrypted overlay 需要的 ESP/IP protocol 50。
因此当前方案关闭 `encrypted=true`，使用 Tailscale WireGuard 隧道承担节点间加密。

## 与业务部署的关系

### 这一层负责什么

- 跨主机容器互通
- 容器名服务发现
- 为 Mongo / NSQ / 监控抓取等提供统一网络平面

### 这一层不负责什么

- 不负责镜像发布
- 不负责业务编排
- 不负责副本调度
- 不自动替代现有 `docker compose up -d`

## 对现有组件的影响

### Mongo

- 如果 `serverC` 上的 Mongo 容器加入 `infra-network`
- 则其他机器上的容器可以继续使用 `mongo:27017`
- 不再需要改成 Tailscale IP 或宿主机 IP

### Prometheus

Prometheus 继续可以通过 overlay 直接抓：

- `qs-apiserver:8080/metrics`
- `qs-collection-server:8080/metrics`
- `qs-worker:9092/metrics`

但前提是这些容器都接入 `infra-network`。

### Nginx

Nginx upstream 也可以继续写容器名，例如：

```nginx
upstream qs_api {
    server qs-apiserver:8080;
}
```

## 运维要求

### 节点初始化

初始化和 join 命令见 [swarm-setup.md](./swarm-setup.md)。

### 网络创建

只在 manager 上创建 `infra-network`。

### 网络验证

重点检查：

- `docker node ls`
- `docker network inspect infra-network`
- `Peers` 是否包含四台机器
- 测试容器能否 `ping mongo` / `ping nsqd`

## 风险与限制

### 优点

- 跨机仍可用容器名
- 不需要把配置全面切成主机 IP
- 兼容现有 Compose 模型

### 成本

- 引入正式的跨云 Swarm 控制面
- 需要严控防火墙和节点互联地址
- overlay 排障会比主机级 VPN 更偏底层

### 不适合的情况

如果未来你决定不再维护 Swarm，而只保留 Compose，那这条路线的长期维护价值会下降。

## 相关文件

- [components/networks/docker-compose.yml](../../components/networks/docker-compose.yml)
- [components/networks/README.md](../../components/networks/README.md)
- [scripts/01-network/swarm-manager.sh](../../scripts/01-network/swarm-manager.sh)
- [scripts/02-components/init-infrastructure.sh](../../scripts/02-components/init-infrastructure.sh)
