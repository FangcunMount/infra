# ServerA 正式监控候选

本目录供 H04–H07 具名窗口审查。#441 的临时采集有独立项目、卷、期限和撤回记录。正式候选与现役 Mac mini 并行采集，后续的查询路由、Grafana 和通知须分别签收。

## 采集与发现

- 使用固定离线镜像，启动前校验实际镜像、卷、网络和文件摘要。
- 安装并固定 `scripts/monitoring/discover.py` 的源码。发现通过本机固定入口和 ServerD 限来源、限命令的 SSH 授权获取两个来源。用 `discovery.example.json` 确认配置结构。SSH 私钥、已知主机文件和实际授权期限由当窗记录。
- `systemd/` 包含 tmpfiles 和刷新服务。启动前先运行一次发现服务，验证五个 ServerA 目标和三个 ServerD Worker 的实际文件。Prometheus 的两个静态目标为自身与 RocketMQ。
- 基础配置加载 `components/prometheus/rules` 的共享规则以及正式候选发现规则。保持只读规则挂载，按窗口决定实际通知路径。使用 `scripts/monitoring/check-servera-monitoring.sh` 验证 Compose、三份 Prometheus 配置和两组候选规则测试。
- `scripts/monitoring/read_servera_candidate.py` 从候选私网命名空间读取。记录完整容器 ID、镜像、StartedAt、两份 Collection 地址、运行 QS 完整源码 SHA 和 UTC 对齐的观测终点。H05 使用基础 Compose 配置，候选进程须覆盖整段两小时，481 个点须满足原十目标、四事务 owner 判据。观察工具在查询前后核对已加载的配置摘要与加载时间，要求本次加载早于观测起点，并拒绝启用历史远程读取的配置。回执仅保存配置摘要和加载时间。

## 历史与查询路由

H03 的同窗口备份、两地读回和隔离恢复已通过后，按 H06 签收的相同归档摘要准备独立历史卷。使用 `compose.yml` 与 `history.override.yml` 同时渲染三服务组合。历史读取器只监听共享命名空间的回环地址，候选保留当前采集，同时通过 Prometheus remote read 查询已保护的历史。

专用查询网仅连接已签收的现役查询代理与候选。把 `route-network.override.yml` 与现役 `deploy/serverA/monitoring-route.yml` 合并渲染，实际路由地址与配置由 H06 签收。通过原调用方实读历史时间戳、值、Prometheus warnings 和 Grafana notices。若进入 H07，恢复已留存的原查询配置、Grafana 数据源与通知路线，重新读回原样本并保留全部卷与原件。
