# AI #246 入窗观测与集中采集诊断

**03:22 缺口后的最新 30 分钟集中采集通过。** 北京时间 11 月 10 日 03:22 三个抓取超时，三个 owner 样本同刻缺失，原因仍待定位。03:28 具名端点直读通过，使用前仍需独立签收。实际窗口前重新核对集中采集、原容器及发布控制，再与账户范围和窗口授权一并签收。生产仍为 No-Go。[执行包 #424](https://github.com/FangcunMount/infra/pull/424)

## 已定位的故障范围

- Mac mini 本机 Prometheus `/-/ready` 返回成功，现有进程与数据卷仍在。实际配置通过 file SD 采集云端。采样时 ServerA 文件为零组，ServerD 曾保留三份 Worker，三个抓取均超时，随后受限发现 SSH 也超时。发现脚本按原 120 秒规则过期旧地址。
- ServerA 上已安装的发现 helper 本地实跑正常，返回 IAM、AI、API 各 1 份、Collection 2 份。Mac mini 对 ServerA、ServerD 的受限 SSH 在建连阶段超时。两目的地使用现有 Tailscale 接口。ServerA 到 Mac mini 的 Tailscale ping 可经 DERP 返回，反向探测超时。
- 用两次具名本地源端口连接复现，ServerA 的 Tailscale 接口分别看到 SSH 22 和 HTTPS 443 的 SYN，并各发出 3 个 SYN-ACK，未见完成握手的 ACK。Mac mini 两个连接均在应用握手前超时。故障范围收敛至返回链路或 Mac mini 接收侧，主机日志和单边抓包仍不足以区分二者。Mac mini 的接收侧抓包当前需要管理员认证。
- 之后跨三个发现周期，ServerA 发现一度恢复到 5 组，ServerD 从 0 回到 3。ServerA 的 5 个应用目标连续三次 down，四 owner 集中样本三次均缺失。SSH 发现的短时恢复与 HTTPS 抓取状态分别验收。

继续查链路时，优先由具备现有权限的 Mac mini 管理员同时观察两端固定流量的 TCP 标志及 Tailscale 客户端状态。恢复后的验收顺序为受限发现 SSH、ServerA 5 个及 ServerD 3 个动态目标、私网 HTTPS 路径、四 owner 集中样本和连续抓取。按原域名、原证书、原限制和原卷复验。

14:20–14:28 UTC 复验时，ServerA 的 5 个目标和四个 owner 样本恢复。14:22 的受限发现直测，ServerA 返回 5 个目标，ServerD 超过 25 秒超时。随后 8 轮连续采样中，ServerA 每轮 5 个目标均为 up，四 owner 可用且新鲜，最旧样本 20.6 秒。ServerD 三个 Worker 在 6 轮全部 up；14:24:41 三个目标缺失，同轮 Broker 为 down；14:25:26 两个 Worker 尚无首个抓取结果。14:25:55 后四个具名 TCP 探针在 ServerD 22 和 5557 均完成双向握手，属于链路恢复时的证据。集中采集仍待签收，W00 保留独立直读方案。

14:14:30–14:44:30 UTC 的 Prometheus 只读范围查询以 15 秒为步长。14:41:30 ServerA 应用和 Worker 同时出现抓取失败，四个 owner 样本同刻缺失。失败抓取耗时约 10 秒。Worker 在 121 个评估点中有 27 个未达到三实例新鲜就绪，Broker 有 11 个未达到目标，最后一次在 14:42:30。末点各目标恢复。评估点数量用于描述采集表现，故障根因仍需链路证据。

14:53–14:54 UTC 同批从 Mac mini 发出 36 个具名 TCP 连接。ServerA 的 22／443 共 18 次、2 次超时；ServerD 的 22／5557 共 18 次、6 次超时。两端按源端口仅记录 TCP 标志计数。八次失败均有主机收到 SYN 并发出 SYN-ACK，未见握手完成。该批证明应用请求前已有间歇性失败，接收侧与返回传输仍需区分。故障时段的 Mac mini 用户可读 Tailscale 日志未提供对应链路事件。八份原件两地逐成员读回并 fsync，归档 6,917 字节，SHA256 `a3d8ea3cfe886a135aa09706ca4309cc965e0f6ccf8418d06ca9a7239031e6c0`。

14:58 UTC 并行比较 Tailscale 发现探针、WireGuard 内的 TSMP、ICMP 和 TCP 22。ServerA 的 24 个探针全通过。ServerD 前三轮四种探针全通过，后三轮四种探针全部超时，成功的发现探针均经中继。同期 Linux 守护进程日志有中继相关记录，现有分类未证实连接重建原因。ServerD 这三轮故障发生在 SSH 之前，仍待定位故障端和传输段。W00 的集中采集验收继续待签收。

北京时间 11 月 9 日 23:33:30 至 11 月 10 日 00:03:30，再次在 Mac mini 的本机 Prometheus 查询 121 个评估点。23:56:15 ServerA 五个目标、ServerD 三个 Worker 和 Broker 同时保有时序但抓取失败，四个 owner 的可用、新鲜及保护样本同时缺失。末点各目标恢复，四个 owner 均可用、新鲜且未保护。Worker 和 Broker 分别有 2 和 6 个点未达到目标。原查询、按固定脚本指标名复验的同窗结果和两地保护回执已保留。集中采集连续性仍不满足 W00，直读方案仍待独立签收。

北京时间 11 月 9 日 23:59:45 至 11 月 10 日 00:29:45，Mac mini 本机 Prometheus 的 121 个评估点均满足具名目标数量、up 和 35 秒新鲜度。四个 owner 在每个点均可用、新鲜且未保护。00:30:35–00:31:20 的四轮目标列表均有 ServerA 五个目标、ServerD 三个 Worker、Broker 与 Prometheus 各一个。最旧目标样本 15.3 秒，最旧 owner 样本 14.9 秒。应用端直读同批通过，六个 QS 实例和原 AI 容器的身份与上次一致，且本次前后一致。直读回执 SHA256 为 `e798be0d042d945f42f879a49def154c19e23385131ae143f37c88009bd6035e`。AI 自动发布关闭，当前没有在途 AI 部署，QS 生产发布工作流手动禁用。该段恢复可进入 W00 审查，签收单和具名窗口授权待完成。

## W00 应用端直读候选

[固定直读脚本](../../scripts/monitoring/m5_window_direct_observe.py)在 ServerA 已有 `qs-ai` 容器内以 UID 10001 执行，只对三个具名 Worker 的 `/readyz` 和 QS、AI、IAM 的固定 `/metrics` 发 GET。两轮间隔 15 秒，脚本预算 45 秒。拒绝跳转、代理和缺失、重复或异常 owner 样本。任一 Worker 非 200，或任一 owner 的 available/fresh 非 1、protected 非 0，结果失败。

```sh
ssh -o BatchMode=yes servera 'sudo -n docker exec -i --user 10001:10001 qs-ai /app/.venv/bin/python -' \
  < scripts/monitoring/m5_window_direct_observe.py > <私有目录>/direct-observer.json
```

执行前对照同一窗口的 ServerA／D 快照核实六个 QS 完整容器 ID、镜像和源码、以及当前 AI 容器身份。私有目录 0700、原件 0600，签收脚本 SHA、两轮回执 SHA、采样时点和操作者。若运行版本改变，先复审脚本的具名端点。直读仅在 AI 仍运行的 W00 阶段使用，W03 后使用已签收的独立维护网络和 W04 观察。

2026-11-09 北京时间 21:50:58 和 21:51:13，两轮三个 Worker 均通过，四个 owner 均 available/fresh=1、protected=0。实际脚本 SHA256 为 `dc906e33d0f9e97271cb8dcc53c8e8a0bd8c6c7bdc3982a71db6d0e23024ede1`，回执 SHA256 为 `ebc3141991751aedd4c5f5c41eced92ec1e2696aea3eab06e8c8f09cb2373efc`。独立签收需明确直读的时点范围和集中采集待办，回执保留 `prometheus_scrape_verified=false`、`writer_exclusion_verified=false`、`execution_authorized=false`。

北京时间 22:36:21 和 22:36:36，使用相同脚本再次通过两轮。前后六个 QS 实例和原 AI 容器的 ID、镜像、启动时间和重启次数一致。直读回执 SHA256 `3bcf24a48b3e6b85d0b2cb6d4383dc771f240717c4ac226fb31e70a9f8195cc1`。本次原件已两地保全，独立签收和实际窗口前新鲜回执仍待完成。

固定脚本和源提交 `5541f831bfd74bfe7334ab94b40d3b9254317f5d` 的监控验证通过，部署步骤按条件跳过。15 份本轮原件及索引为 23,700 字节，SHA256 `fcdc336d28b378eefbbee57b0e8a94438c85db0428ac53ba5af5a70afde9a768`，MacBook／ServerA 两地逐成员回读与 fsync 通过。[监控 CI](https://github.com/FangcunMount/infra/actions/runs/42629579028)

| 待签收项 | 记录 |
| --- | --- |
| 独立审查人、UTC 时间 | ____ |
| 选择集中采集复验或具名端点直读 | ____ |
| 实际容器清单 SHA、脚本及两轮回执 SHA | ____ |
| 失效条件与窗口前复验结果 | ____ |

### 00:50 集中采集延续复验

北京时间 11 月 10 日 00:20:00–00:50:00，六个具名 job 和三类 owner 指标各 121 个评估点均满足上报数量、预期状态和 35 秒新鲜度。00:50:03–00:50:48 四轮即时检查均有 ServerA 五个目标、ServerD 三个 Worker、Broker 和 Prometheus 各一个，四个 owner 均可用、新鲜且未保护。最旧目标和 owner 样本均为 14.6 秒。本次范围与上一段通过的范围重叠，集中采集通过证据持续至 00:50；历史间歇性故障原因仍待定位。AI 自动发布关闭，QS 生产发布工作流禁用。本批只复查集中采集和发布设置，临窗重新核对实际运行身份和签收。原始查询及两地回执见同日入窗记录。

北京时间 00:25:30–00:55:30 的后续 121 个评估点再次通过，保持 35 秒新鲜度标准。00:55 的固定直读两轮通过，六个 QS 实例及原 AI 容器的完整身份、启动时间和重启次数与上一轮一致，当前采集前后亦一致。私有直读 SHA256 为 `55f89f10be36ac65201d042a2070fa00cd30555303ee1ab94e1416afac58c77e`。窗口审批和临窗复验仍按签收单执行。


### 03:22 集中采集缺口与 03:28 直读复验

北京时间 03:27:45 结束的 30 分钟范围，121 个评估点中有一个未达 W00。03:22:00 IAM、QS API 和一份 Collection 抓取分别耗时约 10.003、10.008、10.003 秒并报 down，三个相应 owner 样本缺失。AI owner 样本仍在，前后 15 秒点四 owner 齐全，末点恢复。该结果证明集中抓取在此时点失败，传输根因仍待定位。

03:28:41 和 03:28:56 以原固定脚本直读，两轮三个 Worker 均为 200，四个 owner 可用、新鲜且未保护。实际六个 QS 实例和 AI 容器身份与上一次原件一致，采样前后相同。回执 SHA256 `9a385924fc1e7295275de6429c93322a60867efec459cdaa8736f2dfeaf1e2a6`。19 份原件共 12,083 字节，SHA256 `10144294b98e86299283fd6a913311964bda5c2360700063f3b1769be63c52a7`，MacBook 与 ServerA 逐成员读回并完成持久化校验。当前按 No-Go 管理，W00 需要新鲜的集中连续证据或具名独立签收的直读路径。


### 03:52 缺口后集中采集复验

北京时间 11 月 10 日 03:22:45 至 03:52:45，六个 job 与三类 owner 指标各 121 点全部满足具名数量、期望状态和 35 秒新鲜度。03:22 缺口原件继续保留，未定位触发原因。窗口授权、临窗新鲜集中证据或独立签收直读方案仍待完成。5 份原件归档 4,394 字节，SHA256 `7ba281986a28e1f5b0bbf99a06c0ee023bafb62662770e8983cc00313d7f5e9d`，两地逐成员读回并完成持久化校验。
