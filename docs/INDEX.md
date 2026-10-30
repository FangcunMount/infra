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
│   ├── perf-runner.md
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
    ├── swarm-setup.md      # 建网主流程
    └── management.md       # 日常检查/排障参考
```

## 推荐阅读顺序

1. [架构设计](./server/architecture.md)
2. [网络架构](./network/architecture.md)
3. [初始化指南](./server/initialization.md)
4. [升降配操作手册](./server/scaling-runbook.md)
5. [独立 K6 压测机初始化](./server/perf-runner.md)
6. [组件总览](./components/README.md)

## 快速查找

| 我想... | 参考文档 |
|---------|----------|
| 查看RocketMQ生产切换规划与进度 | [M3执行总表](./server/rocketmq-m3-execution.md) |
| 查看RocketMQ切换后的旧链路清理 | [M4清理执行表](./server/rocketmq-m4-execution.md) |
| 准备阿里云 Redis 切到腾讯云 | [Redis 切换手册](./server/redis-tencent-cutover.md) |
| 了解四机拓扑和服务落点 | [架构设计](./server/architecture.md) |
| 查看 IAM 迁至腾讯云 serverA 的结果 | [IAM 腾讯云迁移记录](./server/iam-tencent-servera-migration.md) |
| 参考历史 IAM 迁到 serverB 的步骤 | [历史 IAM 迁移手册](./server/iam-migration-to-serverB.md) |
| 把 Mongo 迁到 serverC | [Mongo 迁移手册](./server/mongo-migration-to-serverC.md) |
| 把 serverA 从阿里云迁到腾讯云 | [serverA 腾讯云迁移记录](./server/serverA-tencent-migration.md) |
| 维护新 serverA 的账户和 CI/CD 授权 | [serverA 账户与权限维护](./server/serverA-access.md) |
| 核对 QS MQ 预检的发布专属 sudo 授权 | [QS MQ 预检授权修复](./server/serverA-qs-mq-preflight-access.md) |
| 评估 200~1000 QPS 该怎么配资源 | [QPS 容量规划报告](./server/qps-capacity-planning.md) |
| 一键准备独立 K6 压测机 | [独立 K6 压测机初始化](./server/perf-runner.md) |
| 初始化四台机器 | [初始化指南](./server/initialization.md) |
| 建 Tailscale + 四节点 Swarm / overlay 网络 | [Swarm 搭建](./network/swarm-setup.md) |
| 调整 serverA / serverB / serverC 部署清单 | [升降配操作手册](./server/scaling-runbook.md) |
| 管理 MongoDB | [MongoDB 快速入门](./components/mongodb-quickstart.md) |
| 管理 NSQ | [NSQ 配置指南](./components/nsq.md) |
| 查看各组件职责 | [组件总览](./components/README.md) |
| 在 serverD 部署 Prometheus + Grafana | [组件总览](./components/README.md) |
| 参考旧 serverB 监控部署 | [ServerB 监控部署指南](./server/serverB-monitoring-deploy-guide.md) |
