# M3 消息、事务与恢复责任清单

本清单只描述五库执行基线的源码责任，不声明生产运行状态。完整SHA及自动核对结果见 [T02源码证据](evidence/rocketmq-m3-inventory-20261019.json)。进度只在 [M3总表](rocketmq-m3-execution.md)维护。

## 1. 领域事件与订阅

| 仓库/事件 | 当前事务/发布入口 | 最终owner/类型 | 消费与保留责任 |
| --- | --- | --- | --- |
| IAM iam.authz.version_changed.v2 | authz UOW → PolicyVersion.Increment → StandardStager | iam.mysql / TRANSACTION | IAM自身每实例fanout、QS每实例authz-sync；reload及VersionGuard继续 |
| IAM iam.login_otp_sms | direct_event_publisher；受sms.provider=mq配置控制 | iam.mysql / NORMAL | 条件能力；当前部署记录为aliyun，不制造一条生产MQ迁移 |
| QS questionnaire.changed | eventing/runtime/publisher，direct best_effort | qs.mysql / NORMAL | qs-worker；保持尽力通知 |
| QS assessment_model.changed | eventing/runtime/publisher，direct best_effort | qs.mysql / NORMAL | qs-worker及qs-apiserver-modelcatalog-hot-rank-v1独立订阅 |
| QS answersheet.submitted | answersheet/transactional_durable_store → Mongo原事务 | qs.mongo / TRANSACTION | qs-worker → EnsureAssessment；202只表示答卷已持久化 |
| QS evaluation.requested | evaluation/intake/transactional_outbox及finalizers | qs.mysql / TRANSACTION | qs-worker，原Run/claim/幂等保留 |
| QS evaluation.retry.requested | evaluation/execute及operator/retry_governance StageAt | qs.mysql / 到期TRANSACTION | 原授权/due/attempt/冻结事件保留，dispatcher独占交接 |
| QS evaluation.outcome.committed | evaluation/outcome/commit/committer | qs.mysql / TRANSACTION | qs-worker → 报告；保留Outcome与原业务证据 |
| QS evaluation.failed | evaluation/execute/evaluation_workflows | qs.mysql / TRANSACTION | 即时失败与未来重试意图不同责任 |
| QS interpretation.report.generated | interpretation/automation/execution/committer | qs.mysql / TRANSACTION | 原Report/Generation、统计/状态投影与幂等 |
| QS interpretation.report.failed | 同上 | qs.mysql / TRANSACTION | 失败裁决与未来重试独立保留 |
| QS interpretation.retry.requested | automation/retry_governance及execution StageAt | qs.mysql / 到期TRANSACTION | 原RetryDecision/NextAttemptAt/attempt；不重做未知模型 |
| QS task.opened.reminder.requested | plan/task_persistence.saveOpened | qs.mysql / TRANSACTION | 原task状态/组织/schedule revision；消费者外部提醒幂等 |
| QS task.opened/completed/expired/canceled | Task事件 → direct best_effort | qs.mysql / NORMAL | 保留原Task与Enrollment状态语义 |

QS目录来源为configs/events.yaml；主worker逻辑channel为qs-worker，三个实例原concurrency=48。新的NORMAL/qs.mysql/qs.mongo物理输入仍共享原逻辑订阅预算，不各分配48。IAM和QS授权订阅要使用固定实例身份替代运行时pid生成的新group，同时保留原版本轮询/freshness保护。

IAM授权写入口不止HTTP：application/authz的Role/Resource/PermissionGrant/Assignment与ReplaceManagedAssignments外，还有maintenance的scopemigrate apply/rollback、conditionretire、operationscatalog、rolemodel和accountprovision/reviewer_scope。各入口的版本增量与Stage调用已在证据中逐文件登记，不能只迁HTTP路径。BootstrapStager、MaintenanceStager与受控工具必须具名适配或显式封闭旧写入，不能留下绕过事务准入的活动写者。

## 2. QS ↔ AI 协议

| 逻辑Topic/消息kind | 生产原事务 | 消费订阅 | 保留责任 |
| --- | --- | --- | --- |
| qs.ai.commands.v1：START、CHANGE、PARTICIPANT_RETRY、EVALUATION_START、EVALUATION_CANCEL | QS MySQL stageCommand → qs.mysql | qs-ai.commands.v1 | request/operation、授权、首次Seal、逻辑attempt与模型重试许可 |
| qs.ai.events.v1：COMMAND_RECEIPT、INTERPRETATION_STATE、EVALUATION_STATE | AI MySQL receiver/state_events → ai.mysql | qs-server.ai-events.v1 | 原Inbox/业务decision/sequence/version/artifact/receipt与冻结wire |
| qs.ai.acks.v1：EVENT_ACKNOWLEDGEMENT | QS MySQL receiver → qs.mysql | qs-ai.acks.v1 | QS投影+Inbox+首份业务ACK，AI重复ACK读取与delivered业务语义 |

入口：QS infra/aibridge/messaging_runtime及rocketmq_runtime，mysql/aibridge/messaging_commands、messaging_receiver和messaging；AI bootstrap/messaging、workflow_transport/mq_receiver、mq_relay、state_events及mysql/messaging。

当前Outbox还支撑Operation、Payload和重复ACK查询，必须先建立档案/receipt兼容reader再停止新Outbox写入。大正文沿用mTLS、组织、收件方、hash约束；Prepared正文不公开。原wire不经JSON重建，不重新Seal。

## 3. 退出与保留清单

| 责任 | M3处理 | 验收边界 |
| --- | --- | --- |
| IAM standard可靠发布Store/Relay，QS MySQL/Mongo发布Relay | 新事务路径退出 | 不再扫描新消息才能投递；历史查询保留 |
| QS AI-command/ACK及AI messaging_outbox MQRelay | 新消息退出 | 先拆archive/receipt/operation，不删旧表 |
| AI interpretation_result_outbox与mq_owned历史 | 兼容只读/受控恢复保留 | 不批量迁成新half，不重置attempt/delivered/first-wire |
| QS evaluation/interpretation StageAt | 业务计划保留，替换到期dispatch | due前不发half，同一计划唯一调度owner |
| IAM sessionrevocation.Worker | 保留 | 用户状态与撤销任务属于原业务，非MQ Relay |
| Redis Pub/Sub signals | 保留 | 唤醒不作为业务可靠提交凭证 |
| AI jobs/checkpoints/model_calls/execution_leases | 保留 | response_received可确定性finalize；dispatched/unknown不重调provider |
| QS消费Run/Inbox、hold、RetryDecision、人工/force retry | 保留 | Broker重投与业务重试授权分开 |
| NSQ cb.failed通知/故障审计与旧历史reader | 新运行链路退出，历史记录保留 | RocketMQ最终结算/原生DLQ/精确审计替换；DB存储失败不得假ACK |
| 生产NSQ连接/启动/自动重启 | T32–T35协调退出 | 明确有效订阅与断联历史；不清空未知队列、不删除卷 |
| Mac mini开发NSQ、隔离CI、SDK兼容包 | 本批保留 | 不等同于生产NSQ未退役 |

恢复入口包含QS outboxreplay、retrygovernance与qs-ai-messaging维护工具，AI maintenance/messaging_audit、messaging_handoff、legacy_results、bootstrap/observe_cutover与recover_semantic_contract。它们的读写与授权边界需逐项随接入更新；历史发布恢复不能授权新业务重做。

## 4. 生产前置和交付

QS源码现有105删除assessment_task.entry_token，down明确拒绝。105独立上线与验收后，M3才允许T30进入生产；不能跳过、改写或以105之前的未兼容镜像回退。当前运行schema、容器、部署SHA与数据库身份须届时只读回查。

新的宿主迁移、业务镜像、v2Topic/ACL和SDK稳定发布均尚未执行。切换前保持NSQ业务运行及自动业务CD暂停；新主机拓扑以infra最新迁移记录为参考，不能照抄M1过期serverB IAM落点。

源代码清单覆盖目录、版本写者、Stage/StageAt、核心receiver/relay、调度及恢复入口；真实有效订阅、积压和在途业务由T30/T32的生产盘点另行证明。仅静态清单通过不会把部署或业务验收标为完成。
