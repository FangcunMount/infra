# Grafana 组件

> 2026-10-18 起，监控运行在旧 Mac mini；当前操作以[监控部署说明](../../deploy/mac-mini/README.md)为准。原 serverD 自动部署入口已退出。

本组件部署在旧 Mac mini，由 `make grafana-start` 或 `make monitoring-up` 管理，通过 provisioning 自动加载 QS 缓存治理、事件系统和高并发治理看板，并依赖 `PROMETHEUS_URL` 指向的 Prometheus 数据源。

## 默认域名

- `grafana.fangcunmount.cn`

## 配置和 CI

Grafana 的 `GF_*` 私有运行环境保存在旧 mini 的 `~/.config/infra-monitoring/grafana.env`，账号、数据库及加密配置随原实例迁移。数据源 URL 为独立 Compose 网络内的 `http://prometheus:9090`，通过 provisioning 的 `PROMETHEUS_URL` 引用。

`.github/workflows/monitoring.yml` 只验证配置和发现逻辑，不需要部署 Secrets。原自动部署到 serverD 的工作流已删除，部署管理改用旧 mini 的 `make monitoring-up` / `make grafana-start`。容量和文件路径见 [旧 mini 监控部署](../../deploy/mac-mini/README.md)。

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
