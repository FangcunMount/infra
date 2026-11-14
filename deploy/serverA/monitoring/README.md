# ServerA 正式监控候选

本目录供 H04–H07 具名窗口审查。#441 的临时采集有独立项目、卷、期限和撤回记录。正式候选与现役 Mac mini 并行采集，后续的查询路由、Grafana 和通知须分别签收。

## 采集与发现

- 使用固定离线镜像，启动前校验实际镜像、卷、网络和文件摘要。
- 安装并固定 `scripts/monitoring/discover.py` 的源码。发现通过本机固定入口和 ServerD 限来源、限命令的 SSH 授权获取两个来源。用 `discovery.example.json` 确认配置结构。SSH 私钥、已知主机文件和实际授权期限由当窗记录。
- `systemd/` 包含 tmpfiles 和刷新服务。启动前先运行一次发现服务，验证五个 ServerA 目标和三个 ServerD Worker 的实际文件。Prometheus 的两个静态目标为自身与 RocketMQ。
- 基础配置加载 `components/prometheus/rules` 的共享规则以及正式候选发现规则。保持只读规则挂载，按窗口决定实际通知路径。使用 `scripts/monitoring/check-servera-monitoring.sh` 验证 Compose、三份 Prometheus 配置和两组候选规则测试。
- `scripts/monitoring/read_servera_candidate.py` 从候选私网命名空间读取。记录完整容器 ID、镜像、StartedAt、两份 Collection 地址、运行 QS 完整源码 SHA 和 UTC 对齐的观测终点。H05 使用基础 Compose 配置，候选进程须覆盖整段两小时，481 个点须满足原十目标、四事务 owner 判据。观察工具在查询前后核对已加载的配置摘要与加载时间，要求本次加载早于观测起点，并拒绝启用历史远程读取的配置。回执仅保存配置摘要和加载时间。

## H04 启动与截止

H04 并行采集使用 `compose.yml` 和 `h04.override.yml`。两份候选的容器重启策略为 `no`。现场按独立签收的 UTC 开窗、最晚启动、最晚中止及授权结束倒排发现、H05 两小时观察和恢复余量。候选若到期停止，保留候选 TSDB 与现役查询。后续进入 H06 使用具名签收的三服务和路由步骤。

1. 用上述两份 Compose 文件执行 `create --no-build --pull never`。绑定每个已创建候选的完整容器 ID、镜像 ID 和 Compose 配置哈希，记录专用网络和 TSDB 卷。保持现役查询代理独立。
2. 在 ServerA 建立 `/var/lib/qlume-monitoring-shadow-windows/<operation>`，由 root 持有、模式 `0700`。按已审查提交放入 `h04/stop-candidate.py` 和 `h04/render_cutoff.py`。将下列字段保存为目录内的 `stop-plan.json`，模式 `0600`，归档 SHA-256 与原具名批准。
3. 在私有目录内运行 `/usr/bin/python3 -B "$STATE/render_cutoff.py" "$OPERATION" "$STATE/stop-plan.json" "$STATE/units"`。复核渲染的同名 service 与 timer，安装到 `/etc/systemd/system`，运行 `systemctl daemon-reload`，用 `systemctl enable --now` 启用具名 timer。实读其加载路径、下次 UTC 运行时间及开机启用状态。批准的最晚中止在计划中对应 `cutoff_utc`。
4. 仅通过 `/usr/bin/python3 -B "$STATE/stop-candidate.py" "$STATE" "$PLAN_SHA256" start` 启动候选。入口持同一把截止锁，核对计划、已加载的 timer、启动期限和两份容器身份。采集器就绪后才启动查询桥。保全 `start-issued.json`、`started.json` 和首个采样回执。
5. 主动中止时使用同一入口的 `stop` 操作。到期 timer 和主动中止均先持久化 `closed.json`，再停止发现、查询桥和采集器。保全 `cutoff-*.json`，读回两个候选、原代理、候选 TSDB 和发现授权撤回。服务端结果未知时先实读原 ID 和已落盘回执。重复执行 `stop` 可以复验同一收口，已关闭操作禁止重启。

计划使用以下字段。三个时间均使用整秒 UTC，例如 `2026-11-14T12:00:00Z`，且依次递增。

| 字段 | 内容 |
| --- | --- |
| `operation` | 目录名和本次具名操作 ID，以 `h04-` 开头 |
| `window_start_utc`、`latest_start_utc`、`cutoff_utc` | 已签收的开窗、最晚启动和最晚中止 |
| `data_volume`、`private_query_network` | `qlume-servera-monitoring-data` 和 `qlume-servera-monitoring-query` |
| `containers` | `servera-collector`、`query-bridge` 各含 `id`、`image`、`compose_hash` |

## 采集交叠与历史备份

1. 按具名批准执行 H04，启动基础配置的候选采集器。Mac mini 继续提供现役采集、查询及告警。记录候选容器、TSDB 卷、配置和发现文件的身份，并从候选回环 API 确认十个目标及四个事务 owner 已有真实采样。
2. 在候选继续本地采集期间，再做用于 H06 的 H03 冷备。B01 在两端用同一绝对 UTC 区间提取原始样本，确认新旧采集已交叠。若 H03 已先做，保留该归档，并用候选启动后的另一次具名 H03 冷备为 H06 提供交叠数据。按 B03 恢复原监控，并从 B04 第二副本完成 B05。
3. 完成 H05 两小时本地验收后，再接入历史读取。H06 按相同 UTC 区间核对 B05 历史副本、候选本地留存和最终查询结果。用即时查询的范围选择器读取原始样本，例如在固定 `time` 查询 `up[5m]`，按完整标签核对采样时间戳和值，再复查四个事务 owner 的观测指标。普通范围查询可能沿用旧值。记录原来已经存在的缺口、冷备和三服务重建时段；若发生新增样本缺口或无法解释原样本缺失，先保留原路由，把本次差异交 H06 审查。B05 前引用的较早历史区间、H05 的实时采集结果和 H06 的交界结果分别用其原回执签收。

## 历史与查询路由

H03 的同窗口备份、两地读回和隔离恢复已通过后，按 H06 签收的相同归档摘要准备独立历史卷。使用 `compose.yml` 与 `history.override.yml` 同时渲染三服务组合。历史读取器只监听共享命名空间的回环地址，候选保留当前采集，同时通过 Prometheus remote read 查询已保护的历史。

专用查询网仅连接已签收的现役查询代理与候选。把 `route-network.override.yml` 与现役 `deploy/serverA/monitoring-route.yml` 合并渲染，实际路由地址与配置由 H06 签收。通过原调用方实读历史时间戳、值、Prometheus warnings 和 Grafana notices。若进入 H07，恢复已留存的原查询配置、Grafana 数据源与通知路线，重新读回原样本并保留全部卷与原件。
