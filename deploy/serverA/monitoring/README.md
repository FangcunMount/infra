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

### ServerD 发现授权和撤回

在同一具名 H04 窗口，先核对 ServerD 主机公钥、OpenSSH 版本、时区、受限发现命令、ServerA Tailnet 来源及原 Mac mini 授权行摘要。ServerA 生成当窗专用 ED25519 密钥，ServerD 只接收公钥字段。以 root 在 ServerD 的 `/var/lib/qlume-monitoring-pilot-authorizations/<operation>` 准备私有目录（`0700`）、`auth-plan.json`（`0600`）及 `serverd-auth.py`、`render_deadline.py`、`render_withdrawal.py`。

计划字段为 `operation_id`、`key_blob`、`public_fingerprint`、`original_line_sha256`、`starts_utc`、`latest_start_utc`、`cutoff_utc`。时间使用整秒 UTC `Z`，最晚加入授权早于截止。公钥 blob 是 `.pub` 文件的第二段，指纹使用 `ssh-keygen -lf` 的 SHA-256。计划摘要与具名批准、已核对的原 Mac mini 授权行摘要一起保全。

```sh
/usr/bin/python3 -B "$STATE/render_withdrawal.py" "$OPERATION" "$STATE/auth-plan.json" Asia/Shanghai "$STATE/units"
/usr/bin/python3 -B "$STATE/serverd-auth.py" append "$AUTH_PLAN_SHA256"
```

先渲染并审查单元，在 ServerD 安装 `/etc/systemd/system` 下的服务和计时器，完成 `daemon-reload`、`enable --now` 和下次触发读回，再执行 append。入口按计划生成限源、限命令及到期授权，拒绝已有撤回记录和不匹配的 timer。到期由持久 timer 调用同一入口的 `withdraw`，主动中止也用 `withdraw` 和同一摘要。读回当窗授权缺席、原 Mac mini 授权行字节一致，并验证新的候选 SSH 认证被拒绝。保留授权和撤回回执。若原行在当窗变化，撤回仍可删除唯一且精确匹配的当窗授权，并保留其他行。实际读回落盘后入口以失败退出，由当窗审查原行变化。候选公钥出现于非精确匹配的授权行时，入口拒绝改写并留待当窗查明。

### ServerA 并行采集

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

在已签收的 H06 导入窗口，用 `history/import-approval.blank.json` 填写 H03/B05 与 H06 操作 ID、操作者、独立审查人、时限、归档及工具镜像摘要。通过既有保护入口读回 B04 归档，核对 B05 绑定。批准范围内，在 ServerA 准备一个本地空卷 `qlume-servera-monitoring-history`，用 `org.fangcunmount.monitoring.h06-operation` 标签绑定 H06 操作 ID。核对卷未被容器引用。

```sh
sudo -n /usr/bin/python3 -B scripts/monitoring/restore_history_volume.py "$B04_ARCHIVE" \
  --b05 "$B05_RECEIPT" --approved-import "$HISTORY_IMPORT_APPROVAL" \
  --max-bytes "$REVIEWED_BYTE_LIMIT" > "$HISTORY_IMPORT_RECEIPT"
```

入窗为导入、读回和恢复操作预留时间。导入入口使用固定 Linux amd64 镜像和生产本机 Docker，逐件验证内容，读回后绑定 B05 与导入批准的原始字节摘要。导入失败、中断或卷已有内容时保留原件与卷现状，交本次窗口复核。

### H06 Worker 发现接续

H04 的临时公钥和采集授权到期即结束，H06 使用自己的发现授权。签收时分别登记 H04 收口回执、H06 发现操作 ID、专用公钥指纹、ServerD 限源限命令、主机指纹、UTC 截止和接班人。后续轮换使用新的 `h06-` 开头的操作 ID 和独立密钥。各次授权用同一 `h04/` 工具渲染独立的 ServerD 持久撤回单元。各自核对实际工作范围后加入，旧授权按原截止撤回。Mac mini 原授权及查询由各自流程保留。

1. 获批后为 H06 安装独立的到期撤回 timer，再加入 H06 公钥。用新私钥、固定 host key 和相同的发现程序向独立输出目录发起一次完整刷新。核对三份 Worker 身份和五个本机应用；新凭证失败时维持现役 Mac mini 路线。
2. H04/H05 证据封存后，用 H04 精确停止计划收口两容器及其 ServerA 发现服务，分别读回 `closed.json`、停止回执及 ServerD 临时授权撤回。确认 H04 发现定时器已经停用，停用本次 H04 截止定时器并保留历史回执。候选 TSDB 保留，原代理仍使用 Mac mini。
3. 在 H06 具名窗口，以同目录原子替换发布已审查的 `discovery.json`。其 `identity` 指向新私钥，`output` 指向正式目标目录。用正式发现服务生成两份新鲜文件并启用刷新 timer，再启动 H06 三服务。读回十个目标、三个 Worker 的最近成功采样和四个事务 owner。记录 H04 停止、H06 重建及本地采样空档并按原样本规则复核，再切现役代理。
4. 正式运行后的凭证轮换先在重叠期独立探测新授权。原子切换发现配置后，用新凭证执行正式刷新，并核对新鲜 Worker 目标及样本，再撤回原授权。旧凭证仍在有效期且获准时可恢复原配置。发生未收口的正式采集或凭证故障，按 H07 切回 Mac mini，保留两个采集器数据和回执。轮换及撤回各自按独立截止运行。

专用查询网仅连接已签收的现役查询代理与候选。把 `route-network.override.yml` 与现役 `deploy/serverA/monitoring-route.yml` 合并渲染，实际路由地址与配置由 H06 签收。通过原调用方实读历史时间戳、值、Prometheus warnings 和 Grafana notices。若进入 H07，恢复已留存的原查询配置、Grafana 数据源与通知路线，重新读回原样本并保留全部卷与原件。

### H03 / H06 原始样本复核

使用 `scripts/monitoring/capture_servera_history.py` 对同一已结束的 UTC 区间取证。`--start` 与 `--end` 使用 Unix 秒，区间最长 900 秒。四条路线为 `macmini`、`candidate`、`history` 和 `merged`。各次传入相同的运行 QS 完整 SHA 及两份 Collection IP。每条路线的 `--binding` 独立记录完整容器 ID、镜像 ID 和原 Docker `started_at`。回执保留每个查询的原始 HTTP 正文、解析后的样本、读前后容器与卷身份，以及加载配置摘要和 TSDB 边界。

在 B01 冷备前先用 `macmini` 与 `candidate` 回执确认两端原样本交叠。H06 在启用历史读取前保存同一区间的候选本地回执，恢复后采集 `history` 与 `merged`。现场保留 B05 实际恢复回执、具名导入批准和实际导入回执的原始字节。工具核对导入程序记录的两份原件 SHA-256、操作 ID、归档和实际读取器卷。导入回执须证明逐件读回及持久化，读回时间须落在批准窗口内。

供 H06 使用的冷备，先在具名 H03 窗口用同一操作 ID 执行以下步骤。B01 并发读取两个采集器，分别保留原始 HTTP 正文、执行状态和错误，核对所有序列共享一段新鲜的健康采样区间。采集失败或样本超龄时保留原件并暂停签收。

```sh
python3 -B scripts/monitoring/capture_servera_b01.py \
  --evidence-parent "$PRIVATE_PARENT" --operation-id "$H03_OPERATION" --qs-source "$QS_SOURCE" \
  --collection-ip "$IP1" "$IP2" --macmini-binding macmini-binding.json --candidate-binding candidate-binding.json
python3 -B scripts/monitoring/bind_servera_b01.py \
  --operation-id "$H03_OPERATION" --source "$ORIGINAL_H03_SOURCE" \
  --b01 "$B01_DIR/b01-receipt.json" --out "$H03_SOURCE"
```

B02 审批使用 `H03_SOURCE` 原件摘要。B04 第二副本保留同一来源、批准和启动凭证，B05 使用同一清单。H06 在历史卷导入后用 B01 的原时间区间从实际历史读取器取证，然后复算整条链。原 B01 区间与下一段交界分类可分别读取。

```sh
python3 -B scripts/monitoring/verify_b01_b05.py \
  --b01 "$B01_DIR" --second-copy "$VERIFIED_SECOND_COPY" --b05 "$B05_RECEIPT" \
  --import-proof "$HISTORY_IMPORT_RECEIPT" --import-approval "$HISTORY_IMPORT_APPROVAL" \
  --history "$HISTORY_B01_CAPTURE"
```

```sh
python3 -B scripts/monitoring/capture_servera_history.py macmini \
  --start "$START" --end "$END" --qs-source "$QS_SOURCE" \
  --collection-ip "$IP1" "$IP2" --binding macmini-binding.json > macmini.json
python3 -B scripts/monitoring/servera_history_seam.py overlap macmini.json candidate.json > overlap.json
python3 -B scripts/monitoring/classify_servera_history.py macmini.json history.json candidate.json merged.json \
  --local-boundary "$LOCAL_START_UTC" --b05 "$B05_RECEIPT" \
  --history-volume-proof "$HISTORY_IMPORT_RECEIPT" --import-approval "$HISTORY_IMPORT_APPROVAL" > classification.json
```

归因按完整标签、毫秒时间戳和原值比较。只有原采集和恢复归档一致，且缺口在对应候选首样本前并落在原缺口内，才记录为既有缺口。原采集的失败值继续记录，包括在同时间戳按 Prometheus 本地优先规则覆盖的值。候选自身缺样、非健康值、合并新增缺口或查询注解须暂停 H06。保留原件并复核，已切换时按 H07 恢复。真实调用方、Grafana 和通知分别留现场或签收原件。

### H06 / H07 现役查询代理读回

切换前保留 Mac mini 原始查询回执、ServerA 代理原配置及 Grafana 原数据源。每段读回使用各自审查的代理完整容器 ID、镜像 ID、原始 `started_at` 和容器内 `/etc/nginx/nginx.conf` 的 SHA-256。工具从 ServerA 现役代理网络命名空间查询 9090 兼容入口。H06 还核对实际代理在专用查询网的地址，并从精确候选的网络命名空间读取本机活动目标。十个目标必须完整、健康且最近抓取不超过 35 秒，候选镜像、启动时间和加载配置必须与 merged 回执相同。抓取文件保留历史 HTTP 正文、状态及候选活动目标读回。

```sh
python3 -B scripts/monitoring/verify_servera_route.py h06 merged.json \
  --proxy h06-proxy-binding.json --capture h06-proxy-raw.json > h06-proxy-review.json
python3 -B scripts/monitoring/verify_servera_route.py h07 macmini.json \
  --proxy h07-proxy-binding.json --capture h07-proxy-raw.json > h07-proxy-review.json
```

任一 Prometheus warning、info、非 200 或原始样本差异都暂停签收。H06 现场另行核对实际 QS 查询和认证 Grafana 的数据源、数据帧、通知以及 warning notices。H07 具名恢复使用已保全的旧上游、Grafana 原数据源和通知路径，并保留候选与原数据卷。

在具名 H06 窗口中，`grafana-listener.conf` 可作为现役代理 Nginx `http` 块的 include。先固定 ServerA 监听、源端访问限制、Grafana 的 TLS 服务端名称和相互认证材料，按窗口签收只读挂载证书与私钥，并用 `nginx -t` 核对最终加载配置。认证规则读取经过私有监听和候选查询桥两层白名单。现场分别复验 GET `/api/v1/rules`、现役 QS 兼容查询、告警通知及恢复。缺失客户端证书、错误 CA、规则 POST 及管理端点访问应被拒绝。实际证书、私钥及外部访问设置由当窗保全。
