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
