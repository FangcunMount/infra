# M6-05 事件告警邮件接线候选

此组件默认不运行：Compose profile 为 `alerting`，Prometheus 的 `PROMETHEUS_ALERTMANAGER_ENABLED` 默认为 `false`。合并代码不会自动发送邮件。现有 Prometheus 规则仍是唯一规则源；Alertmanager 只把 `subsystem="event"` 的规则路由到邮件，其他规则保留原可见性但不在本次扩大通知范围。

启用前必须明确 SMTP 服务、发件地址与认证账号，创建专用授权码文件，并指定主值守和替补。当前仅有一个个人初始收件地址，尚无发送服务和替补，故本组件不满足生产送达验收。不要把 SMTP 密码、授权码或实际收件地址提交到仓库、CI 日志或公开审核材料。

在 serverD 上按审核包准备：

1. 在 `/data/infra/alertmanager/` 下备份旧配置并准备 `data/`。给专用 `smtp_password` 文件设置 UID/GID 2000/2000、权限 0400；给 `data/` 设置 2000/2000。不要读取或打印密码内容。
2. 通过环境变量 `ALERTMANAGER_SMTP_SMARTHOST`（`host:port`）、`ALERTMANAGER_SMTP_FROM`、`ALERTMANAGER_SMTP_AUTH_USERNAME`、`ALERTMANAGER_EMAIL_TO` 调用 `render-config.py`，输出到 `/data/infra/alertmanager/alertmanager.yml`，权限 0640，属主／组 2000/2000。生成内容仅存地址和密码**文件路径**，不会复制密码。
3. 用固定镜像 `prom/alertmanager:v0.34.1` 的 `/bin/amtool check-config` 校验配置。只在配置、挂载权限和 serverD `infra-network` 都核对后，用 `docker compose --profile alerting up -d alertmanager` 启动并检查 `/-/ready`。
4. 再将 serverD 的 `PROMETHEUS_ALERTMANAGER_ENABLED=true`，单独重建 Prometheus；核对 `/api/v1/alertmanagers` 有活动目标、现有规则仍加载、没有重复 Alertmanager。不要仅凭这些状态宣布送达。
5. 经最终审核，使用受控测试规则验证 Prometheus firing → Alertmanager 路由／发送 → 收件人实际收到并确认 → resolved；不能用真实业务故障制造测试。无论测试成功与否，清理测试规则与通知，记录 UTC+8 时间窗。

回退时先把 Prometheus 开关设回 `false` 并重建 Prometheus，确认活动 Alertmanager 目标为空；再停止 `alertmanager`，保留配置、密码文件和通知历史供审计。不得执行 serverD 数据销毁目标。告警发送失败或缺少替补时，M6-05 保持未验收。

Alertmanager 的 SMTP 文件配置和 Prometheus 静态目标分别按 [Alertmanager 配置](https://prometheus.io/docs/alerting/latest/configuration/) 与 [Prometheus 配置](https://prometheus.io/docs/prometheus/latest/configuration/configuration/) 使用；邮件路径尚未做生产发送验收。
