# AI #246 入窗观测与集中采集诊断

**集中采集仍异常，应用端直读通过。** 本页给出 W00 的候选观测方案。集中采集恢复并验收，或独立审查人接受该方案后，再与账户范围、具名窗口授权一并签收。生产仍为 No-Go。[执行包 #424](https://github.com/FangcunMount/infra/pull/424)

## 已定位的故障范围

- Mac mini 本机 Prometheus `/-/ready` 返回成功，现有进程与数据卷仍在。实际配置通过 file SD 采集云端。采样时 ServerA 文件为零组，ServerD 曾保留三份 Worker，三个抓取均超时，随后受限发现 SSH 也超时。发现脚本按原 120 秒规则过期旧地址。
- ServerA 上已安装的发现 helper 本地实跑正常，返回 IAM、AI、API 各 1 份、Collection 2 份。Mac mini 对 ServerA、ServerD 的受限 SSH 在建连阶段超时。两目的地使用现有 Tailscale 接口。ServerA 到 Mac mini 的 Tailscale ping 可经 DERP 返回，反向探测超时。
- 用两次具名本地源端口连接复现，ServerA 的 Tailscale 接口分别看到 SSH 22 和 HTTPS 443 的 SYN，并各发出 3 个 SYN-ACK，未见完成握手的 ACK。Mac mini 两个连接均在应用握手前超时。故障范围收敛至返回链路或 Mac mini 接收侧，主机日志和单边抓包仍不足以区分二者。Mac mini 的接收侧抓包当前需要管理员认证。
- 之后跨三个发现周期，ServerA 发现一度恢复到 5 组，ServerD 从 0 回到 3。ServerA 的 5 个应用目标连续三次 down，四 owner 集中样本三次均缺失。SSH 发现的短时恢复与 HTTPS 抓取状态分别验收。

继续查链路时，优先由具备现有权限的 Mac mini 管理员同时观察两端固定流量的 TCP 标志及 Tailscale 客户端状态。恢复后的验收顺序为受限发现 SSH、ServerA 5 个及 ServerD 3 个动态目标、私网 HTTPS 路径、四 owner 集中样本和连续抓取。按原域名、原证书、原限制和原卷复验。

14:20–14:28 UTC 复验时，ServerA 的 5 个目标和四个 owner 样本恢复。14:22 的受限发现直测，ServerA 返回 5 个目标，ServerD 超过 25 秒超时。随后 8 轮连续采样中，ServerA 每轮 5 个目标均为 up，四 owner 可用且新鲜，最旧样本 20.6 秒。ServerD 三个 Worker 在 6 轮全部 up；14:24:41 三个目标缺失，同轮 Broker 为 down；14:25:26 两个 Worker 尚无首个抓取结果。14:25:55 后四个具名 TCP 探针在 ServerD 22 和 5557 均完成双向握手，属于链路恢复时的证据。集中采集仍待签收，W00 保留独立直读方案。

## W00 应用端直读候选

[固定直读脚本](../../scripts/monitoring/m5_window_direct_observe.py)在 ServerA 已有 `qs-ai` 容器内以 UID 10001 执行，只对三个具名 Worker 的 `/readyz` 和 QS、AI、IAM 的固定 `/metrics` 发 GET。两轮间隔 15 秒，脚本预算 45 秒。拒绝跳转、代理和缺失、重复或异常 owner 样本。任一 Worker 非 200，或任一 owner 的 available/fresh 非 1、protected 非 0，结果失败。

```sh
ssh -o BatchMode=yes servera 'sudo -n docker exec -i --user 10001:10001 qs-ai /app/.venv/bin/python -' \
  < scripts/monitoring/m5_window_direct_observe.py > <私有目录>/direct-observer.json
```

执行前对照同一窗口的 ServerA／D 快照核实六个 QS 完整容器 ID、镜像和源码、以及当前 AI 容器身份。私有目录 0700、原件 0600，签收脚本 SHA、两轮回执 SHA、采样时点和操作者。若运行版本改变，先复审脚本的具名端点。直读仅在 AI 仍运行的 W00 阶段使用，W03 后使用已签收的独立维护网络和 W04 观察。

2026-11-09 北京时间 21:50:58 和 21:51:13，两轮三个 Worker 均通过，四个 owner 均 available/fresh=1、protected=0。实际脚本 SHA256 为 `dc906e33d0f9e97271cb8dcc53c8e8a0bd8c6c7bdc3982a71db6d0e23024ede1`，回执 SHA256 为 `ebc3141991751aedd4c5f5c41eced92ec1e2696aea3eab06e8c8f09cb2373efc`。独立签收需明确直读的时点范围和集中采集待办，回执保留 `prometheus_scrape_verified=false`、`writer_exclusion_verified=false`、`execution_authorized=false`。

固定脚本和源提交 `5541f831bfd74bfe7334ab94b40d3b9254317f5d` 的监控验证通过，部署步骤按条件跳过。15 份本轮原件及索引为 23,700 字节，SHA256 `fcdc336d28b378eefbbee57b0e8a94438c85db0428ac53ba5af5a70afde9a768`，MacBook／ServerA 两地逐成员回读与 fsync 通过。[监控 CI](https://github.com/FangcunMount/infra/actions/runs/42629579028)

| 待签收项 | 记录 |
| --- | --- |
| 独立审查人、UTC 时间 | ____ |
| 选择集中采集复验或具名端点直读 | ____ |
| 实际容器清单 SHA、脚本及两轮回执 SHA | ____ |
| 失效条件与窗口前复验结果 | ____ |
