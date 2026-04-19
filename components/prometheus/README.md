# Prometheus 组件

本组件通过 Docker service discovery 抓取 `qs-apiserver` 与 `qs-worker` 的 `/metrics`。

## 默认抓取方式

- 通过 `/var/run/docker.sock` 发现带 `prometheus.scrape=true` 标签的容器
- 仅抓取 `infra-network` 网络中的容器
- 当前默认覆盖：
  - `qs-apiserver:8080/metrics`
  - 所有 `qs-worker:*:9092/metrics` 副本

抓取依赖：

- `qs-server` 容器加入 `infra-network`
- `qs-apiserver` / `qs-worker` 在 compose 中带有 `prometheus.*` 标签

## 关键环境变量

- `PROMETHEUS_RETENTION_TIME`
- `PROMETHEUS_SCRAPE_INTERVAL`
- `PROMETHEUS_MEMORY_LIMIT`
- `PROMETHEUS_CPUS`
