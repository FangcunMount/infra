# M4 IAM 生产消息装配清理

本文记录C02-01的源码范围、替代证明和保留责任；状态与进度只由[M4总表](rocketmq-m4-execution.md)维护。候选IAM PR154固定为9203ad1802da2cf07daaf380a7c3613930b52134。源码合并不代表最终镜像、生产部署或业务验收。

## 当前唯一装配

`process.prepareMessaging`拒绝NSQ、无事务owner的普通消息Relay和混合旧Relay配置。`platform.InitEventing`仅接受显式RocketMQ、唯一`iam.mysql`及关闭旧Relay开关，随后构造原TransactionEventing。AuthZ容器只调用RocketMQ policy subscriber，不再分配NSQ provisioner/subscriber。

这些拒绝证明有明确边界：InitEventing在自身catalog/数据库访问前拒绝；prepareMessaging在消息资源准备/SDK创建前拒绝。完整进程的基础MySQL/Redis初始化顺序没有修改，不能据此声称整个APIServer尚未打开任何数据库连接。

| 已退出对象 | 结果 |
| --- | --- |
| `platform.initReliableEventing` | 删除标准发布Outbox Stager/Store/Relay及其producer创建 |
| `platform.newEventTransport`、gatedTransport、publicationGate | 删除供旧Relay选择NSQ或普通RocketMQ的装配及暂停包装 |
| `Container.initSDKPolicySync`的NSQ选择分支 | 删除；容器仅调用原RocketMQ订阅器 |
| `ensureSDKDurableTopics`与旧topic清单 | 删除，启动不再自动创建NSQ Topic |
| EventingDeps/RuntimeOptions的旧NSQ及Relay运行参数 | 删除当前容器不再消费的字段；仅保留旧Relay enabled的否定保护 |
| 三个旧生产装配专项夹具 | 退出旧wiring、NSQ业务和四进程旧/标准Outbox交接；替代证明如下 |
| 三个旧proof/image-handoff脚本 | 参数处理、Docker、构建、临时目录或数据库调用前返回退役错误 |
| M6旧/新NSQ镜像回退workflow及标准Outbox CI步骤 | 退出活动CI；原提交及历史报告保留 |

## 测试替代映射

| 退出的旧证明 | 继续保护的当前性质 | 当前验证 |
| --- | --- | --- |
| `TestReliableMessagingPlatformWiring` | 原ID/wire、原事务提交/回滚、可选NORMAL通知、装配拒绝 | InitEventing真实正向构造、依赖前拒绝矩阵；原DirectEventPublisher golden测试；`TestM3ActualBrokerHost` |
| `TestReliableMessagingIAMQSBusinessRoundtrip` | 授权事实与精确版本、IAM自身/QS fanout、消费幂等及freshness | 当前原生Broker用例中的`proveM3BusinessFanout`，独立QS正式源码二进制与真实mTLS |
| `TestMaintenanceBootstrapHandoff`及child | 原根事务与操作journal、原维护命令提交归属、恢复与关闭 | M3 schema/planned-policy/五维护入口的原生MySQL门禁；`TestM3ActualOwnerDrain`及原生CLI验证 |
| 原NSQ镜像handoff | 当前事务owner、跨实例回查、未知确认和消费者收敛 | infra `rocketmq-iam.yml`固定候选、runtime=true、qs_ref与三档MySQL完整矩阵 |

旧NSQ/schema40回退行为本身已退出，不宣称新用例验证了旧回退。原fixture的投递语义不能当作事务语义；最终门禁使用发布的稳定SDK与真实宿主/数据库/Broker，不以编译成功或模拟transport替代。

## 明确保留

- PlannedUnitOfWork、精确版本CAS、授权操作journal、公开幂等结果与权限查询。
- 原事务witness、store/epoch/route revision、Checker、准入、真实在途与有界关闭。
- 可选NORMAL SMS及其原消费语义；IAM与QS各自的逻辑订阅，不放大配额。
- 当前`iam_message_failure_audit`终态审计；独立真实MySQL required job继续执行且拒绝skip。
- Redis撤销专用`identity_session_revocation_outbox`及其worker、业务重试与补偿。
- 历史Outbox的只读未决检查、原表/卷/迁移和备份；后续职责解耦与资产处置分别归C05/C07。
- SDK通用NSQ兼容与Mac mini开发依赖。宿主内部孤立SDK helper、旧维护/历史reader与残余测试工具由C03/C04/C05收口，本批不将其误算为当前生产装配。旧MaintenanceStager仍调用RequireOutbox，当前transaction协议数据库会拒绝标准Outbox写入，不能绕开原协议屏障。

本批本地237项相关race通过，1项MySQL并发条件用例未在MacBook启动数据库，改由required原生MySQL执行。三旧脚本的六组参数/副作用边界通过；源码、文档、完整CI、原生报告和合并SHA由最终receipt关联。没有SSH、生产部署、DDL、凭据轮换、业务/模型调用或历史资产删除；IAM/QS暂停与AI自动CD关闭保持。

当前候选完整11项CI通过；三档MySQL各原生原生迁移/维护/CLI/受管Assignment并发验证通过，零失败/跳过；真实Broker/owner关闭/fanout矩阵仍以最终receipt为准，不提前计为完成。
