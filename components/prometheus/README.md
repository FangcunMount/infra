# Prometheus 组件

本组件用于抓取 `qs-apiserver` 与 `qs-worker` 的 `/metrics`。

## 默认抓取目标

- `qs-apiserver:8080/metrics`
- `qs-worker:9092/metrics`

两个 target 都依赖服务加入 `infra-network`。

## 关键环境变量

- `PROMETHEUS_RETENTION_TIME`
- `PROMETHEUS_SCRAPE_INTERVAL`
- `PROMETHEUS_MEMORY_LIMIT`
- `PROMETHEUS_CPUS`
