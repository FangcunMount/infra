# 网络管理文档

本目录包含基础设施网络管理的核心文档。

## 📚 文档列表

### 1. [网络管理完整指南](./网络管理完整指南.md) ⭐ 推荐首读

**适用场景**: 日常网络管理、业务网络创建、问题排查

**内容概览**:
- 网络架构设计原则（为什么这样设计）
- Makefile 快速命令（最常用）
- 业务网络管理（创建、删除、查看）
- 常用场景示例（开发环境、生产环境、内部网络）
- 故障排查指南

**适合人群**: 开发者、运维人员

**快速开始**:
```bash
# 创建业务网络
make app-network-create NAME=miniblog-network

# 查看所有网络
make app-network-list
```

---

### 2. [Docker Swarm 部署指南](./Docker_Swarm部署指南.md)

**适用场景**: 跨主机部署、生产环境集群

**内容概览**:
- 快速开始（5分钟部署）
- Swarm 集群初始化
- Overlay 网络配置
- 跨主机服务部署
- 集群管理命令
- 故障排查

**适合人群**: 运维人员、架构师

**快速开始**:
```bash
# ServerA - 初始化管理节点
make swarm-init ADVERTISE_ADDR=192.168.1.100

# ServerB - 加入集群
make swarm-join MANAGER_IP=192.168.1.100
```

---

### 3. [服务器初始化--网络环境](./服务器初始化--网络环境.md)

**适用场景**: 新服务器初始化、网络环境配置

**内容概览**:
- 服务器网络初始化
- VPN 配置
- 防火墙设置
- 网络优化

**适合人群**: 系统管理员、运维人员

---

## 🎯 快速索引

### 按使用场景查找

| 场景 | 文档 | 章节 |
|------|------|------|
| 创建业务网络 | 网络管理完整指南 | Makefile 快速命令 |
| 跨主机部署 | Docker Swarm 部署指南 | 快速开始 |
| 网络无法通信 | 网络管理完整指南 | 故障排查 - 问题3 |
| Swarm节点故障 | Docker Swarm 部署指南 | 故障排查 |
| 服务器初始化 | 服务器初始化--网络环境 | - |

### 按角色查找

**开发者**:
1. 阅读 [网络管理完整指南](./网络管理完整指南.md) 的"网络架构"部分
2. 学习 Makefile 命令创建业务网络
3. 参考"常用场景"部分的示例

**运维人员**:
1. 阅读 [Docker Swarm 部署指南](./Docker_Swarm部署指南.md)
2. 了解集群管理命令
3. 熟悉故障排查流程

**系统管理员**:
1. 阅读 [服务器初始化--网络环境](./服务器初始化--网络环境.md)
2. 配置服务器网络环境
3. 设置防火墙和安全策略

---

## 🚀 常用命令速查

### 业务网络

```bash
make app-network-create NAME=xxx        # 创建网络
make app-network-list                   # 列出网络
make app-network-delete NAME=xxx        # 删除网络
```

### Docker Swarm

```bash
make swarm-init ADVERTISE_ADDR=xxx      # 初始化集群
make swarm-join MANAGER_IP=xxx          # 加入集群
make swarm-status                       # 查看状态
make swarm-nodes                        # 列出节点
```

### 帮助

```bash
make help                               # 查看所有命令
```

---

## 📖 相关脚本

- 业务网络管理: `scripts/network/app-network-manager.sh`
- Swarm 管理: `scripts/network/swarm-manager.sh`
- VPN 管理: `scripts/network/docker-vpn-manager.sh`
- 网络诊断: `scripts/network/diagnose-network.sh`
- 网络优化: `scripts/network/optimize-network.sh`

---

## 💡 最佳实践

1. **网络命名**: 使用 `<应用名>-network` 格式
2. **网络选择**: 单主机用 `bridge`，跨主机用 `overlay`
3. **子网规划**: 基础设施 `172.20.0.0/16`，业务从 `172.21.0.0/16` 开始
4. **安全性**: 内部服务使用 `INTERNAL=true`，敏感数据使用 `ENCRYPTED=true`
5. **架构原则**: 基础设施被动，业务应用主动

---

**最后更新**: 2025-10-23
