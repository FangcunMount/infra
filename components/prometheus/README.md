# Prometheus 组件

本组件采用“两段式”抓取：

- 对 `serverA` 上的 `qs-apiserver` / `qs-worker` 走 overlay 网络静态抓取
- 对 `serverA` 上的 `qs-collection-server` 也走 overlay 网络静态抓取
- 对 `serverB` 本机容器继续通过 Docker service discovery 抓取

## 默认抓取方式

- 静态抓取：
  - `qs-apiserver:8080/metrics`
  - `qs-collection-server:8080/metrics`
  - `qs-worker:9092/metrics`
- 通过 `/var/run/docker.sock` 发现带 `prometheus.scrape=true` 标签的本机容器
- Docker 自动发现仅抓取 `infra-network` 网络中的本机容器
- 当前默认覆盖：
  - `serverA` 上的 `qs-apiserver`
  - `serverA` 上的 `qs-collection-server`
  - `serverA` 上的单实例 `qs-worker`
  - `serverB` 上带 `prometheus.scrape=true` 的本机容器

抓取依赖：

- `serverA` 与 `serverB` 之间的 `infra-network` overlay 正常互通
- `qs-apiserver` / `qs-worker` 能通过 `qs-apiserver:8080`、`qs-worker:9092` 解析并访问
- 需要本机自动发现的容器加入 `infra-network`
- 需要本机自动发现的容器在 compose 中带有 `prometheus.*` 标签

## 关键环境变量

- `PROMETHEUS_RETENTION_TIME`
- `PROMETHEUS_SCRAPE_INTERVAL`
- `PROMETHEUS_QS_APISERVER_TARGET`
- `PROMETHEUS_QS_COLLECTION_TARGET`
- `PROMETHEUS_QS_WORKER_TARGET`
- `PROMETHEUS_MEMORY_LIMIT`
- `PROMETHEUS_CPUS`

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
