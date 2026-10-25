# M4-C01 冻结清单：旧链路与当前责任

C01盘点已完成。采用[已批准M4规划](rocketmq-m4-execution.md)，以M3最终生产交付和当前main为基线，在独立工作区核对入口→装配→事务/档案→消费者/回执→部署/测试。M3的T34为用户豁免，不作为48h通过。本批没有改业务代码、生产配置或数据；候选文件属于后续逐批评审范围，清单成员不等于可整文件删除。

[机器清单](evidence/rocketmq-m4-c01-inventory-20261025.json)冻结4仓库完整SHA、18个责任单元、699个去重源码文件及摘要。现有Go目标门禁、Python31项、infra7项全部通过且0跳过；Go测试JSON和Python JUnit保留私有证据。生产只读复核8实例/4owner/10 target及公网正常，原三NSQ容器仍停/restart=no。MySQL仅读取46个相关表的466列元数据；Mongo仅读取9个相关集合/索引，未读取业务正文或模型响应。

## 责任与后续任务

| 单元 | 当前入口/责任 | 清理判断与门禁 |
| --- | --- | --- |
| I01 | IAM InitEventing先选transaction owner，仍保留initReliableEventing/标准Outbox/Relay备选 | C02删除备选装配；保留NORMAL通知和宿主关闭/真实在途边界，不能整包删messaging |
| I02 | IAM prepareMessaging/initSDKPolicySync仍能选择NSQ provision/subscriber | C02移除生产NSQ分支；RocketMQ自身订阅与QS fanout继续验收 |
| I03 | IAM PlannedUnitOfWork、操作journal、CAS、witness、native保护 | C05明确保护；授权写入/幂等/未知结果/操作查询仍属当前业务 |
| I04 | IAM prepare-package/CD仍提供NSQ和M1普通消息参数 | C06收敛为最终事务owner/catalog/只读私有挂载；当前CD暂停不解除 |
| Q01 | QS messagingruntime/eventing transport同时含NSQ、NORMAL、TRANSACTION | C02逐分支清理；保留最终事件/消息结算和共享消费预算 |
| Q02 | QS configuredEventSubsystem先选双owner，但旧standardoutbox supervisor、Replay和status仍在 | C02/C05分离扫描发布与当前重试治理；不整包删，不改未来due/attempt授权 |
| Q03 | QS transaction archive先读；Payload/Operation还有历史fallback | C03移除旧reader时保留mTLS/租户/hash、Prepared不可公开及精确receipt/首次ACK |
| Q04 | QS到期dispatcher、业务授权及Mongo答卷/报告证据 | C05全部保护；消费重投不能变成新评分/模型执行授权 |
| Q05 | QS prepare-package/CD仍写NSQ值，API与worker共用发布参数 | C06确保API双owner、IAM精确订阅和worker消费专用，不放大三个worker配额 |
| Q06 | QS历史维护/CD核验工具与固定测试契约 | C04先查workflow/Docker/CLI引用；不按低引用或文件名直接删除 |
| A01 | AI MessagingRuntime保留NSQ/MQRelay和M1普通消息装配 | C02退出备选运行分支；保留最终事务装配、关闭/取消及失败记录 |
| A02 | AI ArchivePayloadReader在无新档案时回退MessagingStore | C03可收敛最终协议，不能削弱当前payload鉴权或把Prepared视作缺记录 |
| A03 | AI TransactionMessagingStore.confirm_event仍锁读并更新interpretation_result_outbox | C05明确保留当前业务ACK/history；保护response/checkpoint/artifact及首次wire，不整表删result_outbox |
| A04 | AI旧schema/NSQ handoff CLI、reader与中间夹具 | C04逐项删除当前无运行责任代码；原报告、已发布SDK/源码tag和迁移链保留 |
| A05 | AI CD bind_messaging只接受NSQ/M1形状，尚不接受最终transactions map | C06补齐最终绑定、固定挂载与真实配置重建门禁后才能考虑CD恢复 |
| F01 | infra旧serverD Make/初始化/Compose定义 | C06移除生产旧启动/复制/chown路径，不能在生产运行旧initializer做“验证” |
| F02 | 通用components/nsq、Mac mini和隔离依赖 | 明确保护；不因生产退役删除SDK通用NSQ或开发依赖 |
| F03 | RocketMQ/监控/保护屏障及已发布SDK真实故障证明 | 保护当前责任和原验收证据；C08验证清理后运行配置、回查/恢复仍可用 |

## 存储和字段

四store的rm_tx_binding/request/execution/witness、native notices全部保留（Mongo witness嵌入execution）。数据库身份、fence、writer epoch、lease/guard、冻结计划/首次wire/Reference及三阶段结果不可改写。历史迁移正文链保持，除非另有完整新安装/升级证明；“不需要历史兼容”不意味着可以让当前schema无法重建。

- IAM：iam_authz_operations、iam_authz_message_protocol及授权事实/版本、会话撤销/Redis职责继续保留。
- QS：ai_messaging_archive/operations/inbox、首次ACK和业务receipt、qs_retry_schedule/schema、Run/Outcome/Generation及原消费幂等继续保留。旧发布Outbox/Replay只是候选，不授权重试业务。
- QS Mongo：answersheets、interpret_report_artifacts、report_generations及查询/模板集合当前业务字段、嵌入原事件和事务Reference继续保留；rm_outbox历史数据也保留，是否去除代码reader由C03另证。
- AI：messaging_archive/event_receipts/inbox、interpretation_result_outbox当前ACK和state历史、sessions/runs/artifacts、execution_jobs/model_calls及response/checkpoint继续保留。原7个blocked请求不重做，未启动评测草稿不启动。

本轮冻结的所有列默认保护，完整列/类型/索引元数据只存0600私有证据，公开仅摘要；C05后续若确定废弃字段，须先证明无当前调用/业务职责，不能凭空表或名称发DDL。

## 生产资产与不可删除边界

serverD的nsqd/nsqlookupd/nsqadmin容器、1519数据文件、三个配置、原444离线授权缓存channel/4364历史副本、完整保护与失败证据保留。旧MySQL/Mongo表、卷、wire及备份至少遵守原30天政策，本批没有物理删除授权；C07需具名对象/期限/保护核验，不执行泛化prune/GC。首次新runtime屏障仍有效，不能恢复旧全量数据覆盖新事实。

Mac mini继续是固定生产SSH入口和监控位置；保留8实例原镜像/预算、四owner绑定与原私网TLS/owned firewall。M4没有自动启用CD的授权；新部署配置通过真实重建和具名审查前，IAM/QS暂停和AI自动部署关闭均保持。

## 接下来的批次

C01只完成盘点冻结，父清理任务不因此提前打勾。优先C06：先移除infra旧生产入口，随后逐仓收敛最终事务配置渲染/挂载、worker消费专用和IAM订阅；再运行实际配置重建门禁。C02–C05随后以单一宿主的小批进入，每批先保护最终协议、当前数据/业务及模型请求次数；C07按保留边界处理，C08做清理后的最终回归。
