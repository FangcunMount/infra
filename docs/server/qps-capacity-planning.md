# QPS 容量规划报告

## P. 代码分析报告

### 分析目标

评估当前四机拓扑在 `200 / 300 / 500 / 800 / 1000 QPS` 五个等级下的可行性，并给出每个等级对应的组件资源配置建议。

> **2026-06 拓扑更新**：`serverA` 已升配至 `4C8G` 并承接 `qs-collection-server`；`serverB` 仅保留 `IAM`；`serverD` 已升配至 `4C4G`。下文分级资源表仍基于升配前的分析基线撰写，具体容器限额需结合新规格重新校准。

### 分析范围

本次分析基于两部分真实配置：

- `infra` 仓库中的当前生产拓扑与节点环境变量
- `qs-server` 仓库中的 `apiserver / collection-server / worker` 生产配置

重点读取了：

- `infra/docs/server/architecture.md`
- `infra/compose/env/prod/serverA.env`
- `infra/compose/env/prod/serverB.env`
- `infra/compose/env/prod/serverC.env`
- `infra/compose/env/prod/serverD.env`
- `qs-server/configs/apiserver.prod.yaml`
- `qs-server/configs/collection-server.prod.yaml`
- `qs-server/configs/worker.prod.yaml`
- `qs-server/build/docker/docker-compose.prod.yml`
- `qs-server/internal/collection-server/options/options.go`
- `qs-server/docs/04-接口与运维/05-事故复盘：2026-04-16 qs.evaluation.lifecycle 积压与 30 秒尾延迟.md`

### 入口与调用路径

当前主链路可以分成两条：

1. 同步主链

`client -> nginx(serverA) -> qs-collection-server(serverA) -> qs-apiserver(serverA) -> MySQL/Redis/Mongo/IAM(serverB)`

2. 异步主链

`submit -> nsqd(serverD) -> qs-worker(serverD) -> qs-apiserver(serverA) -> MySQL/Mongo/Redis`

其中最容易先成为瓶颈的是：

- `serverA` 上的 `nginx + qs-apiserver + qs-collection-server`
- `serverB` 上的 `IAM`
- `serverD` 上的 `qs-worker + NSQ`
- `serverA/serverD -> serverC` 的跨云 Mongo 访问

### 当前职责与依赖

当前目标拓扑：

- `serverA 4C8G`：`nginx + qs-apiserver + qs-collection-server`
- `serverB 2C2G`：`IAM`
- `serverC 4C4G`：`mongodb`
- `serverD 4C4G`：`qs-worker + operating + nsq + prometheus + grafana`
- 云托管：`MySQL`、`Redis`

关键依赖方向：

- `qs-collection-server` 强依赖 `qs-apiserver` 和 `IAM`
- `qs-apiserver` 强依赖 `MySQL / Redis / Mongo`
- `qs-worker` 强依赖 `nsqd`、`qs-apiserver`、`Mongo`
- `Mongo` 独占 `serverC`，但跨云

### 行为 / 契约 / 不变量边界

这份报告讨论的是：

- `混合业务总量`，不是单接口极限
- 默认以 `读多写少`、`wait_report` 不是主流量 为前提
- 目标是“稳定可持续吞吐”，不是短时压测峰值

这份报告不讨论：

- 纯缓存命中的只读压测极限
- 极端长轮询模型
- 多租户大批量后台任务同时压入

### 测试与可观测性现状

优点：

- `qs-apiserver`、`qs-collection-server`、`qs-worker` 都有 Prometheus 指标与健康检查
- `qs-worker` 积压事故已经有真实生产复盘
- `apiserver` / `collection` / `worker` 的资源限制与配置文件都比较清楚

不足：

- 当前 checked-in 的 `prod` 配置仍保留了 `127.0.0.1` 形式的 MySQL / Redis / Mongo 地址，实际生产依赖需要靠部署层覆盖，否则与当前四机拓扑不一致
- `IAM / operating` 没有在本次分析里找到同等级别的代码侧资源基线，相关资源预算属于保守工程估算

### 分析指标与判定

| 指标 | 观察证据 | 判定 |
|------|----------|------|
| `collection` 单实例入口并发 | 当前 `max-concurrency=40`，且代码校验 `max-concurrency cannot be greater than 100` | 红 |
| `apiserver` 下游预算 | MySQL 连接池 `max-open-connections=100`，`mysql/mongo/iam max_inflight=100` | 黄 |
| `worker` 异步预算 | 目标调整为 `3` 副本，单实例并发不再无限放大 | 黄 |
| 节点资源匹配度 | `serverA` 已升至 `4C8G` 并同机部署 `collection + apiserver`；`serverB` 仅 `IAM` | 黄 |
| Mongo 资源独占度 | `serverC` 已独占 Mongo，且已给到 `3072M / 3C` 预算 | 绿 |
| 跨云链路复杂度 | `apiserver/worker -> Mongo` 存在跨云 RTT 与抖动成本 | 黄 |
| 同步尾延迟风险 | 历史事故已证明应用层尾步骤会迅速放大为 MQ 积压 | 黄 |

### 主要风险点

1. `serverA 4C8G` 仍可能先被 `qs-apiserver + qs-collection-server` 顶满。
2. `serverB 2C2G` 仅承载 `IAM`，压力相对可控。
3. `collection-server` 单实例并发上限被代码限制在 `100`，500+ QPS 时单实例思路本身就开始失效。
4. `worker` 需要按 `3` 副本部署，否则异步链路只适合低百级混合流量。
5. 跨云 Mongo 让高 QPS 级别对尾延迟更敏感。

### 初步发现或假设

1. `200 QPS` 可以通过“完成当前四机迁移 + 适度放宽资源和并发”达成。
2. `300 QPS` 可作为当前方案的实现目标，但必须落实 worker `3` 副本与限流/连接池调优。
3. `500 QPS` 起，问题不再是单纯调参数，而是当前主机规格不够。
4. `800 / 1000 QPS` 不适合继续维持“单副本 app 层 + 2C2G 前台节点”的模式。

### 下一步建议

最小合理动作是：

1. 先完成四机真实部署口径收口。
2. 把 `200 / 300 QPS` 作为当前四机方案的主要目标。
3. 把 `500+ QPS` 明确视为下一阶段架构演进，而不是当前配置的自然延伸。

---

## 结论先行

### 当前四机架构在不同 QPS 等级下的判断

| 目标 QPS | 以当前主机规格是否可做 | 结论 |
|----------|------------------------|------|
| `200` | 可以 | 完成部署收口并调优后可稳定承接 |
| `300` | 有条件可以 | 可以冲，但 `serverA/serverB` 会很紧 |
| `500` | 不建议 | 当前主机规格不足，至少要升级前台与 worker 节点 |
| `800` | 不行 | 需要横向扩容 app 层，不能再单实例硬顶 |
| `1000` | 不行 | 需要改拓扑，不再适合维持当前四机混部形态 |

### 这组数字的前提

- 口径是 `普通混合业务总量`
- 不是 `wait_report` 长轮询主导流量
- 不是“纯查询命中缓存”的乐观压测结果
- 不把 `operating` 的后台批处理流量叠加进业务高峰

如果 `wait_report` 占比明显上升，整体承载能力应自动下调一个档位。

---

## 当前硬边界

### 1. collection-server

当前生产配置：

- `grpc_client.max_inflight = 80`
- `submit/query_global_qps = 250`
- `wait_report_global_qps = 120`
- `submit_queue.queue_size = 500`
- `submit_queue.worker_count = 8`
- `concurrency.max-concurrency = 40`

并且代码里有单实例上限：

- `concurrency.max-concurrency cannot be greater than 100`

这意味着：

- 当前单实例 `collection` 更像“低百级吞吐”配置
- 即使往上调，单实例也不应再幻想无限拉高

### 2. apiserver

当前生产配置：

- `mysql.max-open-connections = 100`
- `query/submit_global_qps = 200`
- `mysql.max_inflight = 100`
- `mongo.max_inflight = 100`
- `iam.max_inflight = 100`

这说明：

- `apiserver` 当前就是按 `200 QPS` 量级封顶在配
- 如果目标超过 `300`，必须一起改 `rate_limit + MySQL pool + backpressure`

### 3. worker

当前生产配置：

- `worker.concurrency = 16`
- `mysql.max-open-connections = 30`

这只能支撑：

- 较保守的异步吞吐
- 不适合把高比例提交写链路放大到 500+ QPS

本次 300 QPS 方案将 worker 从单实例改为 `3` 副本，每实例保持中等并发，避免把单个 2C4G 节点上的 Go 进程和 NSQ 都拉到不可控状态。

### 4. 节点规格

当前最紧的节点：

- `serverA 4C8G`（`nginx + qs-apiserver + qs-collection-server`）
- `serverD 4C4G`（`qs-worker + NSQ + operating + monitoring`）

也就是说，系统真正先撞到的不是 `serverC`，而是：

- `qs-apiserver`
- `qs-collection-server`
- `IAM`

---

## 分级资源配置建议

## Tier-200

### 目标

稳定承接 `200 QPS` 混合业务流量。

### 可行性

`可以`，且这是当前四机架构最合理的第一阶段目标。

### 主机规格

维持当前主机规格不变：

- `serverA 4C8G`
- `serverB 2C2G`
- `serverC 4C4G`
- `serverD 4C4G`

### 组件资源建议

| 组件 | 建议资源 | 说明 |
|------|----------|------|
| `nginx` | `0.15C / 128M` | 保持轻量 |
| `qs-apiserver` | `1.2C / 1280M` | serverA 的主要负载 |
| `qs-collection-server` | `0.8C / 640M` | 先把单实例并发适度放宽 |
| `IAM` | `0.45C / 384M` | 保守预算 |
| `nsqd` | `0.25C / 384M` | 部署在 serverD |
| `nsqlookupd` | `0.05C / 64M` | 轻量 |
| `nsqadmin` | `0.05C / 64M` | 轻量 |
| `MongoDB` | `3.0C / 3072M` | 当前已基本就位 |
| `qs-worker` | `2 replicas x 0.50C / 512M` | 先用副本数放大，不单实例硬顶 |
| `operating` | `0.25C / 256M` | 中后台轻负载预留 |

### qs-server 配置建议

| 配置项 | 建议值 |
|--------|--------|
| `collection.max-concurrency` | `60` |
| `collection.grpc_client.max_inflight` | `100` |
| `collection.submit/query_global_qps` | `220~250` |
| `collection.wait_report_global_qps` | `120` |
| `apiserver.rate_limit.query/submit` | `220` |
| `apiserver.mysql.max-open-connections` | `120` |
| `apiserver.backpressure.mysql/mongo/iam.max_inflight` | `120` |
| `worker.concurrency` | `24` |
| `worker.mysql.max-open-connections` | `40` |

---

## Tier-300

### 目标

稳定承接 `300 QPS` 混合业务流量。

### 可行性

`有条件可以`，但这是当前主机规格的高压边缘区。

### 主机规格

仍可尝试维持当前四机规格，但风险很明显：

- `serverA` 余量很薄
- `serverB` 更薄

### 组件资源建议

| 组件 | 建议资源 | 说明 |
|------|----------|------|
| `nginx` | `0.15C / 128M` | 基本不变 |
| `qs-apiserver` | `1.5C / 1536M` | serverA 接近满载 |
| `qs-collection-server` | `1.0C / 896M` | serverB 开始偏紧 |
| `IAM` | `0.50C / 512M` | 不能再太低 |
| `nsqd` | `0.30C / 384M` | 部署在 serverD |
| `nsqlookupd` | `0.05C / 64M` | 维持 |
| `nsqadmin` | `0.05C / 64M` | 维持 |
| `MongoDB` | `3.0C / 3072M` | 先维持当前配置 |
| `qs-worker` | `3 replicas x 0.50C / 512M` | 目标方案，合计约 1.5C / 1536M |
| `operating` | `0.25C / 256M` | 尽量克制 |

### qs-server 配置建议

| 配置项 | 建议值 |
|--------|--------|
| `collection.max-concurrency` | `80` |
| `collection.grpc_client.max_inflight` | `120` |
| `collection.submit/query_global_qps` | `300` |
| `collection.wait_report_global_qps` | `140~150` |
| `apiserver.rate_limit.query/submit` | `300` |
| `apiserver.mysql.max-open-connections` | `140` |
| `apiserver.backpressure.mysql.max_inflight` | `140` |
| `apiserver.backpressure.mongo/iam.max_inflight` | `120~140` |
| `worker.replicas` | `3` |
| `worker.concurrency` | `32` 每实例 |
| `worker.mysql.max-open-connections` | `40` 每实例 |

### 备注

这档位里，`serverA 4C8G` 与 `serverD 4C4G` 仍然是最紧节点；`serverB` 仅承载 `IAM`，压力相对可控。

---

## Tier-500

### 目标

稳定承接 `500 QPS` 混合业务流量。

### 可行性

`当前四机主机规格不建议`。  
如果坚持做，至少要升级主机规格；单纯调 YAML 不够。

### 最低主机规格建议

| 节点 | 建议最低规格 |
|------|--------------|
| `serverA` | `4C4G` |
| `serverB` | `4C4G` |
| `serverC` | `8C8G` 或迁回与 app 同云的更高规格 Mongo |
| `serverD` | `4C8G` |

### 组件资源建议

| 组件 | 建议资源 | 说明 |
|------|----------|------|
| `nginx` | `0.20C / 128M` | 维持轻量 |
| `qs-apiserver` | `2.2C / 2048M` | serverA 的主负载 |
| `qs-collection-server` | `1.5C / 1280M` | 单实例已接近代码上限 |
| `IAM` | `0.8C / 640M` | 不宜继续压低 |
| `nsqd` | `0.40C / 512M` | 中等 |
| `nsqlookupd` | `0.08C / 64M` | 轻量 |
| `nsqadmin` | `0.08C / 64M` | 轻量 |
| `MongoDB` | `6.0C / 6144M` | 4C4G 已不再合适 |
| `qs-worker` | `2.5C / 1536M` | 异步链路必须放大 |
| `operating` | `0.30C / 256M` | 控制住 |

### qs-server 配置建议

| 配置项 | 建议值 |
|--------|--------|
| `collection.max-concurrency` | `100` |
| `collection.grpc_client.max_inflight` | `160` |
| `collection.submit/query_global_qps` | `450~500` |
| `collection.submit_queue.worker_count` | `12~16` |
| `apiserver.rate_limit.query/submit` | `450` |
| `apiserver.mysql.max-open-connections` | `180` |
| `apiserver.backpressure.mysql/mongo.max_inflight` | `160` |
| `apiserver.backpressure.iam.max_inflight` | `140` |
| `worker.concurrency` | `48~64` |
| `worker.mysql.max-open-connections` | `60` |

### 备注

这里有一个决定性问题：

- `collection.max-concurrency` 单实例最多只能到 `100`

所以 `500 QPS` 再往上走，单实例 `collection` 已经开始进入高风险区。  
这也是 `500 QPS` 被视为“当前架构从调参走向扩容”的拐点。

---

## Tier-800

### 目标

稳定承接 `800 QPS` 混合业务流量。

### 可行性

`当前四机规格不行`，且仅靠升级单机也不优雅。  
从这一档开始，`app 层必须横向扩容`。

### 最低拓扑建议

- `qs-apiserver`: `2` 副本起步
- `qs-collection-server`: `2` 副本起步
- `qs-worker`: `2` 副本起步
- `IAM`: 至少与 `collection` 解耦，不再继续和高负载入口硬绑在同一台 `2C2G`

### 最低资源建议

| 组件 | 建议资源 |
|------|----------|
| `nginx` | `0.30C / 256M` |
| `qs-apiserver` | `2 replicas x 2.0C / 1792M` |
| `qs-collection-server` | `2 replicas x 1.2C / 1024M` |
| `IAM` | `1.0C / 768M` |
| `NSQ` | `0.6C / 768M` 总量 |
| `MongoDB` | `8C / 8192M` 级别，且优先与 app 同云 |
| `qs-worker` | `2 replicas x 2.0C / 1536M` |
| `operating` | `0.4C / 384M` |

### qs-server 配置建议

| 配置项 | 建议值 |
|--------|--------|
| `collection.max-concurrency` | `每实例 80~90` |
| `collection.grpc_client.max_inflight` | `每实例 180` |
| `apiserver.rate_limit.query/submit` | `单实例 350~400` |
| `apiserver.mysql.max-open-connections` | `单实例 160~180` |
| `worker.concurrency` | `每实例 48~64` |

### 备注

从这档开始，关注点不再是“单容器给多少资源”，而是：

- 每实例并发预算
- 副本数
- MySQL / Redis / Mongo 的整体并发承载

---

## Tier-1000

### 目标

稳定承接 `1000 QPS` 混合业务流量。

### 可行性

`当前四机混部形态不适合`。  
这一档已经不是“把现有机器再拧一圈”的问题，而是需要重排服务边界。

### 最低建议拓扑

- `nginx` 网关独立
- `qs-apiserver` 独立成应用池
- `qs-collection-server` 独立成入口池
- `IAM` 不再和入口层同机
- `qs-worker` 独立成 worker 池
- `Mongo` 不再建议单节点跨云独撑，优先：
  - 同云更高规格自建
  - 或托管 Mongo / 同类文档库

### 资源建议（最小起步）

| 组件 | 建议资源 |
|------|----------|
| `nginx` | `2 replicas x 0.3C / 256M` |
| `qs-apiserver` | `2~3 replicas x 2.0C / 2G` |
| `qs-collection-server` | `2~3 replicas x 1.2C / 1G` |
| `IAM` | `1~2 replicas x 1.0C / 768M` |
| `NSQ` | `0.8C / 1G` 总量 |
| `MongoDB` | `8C16G` 起步，且尽量同云 |
| `qs-worker` | `2~3 replicas x 2.0C / 1.5G` |
| `operating` | `0.4C / 384M` |

### 备注

如果目标真是 `1000 QPS`，不建议继续把前台同步链固定为单实例部署。

---

## 对当前四机架构的最终判断

### 最值得追求的现实目标

当前这版四机架构，最合理的容量目标是：

- `稳 200 QPS`
- `冲 300 QPS`

### 500 以上的关键变化

不是继续调 Mongo，而是：

1. `serverA/serverB` 先升级规格
2. `collection` 从单实例思维转向多副本
3. `worker` 明显扩容
4. `Mongo` 尽量减少跨云同步热点

### 一句话结论

- `200 QPS`：可以做
- `300 QPS`：可以冲，但很紧
- `500 QPS`：当前主机规格不够
- `800 QPS`：要横向扩 app 层
- `1000 QPS`：要改拓扑，不再适合维持当前四机混部模型
