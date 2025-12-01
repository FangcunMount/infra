# Swarm 双机重建与排障记录

记录本次在 serverA（172.17.0.223）/serverB（172.17.0.226）重建 Docker、初始化 Swarm、恢复 overlay 网络互通的步骤，便于下次复用。

## 环境

- OS: Ubuntu 24.04.3 LTS（两台）
- 内网互通 IP：serverA 172.17.0.223，serverB 172.17.0.226
- Docker: 29.1.1，Compose: v2.40.3

## 关键原则

- Swarm 初始化时必须显式指定内网 IP：`--advertise-addr 172.17.0.223`
- Overlay 网络只有在节点上有任务接入时才会下发；无需额外“触发”，但可以用全局服务占位验证。
- Worker 不创建网络，只创建自身卷。网络由 Manager 创建并下发。

## 操作步骤

### 1) 安装/重装 Docker（两台）

```bash
sudo make server-install-docker
docker --version
docker compose version
```

### 2) 初始化 Swarm（仅 serverA）

```bash
docker swarm init --advertise-addr 172.17.0.223
# 记录输出的 worker token
```

### 3) 加入 Swarm（serverB）

```bash
docker swarm join --advertise-addr 172.17.0.226 172.17.0.223:2377 --token <worker-token>
```

### 4) 创建基础网络/卷并启动 serverA 组件

在 serverA：

```bash
make init-serverA
make serverA-up
```

### 5) 确认 overlay 网络下发到 serverB

- 查看 Peers（serverA）：

```bash
docker network inspect infra-network | grep -A2 Peers
```

期望同时有 172.17.0.223 和 172.17.0.226。

- 查看网络列表（serverB）：

```bash
docker network ls | grep infra-network
```

> 说明：overlay 网络按需下发，节点上有任务接入该网络时才会出现。如果需要强制铺到所有节点，可临时创建一个全局服务：

```bash
docker service create --mode global --name net-test --network infra-network alpine sleep 1d
```

验证完成后删除：

```bash
docker service rm net-test
```

### 6) 初始化 serverB 卷并启动 NSQ

在 serverB：

```bash
make init-serverB
make serverB-up
```

### 7) 互通验证

- serverB → serverA：

```bash
docker exec nsqd ping -c 2 redis-cache
```

- serverA → serverB（用自带 ping 的容器，如 nginx）：

```bash
docker exec nginx ping -c 2 nsqd
```

## 常见排障

- `infra-network` 在 worker 看不到：检查 `docker network inspect infra-network` 的 Peers 是否包含 worker IP；确认放通端口 2377/tcp、7946/tcp+udp、4789/udp；确保有任务挂载该网络（可用全局服务占位）。
- 广播地址错误导致隧道不通：重建 Swarm 时务必用内网 IP 做 `--advertise-addr`。
- 旧节点残留：`docker node rm <旧ID>` 清理 Down 节点后重新 join。

## 命令参考

- 查看 token：`docker swarm join-token worker`
- 重新加入（worker）：`docker swarm leave --force && docker swarm join --advertise-addr <worker-ip> <manager-ip>:2377 --token <token>`
- Manager 状态查看：`docker node ls`，`docker node inspect <node> --pretty | grep -E 'Addr|State|Reachability'`
