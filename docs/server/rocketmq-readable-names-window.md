# 可读资源切换准备清单

本页是 T13–T16 的执行规划，**不是已冻结的生产执行包**。唯一进度见[执行总表](rocketmq-readable-names-execution.md)。T12 已完成稳定 SDK、三库正式接入、五份固定镜像、18项启动、25项配置切换和 ACR 不可变摘要回读；[发布索引](evidence/rocketmq-readable-names-t12-release-20261028.json)保存具体证据。生产切换尚未开始。T13 须补齐实际运行基线、配置摘要、实时责任观察及恢复材料，不以隔离演练或旧快照批准实际删除。

## 固定操作对象

| 主机 | 现有实例 | 目标数量与预算 |
|---|---|---|
| serverA | `iam-apiserver` | 1，1024 MiB / 1 CPU |
| serverA | `qs-apiserver` | 1，1024 MiB / 2 CPU |
| serverA | `qs-collection-server-1`、`qs-collection-server-2` | 2，各320 MiB / 1 CPU |
| serverA | `qs-ai` | 1，768 MiB / 0.75 CPU |
| serverD | `qs-worker-runtime-1`、`qs-worker-runtime-2`、`qs-worker-runtime-3` | 3，各768 MiB / 1 CPU，原并发48 |

以上源于本批只读盘点，T13 必须再次与实际 Compose project/service、容器/镜像及端口回读核对。Broker、NameServer、Dashboard、serverA Nginx不因改名重启；不改数据库 schema、账号凭据、StoreID、writer epoch、`m3-1` 或逻辑消费预算。

新资源来自[唯一 v3 manifest](../../components/rocketmq/serverd-routes-readable-v3.json)：10 Topic / 9 Group，每Topic一读一写队列。旧 v2 的19个对象由[过渡与退役工具](rocketmq-readable-names-transition.md)精确审核。另有旧 v1 manifest 中的10 Topic/12 Group，必须单列逐对象责任证明；v2工具不会按前缀吞入这些对象，未审对象保留。

## 维护前冻结的材料

- 三库正式稳定依赖及源码 SHA，SDK 两个稳定 tag 的共同源码、Release与下载安装 receipt。
- 五份最终镜像的归档摘要、engine/config ID、发布后的不可变 registry digest；八实例启动、原关闭、真实故障与旧新恢复演练的精确报告。
- 四角色不可变 MQ/JOSE 材料及配置文件摘要；仅更新路由文件为 v3，凭据、CA和JOSE原字节保留。既有材料工具使用新的独立版本目录，不提前改活动指针。
- 旧配置/镜像与所有新候选的 pin；预拉取、替换、验证、记录成功及保留操作覆盖在既有 `/var/lib/fangcun-image-retention/deploy.lock`，serverA 同时保留原 AI deploy lock 的身份及模式。
- CD原状态及在途部署：T12 已记录原快照 IAM/QS `PRODUCTION_DEPLOY_PAUSED=false`、AI `AUTO_DEPLOY_ENABLED=true`，并将三库分别设为 true/true/false 后协调合并源码。该暂停只影响自动部署，业务入口与生产容器未切换。T13 再次核验仓库和 production 环境变量无覆盖、没有在途部署；T16 按原记录恢复，发现外部状态变化时不覆盖。
- 合法 system 会话、门店A的专用测试范围、新 SNAP-IV 答卷及新 AI 解读入口就绪；不重试旧答卷或未知模型任务。没有合法会话时等待用户正常登录。

新 Topic 在维护前只预置资源及具名权限并集，不发送生产探针。应用只保留旧新精确权限；拒绝额外权限漂移，ACL准备不重建账号或轮换密码。

## POP 排空证据

5.5.1 的消费 lag 计算依赖在线 Group 的 `CONSUME_POP` 类型、POP buffer offset和in-flight计数；消费者离线后可能没有序列或按普通类型计算。**必须先在旧消费者在线时取证，再停旧实例；缺指标不能填写0。** 追加实际核验：9个Group的15个客户端均为`CONSUME_ACTIVELY`，与固定Proxy对gRPC SimpleConsumer的登记行为一致；普通三项gauge的零值不能单独作为POP排空证明。

本轮只读可达性核验已成功取得11组消费输入的lag/in-flight/ready序列，以及6个已导出的业务半消息序列，当前值均0。这仅证明监控可用，不是停写后的最终排空或删除证明。

维护中的两次有界观察须同时核对：

1. 旧业务准入、模型/评分/报告新任务和到期dispatcher已封闭；已接受工作可以沿旧链路完成。
2. 9个旧Group实际在线连接、真实类型、完整订阅及实例数（保留本批ACTIVELY基线，不强改为POP）；逐 `(Topic, Group)` 检查 `rocketmq_consumer_lag_messages`、`rocketmq_consumer_inflight_messages`、`rocketmq_consumer_ready_messages`。任何缺失、重复、非整数、非零或查询错误均保持未排空。还须读取不依赖Group类型的POP offset/checkpoint buffer及所有revive队列；当前只读快照两种buffer为0、8个revive队列各有1条。原生revive gauge虽带milliseconds后缀，底层lag方法返回记录数；不能将其忽略或直接解释成业务在途，须核对其精确记录及真实故障控制后再冻结排空判据。
3. 精确读取旧原生/PUSH及POP v1/v2 retry、DLQ元数据与责任；`is_retry=true` 没导出时，必须用对应重试对象不存在或实际队列空证据解释，不能将缺序列直接当0。记录broker dispatch落后及实际事务参数。
4. 四owner权威事务记录：Prepared/Unknown、确认缺口、未跟踪分支、矛盾、原生超限责任；业务receipt/Inbox/ACK、deferred及未来计划责任。Committed本地状态不能独自证明最终确认。
5. 导出Topic/Group配置、ACL、offset/POP观察、协议及业务责任摘要。停旧实例后保留最终快照，绝不把旧offset复制到新Topic。

参考固定上游：[ConsumerLagCalculator](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/broker/src/main/java/org/apache/rocketmq/broker/metrics/ConsumerLagCalculator.java)、[BrokerMetricsManager](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/broker/src/main/java/org/apache/rocketmq/broker/metrics/BrokerMetricsManager.java)、[KeyBuilder](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/common/src/main/java/org/apache/rocketmq/common/KeyBuilder.java)。核对blob分别为`3e48a3c5bb94ab5d9175c1ee1e3b3f90b76ba177`、`299b712b3755b4b56bc703ffb9c2a721bf837f73`、`19fe9ec52864badbe55fe766e932e3719ff7ec0f`。

## 窗口与恢复

目标15分钟，上限30分钟；正式候选隔离空输入配置切换段实测31.455秒，不等同于生产维护总时长。T13结合实际排空及业务验收预算冻结期限。提前完成所有下载、校验、资源预置及测试填写。窗口只执行封写/责任排空、停旧、切换固定配置与八实例、新订阅及四ownerChecker、system/新答卷/新AI验收和恢复入口/调度。维护计时开始、每阶段截止、受理测试时刻及首次新责任都写入持久化记录。

新Topic为空且新消费者就绪前不开放发布；不双写、双消费旧新输入，不批量重放已提交事件。已经绑定旧Aborted计划不能自动换路由，Prepared/Unknown必须先收敛。未来未绑定执行的调度保留原授权/时间/attempt/消息/wire；deferred沿已有数据库责任处理。

新链路尚无execution、半消息或消费事实时，按演练恢复兼容旧配置与镜像；本次没有数据库升级，不需要执行旧全量数据库恢复。出现新责任或不能排除新提交后，封新写并前向修复；不翻回旧provider、不换事件ID、不重做模型。30分钟到期不能静默延长。

业务验收及开放后30分钟检查通过后，逐对象复核并按具名清单撤旧权限、清理责任清零资源和回读Broker/NameServer/Dashboard；保留系统/half/op、未结retry/DLQ、历史数据库证据及未清零对象的责任清单。恢复原CD状态，完成发布索引和16项闭环。不新增48小时观察。

固定Proxy来源：[ClientActivity](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/proxy/src/main/java/org/apache/rocketmq/proxy/grpc/v2/client/ClientActivity.java)，blob `abc23a53a3e8bf384027ef211ceecd6bf99f8065`；独立POP指标来源：[PopMetricsManager](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/broker/src/main/java/org/apache/rocketmq/broker/metrics/PopMetricsManager.java)，blob `36a256f2e91a1af008a403be136a377188ae9215`。当前补充核验不授权改Broker参数、暂停业务或删除消息。

## T13–T16 分步安排与验收

以下子步骤不增加16项总数，初始均未完成。每一步记录时间、执行人、精确输入摘要、结果和证据位置；不能以准备材料存在代替生产回读结果。运行时事实在T13重新读取，本节估时不是生产已就绪的证明。

| 总任务 | 子步骤 | 验收标准 | 顺利情况下耗时 |
|---|---|---|---|
| T13 | A：只读复核 serverA/serverD 的八实例、实际镜像/挂载/配置、四owner、Broker参数、监控、CD与部署锁 | 实际基线与候选兼容；配置/权限无未解释漂移；原运行与恢复镜像具名留存 | 30–45分钟 |
| T13 | B：核对旧v1/v2全部资源、订阅、协议未决、业务回执、未来计划及deferred责任 | 每类责任有权威查询和处置人；Prepared/Unknown先收敛；缺指标不填0；形成切换阻断清单 | 20–40分钟 |
| T13 | C：预拉取五份已发布镜像并核对摘要；生成新不可变材料；预置10 Topic/9 Group和旧新精确ACL并集 | 五镜像本地摘要正确；原配置指针未变；新资源类型/队列/权限完整回读；新Topic为空；不发生产探针、不重启应用 | 30–60分钟 |
| T13 | D：冻结具名维护/恢复清单，核对system与新答卷/AI入口，提前收敛长任务 | 每个八实例命令与镜像/材料摘要固定；新旧责任边界、30分钟截止与失败路径明确；合法测试会话可用后才约定窗口 | 10–30分钟，可与预拉取并行 |
| T14 | A：封新写与自主任务，旧消费者/Checker在线完成两轮排空观察 | 普通/POP/重试/DLQ、四owner协议、receipt与未来计划交接均满足冻结判据；未知责任阻断切换 | 3–7分钟 |
| T14 | B：停旧八实例，保存最终进度；切换固定材料/镜像，先启动新消费者与Checker | 不复制offset；新Topic为空；9 Group、4 owner及原预算核对通过；首条新责任持久化标记；失败按责任边界恢复或前向修复 | 7–13分钟 |
| T15 | A：受限system授权变更及IAM/QS双订阅，新答卷→评分→报告，新AI→receipt/state/ACK | 核对同一测试操作的数据库事实、witness、消费效果及业务回执；首次wire不变；不重提交、不重做旧模型任务 | 窗口内5–10分钟，与T14共用30分钟上限 |
| T15 | B：恢复入口与调度，完成开放后连续30分钟检查 | 新Group首条与持续消费、事务/回执积压、错误、重启/OOM和原并发均正常；Dashboard可辨认新业务资源 | 开放后30分钟 |
| T16 | A：导出旧资源配置/ACL/offset/责任证据，按具名清单撤旧权限并逐个删除可退役Topic/Group | 无旧写者/消费者、不可见重试、未决事务或Broker绑定计划；保护系统/half/op/retry/DLQ及数据库历史；Broker/NameServer/Dashboard三方回读 | 30–60分钟 |
| T16 | B：恢复原CD状态与发布索引，核对部署链路和总表 | 配置打包与后续CD使用v3正式候选，原镜像保留/锁继续有效；源码和运维文档合并；16/16有证据闭环 | 15–30分钟 |

估时按 T13 约1.5–3小时、T14约10–20分钟、T15约35–45分钟、T16约45–90分钟安排。整体顺利约4–6小时，按一个工作日预留；包括镜像拉取、API往返及文档/廉价CI收尾，不包括等待用户登录/填写或外部故障修复。T14与T15的受限验收合计目标15分钟、上限30分钟，开放后30分钟检查不占停机时间。任何阶段不能证明剩余步骤能在截止前安全完成，就在开始维护前重新安排；到期不静默延长。

实际未决事务、未结回执、配置漂移、离线主机、拉取失败或受保护POP伴随资源可能增加时间。尤其存在相关retry伴随资源时，既有工具会拒绝删除对应旧Topic；须明确保留与处置责任，T16继续未完成，不能按前缀清理或通过改表掩盖。不为压缩日程降低清零、真实业务或有限恢复边界门禁。本次不新增48小时观察，也不因改名增加DDL、凭据轮换、Broker重启或完整重型矩阵重复运行。
