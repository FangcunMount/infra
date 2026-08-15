# Prometheus 组件

本组件部署在 `serverD`，由 `make serverD-monitoring-up` 或 `make serverD-up` 启动。

本组件采用三类抓取：

- 跨节点单实例 apiserver 走 overlay 网络静态抓取
- 跨节点多实例 collection-server 走 DNS service discovery，每个 A 记录形成独立 target
- Prometheus 所在节点上的 worker 等本机容器通过 Docker service discovery 抓取

## 默认抓取方式

- 静态抓取：
  - `qs-apiserver:8080/metrics`
- DNS 自动发现：`qs-collection-server:8080/metrics`
- 通过 `/var/run/docker.sock` 发现带 `prometheus.scrape=true` 标签的本机容器
- Docker 自动发现仅抓取 `infra-network` 网络中的本机容器
- 当前默认覆盖：
  - `qs-apiserver`（静态 target）
  - `qs-collection-server`（DNS SD 多 target）
  - `qs-worker`（Docker SD 每容器 target）
  - Prometheus 所在节点上带 `prometheus.scrape=true` 的本机容器

抓取依赖：

- 当前 Swarm 节点之间的 `infra-network` overlay 正常互通
- `qs-apiserver` 能通过 `qs-apiserver:8080` 解析并访问
- `qs-collection-server` 的 overlay DNS 必须返回全部 collection 副本地址
- 需要本机自动发现的容器加入 `infra-network`
- 需要本机自动发现的容器在 compose 中带有 `prometheus.*` 标签

## 关键环境变量

- `PROMETHEUS_RETENTION_TIME`
- `PROMETHEUS_SCRAPE_INTERVAL`
- `PROMETHEUS_QS_APISERVER_TARGET`
- `PROMETHEUS_QS_COLLECTION_TARGET`，使用 `host:port` 格式，启动时拆分给 DNS SD
- `PROMETHEUS_MEMORY_LIMIT`
- `PROMETHEUS_CPUS`
- `PROMETHEUS_CONFIG_TEMPLATE_PATH`，默认 `/data/infra/prometheus/prometheus.yml.tmpl`
- `PROMETHEUS_RULES_PATH`，默认 `/data/infra/prometheus/rules`

## 事件系统规则

本组件挂载 `components/prometheus/rules` 到 `/etc/prometheus/rules`，当前包含：

- `qs:event_publish_outcome:rate5m`
- `qs:event_outbox_outcome:rate5m`
- `qs:event_consume_outcome:rate5m`
- `qs:event_consume_duration:p95`
- `qs:event_outbox_backlog:current`
- `qs:event_outbox_oldest_age_seconds:max`
- `qs:event_outbox_status_scrape_failures:rate5m`

事件告警只使用 bounded labels：`source/mode/topic/event_type/outcome`、`relay`、`service`、`store/status`。不要把 `event_id`、`aggregate_id`、error message 写进 label。

## 高并发治理规则

同一 rules 目录还包含 Resilience Plane 规则：

- `qs:resilience_decision:rate5m`
- `qs:resilience_rate_limit:rate5m`
- `qs:resilience_queue:rate5m`
- `qs:resilience_backpressure:rate5m`
- `qs:resilience_lock:rate5m`
- `qs:resilience_queue_depth:current`
- `qs:resilience_queue_status:current`
- `qs:resilience_backpressure_inflight:current`
- `qs:resilience_backpressure_wait:p95`

Resilience 告警覆盖 rate limit surge、SubmitQueue full/depth、backpressure timeout/wait p95、Redis lock error/degraded。规则只使用 bounded labels：`component/scope/resource/strategy/outcome/status`。不要把 request ID、user ID、lock key、error message 写进 label。

## Mongo 数据一致性规则

`qs-data-consistency.yml` 覆盖只读 Mongo 一致性巡检和统一事务内核：high/medium/low drift、30 小时无成功周期、审计错误、checkpoint CAS 冲突、enabled scheduler 无 ready 实例、commit-unknown，以及至少 20 次事务时持续 10 分钟超过 1% 的 rollback 比例。

规则只保留固定 `severity/kind/stage/boundary/outcome` 标签；aggregate ID、request ID 和错误文本只能出现在受限审计输出中，不能进入 Prometheus label。

本地或 CI 验证：

```bash
make prometheus-rules-verify
```
