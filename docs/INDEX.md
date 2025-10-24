# 基础设施文档导航

欢迎使用基础设施项目文档!本文档按照服务器功能和组件进行组织,方便快速查找。

## � 快速开始

- [服务器初始化](./server/initialization.md) - 服务器用户、Docker、网络环境配置
- [Makefile快速参考](./makefile-reference.md) - 常用命令速查
- [组件总览](./components/README.md) - 所有组件的快速参考

## 🖥️ 服务器配置

### 架构设计

- [服务器架构](./server/architecture.md) - ServerA/ServerB角色分配、资源配置、部署流程

### 初始化指南

- [服务器初始化完整指南](./server/initialization.md) - 用户配置、Docker安装、网络环境设置
- [www 用户使用指南](./server/www-user-guide.md) - 业务进程账户的使用方法和最佳实践

## 🔧 组件文档

### 总览

- [组件总览](./components/README.md) - 所有组件快速参考、状态检查、备份恢复

### 存储服务 (ServerA)

- **MySQL** - 关系型数据库 (:3306, 1.5GB)
- **Redis** - 缓存和会话存储 (:6379, 512MB)
- **MongoDB** - 文档数据库 (:27017, 1GB)
  - [MongoDB快速入门](./components/mongodb-quickstart.md) - 快速开始使用MongoDB

### 消息队列 (ServerB)

- [NSQ](./components/nsq.md) - 轻量级实时消息队列 (:4150-4171, 512MB)
  - nsqd, nsqlookupd, nsqadmin完整配置和使用
- **Kafka** - 高吞吐量消息流平台 (:9092, 2GB)

### Web服务 (ServerA)

- **Nginx** - Web服务器和反向代理 (:80, :443, 256MB)

## 🌐 网络管理

- [网络架构](./network/architecture.md) - Overlay网络设计、VXLAN隧道、MTU优化
- [网络管理指南](./network/management.md) - Docker网络、Swarm集群、VPN配置、故障排查

## 🛠️ 工具和参考

- [Makefile参考](./makefile-reference.md) - 完整的Make命令参考和使用说明

## 📊 运维指南

> 注意: 以下运维文档计划创建,目前请参考各组件文档中的相关章节

- 监控配置 - 参考[组件总览](./components/README.md#监控)
- 备份策略 - 参考[组件总览](./components/README.md#备份和恢复)
- 故障排查 - 参考各组件文档的"故障排查"章节
- 安全加固 - 参考[服务器架构](./server/architecture.md#安全加固)

---

## � 文档结构

```text
docs/
├── INDEX.md                        # 本文档 - 导航入口
├── makefile-reference.md           # Makefile命令参考
│
├── server/                         # 服务器配置
│   ├── architecture.md            # 架构设计
│   └── initialization.md          # 初始化指南
│
├── components/                     # 组件文档
│   ├── README.md                  # 组件总览
│   ├── nsq.md                     # NSQ配置
│   └── mongodb-quickstart.md      # MongoDB快速入门
│
├── network/                        # 网络管理
│   ├── architecture.md            # 网络架构
│   └── management.md              # 管理指南
│
├── operations/                     # 运维指南(待创建)
└── optimization/                   # 性能优化(待创建)
```

## 🎯 文档组织原则

- ✅ 按功能模块组织 (服务器/组件/网络/运维)
- ✅ 删除过程性文档,保留成果文档
- ✅ 整合重复内容,避免信息冗余
- ✅ 提供清晰的导航和交叉引用
- ✅ 每个文档独立完整,可单独阅读

## � 快速查找

### 我想

- **部署一台新服务器** → [服务器初始化](./server/initialization.md)
- **了解服务器角色分配** → [服务器架构](./server/architecture.md)
- **配置NSQ消息队列** → [NSQ配置](./components/nsq.md)
- **解决网络问题** → [网络管理](./network/management.md#故障排查)
- **查看所有命令** → [Makefile参考](./makefile-reference.md)
- **检查服务状态** → [组件总览](./components/README.md#组件状态检查)

---

**更新时间**: 2025-01-24  
**文档版本**: v2.0
