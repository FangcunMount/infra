# 可读资源切换准备清单

本页是 T11/T13 的准备材料，**不是已冻结的生产执行包**。唯一进度仍见[执行总表](rocketmq-readable-names-execution.md)。稳定 SDK、最终镜像及完整演练未完成，不能开始维护。执行包须补齐最终 SHA/digest、配置摘要、实时责任观察及恢复材料，不以本页中的旧快照批准实际删除。

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
- CD原状态及在途部署：目前历史快照 IAM/QS `PRODUCTION_DEPLOY_PAUSED=false`、AI `AUTO_DEPLOY_ENABLED=true`。宿主合并会触发CD，因此必须先记录、暂停并等待在途部署结束，再合并宿主稳定依赖；这个子步骤提前于镜像最终冻结，不意味着 T13 或生产切换完成。最后按记录恢复，发现外部状态变化时不覆盖。
- 合法 system 会话、门店A的专用测试范围、新 SNAP-IV 答卷及新 AI 解读入口就绪；不重试旧答卷或未知模型任务。没有合法会话时等待用户正常登录。

新 Topic 在维护前只预置资源及具名权限并集，不发送生产探针。应用只保留旧新精确权限；拒绝额外权限漂移，ACL准备不重建账号或轮换密码。

## POP 排空证据

5.5.1 的消费 lag 计算依赖在线 Group 的 `CONSUME_POP` 类型、POP buffer offset和in-flight计数；消费者离线后可能没有序列或按普通类型计算。**必须先在旧消费者在线时取证，再停旧实例；缺指标不能填写0。**

本轮只读可达性核验已成功取得11组消费输入的lag/in-flight/ready序列，以及6个已导出的业务半消息序列，当前值均0。这仅证明监控可用，不是停写后的最终排空或删除证明。

维护中的两次有界观察须同时核对：

1. 旧业务准入、模型/评分/报告新任务和到期dispatcher已封闭；已接受工作可以沿旧链路完成。
2. 9个旧Group实际在线POP连接、完整订阅及实例数；逐 `(Topic, Group)` 检查 `rocketmq_consumer_lag_messages`、`rocketmq_consumer_inflight_messages`、`rocketmq_consumer_ready_messages`。任何缺失、重复、非整数、非零或查询错误均保持未排空。
3. 精确读取旧原生/PUSH及POP v1/v2 retry、DLQ元数据与责任；`is_retry=true` 没导出时，必须用对应重试对象不存在或实际队列空证据解释，不能将缺序列直接当0。记录broker dispatch落后及实际事务参数。
4. 四owner权威事务记录：Prepared/Unknown、确认缺口、未跟踪分支、矛盾、原生超限责任；业务receipt/Inbox/ACK、deferred及未来计划责任。Committed本地状态不能独自证明最终确认。
5. 导出Topic/Group配置、ACL、offset/POP观察、协议及业务责任摘要。停旧实例后保留最终快照，绝不把旧offset复制到新Topic。

参考固定上游：[ConsumerLagCalculator](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/broker/src/main/java/org/apache/rocketmq/broker/metrics/ConsumerLagCalculator.java)、[BrokerMetricsManager](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/broker/src/main/java/org/apache/rocketmq/broker/metrics/BrokerMetricsManager.java)、[KeyBuilder](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/common/src/main/java/org/apache/rocketmq/common/KeyBuilder.java)。核对blob分别为`3e48a3c5bb94ab5d9175c1ee1e3b3f90b76ba177`、`299b712b3755b4b56bc703ffb9c2a721bf837f73`、`19fe9ec52864badbe55fe766e932e3719ff7ec0f`。

## 窗口与恢复

目标15分钟，上限30分钟；在完整演练给出实际耗时之前不宣称可满足。提前完成所有下载、校验、资源预置及测试填写。窗口只执行封写/责任排空、停旧、切换固定配置与八实例、新订阅及四ownerChecker、system/新答卷/新AI验收和恢复入口/调度。维护计时开始、每阶段截止、受理测试时刻及首次新责任都写入持久化记录。

新Topic为空且新消费者就绪前不开放发布；不双写、双消费旧新输入，不批量重放已提交事件。已经绑定旧Aborted计划不能自动换路由，Prepared/Unknown必须先收敛。未来未绑定执行的调度保留原授权/时间/attempt/消息/wire；deferred沿已有数据库责任处理。

新链路尚无execution、半消息或消费事实时，按演练恢复兼容旧配置与镜像；本次没有数据库升级，不需要执行旧全量数据库恢复。出现新责任或不能排除新提交后，封新写并前向修复；不翻回旧provider、不换事件ID、不重做模型。30分钟到期不能静默延长。

业务验收及开放后30分钟检查通过后，逐对象复核并按具名清单撤旧权限、清理责任清零资源和回读Broker/NameServer/Dashboard；保留系统/half/op、未结retry/DLQ、历史数据库证据及未清零对象的责任清单。恢复原CD状态，完成发布索引和16项闭环。不新增48小时观察。
