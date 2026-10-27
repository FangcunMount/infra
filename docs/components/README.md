# 组件总览

> 2026-10-27：RocketMQ Dashboard 已通过 serverA HTTPS 上线，地址为 [mq.fangcunmount.cn](https://mq.fangcunmount.cn)。Dashboard 与原生 RPC 位于 serverD，serverD 无 Nginx；活动配置、维护与恢复命令见[执行及运行索引](../server/rocketmq-dashboard-servera.md)。

> 2026-10-18 起，监控运行在旧 Mac mini；当前操作以[监控部署说明](../../deploy/mac-mini/README.md)为准。下文 serverD 启动命令及历史拓扑不再适用。

本文档描述当前生产拓扑下，各基础组件部署在哪里、由哪个仓库维护。

## 当前生产落点

| 组件 | 部署位置 | 维护方式 |
|------|----------|----------|
| `nginx` | `serverA` | `infra` 仓库管理 |
| `NSQ` | `serverD` | `infra` 仓库管理 |
| `Prometheus` | `serverD` | `infra` 仓库管理 |
| `Grafana` | `serverD` | `infra` 仓库管理 |
| `MongoDB` | `serverC` | `infra` 仓库管理 |
| `MySQL` | 云服务商 A | 云托管 |
| `Redis` | 云服务商 A | 云托管 |
| `qs-apiserver` | `serverA` | 业务仓库管理 |
| `qs-collection-server` | `serverA` | 业务仓库管理 |
| `IAM` | `serverB` | 业务仓库管理 |
| `qs-worker` | `serverD` | 业务仓库管理 |
| `operating` | `serverD` | 业务仓库管理 |

## infra 仓库直接维护的组件

### Nginx

- 位置：`serverA`
- 部署清单：`deploy/serverA/docker-compose.yml`
- 组件定义：`components/nginx/docker-compose.yml`
- 环境变量：`compose/env/prod/serverA.env`

### NSQ

- 位置：`serverD`
- 部署清单：`deploy/serverD/docker-compose.yml`
- 组件定义：`components/nsq/docker-compose.yml`
- 环境变量：`compose/env/prod/serverD.env`
- 详细文档：[NSQ 配置指南](./nsq.md)

### Prometheus + Grafana

- 位置：`serverD`
- 部署清单：`deploy/serverD/docker-compose.yml`
- 组件定义：`components/prometheus/docker-compose.yml`、`components/grafana/docker-compose.yml`
- 环境变量：`compose/env/prod/serverD.env`
- 一键启动：`make monitoring-up`

### MongoDB

- 位置：`serverC`
- 部署清单：`deploy/serverC/docker-compose.yml`
- 组件定义：`components/mongo/docker-compose.yml`
- 环境变量：`compose/env/prod/serverC.env`
- 详细文档：[MongoDB 快速入门](./mongodb-quickstart.md)
- 迁移手册：[Mongo 迁移到 serverC 指导手册](../server/mongo-migration-to-serverC.md)

## 组件间依赖约定

跨机器容器统一通过 `infra-network` 访问：

- MongoDB：`mongo:27017`
- NSQ Lookupd：`nsqlookupd:4161`
- NSQD：`nsqd:4150`
- Prometheus：旧 mini `127.0.0.1:19090`
- Grafana：旧 mini `127.0.0.1:13000`

业务服务访问数据库/缓存时：

- MySQL：使用云托管地址
- Redis：使用云托管地址

## 可选/开发组件

仓库中仍保留以下组件，但它们不是当前生产拓扑的一部分：

- `components/redis/`：开发或特殊场景下的自管 Redis
- `components/mysql/`：开发环境 MySQL
- `components/prometheus/` / `components/grafana/`：生产监控栈，部署在 `serverD`

其余可选组件可继续用于：

- 本地开发
- 实验环境
- 临时排障

但不要把开发组件误认为当前生产架构的既定落点。
