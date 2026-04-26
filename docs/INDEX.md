# 基础设施文档导航

## 快速开始

```bash
make help
make server-info
make help-mongo
make help-nsq
```

## 文档结构

```text
docs/
├── INDEX.md
├── server/
│   ├── architecture.md
│   ├── iam-migration-to-serverB.md
│   ├── mongo-migration-to-serverC.md
│   ├── qps-capacity-planning.md
│   ├── scaling-runbook.md
│   ├── initialization.md
│   ├── github-actions-deploy-guide.md
│   ├── ssl-guide.md
│   ├── www-user-guide.md
│   └── serverB-monitoring-deploy-guide.md   # 历史/可选
├── components/
│   ├── README.md
│   ├── mongodb-quickstart.md
│   └── nsq.md
└── network/
    ├── architecture.md
    ├── swarm-setup.md
    └── management.md
```

## 推荐阅读顺序

1. [架构设计](./server/architecture.md)
2. [网络架构](./network/architecture.md)
3. [初始化指南](./server/initialization.md)
4. [升降配操作手册](./server/scaling-runbook.md)
5. [组件总览](./components/README.md)

## 快速查找

| 我想... | 参考文档 |
|---------|----------|
| 了解四机拓扑和服务落点 | [架构设计](./server/architecture.md) |
| 把 IAM 迁到 serverB | [IAM 迁移手册](./server/iam-migration-to-serverB.md) |
| 把 Mongo 迁到 serverC | [Mongo 迁移手册](./server/mongo-migration-to-serverC.md) |
| 评估 200~1000 QPS 该怎么配资源 | [QPS 容量规划报告](./server/qps-capacity-planning.md) |
| 初始化四台机器 | [初始化指南](./server/initialization.md) |
| 建四节点 Swarm / overlay 网络 | [Swarm 搭建](./network/swarm-setup.md) |
| 调整 serverA / serverB / serverC 部署清单 | [升降配操作手册](./server/scaling-runbook.md) |
| 管理 MongoDB | [MongoDB 快速入门](./components/mongodb-quickstart.md) |
| 管理 NSQ | [NSQ 配置指南](./components/nsq.md) |
| 查看各组件职责 | [组件总览](./components/README.md) |
| 参考旧监控部署 | [ServerB 监控部署指南](./server/serverB-monitoring-deploy-guide.md) |
