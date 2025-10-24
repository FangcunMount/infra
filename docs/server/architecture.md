# 服务器架构设计

## 概述

本项目采用**双服务器分布式架构**，将基础设施服务按功能分布在两台服务器上，实现负载均衡和高可用性。

## 服务器配置

### ServerA (2C4G) - 主节点

- **IP地址**: 121.43.138.102
- **角色**: 主应用服务器 + 管理节点
- **配置**: 2核CPU / 4GB内存
- **操作系统**: Linux (建议 Ubuntu 20.04+)

**部署服务**:

- Nginx (Web服务器/反向代理)
- MySQL (关系型数据库)
- Redis (缓存)
- MongoDB (文档数据库)

**职责**:

- Web流量接入和转发
- 数据存储服务
- Docker Swarm Manager (管理节点)
- 监控和管理界面

### ServerB (2C4G) - 消息队列节点

- **IP地址**: 112.126.82.123
- **角色**: 消息队列专用服务器
- **配置**: 2核CPU / 4GB内存
- **操作系统**: Linux (建议 Ubuntu 20.04+)

**部署服务**:

- NSQ (轻量级消息队列)
  - nsqd (消息存储)
  - nsqlookupd (服务发现)
  - nsqadmin (管理界面)
- Kafka (可选 - 高吞吐量消息队列)

**职责**:

- 消息队列处理
- 异步任务处理
- 事件驱动通信
- Docker Swarm Worker (工作节点)

## 架构图

```text
                    ┌─────────────────────┐
                    │   Internet/客户端   │
                    └──────────┬──────────┘
                               │
                               │ HTTPS/HTTP
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                         ServerA (2C4G)                        │
│                      121.43.138.102                          │
│                                                              │
│  ┌──────────────┐    ┌──────────┐    ┌──────────────┐     │
│  │    Nginx     │───▶│  MySQL   │    │   MongoDB    │     │
│  │   80/443     │    │   3306   │    │    27017     │     │
│  └──────┬───────┘    └──────────┘    └──────────────┘     │
│         │                                                    │
│         │            ┌──────────┐                          │
│         └───────────▶│  Redis   │                          │
│                      │   6379   │                          │
│                      └──────────┘                          │
│                                                              │
│  [Swarm Manager] [监控] [日志]                              │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         │ Overlay Network
                         │ (infra-network)
                         │
┌────────────────────────┴─────────────────────────────────────┐
│                         ServerB (2C4G)                        │
│                      112.126.82.123                          │
│                                                              │
│  ┌──────────────────────────────────────────────┐          │
│  │             NSQ 消息队列集群                  │          │
│  │                                              │          │
│  │  ┌─────────────┐  ┌──────────────┐         │          │
│  │  │  nsqlookupd │  │    nsqd      │         │          │
│  │  │    4160     │◀─│  4150/4151   │         │          │
│  │  └─────────────┘  └──────────────┘         │          │
│  │                                              │          │
│  │  ┌─────────────┐                            │          │
│  │  │  nsqadmin   │                            │          │
│  │  │    4171     │  (仅127.0.0.1访问)         │          │
│  │  └─────────────┘                            │          │
│  └──────────────────────────────────────────────┘          │
│                                                              │
│  [Swarm Worker] [消息处理]                                  │
└──────────────────────────────────────────────────────────────┘
```

## 服务分布策略

### 为什么这样分布？

#### ServerA - 存储服务集中

**优势**:

1. **数据一致性**: 所有存储服务在同一服务器,减少网络延迟
2. **事务支持**: 本地事务处理更高效
3. **备份简化**: 统一备份策略和恢复流程
4. **监控集中**: 统一监控所有数据库服务

**挑战**:

- I/O密集,需要优化磁盘性能
- 内存压力较大(MySQL + Redis + MongoDB)

#### ServerB - 消息队列独立

**优势**:

1. **资源隔离**: 消息队列不与数据库竞争资源
2. **横向扩展**: 易于增加更多消息队列节点
3. **故障隔离**: 消息队列问题不影响主服务
4. **性能优化**: 针对消息处理优化网络和内存

**挑战**:

- 跨服务器通信延迟
- 需要配置 Overlay 网络

## 网络通信

### Overlay 网络 (infra-network)

所有服务通过 Docker Overlay 网络通信:

- **子网**: `172.20.0.0/16`
- **网关**: `172.20.0.1`
- **加密**: 启用 (encrypted=true)
- **MTU**: 1500

### 服务访问模式

#### 外部访问 (Internet → ServerA)

```text
用户 → Nginx (80/443) → 后端应用
                      ↓
               MySQL/Redis/MongoDB
```

#### 应用访问消息队列 (ServerA → ServerB)

```text
应用服务 → Overlay Network → NSQ (ServerB)
```

#### 消息队列访问数据库 (ServerB → ServerA)

```text
NSQ Consumer → Overlay Network → MySQL/Redis (ServerA)
```

### 端口映射

#### ServerA 开放端口

| 服务 | 端口 | 用途 | 外部访问 |
|------|------|------|----------|
| Nginx | 80 | HTTP | ✅ |
| Nginx | 443 | HTTPS | ✅ |
| MySQL | 3306 | 数据库 | ⚠️ 建议限制 |
| Redis | 6379 | 缓存 | ⚠️ 建议限制 |
| MongoDB | 27017 | 文档数据库 | ⚠️ 建议限制 |

#### ServerB 开放端口

| 服务 | 端口 | 用途 | 外部访问 |
|------|------|------|----------|
| nsqlookupd | 4160 | TCP接口 | 🔒 内网 |
| nsqlookupd | 4161 | HTTP接口 | 🔒 内网 |
| nsqd | 4150 | TCP接口 | 🔒 内网 |
| nsqd | 4151 | HTTP接口 | 🔒 内网 |
| nsqadmin | 4171 | 管理界面 | 🔒 127.0.0.1 |

> ⚠️ 建议限制 = 应通过防火墙或VPN限制访问
> 🔒 内网 = 仅限 Overlay 网络内访问
> 🔒 127.0.0.1 = 仅限本机访问 (需SSH隧道)

## 资源分配

### ServerA 资源预算

```yaml
Nginx:    CPU: 0.5核  内存: 256MB
MySQL:    CPU: 1.0核  内存: 1.5GB
Redis:    CPU: 0.5核  内存: 512MB
MongoDB:  CPU: 1.0核  内存: 1GB
系统预留:  CPU: 0.5核  内存: 512MB
```

**总计**: CPU: ~3.5核 (超配) / 内存: ~3.8GB

### ServerB 资源预算

```yaml
nsqlookupd: CPU: 0.05核  内存: 32MB
nsqd:       CPU: 0.80核  内存: 512MB
nsqadmin:   CPU: 0.05核  内存: 32MB
系统预留:   CPU: 0.5核   内存: 512MB
```

**总计**: CPU: ~1.4核 / 内存: ~1.1GB

> 💡 **提示**: CPU 超配是合理的,因为服务通常不会同时达到峰值

## 高可用考虑

### 当前架构的局限性

1. **单点故障**:
   - ServerA故障 = 所有存储服务不可用
   - ServerB故障 = 消息队列不可用

2. **无自动故障转移**:
   - 需要手动恢复服务
   - 无主从复制配置

### 推荐改进方案

#### 短期改进 (保持2台服务器)

1. **数据库备份**:

   ```bash
   # 每日自动备份到对方服务器
   ServerA MySQL → 备份到 ServerB
   ServerA MongoDB → 备份到 ServerB
   ```

2. **NSQ 集群化**:

   ```bash
   # 在ServerA也部署nsqd (只作为备份)
   主: ServerB nsqd
   备: ServerA nsqd
   ```

3. **监控告警**:
   - 配置健康检查
   - 服务故障自动通知

#### 长期改进 (3+服务器)

1. **MySQL 主从复制**:

   ```text
   ServerA: MySQL Master
   ServerC: MySQL Slave
   ```

2. **MongoDB 副本集**:

   ```text
   ServerA: Primary
   ServerC: Secondary
   ServerD: Arbiter
   ```

3. **Redis 哨兵模式**:

   ```text
   ServerA: Master
   ServerC: Slave + Sentinel
   ServerD: Sentinel
   ```

4. **NSQ 多节点集群**:

   ```text
   ServerB: nsqlookupd + nsqd
   ServerC: nsqlookupd + nsqd
   ```

## 扩容策略

### 垂直扩容 (升级配置)

优先考虑升级 ServerA:

```text
2C4G → 4C8G
```

原因:

- ServerA 资源压力更大
- 数据库性能受限于CPU和内存
- ROI (投资回报率) 更高

### 水平扩容 (增加服务器)

**ServerC** - 读取负载分担

建议配置: 2C4G

部署:

- MySQL Slave (读副本)
- Redis Slave (读副本)
- MongoDB Secondary

**ServerD** - 任务处理节点

建议配置: 2C4G

部署:

- 应用容器 (消费NSQ消息)
- 定时任务
- 后台处理服务

## 部署流程

### 1. 初始化服务器

```bash
# 在 ServerA 执行
cd /path/to/infra
make server-init         # 初始化用户和Docker

# 在 ServerB 执行
cd /path/to/infra
make server-init
```

### 2. 配置环境变量

编辑 `compose/env/prod/env`:

```bash
NODE_A_IP=121.43.138.102
NODE_B_IP=112.126.82.123
```

### 3. 初始化网络 (ServerA - Manager)

```bash
# 在 ServerA 执行
make swarm-init          # 初始化 Swarm
make network-init        # 创建 Overlay 网络
```

### 4. 加入 Swarm (ServerB - Worker)

```bash
# 在 ServerA 获取加入命令
docker swarm join-token worker

# 在 ServerB 执行返回的命令
docker swarm join --token SWMTKN-xxx 121.43.138.102:2377
```

### 5. 部署服务

```bash
# 在 ServerA 部署存储服务
make mysql-start
make redis-start
make mongo-start
make nginx-start

# 在 ServerB 部署消息队列
make nsq-start
```

### 6. 验证部署

```bash
# 检查服务状态
make status

# 检查网络连通性
make network-status

# 测试服务
make test
```

## 监控和维护

### 日常检查

```bash
# 查看资源使用
make stats

# 查看服务日志
make logs SERVICE=<service_name>

# 查看Swarm状态
docker node ls
```

### 性能监控

推荐工具:

- **cAdvisor**: 容器监控
- **Prometheus**: 指标采集
- **Grafana**: 可视化仪表盘
- **Portainer**: Docker管理界面

### 备份策略

```bash
# 数据库备份 (自动)
make backup              # 备份所有数据库

# 配置备份 (手动)
tar -czf config-backup.tar.gz compose/ components/ .env
```

## 故障处理

### ServerA 故障

1. **快速恢复**:

   ```bash
   # 在备份服务器恢复数据
   make restore
   ```

2. **临时方案**:
   - 启用维护页面
   - 切换到备份数据库 (如果有)

### ServerB 故障

1. **影响**:
   - 消息队列不可用
   - 异步任务停止
   - 实时功能受影响

2. **恢复**:

   ```bash
   # 重启 ServerB
   make nsq-start
   ```

3. **备用方案**:
   - 消息暂存到 Redis
   - 降级为同步处理

### 网络故障

```bash
# 检查网络
make network-status

# 重置网络
make network-reset

# 重新加入 Swarm
make swarm-rejoin
```

## 安全加固

### 防火墙规则

**ServerA**:

```bash
# 只允许必要端口
sudo ufw allow 22        # SSH
sudo ufw allow 80        # HTTP
sudo ufw allow 443       # HTTPS
sudo ufw allow 2377/tcp  # Swarm管理
sudo ufw allow 7946      # Swarm节点通信
sudo ufw allow 4789/udp  # Overlay网络
sudo ufw enable
```

**ServerB**:

```bash
sudo ufw allow 22        # SSH
sudo ufw allow 7946      # Swarm节点通信
sudo ufw allow 4789/udp  # Overlay网络
# NSQ端口只允许内网访问
sudo ufw enable
```

### SSH访问

```bash
# 禁用密码登录,只允许密钥
PasswordAuthentication no

# 更改SSH端口
Port 2222
```

### 数据库安全

```bash
# MySQL 只监听内网
bind-address = 127.0.0.1

# Redis 启用认证
requirepass <strong_password>

# MongoDB 启用认证
security:
  authorization: enabled
```

## 参考文档

- [服务器初始化](./initialization.md)
- [网络架构](../network/architecture.md)
- [组件文档](../components/)
- [运维指南](../operations/)

---

**更新时间**: 2025-01-24  
**架构版本**: v1.0
