# Prometheus 组件

> 2026-10-18 起，监控运行在旧 Mac mini；当前操作以[监控部署说明](../../deploy/mac-mini/README.md)为准。旧 Swarm 部署模板仅供回滚参考。

本组件部署在旧 Mac mini，由 `make prometheus-start` 或 `make monitoring-up` 管理。云端目标由 mini 主动发现和抓取。

## 当前采集方式

旧 mini 每 30 秒通过固定只读 SSH 命令读取 serverA/serverD 容器元数据，生成 file service discovery；Prometheus 每 15 秒通过 serverA 的私网 Nginx 指标入口主动抓取各实例。mini 不加入 Swarm，不挂载云端 Docker socket，serverD 不运行采集代理。

现有 job、instance 和 worker component 标签保持兼容。collection 和 worker 的副本变化由发现脚本反映，不能改为只抓取一个轮询地址。具体网络、凭据限制及生命周期见 [旧 mini 监控部署](../../deploy/mac-mini/README.md)。

## 数据与配置

- 实际配置：`~/infra-monitoring/config/prometheus.yml`。
- 逐实例发现：`~/infra-monitoring/config/targets/*.json`。
- 规则：`~/infra-monitoring/config/rules/*.yml`。
- 持久卷：`infra_prometheus_data`，显式 external，管理操作不自动删除。
- `PROMETHEUS_RETENTION_TIME` 默认为 30d，`PROMETHEUS_RETENTION_SIZE` 默认为 8GB；WAL/head 需要额外磁盘空间。
- 原 `docker-compose.yml` 和 `prometheus.yml.tmpl` 是旧 Swarm 部署及回滚参考，当前由 `deploy/mac-mini/docker-compose.yml` 加载 `components/monitoring/prometheus.yml`。

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

### M5-05 最佳努力副作用

`QSBestEffortSideEffectFailure` 监测 `qs_worker_best_effort_side_effect_total{result=~"call_failed|response_rejected"}` 在最近五分钟内是否增加，按事件类型和结果分别告警。问卷／量表二维码后处理若报告 `not_configured`，同样告警：发布后应可定位这一未执行的后处理。`task.completed/expired/canceled` 三条外围通知的 `not_configured` 保留在指标和 Worker 警告日志中，因通知目标是否应配置尚需逐环境审核，暂不据此告警；切流前必须核对各环境的预期接收方。`task.opened` 主动提醒有独立的可靠意图设计。`call_succeeded` 仅表示当前外部调用未报错，不证明用户收件；`task.expired` 的 `missed_open_window` 抑制不是失败。

告警处理先按 `event_type`、时间和 Worker 实例检索警告日志中的原 `event_id`，再核对问卷／模型发布状态或 MySQL Task 当前状态，并确认外部系统是否已经接受调用。问卷／量表可在运营界面验证按原 code／version 取得二维码；当前没有针对完成、过期、取消通知的专用人工重发入口。外部调用结果未知时不要直接重投 NSQ 消息或再次调用通知接口；记录事件身份、核对结论、责任人及人工动作后再处理。`qs_event_consume_total{outcome="acked"}` 只表示消息已确认，不能替代这个副作用指标。若新指标缺失，先核对 `up{job="qs-worker"}` 和 Worker `/metrics` 抓取，不能把缺失解释为零失败。

本规则需随 QS 的 M5-05 Worker 指标变更共同审核；合并配置文件本身不会完成生产监控发布，实际告警触发、日志定位和人工操作仍须现场演练。

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

## qs-ai 生成与回传规则

`qs-ai.yml` 使用固定指标名，覆盖 API 不可达、数据库采集失败、排队超过 120 秒、租约恢复停滞、结果回传超过 120 秒、未知模型调用、结果时间戳缺失、完整模型响应超过 120 秒和日容量拒绝。条件持续两分钟才告警；未采集到数据不能当作零积压。连接数保留为观察指标，不能拿跨进程总数与单个进程池大小比较。

首次部署先发布 qs-ai `/metrics`，再更新本组件的模板和规则，检查 `qs-ai` target、规则组和指标。规则单测验证等待时间、触发、恢复、抓取目标缺失和零样本；不会往生产写入假任务或伪造故障。发布时还需验证实际抓取和规则加载。告警在 Prometheus/Grafana 中可见；没有配置通知通道时不宣称完成外部通知。

未知调用告警只能提示人工核对模型回执，禁止直接重发。容量拒绝告警不能自动修改业务策略。本批阈值是初始运维门槛，不是性能 SLA；qs-ai 的 `docs/operational-metrics.md` 记录每个聚合值的窗口、边界和故障处理。
