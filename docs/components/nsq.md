# NSQ 消息队列

## 概述

当前生产目标中，NSQ 部署在 `serverD (4C4G)`，与 `qs-worker`、`operating` 同机。

包含三个组件：

- `nsqlookupd`
- `nsqd`
- `nsqadmin`

## 部署位置

| 组件 | 位置 | 暴露方式 |
|------|------|----------|
| `nsqlookupd` | `serverD` | `4160/tcp`, `4161/tcp` |
| `nsqd` | `serverD` | `4150/tcp`, `4151/tcp` |
| `nsqadmin` | `serverD` | `127.0.0.1:4171` |

## 关键文件

| 文件 | 作用 |
|------|------|
| `deploy/serverD/docker-compose.yml` | serverD NSQ stack |
| `compose/env/prod/serverD.env` | NSQ 环境变量 |
| `components/nsq/docker-compose.yml` | 组件定义 |
| `components/nsq/nsqd.conf` | nsqd 配置 |
| `components/nsq/nsqlookupd.conf` | nsqlookupd 配置 |
| `components/nsq/nsqadmin.conf` | nsqadmin 配置 |

## 常用命令

```bash
make serverD-up
make serverD-down
make serverD-logs
make serverD-status

make nsq-topics
make nsq-stats
make nsq-logs
make nsq-admin
```

## 服务发现约定

业务容器通过 `infra-network` 访问：

- `nsqlookupd:4161`
- `nsqd:4150`

推荐：

- 生产者优先连 `nsqd:4150`
- 消费者优先通过 `nsqlookupd:4161` 做发现

## 环境变量

`compose/env/prod/serverD.env` 里至少需要：

```bash
INFRA_HOST_LABEL=serverD
NSQLOOKUPD_TCP_PORT=4160
NSQLOOKUPD_HTTP_PORT=4161
NSQD_TCP_PORT=4150
NSQD_HTTP_PORT=4151
NSQADMIN_PORT=4171
NSQLOOKUPD_MEMORY_LIMIT=96M
NSQLOOKUPD_CPUS=0.04
NSQD_MEMORY_LIMIT=384M
NSQD_CPUS=0.20
NSQADMIN_MEMORY_LIMIT=96M
NSQADMIN_CPUS=0.04
NSQD_BROADCAST_ADDRESS=${NODE_D_IP}
```

## 运维建议

- `nsqadmin` 只绑定 `127.0.0.1`
- `NSQD_BROADCAST_ADDRESS` 应填写 `serverD` 对其他节点可达的地址
- 业务侧配置不要写死公网 IP，优先使用 overlay 服务名

## 相关文档

- [组件总览](./README.md)
- [网络架构](../network/architecture.md)
- [服务器架构设计](../server/architecture.md)
