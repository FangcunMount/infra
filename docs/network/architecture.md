# 网络架构

## 概述

本项目采用**单一 Overlay 网络**设计，支持跨服务器的分布式部署。所有基础设施服务通过统一的 Overlay 网络进行通信，实现服务发现、负载均衡和安全加密。

## 网络拓扑

```text
┌─────────────────────────────────────────────────────────────┐
│                    infra-network (Overlay)                  │
│                     172.20.0.0/16                           │
│                                                             │
│   ┌──────────────────┐         ┌──────────────────┐       │
│   │    ServerA       │         │    ServerB       │       │
│   │ 121.43.138.102   │         │ 112.126.82.123   │       │
│   │                  │         │                  │       │
│   │  ┌───────────┐   │         │  ┌────────────┐ │       │
│   │  │  Nginx    │   │         │  │   nsqd     │ │       │
│   │  └───────────┘   │         │  └────────────┘ │       │
│   │  ┌───────────┐   │         │  ┌────────────┐ │       │
│   │  │  MySQL    │   │         │  │ nsqlookupd │ │       │
│   │  └───────────┘   │         │  └────────────┘ │       │
│   │  ┌───────────┐   │         │  ┌────────────┐ │       │
│   │  │  Redis    │   │         │  │ nsqadmin   │ │       │
│   │  └───────────┘   │         │  └────────────┘ │       │
│   │  ┌───────────┐   │         │                  │       │
│   │  │ MongoDB   │   │         │                  │       │
│   │  └───────────┘   │         │                  │       │
│   │                  │         │                  │       │
│   └──────────────────┘         └──────────────────┘       │
│                                                             │
│   [Encrypted VXLAN Tunnel - Port 4789/UDP]                │
└─────────────────────────────────────────────────────────────┘
         │                                    │
         │                                    │
    Physical Network (Internet)
```

## 核心网络: infra-network

### 基本配置

| 属性 | 值 | 说明 |
|------|-----|------|
| **网络名称** | `infra-network` | 统一的基础设施网络 |
| **驱动类型** | `overlay` | 支持跨主机通信 |
| **子网** | `172.20.0.0/16` | 65,534个可用IP地址 |
| **网关** | `172.20.0.1` | 默认网关 |
| **MTU** | `1500` | 最大传输单元 (可配置) |
| **加密** | `enabled` | VXLAN流量加密 |
| **可附加** | `yes` | 允许独立容器连接 |

### 网络标签

```yaml
labels:
  - infra.network=backend
  - infra.purpose=distributed-service-communication
```

## 为什么使用 Overlay 网络？

### Overlay vs Bridge 对比

| 特性 | Bridge | Overlay |
|------|--------|---------|
| **跨主机通信** | ❌ 不支持 | ✅ 支持 |
| **服务发现** | ❌ 手动配置 | ✅ 自动DNS |
| **负载均衡** | ❌ 无 | ✅ 内置 |
| **加密传输** | ❌ 无 | ✅ 支持 |
| **横向扩展** | ❌ 困难 | ✅ 简单 |
| **适用场景** | 单机部署 | 分布式部署 |

### Overlay 网络优势

1. **跨主机通信**
   - 容器可以在不同物理服务器间透明通信
   - 无需复杂的网络配置
   - 自动路由和转发

2. **自动服务发现**
   - 内置DNS服务
   - 服务名称自动解析
   - 动态更新服务地址

3. **内置负载均衡**
   - VIP (虚拟IP) 机制
   - 自动流量分发
   - 故障自动转移

4. **安全加密**
   - VXLAN封装
   - AES-GCM加密
   - 端到端安全

5. **横向扩展**
   - 轻松添加新节点
   - 自动网络配置
   - 无缝服务迁移

## 技术实现

### VXLAN 隧道

Overlay网络使用VXLAN (Virtual Extensible LAN) 技术:

```text
┌─────────────────────────────────────────────────┐
│  Container → Docker Bridge → VXLAN → Host NIC   │
│                                                 │
│  [容器IP] → [172.20.x.x] → [封装] → [公网IP]   │
└─────────────────────────────────────────────────┘
```

**工作原理**:

1. 容器发送数据包到网关 `172.20.0.1`
2. Docker封装数据包为VXLAN格式
3. 通过UDP端口4789发送到目标主机
4. 目标主机解封装并转发到目标容器

### 加密机制

启用加密后的数据流:

```text
原始数据 → AES-GCM加密 → VXLAN封装 → UDP传输
```

- **算法**: AES-256-GCM
- **性能影响**: 约5-10%的CPU开销
- **安全级别**: 企业级加密标准

## 连接的服务

### 服务清单

所有基础设施服务都连接到 `infra-network`:

| 服务 | 位置 | 内部地址 | 说明 |
|------|------|----------|------|
| **Nginx** | ServerA | 动态分配 | Web服务器 |
| **MySQL** | ServerA | 动态分配 | 关系型数据库 |
| **Redis** | ServerA | 动态分配 | 缓存 |
| **MongoDB** | ServerA | 动态分配 | 文档数据库 |
| **nsqd** | ServerB | 动态分配 | 消息存储 |
| **nsqlookupd** | ServerB | 动态分配 | 服务发现 |
| **nsqadmin** | ServerB | 动态分配 | 管理界面 |

### 服务发现示例

容器可以通过服务名称直接访问:

```bash
# 在任何容器内
ping mysql              # 自动解析到 MySQL 容器IP
curl http://nsqd:4151   # 访问 NSQ HTTP API
redis-cli -h redis      # 连接 Redis
```

## 端口映射策略

### 外部暴露端口 (ServerA)

```yaml
# 必须暴露的服务
Nginx:
  - "80:80"      # HTTP
  - "443:443"    # HTTPS

# 建议限制访问的服务
MySQL:
  - "3306:3306"  # 仅限信任IP
Redis:
  - "6379:6379"  # 仅限信任IP
MongoDB:
  - "27017:27017" # 仅限信任IP
```

### 内部端口 (ServerB)

```yaml
# NSQ 不对外暴露端口
# 所有访问通过 Overlay 网络
nsqlookupd:
  - 4160:4160  # TCP (内网)
  - 4161:4161  # HTTP (内网)

nsqd:
  - 4150:4150  # TCP (内网)
  - 4151:4151  # HTTP (内网)

nsqadmin:
  - 127.0.0.1:4171:4171  # 仅本地访问
```

## 网络性能优化

### MTU 优化

**默认值**: 1500 (以太网标准)

**调整建议**:

```bash
# 如果跨公网通信,减小MTU避免分片
INFRA_NETWORK_MTU=1450 make network-init

# 如果内网环境,可以增大MTU提高性能
INFRA_NETWORK_MTU=9000 make network-init  # Jumbo Frame
```

**影响**:

- MTU过大 → 可能导致分片,降低性能
- MTU过小 → 增加封装开销

### 子网规划

**当前配置**: `172.20.0.0/16`

**容量**: 65,534个可用IP

**扩展建议**:

- 小型部署: `/24` (254个IP) 足够
- 中型部署: `/20` (4,094个IP)
- 大型部署: `/16` (65,534个IP) ✅ 当前

### 网络隔离

可以创建多个Overlay网络实现隔离:

```yaml
# 生产网络
infra-network:
  subnet: 172.20.0.0/16

# 测试网络
test-network:
  subnet: 172.21.0.0/16

# 监控网络
monitor-network:
  subnet: 172.22.0.0/16
```

## 前置要求

### Docker Swarm

Overlay网络依赖Docker Swarm:

```bash
# 初始化 Swarm (在管理节点)
docker swarm init --advertise-addr 121.43.138.102

# 加入 Swarm (在工作节点)
docker swarm join --token SWMTKN-xxx 121.43.138.102:2377
```

### 防火墙规则

必须开放以下端口:

```bash
# Swarm 管理端口
2377/tcp   # Swarm 管理通信

# Swarm 节点通信
7946/tcp   # 容器网络发现
7946/udp   # 容器网络发现

# Overlay 网络
4789/udp   # VXLAN 数据平面
```

### 系统要求

- **Linux内核**: 3.10+ (建议4.0+)
- **Docker版本**: 17.06+ (建议19.03+)
- **网络模块**: VXLAN内核模块已加载

检查命令:

```bash
# 检查内核版本
uname -r

# 检查VXLAN模块
lsmod | grep vxlan

# 检查Docker版本
docker version
```

## 单机部署说明

即使在单机环境下,仍使用Overlay网络:

**原因**:

1. **环境一致性**: 开发/测试/生产环境配置相同
2. **便于扩展**: 随时可以添加新节点
3. **功能完整**: 享受服务发现等高级特性
4. **避免重构**: 不需要后期修改网络配置

**单机初始化**:

```bash
# 1. 初始化单节点Swarm
docker swarm init

# 2. 创建Overlay网络
make network-init

# 3. 部署服务
make up
```

## 安全配置

### 网络加密

**启用加密** (推荐):

```bash
# 创建网络时启用
docker network create \
  --driver overlay \
  --opt encrypted=true \
  infra-network
```

**性能影响**:

- CPU开销: 5-10%
- 延迟增加: <1ms
- 吞吐量: 轻微下降

**适用场景**:

- ✅ 跨公网通信
- ✅ 敏感数据传输
- ⚠️ 高性能要求场景 (权衡考虑)

### 网络隔离

**基本隔离**:

```yaml
# Overlay网络与宿主机网络隔离
# 容器只能访问同网络的其他容器
```

**高级隔离**:

```bash
# 使用多个网络
frontend-network:  # Web层
backend-network:   # 业务层
data-network:      # 数据层
```

### 访问控制

**限制nsqadmin访问**:

```yaml
nsqadmin:
  ports:
    - "127.0.0.1:4171:4171"  # 只绑定本地
```

访问方式:

```bash
# 使用SSH隧道
ssh -L 4171:localhost:4171 user@112.126.82.123

# 然后访问
http://localhost:4171
```

## 环境变量配置

可通过环境变量自定义网络配置:

```bash
# 子网配置
INFRA_BACKEND_SUBNET=172.20.0.0/16

# 网关配置
INFRA_BACKEND_GATEWAY=172.20.0.1

# MTU配置
INFRA_NETWORK_MTU=1500

# 应用配置
make network-init
```

**配置文件位置**: `compose/env/prod/env`

## 故障排查

### 网络无法创建

**症状**: `Error response from daemon: network ... already exists`

**解决**:

```bash
# 查看现有网络
docker network ls

# 删除冲突网络
docker network rm infra-network

# 重新创建
make network-init
```

### 服务无法通信

**症状**: 容器之间无法ping通

**排查步骤**:

```bash
# 1. 检查网络状态
make network-status

# 2. 检查服务网络配置
docker inspect <container> | grep -A 10 Networks

# 3. 检查防火墙
sudo ufw status

# 4. 测试DNS解析
docker exec <container> nslookup mysql
```

### 跨主机通信失败

**症状**: ServerA无法访问ServerB的服务

**排查步骤**:

```bash
# 1. 检查Swarm状态
docker node ls

# 2. 检查端口开放
nc -zv <target_ip> 4789  # VXLAN端口
nc -zv <target_ip> 7946  # 节点通信

# 3. 检查路由
traceroute <target_ip>

# 4. 重建网络
make network-reset
```

### 网络性能问题

**症状**: 延迟高,丢包

**诊断**:

```bash
# 检查MTU
docker network inspect infra-network | grep -i mtu

# 测试延迟
docker exec <container> ping -c 10 <target_service>

# 检查网络统计
docker stats
```

**优化**:

```bash
# 调整MTU
INFRA_NETWORK_MTU=1450 make network-reset

# 禁用加密 (如果内网环境)
docker network create --driver overlay infra-network
```

## 迁移说明

### 从 Bridge 迁移到 Overlay

如果之前使用Bridge网络:

```bash
# 1. 备份配置
docker-compose config > backup.yml

# 2. 停止所有服务
make down

# 3. 删除Bridge网络
docker network rm <old_network>

# 4. 初始化Swarm
make swarm-init

# 5. 创建Overlay网络
make network-init

# 6. 重新部署
make up
```

### 从旧网络名迁移

如果之前使用 `infra-frontend`:

```bash
# 1. 停止服务
make down

# 2. 删除旧网络
docker network rm infra-frontend

# 3. 重置基础设施
make reset

# 4. 启动服务
make up
```

## 网络管理命令

### 初始化网络

```bash
make init              # 完整初始化（网络+卷）
make network-init      # 仅初始化网络
```

### 查看状态

```bash
make network-status    # 网络状态概览
make network-list      # 列出所有网络
make network-inspect   # 查看网络详情
```

### 重置网络

```bash
make network-reset     # 删除并重建网络
```

### 诊断工具

```bash
# 网络诊断
make network-diagnose

# 性能测试
make network-test

# 连通性检查
make network-check
```

## 监控和维护

### 监控指标

关键指标:

```yaml
网络吞吐量: rx_bytes, tx_bytes
网络延迟: ping, traceroute
丢包率: packet_loss
连接数: connections
```

### 日常维护

```bash
# 定期检查网络状态
make network-status

# 清理未使用的网络
docker network prune

# 查看网络流量
docker stats

# 检查网络日志
journalctl -u docker -f | grep -i network
```

### 性能基准

**正常指标**:

```yaml
延迟 (同主机): < 1ms
延迟 (跨主机): < 5ms (取决于物理网络)
丢包率: < 0.1%
吞吐量: 接近物理网卡带宽
```

## 扩展阅读

### 官方文档

- [Docker Overlay Networks](https://docs.docker.com/network/overlay/)
- [Docker Swarm Networking](https://docs.docker.com/engine/swarm/networking/)
- [VXLAN Overview](https://docs.docker.com/network/drivers/overlay/#vxlan-encapsulation)

### 相关文档

- [服务器架构](../server/architecture.md)
- [网络管理指南](./management.md)

---

**更新时间**: 2025-12-01  
**文档版本**: v2.0
