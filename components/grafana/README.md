# Grafana 组件

本组件通过 provisioning 自动加载 QS 缓存治理、事件系统和高并发治理看板，并依赖同网络中的 `prometheus` 数据源。

## 默认域名

- `grafana.fangcunmount.cn`

## 关键环境变量

- `GRAFANA_DOMAIN`
- `GRAFANA_ROOT_URL`
- `GRAFANA_ADMIN_USER`
- `GRAFANA_ADMIN_PASSWORD`
- `GRAFANA_MEMORY_LIMIT`
- `GRAFANA_CPUS`

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
Resilience dashboard 使用 `qs_resilience_*` 原始指标和 `qs:resilience_*` recording rules。UID 固定，供 operating 前端通过 `REACT_APP_GRAFANA_URL` 自动生成深链接。
