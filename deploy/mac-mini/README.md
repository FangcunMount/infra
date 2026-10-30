# 旧 Mac mini 监控

Prometheus v2.54.1 和 Grafana 11.1.4 在 M2/8GB Mac mini 的独立 Compose 项目 `macmini-monitoring` 运行。serverD 不运行监控存储、采集代理或查询引擎。

## 采集与查询

Mac mini 每 30 秒通过受限 SSH 命令读取 serverA、serverD 的运行容器元数据，生成 Prometheus file SD。云端辅助脚本只有被 SSH 调用时才执行，不是常驻代理，不访问应用凭据。专用公钥在 root authorized_keys 中必须限制来源为 mini Tailscale IP，使用 `restrict` 和固定 `command=/usr/local/sbin/infra-monitoring-discovery`。主机密钥单独固定。

`discover.py` 使用原 `iam-apiserver` 身份发现 IAM 9080 的 `/metrics`（job=`iam`），仅从现有私网代理抓取，不新增业务端口或更改应用鉴权。其余保留原 job/instance/component 标签，动态发现 collection、worker 的全部副本。每个目标经 serverA 原有 Nginx 的 `monitoring.fangcunmount.cn` 虚拟主机代理到 overlay IP 的固定 `/metrics`，只允许 mini 的 Tailscale 来源。容器 extra_hosts 将该域名固定到 serverA 私网地址，不需要公网 DNS；TLS 使用原通配符证书。云端业务容器无需发布新的 metrics 端口。

Prometheus 只在 mini loopback 的 19090 发布，Grafana 只在 loopback 的 13000 发布；Tailscale Serve 将两端口转给 tailnet，禁止 Funnel。Grafana 公网域名仍由 serverA 终止 TLS。serverA 的轻量 `prometheus-route` Nginx 仅将现有 `prometheus:9090` 只读查询转到 mini，以兼容已经运行的 API 配置，不采集或存储指标，也不需要重启业务进程。

## 文件与生命周期

- 实际运行目录：`~/infra-monitoring`，配置和发现结果位于其 `config/`。
- 专用 SSH key、known_hosts、Grafana 环境及 runtime.env：`~/.config/infra-monitoring`，目录权限 0700，私钥/凭据文件权限 0600。
- 持久卷：`infra_prometheus_data`、`infra_grafana_data`，与开发依赖卷隔离。
- 发现定时器：用户 LaunchAgent `cn.fangcunmount.monitoring-discovery`，每 30 秒刷新；单一来源失败保留最近结果，超过 120 秒过期。
- Prometheus 保留 30 天并限制 blocks 为 8GB；WAL/head 和备份也占磁盘，需另留空间。

在旧 mini 执行：

```sh
make monitoring-up
make monitoring-status
make monitoring-discover
make prometheus-targets
```

启动使用 `--pull never`，先准备已验证的 ARM64 镜像。不要在 SSH 中解锁或导出系统钥匙串；公共镜像可通过 Docker Engine API 匿名拉取。更新部署时将已审阅的 compose、Prometheus 配置及 discover.py 同步到运行目录，再执行管理入口。旧的 grafana-serverd 工作流已删除，避免自动在错误主机重建 Grafana；当前 CI 验证配置，不自动部署生产监控。

## 迁移和恢复

迁移前先运行临时 Prometheus 验证全部目标。停止旧 Prometheus/Grafana 后复制 TSDB（含 WAL）、Grafana SQLite/插件、rules、provisioning 和 dashboards，恢复到 mini 独立卷，以同版本启动。比较历史查询和 Grafana 数据库内容，再切换 serverA 的 Grafana、collection/worker 观测 upstream。

serverD 原卷和停机归档作为本次迁移回滚副本保留，不因迁移自动删除。需要回滚时先停止 mini 两服务和兼容转发，再用迁移前 serverD 配置启动原卷并恢复 serverA upstream；迁移后的新指标不会自动回传到旧卷，需要单独处理。家庭网络、Docker Desktop 或 mini 故障时监控受影响，业务进程仍在云端运行。

## 验收

区分配置/单元测试、容器 health、真实逐实例抓取、历史数据和 Grafana 登录/人工面板验收。预期基线为 3 worker、2 collection、1 API、1 AI、1 Prometheus 自监控；副本变化后以实时发现为准。测试既有 readiness/federate 和 API 查询路径，并确认 gateway 从其他来源被拒绝。检查其他容器 ID、启动时间及挂载未改变。

## M2/M3 监控配置收口

当前发布只更新冻结于 `bcb5a32501f39ae5b0463a9316c11e3c548f7a01` 的两个规则文件、Overview／Transactions 仪表盘，并移除旧 `event-outbox.json`。使用现有 monitoring 工作流的 `assets-dry-run` 先核对实际 `macmini-001.local`、项目和挂载、原 provisioner、真实 promtool 及当前配置哈希；`assets-apply` 必须带同一 `expected_state`，且在业务服务更新完成后执行。

更新前备份五个候选路径，使用原子文件替换，向现有 Prometheus 发送 HUP 并核验重载时间和已加载规则身份。验证失败恢复原文件。Grafana 沿用原文件 provisioner；不替换镜像、不读取凭据、不操作监控数据卷或数据库。制品只证明配置文件／规则加载和健康状态，`dashboard_api_verified=false` 明确保留后台认证接口的独立验收边界。服务数据、TSDB、Grafana SQLite 和其他配置不属于本次复制清单。
