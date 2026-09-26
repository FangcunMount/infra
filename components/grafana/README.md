# Grafana 组件

本组件部署在 `serverD`，由 `make serverD-monitoring-up` 或 `make serverD-up` 启动，通过 provisioning 自动加载 QS 缓存治理、事件系统和高并发治理看板，并依赖 `PROMETHEUS_URL` 指向的 Prometheus 数据源。

## 默认域名

- `grafana.fangcunmount.cn`

## 关键环境变量

- `GRAFANA_DOMAIN`
- `GRAFANA_ROOT_URL`
- `GRAFANA_ADMIN_USER`
- `GRAFANA_ADMIN_PASSWORD`
- `GRAFANA_MEMORY_LIMIT`
- `GRAFANA_CPUS`
- `GRAFANA_PROVISIONING_PATH`，默认 `/data/infra/grafana/provisioning`
- `GRAFANA_DASHBOARDS_PATH`，默认 `/data/infra/grafana/dashboards`
- `PROMETHEUS_URL`，默认 `http://prometheus:9090`

## CI/CD

GitHub Actions 入口：

- `.github/workflows/grafana-serverd.yml`

必需 Secrets：

- `SVRD_HOST`
- `SVRD_USERNAME`
- `SVRD_SSH_KEY`
- `GRAFANA_ADMIN_PASSWORD`

可选 Secrets / Variables：

- `SVRD_SSH_PORT`
- `SVRD_SUDO_PASSWORD`
- `GRAFANA_DOMAIN`
- `GRAFANA_ROOT_URL`
- `GRAFANA_ADMIN_USER`
- `GRAFANA_MEMORY_LIMIT`
- `GRAFANA_CPUS`
- `PROMETHEUS_URL`

## Nginx 接入

Grafana 的 Nginx 配置模板位于：

- `components/grafana/nginx/grafana.conf`

部署到运行目录示例：

```bash
bash scripts/03-nginx/nginx-app-manager.sh deploy grafana components/grafana/nginx/grafana.conf
```

## Dashboard 清单

- Cache：`cache-overview`、`cache-family`、`cache-warmup`、`cache-hotset`、`cache-query-version`、`cache-worker-lock`
- Event：`event-overview`、`event-outbox`、`event-worker`
- Resilience：`resilience-overview`、`resilience-ratelimit`、`resilience-submitqueue`、`resilience-backpressure`、`resilience-locks`

Event dashboard 使用 `qs_event_*` 原始指标和 `qs:event_*` recording rules。UID 固定，供 operating 前端通过 `REACT_APP_GRAFANA_URL` 自动生成深链接。
`event-worker` 还按事件类型和处理结果展示五条最佳努力流的五分钟副作用指标；它用于值班定位，`increase` 是区间估算，缺少时序不表示零失败。图表不包含事件 ID，需按时间和事件类型回查 Worker 日志中的原 ID，再核对外部结果后决定人工处理。该看板不配置告警接收渠道，也不表示消息已可靠送达或用户已收件。
Resilience dashboard 使用 `qs_resilience_*` 原始指标和 `qs:resilience_*` recording rules。UID 固定，供 operating 前端通过 `REACT_APP_GRAFANA_URL` 自动生成深链接。
