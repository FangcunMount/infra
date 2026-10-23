# M3 事务消息观察与恢复边界

[M3 总表](rocketmq-m3-execution.md)记录 T24 的完成状态。此文档与只读工具是 T24 实施中的工作，真实 DLQ 定向验收已通过；宿主指标、准入保护、完整回归与生产启用仍待独立验证。它不授权生产变更，也不替代 T25/T29 的具名恢复演练。

## 分清责任再处置

| 观察 | 可以证明 | 不能据此推断 |
| --- | --- | --- |
| 原事务精确 Committed witness | 本地业务与该分支已共同提交 | Broker 已接受最终确认或消费者已完成 |
| `FinalUnknown` 结果及累计计数 | 某次最终确认未证实 | 当前未决数量；之后回查可能已成功 |
| Checker 的 Commit 计数 | Checker 作出过提交决定 | EndTransaction RPC 已收到成功确认 |
| Broker half-message 按 Topic 计数 | Broker 的事务计数观察 | 精确分支、最老未决年龄或无漂移的持久化事实 |
| SDK 回查排队及在途数 | 当前实例所持资源 | 全 owner 所有实例的积压 |
| 业务 receipt / 投影版本 | 精确业务链路已经确认的效果 | 其他订阅也已收敛 |
| 原生事务超限或 DLQ 索引 | 对应 Broker 原生记录存在 | 可以换事件 ID、重做业务或重新调用模型 |

因此，累计 `FinalUnknown` 不直接触发“当前未决超过300秒”的保护；已提交的历史结果也不能靠按创建时间扫描而永远算作未决。回查成功后的传输观察与原 witness 权威分开记录。缺少可信观察时显示不可用或候选责任，不能填零伪装健康。

## 准入与恢复责任

四个事务 owner 为 `iam.mysql`、`qs.mysql`、`qs.mongo`、`ai.mysql`。连接与 owner 来自宿主显式配置，消息属性和审计 key 不决定连接哪一个数据库。关闭新准入后保留 Checker 与必要协议维护；不将取消、lease 到期或进程退出当作 Rollback 证据。消费幂等、原业务 retry 授权与模型 unknown 治理保持原责任。

告警与保护门槛沿用规划：当前未决持续超过120秒告警；超过300秒、回查饱和持续120秒或出现原生事务超限，封闭受影响 owner 的新准入并进入具名处置。配置、权限、路由及权威证据矛盾需要立即拒绝新执行。宿主采样和保护实现仍须验证，不能把本段文字当作已生效的自动控制。

恢复前核对原 owner/store/epoch、实际 Topic/type/revision、精确 Reference/wire 摘要、数据库事实、业务 receipt 与消费责任。没有精确证明的结果保持 Unknown。解除保护需要明确的处置记录和绑定、容量及未决责任复核；不自动切回 NSQ/Outbox，不通过 Checker、中止器或消费重投授权业务或模型重做。

## 只读原生索引审计

事务超限使用现有 [audit_transaction_limit.py](../../scripts/rocketmq/audit_transaction_limit.py)。新增 [audit_native_dead_letters.py](../../scripts/rocketmq/audit_native_dead_letters.py)按冻结的 v2 manifest 和具名 route 选择原生 `%DLQ%` Group，拒绝未登记、无订阅或非规范资源。两者只运行 `docker inspect` 和固定 `queryMsgByKey`，不解析或导出正文、不移动消费位点、不补建 Topic、不重放消息、不改变 ACL 或数据库。

DLQ 工具参数为 `--container`、`--project`、`--manifest`、`--route`、`--key` 和 `--output`，必须显式指定。它先验证 Compose 项目身份，再按一个 Group、一个受限 key 查询最多64条索引。输出0600文件原子新建，不覆盖现有文件或跟随已有链接；标准输出仅含条数、是否可能截断和告警枚举，不回显 key、消息 ID、原生日志或正文。失败返回固定 unavailable，不泄露命令输出和凭据。

| 退出码 | 含义 |
| --- | --- |
| 0 | 该 key 的权威索引表返回零条；不证明整个 DLQ 为空 |
| 1 | 路由、项目、读取、格式或文件创建未通过；不能解释为零条 |
| 2 | 找到该 key 的原生 DLQ 索引，产生 critical 记录，等待具名治理 |

64条表示可能截断。索引小时是 Broker 索引时间，不是最老未决事务年龄。报告的 `index_format_version` 只声明固定解析格式；真实 Broker 版本、镜像 digest 和实际参数由验收报告/生产清单分别绑定，不能从该字段推断。

一个 Group 可能对应多个物理输入及事务 owner，例如 `qs-worker` 的评分订阅同时承接 MySQL、Mongo。审计报告保留完整候选 owner 集合并标记歧义，不凭 Group 或 key 选择某个数据库、修改 witness 或替任何 owner 确认事务。原生索引是取证材料，不是业务重试授权。

固定5.5.1的 [QueryMsgByKeySubCommand](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/tools/src/main/java/org/apache/rocketmq/tools/command/message/QueryMsgByKeySubCommand.java)输出消息索引表。工具承诺限制输出，不据此承诺Broker/MQAdmin内部不加载消息内容。纯解析/权限与隐私测试只证明工具边界；T24 必须另取得真实 DLQ 记录的原生验收，不能用拼接文本替代。

## Broker 中断后的协调恢复

T23 开发验收39906622326证明了以下受控路径，完整矩阵和生产仍单独记账：

1. 保留原数据库、消息身份、首次 wire 与 writer epoch；关闭新准入，排空失败的旧 AI 监督器和其所属 SDK 资源。
2. 恢复原 Broker 与持久化存储，回读实际参数、NameServer 路由与认证 Proxy QueryRoute。
3. 以原绑定启动新 QS 进程和新 AI owner，暂停准入完成原 Reference 回查，再恢复消费者并核对 receipt/state/ACK。
4. 原业务不重做，不重新准备旧 execution 的半消息，不增加模型调用；恢复后首次生成的业务 ACK 仍按其自己的原事务发送。所有未决责任保留到精确处置完成。

固定 Go5.1.4 存活消费者可能等待5分钟 settings 周期同步。上述路径包含显式受影响实例重启，不宣称存活 Go 自动恢复。新 AI DI runtime 也不冒充新的 Python OS 进程。恢复预算须依据实际回读和有限窗口演练，不能把配置乘积直接称为 SLA。

隔离 Go 探针的 `close_for_recovery` 仅移交临时 schema 清理责任；生产部署没有此控制命令，禁止把测试探针或临时库 DROP 逻辑用于生产。生产动作仍等待 T29 固定镜像/配置/资源清单与 T30 具名确认。Prometheus/Grafana 继续由 Mac mini 采集，不在 serverD 增加常驻代理，不改变原三个 worker 的配置。

原生DLQ验收探针位于[scripts/rocketmq/probes/native-dead-letter](../../scripts/rocketmq/probes/native-dead-letter/main.go)，锁定公开Go预发布tx.3、无本地replace。39916396134已完成真实5.5.1隔离验收8项、零失败跳过：校验实际Compose身份，显式设置并回读该测试Group的有限重试参数，证明原消息经过失败handoff后出现真实DLQ索引、重复只读导出一致，以及所属进程、容器与私有文件清理。完整PR回归与宿主保护仍待完成。探针或其NORMAL测试消息不代表业务中间上线。

隔离入口为`make rocketmq-native-dlq-audit-test`，显式传入SDK_DIR及已验证测试镜像。开发CI复用rocketmq-limits工作流的native_dlq=true模式，只选择native-index-audit；未选择的SDK事务矩阵不是已通过项。PR继续要求原SDK两档及新增审计job全部通过。新的CLI模式拒绝与其他SDK/宿主profile混用，在任何子进程启动前失败。


## 回查 RPC 后的确认审计

SDK源码PR54增加独立的正向回查审计。Checker.Check仍只读取精确本地证据；只有实际EndTransaction成功之后，运输适配才在原有界worker内，用新协议事务记录精确分支的确认。原业务事务、witness终态和winner token均不改变，不调用executor、不重新准备旧半消息。Python数据库工作回到宿主loop，拒绝AUTOCOMMIT或外部绑定会话；容量保留到实际审计完成。

39919796704两档各41项证明了新实例、跨语言MySQL及Go Mongo的正向记账，源码/存储与候选wheel验收分别通过。此处是已合并源码能力，尚未发布新固定版本或更新三个业务库依赖，不能视为宿主保护已启用。

确认计数与持久化审计计数分开；RPC ACK后进程退出或审计数据库失败时，Broker可能已经接受确认。这样的缺口不能标作确定的Broker半消息积压，也不能靠累计Unknown或租约时间推算精确最老年龄。宿主采样与保护仍需验证这些边界，并保留Checker和原业务恢复责任。

## T25 准备：旧 NSQ 排空观察

[nsq_drain_evidence.py](../../scripts/rocketmq/nsq_drain_evidence.py)仅离线核对冻结清单和原始只读捕获，不连接服务、不清空队列、不创建订阅、不确认消息。输入各不超过4 MiB；输出以0600原子新建，不覆盖旧证据。标准输出只给固定状态与节点数，不回显订阅、客户端或原始响应。

输入格式：

- 清单 `schema=m3-nsq-drain-inventory/v1`：`nodes[]` 每项含 `node_id`、完整 `container_id`、原 `docker inspect` 的 `container_started_at`、`version=1.3.0` 及 `topics`（精确Topic到全部Channel名数组）。必须有节点和Topic；不得从空响应推导空清单。清单须在T30根据实际节点及有效/历史订阅责任冻结，不能直接照抄过期部署记录。
- 捕获 `schema=m3-nsq-drain-captures/v1`：`nodes[]` 每项含 `node_id` 与恰好两个 `captures`。每份含上述容器身份、`captured_at`（UTC Z）、`request_path=/stats?format=json&include_clients=false&include_mem=false` 和未经重建的 `stats` JSON对象。必须从原节点全量采集，不用Topic/Channel过滤结果代替全清单。工具能拒绝声明的过滤路径，不能证明采集方没有伪造声明或内容。
- 同节点两份必须相隔5–60秒，后一份在判定时不超过15秒且不在未来。NSQ `start_time`及精确容器启动时间不变；节点、Topic、Channel清单必须完全匹配，重复、遗漏、未登记和缺字段都拒绝。

判定同时要求全部Topic和Channel的`depth/backend_depth`为零，全部Channel的`in_flight_count/deferred_count`为零；两次Topic的`message_count/message_bytes`和Channel的`message_count/requeue_count/timeout_count`均不变化。这样即使新消息已在采样间消费完毕，也不能把这段窗口当作稳定排空。旧消费者仍可连接；连接数为零不构成HTTP写者退出证据。

这些字段直接对应固定[NSQ1.3.0 stats结构](https://github.com/nsqio/nsq/blob/v1.3.0/nsqd/stats.go)和[HTTP统计入口](https://github.com/nsqio/nsq/blob/v1.3.0/nsqd/http.go)。`include_clients=false`避免采集客户端细节，也意味着此报告不提供生产连接盘点。后台队列字段只是原生队列计数，不推断底层磁盘可靠性。

```sh
python3 scripts/rocketmq/nsq_drain_evidence.py \
  --inventory /受限目录/nsq-inventory.json \
  --captures /受限目录/nsq-captures.json \
  --output /受限目录/nsq-drain-observation.json
```

成功状态为`nsq_drain_observed`，始终保留`cutover_authorized=false`。它不是旧HTTP/TCP写者、Relay、自主任务、在途业务或未来调度已经停止的证明，也不是原生超限、历史业务回执或事务audit缺口的处置授权；这些责任必须在T25/T30–T32单独冻结并验证。不可通过删Channel、清空队列、改计数或遗忘旧责任让工具通过。

真实依赖验收由[独立CI](../../.github/workflows/rocketmq-nsq-drain.yml)创建唯一临时NSQ1.3.0，验证原生后台队列、in-flight、deferred、原FIN后的排空、采样间发布/消费以及同容器重启。临时`/data`使用有界tmpfs，不产生生产卷或匿名数据卷；清理必须保留既有容器且回读无本attempt残留。尚未取得这项CI通过前，只记录纯测试与接线，不勾选T25。
