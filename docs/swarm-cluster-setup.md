# Docker Swarm 集群配置指南

## 问题描述

当在多台服务器上部署分布式服务（如 NSQ）时，需要确保所有服务器加入同一个 Docker Swarm 集群，共享 overlay 网络。

## 当前问题

- ServerA (shujie001): 独立的 Swarm 集群 + infra-network
- ServerB (shujie002): **独立的** Swarm 集群 + infra-network（错误❌）

## 解决步骤

### 1. 在 ServerA (Manager 节点) 获取 Join Token

```bash
# SSH 到 ServerA
ssh root@shujie001

# 获取 worker 节点加入令牌
docker swarm join-token worker

# 输出示例：
# To add a worker to this swarm, run the following command:
#     docker swarm join --token SWMTKN-1-xxxxx... <ServerA-IP>:2377
```

### 2. 在 ServerB 上清理独立的 Swarm

```bash
# SSH 到 ServerB
ssh root@shujie002

# 停止所有服务
cd /opt/infra
make stop-nsq  # 如果有其他服务也需要停止

# 查看当前 Swarm 状态
docker info | grep Swarm

# 离开当前 Swarm（会删除所有 overlay 网络）
docker swarm leave --force

# 验证 Swarm 已离开
docker info | grep Swarm
# 应该显示: Swarm: inactive

# 删除旧的 overlay 网络（如果还存在）
docker network rm infra-network 2>/dev/null || true
```

### 3. ServerB 加入 ServerA 的 Swarm 集群

```bash
# 在 ServerB 上执行（使用步骤 1 中获取的命令）
docker swarm join --token SWMTKN-1-xxxxx... <ServerA-IP>:2377

# 验证加入成功
docker info | grep Swarm
# 应该显示: Swarm: active
#           NodeID: xxxx
#           Is Manager: false

# 查看网络（应该能看到 ServerA 的 infra-network）
docker network ls | grep infra-network
```

### 4. 在 ServerA 验证集群状态

```bash
# SSH 到 ServerA
ssh root@shujie001

# 查看集群节点
docker node ls

# 输出示例：
# ID                            HOSTNAME     STATUS    AVAILABILITY   MANAGER STATUS
# abc123... *                   shujie001    Ready     Active         Leader
# def456...                     shujie002    Ready     Active         
```

### 5. 重新部署 NSQ（在 ServerB）

```bash
# SSH 到 ServerB
ssh root@shujie002

# 确保配置文件已更新（修复 TOML 格式）
cd /opt/infra

# 重新部署 NSQ
make install-nsq
```

## 网络架构说明

### Swarm 集群模式

```
┌─────────────────────────────────────────────────────┐
│               Docker Swarm Cluster                  │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────────┐      ┌──────────────────┐   │
│  │  ServerA         │      │  ServerB         │   │
│  │  (Manager)       │◄────►│  (Worker)        │   │
│  │                  │      │                  │   │
│  │  infra-network   │      │  infra-network   │   │
│  │  (overlay)       │◄────►│  (overlay)       │   │
│  │  172.20.0.0/16   │      │  172.20.0.0/16   │   │
│  │                  │      │                  │   │
│  │  ┌──────────┐    │      │  ┌──────────┐    │   │
│  │  │nsqlookupd│    │      │  │   nsqd   │    │   │
│  │  │nsqadmin  │    │      │  │          │    │   │
│  │  └──────────┘    │      │  └──────────┘    │   │
│  └──────────────────┘      └──────────────────┘   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 关键要点

1. **Overlay 网络共享**: 加入同一 Swarm 后，overlay 网络 `infra-network` 在所有节点间自动同步
2. **服务发现**: 容器可以通过服务名跨主机通信（如 `nsqlookupd:4160`）
3. **Manager vs Worker**: 
   - Manager: 管理集群，可以部署服务（ServerA）
   - Worker: 执行任务，运行容器（ServerB）

## 防火墙配置（重要）

Swarm 集群需要开放以下端口：

```bash
# 在所有节点上执行
firewall-cmd --permanent --add-port=2377/tcp   # Swarm 管理通信
firewall-cmd --permanent --add-port=7946/tcp   # 节点间通信
firewall-cmd --permanent --add-port=7946/udp   # 节点间通信
firewall-cmd --permanent --add-port=4789/udp   # overlay 网络流量
firewall-cmd --reload
```

## 常见问题

### Q1: ServerB 无法加入 Swarm，提示网络不可达

**解决**: 检查防火墙配置，确保 2377 端口开放

```bash
# ServerA
firewall-cmd --list-ports | grep 2377
telnet <ServerA-IP> 2377  # 从 ServerB 测试
```

### Q2: 加入后网络还是不通

**解决**: 检查 overlay 网络加密和 MTU 设置

```bash
docker network inspect infra-network
# 确认两台服务器上的网络配置一致
```

### Q3: 想要添加更多服务器

**解决**: 在新服务器上执行步骤 2-3，使用相同的 join token

## 安全建议

1. **限制 Manager 节点**: 生产环境建议 3 个 Manager 节点（高可用）
2. **定期轮换 Token**: `docker swarm join-token --rotate worker`
3. **TLS 加密**: Swarm 默认启用 TLS，确保不要禁用
4. **网络隔离**: overlay 网络已启用加密（`--opt encrypted=true`）

## 参考资料

- [Docker Swarm 官方文档](https://docs.docker.com/engine/swarm/)
- [Overlay 网络详解](https://docs.docker.com/network/overlay/)
- [NSQ 集群部署](https://nsq.io/deployment/docker.html)
