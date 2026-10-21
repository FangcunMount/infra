# M3 完整实施规划：业务事务接入、稳定发布与生产切换

本文件是 M3 唯一进度总表，维护已批准规划、任务、证据和交付状态。M2 保持 [24/24](rocketmq-m2-execution.md)，不重复计数。最初状态为 0/36；任务通过实现与验证后才勾选，合并、发布、部署和业务验收分别记账。

## 当前执行快照

- 进度：**16/36**；T01–T16实现与任务必需验证完成，相关源码与infra均已合并。T15完整UTC race7327通过/60项既有可选依赖跳过、完整固定lint零问题；真实Broker/MySQL三档事件各17项、同候选命令各15项均0失败/跳过、清理完整。源码CI28项成功/1项API同步不适用，infra28项全部成功。生产切换未执行。
- 隔离工作区：`/Users/yangshujie/.codex/worktrees/rocketmq-m3/{infra,sdk,iam,qs-server,qs-ai}`，各仓库分支 `codex/rocketmq-m3`；原工作区不改动。
- 源码合并：IAM PR134/135、QS PR409及SDK修复/索引PR46/47已合并；infra PR41已合并d544918f。固定Go修订预发布tx.2已发布并重验；稳定SDK配对发布未执行。生产部署/DDL/Topic/ACL/provider切换未执行；system验收与48小时观察未开始。
- 生产前置：QS MySQL 105（旧 Task entry_token 退役）须独立完成原有保护、恢复及验收。源码开发不受阻；T30 及后续生产任务受此门禁约束，不把 105 上线伪装成本批完成项。
- 运行事实使用执行时的只读核验，不从 main、CI 或部署文档推断生产已升级。
- 当前批次：T17进行中，16/36。维护只读PR177与worker准备只读PR178已合并，双MySQL各4146/4161零失败跳过、12检查均成功且tree一致。ResolveUnknown新真实Broker六档39635351591已核验：精确74f9d35/cbe1d9d每档12宿主/35证据、零失败跳过和完整清理；源PR179与工具PR108其余合并门禁继续追踪。dispatch预算只读PR180本地3125通过、4原生待CI；完整串行SDK dispatch PR181精确764415c通过65目标、3157完整单元及407类型，15原生仅收集待CI。终态/candidate/恢复/维护SDK及统一装配未完成，默认装配关闭，T17不勾选。[证据](evidence/rocketmq-m3-ai-state-20261021.json)。


### T13 分批验证（任务已闭环，13/36）

| 子批次门禁 | 状态 | 可核验证据 |
| --- | --- | --- |
| 冻结计划、原wire与到期核心 | ✅ 源码/目标测试通过 | 9e18668b；72目标+48架构race，全仓7144通过/60既有可选跳过；尚未合并 |
| 原MySQL/Mongo Run与计划共同提交/回滚 | ✅ 隔离三档通过 | c1e6a137；CI39459759364，8.0.36/8.0.44/8.4.11各14项，零失败/跳过，资源清理完整 |
| 自动授权入口与真实到期Broker | ✅ 隔离三档通过 | 源码37896a33/候选55889874；V2新调度与V1旧责任分开，199目标测试通过/5既有可选跳过，7147全仓race通过；CI39462312786三档各31项零失败/跳过，清理完整；observer ACK，不计system或下一业务消费验收 |
| 人工/force原授权根事务 | ✅ 隔离三档通过 | 修正候选3b465b52；CI39471075323每档30项零失败/跳过，初始Assessment夹具插入错误及清理证据保留；无system/生产验收 |
| 自动暂停与显式Aborted dispatch恢复 | ✅ 最终隔离三档通过 | fd985a122/CI39475640759每档41项零失败/跳过，真实lease竞争中止后显式新fence、first wire/selectedAt及旧精确Aborted witness保留；observer仅ACK |
| 旧未来责任交接与Replay/状态边界 | ✅ 最终隔离三档通过 | fd985a122/CI39475640062每档44项零失败/跳过，原根交接/回滚、first wire/due、旧Relay/Replay及状态读取兼容全部通过，完整清理 |


## 1. 目标、基线和授权边界

IAM、qs-server、qs-ai 最终采用 RocketMQ：可靠发布使用事务消息，尽力通知使用 NORMAL，退出适用链路的新发布 Outbox/Relay 和生产 NSQ 依赖。完成口径包括生产切换、合法 system 账号验收及连续 48 小时观察。

| 仓库 | 起始 main SHA | 责任 |
| --- | --- | --- |
| reliable-messaging | `1630aa59d87abf1c69f183be4be7c662a29cae52` | 已有 M2 事务 SDK；预发布运行源码 bfaae2b |
| IAM | `b8e8a9e604074f9850472f2538137e342964fc0c` | 授权事实、策略版本及订阅 |
| qs-server | `f6ee489a88276822069612865f2decf40168afdd` | MySQL/Mongo 业务事务、消费与 AI 对接 |
| qs-ai | `c288eb94c09a8ac930f0ae6b03d62a09147b72fb` | 模型事实、状态、冻结结果及回执 |
| infra | `5ae07289d64ef44a50e79d4d387cc0d13d555cf9` | serverD Docker Broker、资源与生产交付 |

已确认：先完成固定预发布接入验证，再发布稳定 SDK；生产只做一次协调切换，维护窗口目标 30 分钟；IAM 增加可选幂等键和操作查询，兼容旧调用。保持三个 worker 原资源及并发，不迁 Redis、不做 Broker HA 改造或跨云吞吐压测。历史 Outbox 表、NSQ 数据卷和事务证据不在本批物理删除范围。

生产执行前必须先完成候选、恢复演练与固定清单，列明主机、容器、源码/镜像摘要、DDL、资源变更、停写与恢复步骤，再按现有具名批准机制确认。开发授权不替代生产批准文件，测试批准不得用于生产。

## 2. 最终契约

### 消息与持久化责任

| 链路 | 最终机制 | 原子性与保留责任 |
| --- | --- | --- |
| IAM policy version changed | TRANSACTION / iam.mysql | 授权事实、精确版本与全部 witness |
| answersheet.submitted | TRANSACTION / qs.mongo | 答卷、幂等结果、V2 事件证据与 witness |
| 评分请求/结果/失败 | TRANSACTION / qs.mysql | Run、Outcome、失败裁决与消费幂等 |
| 报告生成/失败 | TRANSACTION / qs.mongo | Generation、Report、冻结输入与恢复 |
| Task 开放提醒 | TRANSACTION / qs.mysql | 任务状态、提醒事件与外部提醒幂等 |
| 未来评分/报告重试 | 到期 dispatch 的 TRANSACTION / 各自原 MySQL、Mongo owner | 原授权、due、attempt、冻结事件与唯一调度责任 |
| 问卷/模型目录/Task 尽力通知 | NORMAL | 原 best_effort 语义与独立 fanout |
| QS → AI command | TRANSACTION / qs.mysql | operation、授权、首次 wire 与业务 receipt |
| AI → QS receipt/state | TRANSACTION / ai.mysql | 原 Inbox/状态、业务事实与 witness |
| QS → AI event ACK | TRANSACTION / qs.mysql | Inbox、投影、首次 ACK 与 witness |
| Redis 唤醒/会话撤销/jobs/checkpoints | 原机制 | 不属于待删除的发布 Relay |

发布型 Outbox 退出意味着新业务提交后不再依赖扫描待发布消息才能正常投递。不可变正文档案、回执、幂等、调度、审计及人工恢复继续保存；不能改名后宣称已消除 Outbox。

### 三库公共发送边界

幂等预查 → 持久化完整冻结计划 → 全部分支半消息明确 Prepared → 宿主开启原根事务并首先 Bind guard → 同事务业务/证据/全部 witness → 宿主根提交 → 权威读取确定 Broker 决议。任一半消息失败或 Unknown 不执行业务。

- SDK executor 不重复调用业务；数据库 callback 重入仅允许确定性 DB 操作。ID、时间、签名加密、半消息和外部调用在 callback 外冻结。
- LocalCommitted + FinalUnknown 不表示业务回滚。Checker/中止器/消费重投不授权模型或业务重做。
- 每事务最多 16 分支，超限在业务提交前拒绝，不拆分原子业务。重复请求复用首次完整计划与 wire。
- 新旧证据显式区分版本；旧 Outbox 不冒充 witness。构造/Start 不执行 DDL。
- 新迁移按当前 head 预定 IAM42、QS106/41、AI0041；编号冲突按最新 main 顺延并重新冻结摘要，不改写旧迁移。

### IAM

授权写入口拆成只读 planner 与原事务 executor，冻结 expected/target policy version 和事件。根事务重校验权限与业务条件，CAS 更新策略版本，提交业务及 witness。覆盖角色、资源、Grant、Assignment、受管替换及维护入口；无实际变更不制造版本事件。冲突明确中止并返回冲突，不自动重跑。保留 post-commit Runtime reload、版本轮询与 freshness。

可选 Idempotency-Key 按主体、组织/全局 scope、操作类型隔离；同键同输入读取原操作，不同输入 409。无键分配操作 ID，不承诺跨请求去重。响应附操作引用；GET /api/v4/authz/operations/:operation_id 按当前身份、scope 和原操作权限保护，输出业务结果/策略版本/三阶段状态，不输出 wire/token/密钥。未知提交不误报失败回滚；调用方查询或复用原键，不盲换键重试。IAM 自订阅与 QS 订阅分别证明收敛。

### QS 领域与调度

Mongo CreateDurably 替换 Outbox Stage，答卷/幂等/V2 证据/witness 共同提交；202 只表示已证明业务持久化，提交未知精确读取恢复。评分/报告/提醒保留原提交器、CAS、claim、失败裁决与幂等。best_effort 使用最终 NORMAL，目录与 worker 独立订阅保留。

原事务保存 RetryDecision、NextAttemptAt、attempt、授权及冻结事件。到期 dispatcher 准备半消息后，以原事务 CAS 写 dispatch 事实和 witness；MQ 故障不增加业务 attempt、不提前到期或重执行。旧/新调度精确交接，不把长期 Unknown 半消息当定时器；旧 Replay 不接管新事务事件。

### QS ↔ AI

先拆旧 Outbox 的 immutable archive、operation/Inbox/receipt、SDK 协议状态。QS command 首份 Seal 和身份在事务外冻结，重复读取首次档案。接收 AI 事件先准备业务 ACK 半消息，再原事务提交 Inbox/投影/首份 ACK/witness，提交前不确认原 delivery；重复事件复用 ACK。正文沿用 mTLS/tenant/recipient/hash 校验，Prepared 正文不可公开。

AI StateEventRecorder 拆成 frozen plan builder 与原事务写入；EventSession.commit 不执行 MQ I/O，BorrowedTransactions 根提交仍属接收器。分别改造 command receipt、interpretation/evaluation state、event ACK。已持久化模型 response/checkpoint 用于确定性 finalization，MQ 故障不增加 invocation；dispatched/unknown 保留 provider_result_unknown，问题 ID/sequence/artifact/密文/版本预冻结并在事务内复核。历史 result_outbox/mq_owned/attempt/first-wire/delivered/receipt 保留兼容读取，新消息退出旧 MQRelay 扫描。

### 路由、预算和生命周期

v2 route_revision=m3-1，四 owner 使用精确 DB/账号/Topic 绑定；NORMAL 与 TRANSACTION 分 Topic，不原地改类型。同逻辑订阅共享预算，不放大原 worker 并发。空闲 producer 同样 Start 完整 owner Checker。writer epoch 随写协议冻结，不随镜像重启自动变更。

| 宿主 owner | 发送 | Checker worker/queue | 每 5 秒维护上限 |
| --- | --- | --- | --- |
| IAM iam.mysql | 8 | 4/32 | 100 |
| QS qs.mysql | 4 | 2/16 | 50（同进程双 owner） |
| QS qs.mongo | 4 | 2/16 | 50（同进程双 owner） |
| AI ai.mysql | 4 | 1/16 | 100 |

只启动进程真实拥有的 owner；DB 回查 2s、RPC 5s、lease60s，不扩大宿主 DB pool/业务配额。关闭先封准入、等真实业务、保持 Checker、排空回查/客户端，最后宿主 DB/loop；ShutdownIncomplete 保留真实未完成容量。

## 3. 里程碑与任务

| 里程碑 | 内容 | 任务 | 状态 | 完成门禁 |
| --- | --- | --- | --- | --- |
| M3-P | 基线、清单与接入基础 | T01–T04 | ✅ 已完成 | 责任、迁移契约、实现验证与合并 |
| M3-1 | IAM | T05–T08 | ✅ 已完成 | 原事务、幂等与双订阅 |
| M3-2 | QS 领域及调度 | T09–T13 | ✅ 已完成 | 双存储及未来授权/到期dispatch/责任交接验证通过，相关源码和infra已合并；生产另行切换 |
| M3-3 | QS↔AI | T14–T20 | ☐ 进行中 | 档案、回执、安全、模型恢复 |
| M3-4 | 故障与运维 | T21–T25 | ☐ 待开始 | 真实故障及切换工具 |
| M3-5 | 稳定发布及候选 | T26–T29 | ☐ 待开始 | 正式制品及最终镜像演练 |
| M3-6 | 生产切换 | T30–T33 | ☐ 待开始 | 105 前置、实际部署及 system 验收 |
| M3-7 | 观察与退役 | T34–T36 | ☐ 待开始 | 48h 观察及责任退出 |

| 完成 | ID | 任务及验收结果 | 状态/证据 |
| --- | --- | --- | --- |
| ✅ | T01 | 执行总表、独立工作区、完整 SHA 基线、证据格式及 PR 台账 | 2026-10-19；实现8e5c9a9；[基线与36项/8里程碑验证](evidence/rocketmq-m3-baseline-20261019.json)；[PR37](https://github.com/FangcunMount/infra/pull/37)已合并878c130 |
| ✅ | T02 | 全部生产者/消费者/订阅/Outbox/调度/恢复清单及105前置 | 2026-10-19；[责任清单](rocketmq-m3-inventory.md)/[源码核验](evidence/rocketmq-m3-inventory-20261019.json)：17目录事件、9协议kind、39文件、IAM12版本调用文件、QS8 Stage文件；生产盘点另属T30/T32 |
| ✅ | T03 | 三库预发布依赖、显式配置、owner、准入、预算、生命周期基础 | 2026-10-19；[源码/依赖/审计/验证](evidence/rocketmq-m3-foundation-20261019.json)；初版IAM e50686c7 / QS98645d817 / AI81db026；race63/56、AI45通过；PR130/407/158已合并；最终CI/合并见T04证据；真实依赖另属T22/T23 |
| ✅ | T04 | 宿主迁移、索引、档案、V2业务证据与兼容/安装边界 | 2026-10-19；[完整证据与全部失败历史](evidence/rocketmq-m3-storage-20261019.json)；IAM78b5495c三档原生+独立并发通过，QS2936bd512当头原生档案/双库步骤通过，AI10687a1两档各205定向与3101完整用例0跳过；四库PR均合并，三库最终完整CI通过；生产未切换 |
| ✅ | T05 | IAM 所有授权写入口 planner 与精确版本/业务 CAS | 2026-10-19；[完整证据](evidence/rocketmq-m3-iam-planning-20261019.json)；ea95cd9e全CI及三档MySQL每档7项0跳过、独立并发通过；[PR131](https://github.com/FangcunMount/iam/pull/131)合并c2aa3635；实际Sender装配属T06 |
| ✅ | T06 | IAM 原 GORM 事务业务/版本/witness 原子提交 | 2026-10-20；89bdcf58三档MySQL每档12具名项、共36项0跳过；Mac mini隔离RocketMQ5.5.1/MySQL8.0.44完整21项0失败0跳过，含实际IAM宿主4项证明，临时资源已清理；[完整证据](evidence/rocketmq-m3-iam-transactions-20261019.json)；[PR132](https://github.com/FangcunMount/iam/pull/132)合并7accc92c，生产未变更 |
| ✅ | T07 | IAM 幂等键/操作查询，重复/冲突/越权/未知验证 | 2026-10-20；57b07bab正式Go SDKtx.2；必需三档MySQL原事务/HTTP各34项，真实Broker各21项，全部0失败/跳过；PR134合并d53c36a9；[证据](evidence/rocketmq-m3-iam-operations-20261020.json) |
| ✅ | T08 | IAM 自身与 QS 订阅、乱序和 freshness 回归 | 2026-10-20；IAM51405831/QS696ee314锁定正式Go SDKtx.2；三档MySQL原事务各34项、成对Broker/fanout各22项0失败/跳过，Mac mini额外22项通过；IAM PR135合并e3efa5b3、QS PR409合并2e95630b；[证据](evidence/rocketmq-m3-iam-fanout-20261020.json) |
| ☑ | T09 | QS Mongo 答卷，202/幂等/callback/未知提交 | 已完成实现与验证；原事务/冻结BSON与wire、V2精确读取、实际Collection/gRPC 202和503、并发原赢家、Mongo failpoint重入、ACK客户端丢弃及新实例读取16项在Mac mini和GitHub实际通过。最终源码deb46e67全仓race6909通过/60既有可选依赖跳过，同包策略与87项文档检查通过；PR410合并3afc76a6，PR411/infra46最终头CI和合并单列；不表示生产或system验收。[证据](evidence/rocketmq-m3-qs-answer-20261020.json) |
| ✅ | T10 | QS 评分请求、结果和失败，Run 与幂等 | 2026-10-20；5a1f489bb完整CI28成功/1不适用，完整UTC race6977通过；双档原生Broker各9项0失败/跳过/race。保留Run claim、首次wire、未来原due/授权及原调度职责（T13再交接）。[证据/失败历史](evidence/rocketmq-m3-qs-evaluation-20261020.json)；PR412合并db9b4918、infra49合并a4547f83；生产未变更 |
| ✅ | T11 | QS 报告生成及失败，冻结输入和终态恢复 | 2026-10-20；qs.mongo原事务/共享owner、首次BSON与wire、Run原claim CAS、V2权威审计、只读恢复及显式无DDL装配。最终f8566a830真实Broker/Mongo14项0失败/跳过，完整race7050通过；QS PR414合并20c29ba8（28成功/1不适用），infra PR52合并7b83e264（14成功）。[证据与全部失败历史](evidence/rocketmq-m3-qs-report-20261020.json)。生产未变更 |
| ✅ | T12 | QS 提醒事务、最终 NORMAL 与 fanout | 2026-10-20；冻结首次入口/wire、原pending/revision CAS+witness、归属原根再校验、关闭新提醒仍保留旧执行恢复。最终f37afca0/infra c27ef043双档各15项0失败/跳过，source race7087通过/60既有可选跳过；QS PR415/416及infra54/57全部合并，最终CI分别28成功/1不适用与9成功。[全部证据/失败历史](evidence/rocketmq-m3-qs-task-20261020.json)。生产未变更 |
| ✅ | T13 | 到期 dispatcher、重试授权、交接和 Replay 边界 | 2026-10-21；最终7e8aba25/fd985a122全仓race7198通过/60既有可选跳过、固定lint零问题；原库三档各44项、真实Broker三档各41项均0失败/跳过/无race且清理完整。QS当前头28项CI成功/1API同步不适用，PR417合并133fc073；infra22项CI全部成功，PR61合并d4324a87。[完整证据与失败历史](evidence/rocketmq-m3-qs-retry-20261021.json)。生产未变更 |
| ✅ | T14 | QS command/档案，Operation/Payload新旧兼容 | 2026-10-21；冻结首次wire/输入、原SQL事实/operation/档案/witness、序号CAS与真实前序receipt门禁；实际Participant的Pending查询和原请求复用保留当前权限及资源绑定，计划不冒充已接受业务。最终3dd33af4f完整race7290通过/60既有可选跳过、完整lint零问题，三档Broker/MySQL各15项零失败/跳过并完整清理；QS CI28成功/1不适用，PR418合并0ed41ea5；infra25项CI成功，PR68合并53d18bb5。[全部证据/失败历史](evidence/rocketmq-m3-qs-ai-command-20261021.json)。生产未变更 |
| ✅ | T15 | QS AI事件 Inbox/投影/首次ACK/witness原子提交 | 2026-10-21；最终762c2db0d完整race7327通过/60既有可选跳过、完整固定lint零问题；事件三档各17项、同候选命令三档各15项均0失败/跳过/无race，清理完整。QS PR419当前头CI28成功/1项API同步不适用，合并be22b927；infra PR72当前头28项全部成功，合并db183399f。[全部证据/失败历史](evidence/rocketmq-m3-qs-ai-event-20261021.json)。生产未变更 |
| ✅ | T16 | AI command admission/receipt 原事务与根提交归属 | 2026-10-21；AI9485f28完整两档各3531项零失败/跳过、14项检查成功；已发布Python SDK0.4.0a1/client5.1.2与Broker5.5.1六档每档15项协议检查/8项实际宿主用例通过、清理完整。AI PR159合并e8392c05；infra PR83当前头37项成功、合并b770ed68。[全部证据/失败历史](evidence/rocketmq-m3-ai-admission-20261021.json)。受控QS输入/observer，不计成对业务、真实模型或生产验收 |
| ☐ | T17 | AI interpretation/evaluation计划冻结，退出commit hook编排 | 进行中；原ResolveUnknown源码已合并，两档各4136、4只读/12原根与入口通过，旧超时与同源重验保留。新Broker12/35档、维护/串行准备/dispatch与其余状态、统一装配待闭环；默认装配未启用。[证据](evidence/rocketmq-m3-ai-state-20261021.json) |
| ☐ | T18 | AI确定性finalization，故障不增加模型调用 | 待开始 |
| ☐ | T19 | AI历史reader/RPC/诊断/恢复兼容，退出新消息Relay | 待开始 |
| ☐ | T20 | 成对契约、安全、wire、receipt/ACK重复与取消 | 待开始 |
| ☐ | T21 | infra生产v2 manifest、ACL、TLS与冲突拒绝 | 待开始 |
| ☐ | T22 | 宿主真实生命周期、跨实例Checker与资源上界 | 待开始 |
| ☐ | T23 | 宿主端到端及真实网络/进程/DB/Broker故障 | 待开始 |
| ☐ | T24 | 指标、告警、准入保护、DLQ/超限审计与规程 | 待开始 |
| ☐ | T25 | 切换工具、排空、调度交接与回退/前向恢复演练 | 待开始 |
| ☐ | T26 | 预发布三库完整CI/API评审/混合链路，稳定协议冻结 | 待开始 |
| ☐ | T27 | 同SDK SHA的稳定Go/Python发布、摘要/锁/receipt | 待开始 |
| ☐ | T28 | 三库正式稳定制品重装及完整非空零跳过门禁 | 待开始 |
| ☐ | T29 | 最终镜像/配置摘要及恢复启动/30分钟切换演练 | 待开始 |
| ☐ | T30 | 105前置、真实库/运行基线及具名生产清单 | 待开始；生产前置未核验 |
| ☐ | T31 | 回读生产v2资源/配置与Mac mini告警，保持封准入 | 待开始 |
| ☐ | T32 | 排空、交接、同窗口保护及显式离线迁移 | 待开始 |
| ☐ | T33 | 最终镜像/Checker/消费者/system验收及恢复准入 | 待开始 |
| ☐ | T34 | 连续48小时业务/回执/积压/资源观察 | 待开始 |
| ☐ | T35 | 生产NSQ及自动重启/活动连接责任退出，保留数据 | 待开始 |
| ☐ | T36 | 依赖/文档审计、合并收尾、发布索引及36项闭环 | 待开始 |

依赖：T01→T02→T03→T04→IAM→QS→成对QS/AI→运维故障→稳定SDK/最终候选→生产→观察退役。按表推进，前一接入批次通过其门禁后才进入下一批；源码开发不要求先执行生产105。

## 4. 验证、发布与生产流程

### 验收矩阵

| 类别 | 必须证明 |
| --- | --- |
| 原事务 | GORM、MySQL、Mongo、SQLAlchemy业务+witness原子；错误连接/失效事务/savepoint拒绝 |
| 幂等冻结 | 单一有效执行、输入冲突、首次ID/时间/密文/wire复用、CAS冲突 |
| 业务 | 授权双订阅、答卷→评分→报告、提醒、自动/人工/暂停重试、AI command→receipt→state→ACK |
| 真实故障 | half/final丢回复、DB提交前后断网、部分分支、SIGKILL、新实例回查、Broker重启 |
| AI | main c321a694 | [PR158](https://github.com/FangcunMount/qs-ai/pull/158)已合并；[完整CI](https://github.com/FangcunMount/qs-ai/actions/runs/39254547832)/[M7](https://github.com/FangcunMount/qs-ai/actions/runs/39254547837)通过 | 自动生产部署false，M3未切换 |
| 生命周期 | 关闭准入、真实在途、队列/锁等待、关闭超时/重复关闭/客户端隔离 |
| 安全 | owner/类型/ACL/查询越权拒绝，Prepared正文不可读 |
| 兼容恢复 | 旧档案、非空记录、未来计划精确交接，unknown不重置 |
| 资源 | 原三worker配置不变，逻辑预算不放大，D可用内存≥512MiB，无OOM/非预期重启 |

使用隔离Compose/回环端口/临时DB/独立进程，required缺依赖失败，报告非空、0失败、0跳过。沿用M2 Broker/客户端与存储矩阵，另外绑定宿主真实版本；SDK探针不代替宿主验收。

预定稳定Go v0.5.0、Python0.4.0/tag python/v0.4.0；发布前确认未占用，若占用递增patch，不覆盖。三库先用固定预发布验收；必要SDK修复单独评审，不无故改M2 codec/指纹/schema。两个稳定tag绑定同一合并SHA，完整CI、wheel/sdist、摘要、锁和receipt通过后发GitHub正式Release，不新增PyPI。三库用正式模块/wheel重新构建验收，不用replace/editable或工作区导入。

指标：三阶段/Checker/队列/DB错误/维护/未决增龄/消费积压/业务receipt，不带高基数身份或正文。未决>120s告警；>300s、回查饱和120s或原生超限封对应owner新准入但保留Checker；绑定/权限/证据矛盾立即拒绝并告警。恢复需明确核验，不自动fallback。Broker实际回查参数及48h保留先不改；回读并实证有限窗口，配置乘积不是SLA；不足则阻断并单独评审。监控仍在Mac mini，不在D加常驻代理。

### 协调生产切换

窗口前105独立验收，候选/恢复/启动/30分钟演练通过。CD继续暂停，固定镜像/工具/manifest/配置/凭据权限及具名批准。提前封长任务新准入，让AI/外部调用自然收敛，不强杀模型任务赶时间。

窗口内：先封新写（IAM留登录鉴权读取），旧已接受工作继续收敛；核对有效NSQ内存/磁盘depth、inflight、deferred及到期Outbox/receipt，旧消息只沿原NSQ排空。未来计划保留原身份/授权/due，证明旧调度退出。再停相关旧写者/自主任务，完成同窗口保护与批准的离线DDL；QS遵循现有双库身份/保护/恢复协议。启动消费者与Checker、保持外部封准入；合法system登录验收核对DB/witness/消费/receipt后恢复准入。无会话时用户正常登录配合，不用探针/替代身份冒充。

首个新runtime启动前按批准范围恢复；发出第一个启动命令后，即使未ready也不能旧全库备份覆盖。provider回退独立判断：无新责任，或half已全部处置且无新业务提交，才可用已验证schema兼容的NSQ回退候选。已Committed/有消费效果/无法排除提交则向前恢复，不翻开关、换ID或重调模型。

连续48h观察，低流量补充有界system验收。观察期旧生产/消费责任退出，可停NSQ并保留恢复材料；通过后关闭自动重启/部署入口/活动连接/旧Relay。Mac mini开发NSQ与测试/SDK兼容包不在生产退役范围。历史表/卷/wire/备份按原保留政策，不自动删除，未决责任不得GC。

## 5. 进度和证据规则

每完成任务，先保存实现与必需验证证据，再更新勾选、完成时间、源码SHA、CI/报告/PR状态，并在会话报告本次项/总进度/阻塞/下一项。状态：待开始、进行中、验证失败、受阻、已完成。任务勾选不表示已合并或生产上线；里程碑要求所属任务、PR合并和门禁全部通过。新增/拆分任务显式调整分母，保留失败历史。

证据JSON格式：format_version、task_ids、observed_at、repository/source_sha、命令与exit/status、测试passed/failed/skipped、dependency versions/digests、报告/CI/PR链接、清理结果、边界声明。原始敏感材料仅放私有0600位置，不提交正文/凭据。报告区分pure/source/integration/fault/published-installation/production/business/observation。

验证命令按任务实际记录，不把参考命令写成已执行：基础检查 `git diff --check`；Go目标package及race；Python目标pytest/type/lint；infra离线脚本单测；required真实依赖门禁另行记录。T01验证进度表36个唯一任务ID、勾选计数、8个里程碑分区、基线与工作区branch/clean state。

M3完成要求36项实现验证、源码合并、稳定SDK与固定生产镜像、适用新发布退出Outbox、生产NSQ退出、system验收和连续48h观察全部通过，并保留历史读取/恢复窗口/回退限制/未结责任记录。

### PR / 发布 / 部署台账

| 对象 | 分支/制品 | PR/合并 | 发布/部署/验收 |
| --- | --- | --- | --- |
| infra | codex/rocketmq-m3 | [PR37](https://github.com/FangcunMount/infra/pull/37)已合并878c130；进度后续PR单列 | M3生产变更未执行 |
| SDK | codex/rocketmq-m3 | 无M3变更 | 仍为M2固定预发布 |
| IAM | main c0acb432；T05 codex/rocketmq-m3-iam | [PR130](https://github.com/FangcunMount/iam/pull/130)已合并；[最终CI](https://github.com/FangcunMount/iam/actions/runs/39255584214)/[独立并发](https://github.com/FangcunMount/iam/actions/runs/39255584248)通过 | 生产CD保持暂停，M3未切换 |
| QS | main9ebf2d6c | [PR407](https://github.com/FangcunMount/qs-server/pull/407)已合并；[最终CI](https://github.com/FangcunMount/qs-server/actions/runs/39255581089)通过 | 生产CD保持暂停，M3未切换 |
| AI | main c321a694 | [PR158](https://github.com/FangcunMount/qs-ai/pull/158)已合并；[完整CI](https://github.com/FangcunMount/qs-ai/actions/runs/39254547832)/[M7](https://github.com/FangcunMount/qs-ai/actions/runs/39254547837)通过 | 自动生产部署false，M3未切换 |

### 执行记录

- 2026-10-19：批准M3完整规划；已从各仓库origin/main建立五个独立工作区。首次状态0/36，生产前置105独立处理，尚未核验完成。
- 2026-10-19：T01完成。提交8e5c9a9建立完整规划、五库SHA/工作区与证据格式；36个连续唯一任务、8个里程碑、5个隔离分支及diff检查通过；进度1/36，尚未合并或生产变更。
- 2026-10-19：T02完成，进度2/36。全目录与协议kind覆盖核对、39个源码文件摘要及版本/Stage调用扫描通过；IAM维护工具的写入口已显式纳入，sessionrevocation、业务调度、AI未知调用治理继续保留。T03窄基线：IAM授权/原UOW及options通过，QS options/答卷/证据通过，AI29项通过。初次uv因PATH缺失exit127，改用已安装的绝对路径后成功；不隐去该工具失败，不据此声称真实依赖故障或生产验收已通过。
- 2026-10-19：T03源码基础完成，进度3/36。三库固定M2预发布；显式owner/store/epoch/v2/预算与无网络、无DB查询的构造通过。宿主准入与SDK最终关闭分开，暂停保留Checker，ShutdownIncomplete继续Wait；旧Relay装配拒绝事务配置。IAM63/QS56目标race节点、AI42项均0失败0跳过，QS679回归通过，IAM96通过/1既有MySQL依赖跳过；后者不计为原事务证明。Go vet、Python lint/type和文档门禁通过；SDK失败交接重审与失败历史留证。PR130/407/158草稿已提交，合并/真实Broker验证/生产仍未完成。本机Docker未运行，不启动已有依赖；后续真实存储用隔离CI。
- 2026-10-19：T03自审补充81db026，关闭预算为负数/NaN/无穷时在封准入之前拒绝，AI最新45项0失败0跳过；初次42项证据保留历史。infra PR37建立，全部PR仍草稿，仓库CI排队/运行中，未创建稳定tag或生产变更。

- 2026-10-19：T04第一批已提交三库独立schema、QS V2引用及原生安装/原事务兼容测试。IAM完整CI及MySQL8.0.36/8.0.44/8.4通过；QS离线105/40→106/41升级和双库原事务证明通过；AI修复0041探针与测试库反射、head白名单边界后，两档MySQL原生证明通过，完整CI重跑。源码验证QS230 race无跳过、AI58定向无跳过；IAM广回归18个既有可选DB用例、AI旧控制4个DB用例本地跳过，不计真实依赖通过。全部失败及修复保留于[本批证据](evidence/rocketmq-m3-storage-20261019.json)。不可变档案/兼容读取尚未完成，T04不勾选，总进度保持3/36；源码未合并，生产无操作。

- 2026-10-19：交付前发现三库main已并行合入公网MySQL TLS（IAM bf2882e9 / QS39cb018d9 / AI8fc9c09）。在M3分支合并这些已提交变化，保留TLS factory/维护入口和M3元数据、当前0041校验。未改其他工作区。合并后Go定向测试、AI63项TLS/配置/消息/文档与静态/type门禁通过；三库完整CI重新触发。原候选IAM/QS全CI、AI两档M7（含原生2项及历史回执/模型回归）通过只归属其原SHA，不冒充合并后结果；最新证据与PR台账已更新。总数仍3/36，T04进行中，未合并M3到main、未部署生产。

- 2026-10-19：T04第二批提交QS f008cc732 / AI9b84e89，不可变原header/body/first-wire codec、共享uint64向量、原事务档案guard、精确committed证据读取及仅身份缺失时的旧reader回落。QS3包race/架构、AI45项0失败0跳过及全库type/lint通过；新增原生档案测试仅编译/收集，本地未运行DB。同步main后的IAM/QS完整CI通过；AI完整CI暴露0041旧handoff/inventory whitelist及历史/current fixture scope失败，已限定范围修复，保留旧全库转换/备份拒绝。隔离原生/全CI正在新候选上验证，T04仍不勾选，总计3/36；没有生产DDL/业务链路切换。

- 2026-10-19：T04档案验收推进：AI10687a1的两档MySQL各205项（3原生schema/archive＋119 source regression＋83原事务/交接/模型恢复），均0FAIL/ERROR/SKIP并完成wheel/sdist构建；QS c5683c7df原生M3档案/双库步骤通过，最终2936bd512仅移除lint发现的无效赋值并绑定文档，固定lint0问题、87 docs门禁通过。IAM主CI已通过，但独立并发工作流status仍拒绝正确42，已提交78b5495c精确表清单修复和拒绝测试，等待原生重跑。只读回读确认IAM/QS生产CD暂停、AI自动部署false；未改变量。全部历史失败/候选保持来源；总计仍3/36，T04等最终必需门禁后打勾。

- 2026-10-19：T04完成，总进度4/36。三库schema、双库原事务、不可变档案、精确committed读取、Prepared/损坏拒绝及旧reader兼容必需验证通过；AI全3101项/每MySQL版本0跳过，IAM当头三档原生与独立并发全部通过，QS当头M3原生步骤通过。T04候选固定供最终全CI/PR合并；M3-P不提前标完成。进入T05独立工作区，仅推进IAM源码与隔离测试，不触碰生产。

- 2026-10-19：M3-P完成。最终三库全部PR门禁通过，精确head合并IAM PR130→c0acb432、QS PR407→9ebf2d6c、AI PR158→c321a694、infra PR37→878c130。合并前后只读确认生产CD暂停/自动部署false，未发布稳定SDK或执行生产M3。infra同步已由其他工作流合入的MySQL TLS工具/CA，逐文件保留该main内容；不改写其交付证据。T05在独立iam-business工作区基于c0acb432继续；当前4/36，新增冻结计划/原事件复用/CAS基础与真实并发测试尚待完整任务验收。

- 2026-10-19：T05持续推进，总进度4/36。冻结计划、精确权限版本、物理只读规划及根事务CAS在2fb64753完整CI/三档MySQL与独立并发通过。56012bf9增加Grant/Assignment规划、原名称身份、跨公司保留及授权后no-op；目标race69通过，3项既有可选本地MySQL跳过不计原生证明。新候选PR131 CI运行中，维护工具入口仍待实现；Sender原事务整合另属T06。全部故障/修复分候选保留，不提前勾选。

- 2026-10-19：T05完成，总进度5/36。IAM ea95cd9e完整CI39265370007及独立并发39265370036通过；三档MySQL各7个具名原生用例（schema、精确CAS/物理只读、5类维护规划）0失败0跳过，保留日志摘要。PR131按精确head合并c2aa3635；合并前只读确认PRODUCTION_DEPLOY_PAUSED=true。T06转入独立分支推进原根事务/半消息证据/精确事件/witness和取消后回调记账，不提前标记业务上线。

- 2026-10-19：T06推进，保持5/36。7730207d原根事务、半消息/事件门禁、回滚和单次执行在三档MySQL通过，完整CI、独立并发和SDK隔离通过；保留d7e5ce77夹具参数绑定失败。0bd208a2补冻结本地资料、原wire保留、业务/维护ID分配、原事务审计时钟和有界规划准入，177个目标source race通过，9项既有本地DB跳过不计验收；最新原生候选验证中。platform/维护CLI装配及完整业务状态仍未完成；PR132保持草稿，不打勾。

- 2026-10-19：T06继续，进度5/36。0bd208a2完整CI39270215122、三档MySQL（含实际宿主应用入口和冻结ORM）、并发39270214607与SDK隔离39270214851通过。feb0369c新增platform/维护CLI显式事务目录与owner生命周期；本地race、lint、vet、docs通过。infra新增仅隔离Compose内运行的实际IAM Broker验收，生成独立账号/Topic/Group并锁源码SHA，不接受生产端点；即将由CI验证，不把存储半消息fixture冒充真实Broker。T06未勾选，源码未合并，生产无操作。

- 2026-10-19：T06继续，保持5/36。feb0369c完整CI39276085368、并发39276085627及SDK隔离39276085506成功。infra dd0be29实际IAM Broker矩阵39277154976的3个job均无step启动，GitHub annotation提示账户支付失败或spending limit；不是测试执行失败或通过，不重复重跑空作业。已请求恢复Actions额度；继续本地代码/验证，不跳过原生与真实Broker门禁。
- 2026-10-19：T06补显式宿主发布协议门禁，新增IAM迁移43（42保持不变），默认保留outbox，不自动切换。原事务共享锁约束新版旧Stager/事务写者；旧二进制仍须在T32退出。同步接入启动失败、独立退出预算、drain先封准入及事务owner readiness；本地补充MySQL9.3临时实例验证不替代固定8.0/8.4 Compose矩阵。源码基线已整合main403d41c2的既有Redis交付提交，不属于M3新增Redis操作。

- 2026-10-19：T06候选固定为733c2dc2，已推送PR132并更新描述。全仓source race1898通过/0失败/31项既有环境用例跳过；425项定向source race通过/5跳过；额外隔离MySQL9.3包含完整迁移链15项通过/0跳过，绑定精确SHA、私有日志摘要及清理回执。该额外版本不能替代规定的8.0/8.4 Compose或实际Broker门禁，故保持5/36，不合并草稿、不切生产。infra真实宿主workflow已锁定新候选；账户门禁历史保留，最新CI状态分别回读。

- 2026-10-19：T06最终当前候选89bdcf58补五类维护原根事务测试；额外MySQL9.3在干净源码上20项通过/0失败/0跳过并清理，integration-tag lint与五包race通过。新增required CI具名验证，保留夹具导入别名编译失败历史。Broker矩阵指向同一候选，T06仍不勾选。等待正式门禁期间在独立stacked工作区推进同一IAM批次T07；M3-2/QS仍等待IAM门禁，不扩展生产授权。

- 2026-10-20：T07候选基础723f171a已推送PR134，进度保持5/36。完整source race1903通过/0失败/31既有环境跳过；额外隔离MySQL9.3干净源码27项0失败0跳过，包含8并发赢家、结果共同提交/回滚、资格不可重用、过期与在途竞争、错误绑定/损坏证据。新增IAM44，未改写42/43。Schema/模型/存储不等于公开幂等API或SDK联合装配完成，T07不勾选。
- 2026-10-20：回读T06前候选733c2dc2完整CI39280693975及独立并发39280695177、SDK隔离39280694020、镜像交接39280693944均成功；最新89bdcf58还须单独等待完整结果。infra728f9e1的真实Broker矩阵39282025800，8.4 job118158047787无step并再次明确报告GitHub支付/额度限制，其余当时排队；历史阻塞仍未被测试通过替代。

- 2026-10-20：回读89bdcf58完整CI39281936066、并发39281935978、SDK隔离39281936049、镜像交接39281935906全部通过；下载三档MySQL具名测试日志，每档12项，共36通过/0失败/0跳过，摘要归档。仍不把存储半消息fixture当作真实Broker。只读核对mac-mini-old Docker与资源后，使用f86247d infra、89bdcf58 IAM、bfaae2b SDK建立临时独立Compose验收；首次拉镜像遇非交互PATH缺credential helper，修正并选择已核对8.0.44本地镜像后在执行。现有服务保持运行；真实验收未结束，不打勾，保持5/36。

- 2026-10-20：T07候选3fc8b406已推送PR134，进度5/36。新增HTTP可选键/操作引用/受保护查询、类型化结果与SDK/业务双guard装配、原事务no-op、查询真实在途关闭及总扫描预算50+50。全仓race1925通过/31既有可选跳过，API/Swagger/Gin一致、Spectral原110条基线未增加，lint/docs通过；干净候选额外MySQL9.3为29项0失败0跳过，临时数据已清理。新增HTTP+MySQL联合用例继续本地验证，不计作system或Broker验收。
- 2026-10-20：用户明确“暂不处理，继续离线实现”，infra Actions账单门禁暂缓；此后不为账单重跑云端CI，新增源码/进度先保留本地提交。Mac mini第一轮实际Broker验收基础18项通过、IAM宿主用例失败，整轮失败且临时容器/探针/数据已清理。保留失败回执和摘要，新增固定脱敏诊断及显式0700目录/0600本地日志捕获后第二轮在执行；不以18项基础通过勾选T06。

- 2026-10-20：T06实现及验证完成，打勾并更新总进度6/36。IAM89bdcf58在隔离Docker RocketMQ5.5.1/MySQL8.0.44最终21项0失败0跳过，含真实宿主半消息不可见、原根事务/wire/witness、RoleCatalog入口、回滚无消息/事实四项；报告保存镜像ID、固定客户端、实际参数、源码和清理回执。既有三档MySQL源码门禁共36项0跳过，构成独立存储与真实Broker证据；第一轮失败未删除或冒称业务缺陷已定位。PR132合并、infra云端CI、生产及system仍分别待完成，M3-1里程碑未完成。

- 2026-10-20：用户将infra改为public；只读核实PUBLIC后恢复推送与云端门禁。infra57f1c98的新CI已实际运行，serverA/监控/Prometheus配置检查通过，IAM矩阵39321850663运行中；旧账单失败历史保留，不继续视作当前阻塞。当前IAM98d0af8d包含业务结果原子凭证真实Broker断言；离线fd8dd30f在8.0.36/8.0.44各34项0失败0跳过，98d0af8d在8.4.11同为34项0失败0跳过，私有临时项目及在途进程已清理、既有11容器未变。云端门禁固定同一98d0af8d并显式要求业务结果证明；T07继续待完整结果，不提前打勾。
- 2026-10-20：T06 PR132按精确89bdcf58源码、全绿检查及既有真实Broker证明完成合并，merge7accc92c；合并前回读PRODUCTION_DEPLOY_PAUSED=true且最新main403d41c2已在候选历史中。进度仍6/36，合并与生产独立，M3-1等待T07/T08及相应合并门禁。

- 2026-10-20：infra public后39322133359真实执行，账单门禁已恢复。IAM98d0af8d完整CI、并发、SDK兼容与镜像构建通过；required MySQL8.0.36/8.0.44/8.4原事务及HTTP各34项全部通过。Broker8.0.36为21项通过，另外两档在宿主测试出现失败但已输出业务receipt；尚未定位原因，T07标验证失败且进度保持6/36。新增仅文件名/行号的race脱敏诊断，并在Mac mini固定98d0af8d/8.4临时独立项目复现；T08双实例及QS乱序通知/freshness回归已本地通过，真实fanout与任务门禁仍待完成。

- 2026-10-20：诊断矩阵39324475047三档均复现Go driver metric.go:321/338指标回写与ACK hook并发race，所有失败保留。独立SDK工作区补确定性回归：修复前3条race并失败，atomic meter pointer修复后通过，真实TLS400次ACK/连续metric-off回写通过，make check通过；待单独PR/固定Go修订制品及宿主重验，T07不勾选。T08新增IAM PR135、QS PR409；IAM source race1926通过/31既有可选跳过，QS目标85项通过，87项文档自测及facts通过。首次本地全仓源测试umask077改变既有权限夹具而失败，正常umask022复验通过，未改写该既有业务。Mac mini T08实际夹具发现writer缺声明身份resolver，修正为生产同样的ApplicationUnitOfWork(resolver)装配；当前仍未获得fanout通过证据，进度6/36。

- 2026-10-20：SDK独立修复8fb6fc57创建[PR46](https://github.com/FangcunMount/reliable-messaging/pull/46)。38份Apache源码和新meter-snapshot.patch可完全复现；make check、真实TLS/race及golangci2.5.0通过，Go1.25.9/1.25.12云端源码检查已通过，PR检查/NSQ兼容与实际SDK双存储/跨语言矩阵继续运行。拟发布新的Go修订预发布v0.5.0-rocketmq-tx.2，不移动旧tag，不修改Python源码；稳定Go/Python同SHA配对仍由T27执行。[修复证据](evidence/rocketmq-m3-sdk-meter-repair-20261020.json)。

- 2026-10-20：SDK PR46全部当前检查通过，按固定8fb6fc57完成合并（d06861e5）；Go1.25.9/1.25.12 make check、lint、Redis与NSQ兼容均绿。双存储及跨语言实际SDK矩阵39326382808仍在执行，Go修订tag尚未发布，宿主仍未切换依赖；M3保持6/36，源码合并/发布/宿主/生产分别记录。

- 2026-10-20：SDK实际双存储及跨语言矩阵39326382808两档各31项0失败/跳过，临时容器/进程/私有目录全部清理。已发布固定Go修订预发布v0.5.0-rocketmq-tx.2，源码8fb6fc57；正式tag下载模块213份选定源码逐字节匹配，模块缓存race回归/SDK探针构建通过，六个GitHub资产重新下载摘要全部一致。Python仍为原0.4.0a1/bfaae2b，不覆盖已有版本；T27稳定配对发布尚未执行。IAM/QS开始锁定新Go模块并重验，T07/T08未打勾，生产未变更。

- 2026-10-20：IAM T07固定57b07bab正式模块tx.2，1925源码race通过/31既有可选跳过；T08合入同一依赖修复并修正fixture resolver，冻结IAM51405831、QS696ee314。QS SDK交接版本门禁先拒绝升级；核对tx.1..tx.2仅metric.go运行实现变化，NSQ/legacy-wire/消费结算逐字节未变后，更新精确版本白名单及漂移突变回归，87项自测和文档facts通过，保留未来版本拒绝。当前三源码均已推送草稿PR，开始以正式模块重跑原事务与实际成对门禁，仍6/36，未变更生产。

- 2026-10-20：Mac mini固定IAM51405831/QS696ee314/正式SDKtx.2的隔离Broker/MySQL8.4.11最终22项0失败/跳过；两个独立IAM模块订阅均真实收到撤销、加载目标版本并拒绝旧权限，独立QS进程真实订阅后剔除两个主体旧缓存、核验主库并拒绝旧快照，客户端/进程/容器/私有数据已排空。限定主库reader是测试端口，非生产gRPC或system身份。云端T07三档39329371609、T08三档39329479386继续；IAM镜像一次公开Go代理HTTP2失败只重跑失败作业，QS原效果恢复一次权威读取拒绝保留并同源码复现，不修改其保护条件。进度仍6/36。

- 2026-10-20：T07/T08完成实现和必需验证，打勾并更新8/36。下载核对T07三档原事务/HTTP各34项、Broker各21项；T08三档原事务各34项、成对Broker各22项，全部0失败/跳过、无race且临时资源排空，实际模块均tx.2，源码精确匹配。PR134合并d53c36a9，PR135合并e3efa5b3，QS PR409合并2e95630b；两宿主生产CD仍暂停。SDK索引PR47合并9da9c213。infra PR41其他SDK/故障回归仍在执行，里程碑M3-1暂不标完成，不进入QS领域接入批次。QS原效果权威读取首次失败后同源码复验通过，原因仍未知并保留到T23/T25，不改写恢复保护或宣称修复。

- 2026-10-20：infra PR41固定4369e6a的13项当前检查全部成功，包括普通消息、实际SDK、包级故障与完整事务回归；已合并d544918f。至此M3-1所属T05–T08及相关SDK/IAM/QS/infra源码门禁闭环，里程碑标完成，任务总进度8/36。进度归档采用仅文档后续PR，不移动发布tag、不重复长时源码验收。接下来按顺序进入M3-2/T09答卷原Mongo事务接入；生产准入/NSQ/账号验收边界不变。

- 2026-10-20：M3-1进度归档PR44已合并234e39f1。进入T09，QS独立工作区codex/rocketmq-m3-qs-domain固定基线2e95630b；答卷应用/Mongo仓储、证据、事务运行器与Collection提交五包race窄基线通过。已确认现有202恢复依赖原幂等读取，写仓储和审计/原效果恢复仅识别V1，Mongo重入callback内仍会生成BSON_id/审计时间；新路径需在准备半消息前冻结完整业务文档及原wire、持久V2并借用原session witness，保留历史V1读取且封闭新事务事件旧Replay。M3仍8/36，无生产写入。

- 2026-10-20：T09 首批候选080d4d7d提交草稿QS PR410。新增独立原Mongo事务持久化入口，原事务外冻结BSON身份/审计时钟/首份wire，V2接受结果同时核对完整Reference、冻结计划、事实及Committed witness，拒绝已有session内准备半消息；历史V1读取及旧Replay保护未改写。d4cd66a0默认源码全仓race6904通过/0失败/60既有可选依赖跳过，定向冻结与历史恢复回归通过；新增required原生Broker/Mongo夹具独立要求零跳过。第一轮Docker私有配置缺Compose插件，未启动业务，专用目录已清理；第一轮真实宿主在failpoint命令处被驱动拒绝无序bson.M，9项套件未完成且失败报告保留。已改为有序bson.D，并扩展为11项精确身份/嵌套边界验收继续复验；42项infra自测通过。T09仍进行中，总进度8/36；完整装配、202、并发及跨实例门禁待完成，生产CD回读仍暂停。

- 2026-10-20：T09 Mac mini 首批实际宿主验收固定QS080d4d7d/infra741c9cb/正式SDKtx.2，RocketMQ5.5.1和Mongo7.0.37独立副本集下11项0失败/0跳过/无race，含服务端failCommand写冲突触发原WithTransaction重入、半消息不可见、业务+witness/首wire、已提交ACK客户端丢弃恢复、原根回滚、重复/冲突、完整身份与嵌套拒绝和关闭准入。报告回读实际Broker参数与镜像摘要，全部专用容器/进程/私有数据目录已清理；ACK丢弃不冒称网络丢包。固定golangci2.5.0零问题；87项文档自测、hygiene及facts通过，仅更新源码基线标记，未改写历史验收。此为原CreateDurably入口证明，不替代完整Survey/Collection、202、并发与跨实例任务门禁。T09保持进行中、总计8/36，草稿PR410与required云端矩阵继续。

- 2026-10-20：infra PR45实际在线执行，QS PR410当前20项检查通过、2项继续，无失败；infra新增original-mongo-root/Go1.25.9在模块读取阶段失败。QS go.mod明确最低Go1.25.12且GOTOOLCHAIN=local，因此此宿主组合无效；将宿主工作流固定为实际1.25.12，独立SDK既有1.25.9/1.25.12矩阵保持。失败run39335160523/job118342693230与原始日志摘要保留，不把无效组合重试标绿。此为CI配置修正，业务门禁仍待当前候选完成。

- 2026-10-20：T09装配批次固定QSf95ebc05、infra4c321148在Mac mini扩展至15项原生验收全部通过，0失败/0跳过/无race，专用容器/进程/目录全部清理；Survey显式选用事务Store，真实protobuf/gRPC服务经受控bufconn连接Collection application/REST，Committed精确证据返回原ID的202，Reference冲突返回503；并发同键仅原赢家执行一次，旧owner关闭后新client/runtime复用原结果。Collection到protobuf及身份为夹具端口，未冒称生产TLS/IAM/system或进程SIGKILL证明，真实包级丢回复及进程退出仍归T22/T23。全仓race6907通过/60既有可选依赖跳过；固定lint2.5零问题，87项文档自测/hygiene/facts通过；源码基线f95ebc05、后续文档head321e0989独立记录。当前准备宿主实际Go1.25.12 required云端门禁；T09未勾选，8/36，源码合并/生产分别待完成。

- 2026-10-20：QS PR410当前头25项检查通过、1项API生成同步不适用，按f78987ec精确头合并main3afc76a6，生产CD合并前回读仍暂停；PR411改为main并为321e0989显式触发同头CI39337474712，避免原feature基底未触发main限定CI而漏门禁。infra最新Go1.25.12宿主11项39336176609与装配15项39337093068均在线通过，后者已下载核对0失败/0跳过及全部清理回执。复核发现V1标记若同时包含V2事务证据会进入历史接受分支；新增纯版本选择拒绝与真实HTTP503回归，源码62dfaac1/文档head528ec496，验收扩为16项后重新绑定。全仓race6908通过/60既有可选依赖跳过、固定lint2.5零问题和87项文档检查通过；最终16项本地/云端复验继续，T09仍8/36，历史15项成功不改写成新头证明。

- 2026-10-20：T09实现及必需验证完成，勾选并更新9/36。最终16项原生门禁本地528ec496/infra4be8e6a及云端39338243991均0失败/0跳过/无race，已下载核对真实报告摘要18dff0cb及全部资源清理回执；当前deb46e67相对528仅增加同包回归与文档标记，生产和原生夹具源码相同，不重标旧报告SHA。原Tier1失败39337890729/job118351863412保留：Collection代码注释变更缺少同包测试，已加入“ID存在但证据Unavailable不可接受/重写”的有意义回归，同包策略对实际main基底复验通过。deb46e67全仓race6909通过/0失败/60既有可选依赖跳过，87项文档检查通过；当前头CI继续，旧321手动CI因候选被替代在排队中取消。infra PR45当前11项全成功并合并0237e589；QS PR411及infra46尚未合并，M3-2不标完成。下一项T10只读定位了评分请求、结果与失败三个原根事务，以及失败路径中的未来重试责任；独立工作区qs-evaluation开始本批，不更改生产链路。

- 2026-10-20：T10首个代码批次991aa1e3已本地提交，尚未发布或合并。为现有committed_event_evidence JSON列提供平面V1/V2 codec，保留原结果/report-input bytes、业务schemaVersion及历史V1语义；Outcome增加独立V2元数据，拒绝混合协议/业务绑定冲突，SQL写入要求原事务且拒绝Mongo owner。只读审计通过显式host primary binding与2秒预算读取精确witness；没有authority时为Unknown，不冒称Outbox行、published或消费者完成。evidence、Outcome domain、MySQL仓储、scheduler audit及outcome commit五包race通过，固定golangci2.5零问题；新测试最初漏检查mock pool.Close返回值已修正后复验通过。三个业务提交器、真实MySQL JSON/guard及Broker验收尚未完成，T10仍进行中，总进度9/36。

- 2026-10-20：T09装配QS PR411当前头25项成功、1项API生成同步不适用，合并733ce4d80dfeda1f7214961aaf04664765b47500；infra PR46八项全部成功，合并1f2c2ad7dd5ce243a7478a7039784f79b6295c91。合并前QS生产CD回读仍为暂停。实现、原生验收、源码CI与合并分别闭环；T09保持已完成，M3-2其余任务未完成，总计9/36。

- 2026-10-20：T10新增原MySQL提交边界及评分成功显式入口，源码37ca33120eef（文档head e5c2b853a42a），草稿[QS PR412](https://github.com/FangcunMount/qs-server/pull/412)。完整结果/report-input及原wire在事务前冻结；全部半消息后借用同一主库根事务，先guard、后Outcome/投影/Assessment/Run claim、最后witness。关闭/取消时等待已准入的真实本地callback；原根ACK或新权威读取确认提交后保留LocalCommitted/FinalUnknown。事务Unknown不再触发引擎即时计算失败/新重试授权。目标race及固定lint2.5（含原生标签）通过，87项文档自测/hygiene/facts通过；新增真实MySQL 8.0.36/8.0.44/8.4.11 required任务正在执行，其half发送器明确为夹具模拟，不冒称Broker/网络故障。评分请求、失败及未来调度交接、完整装配和跨实例冻结结果恢复尚未完成；T10仍进行中，总计9/36，无生产切换。

- 2026-10-20：T10评分成功批次更新到de7db811，默认全仓race6941通过/0失败/60既有可选依赖跳过。真实MySQL门禁39397037300三档各6项0失败/跳过，下载核对报告及摘要，新增精确业务key读取/原始身份碰撞拒绝；half发送端明确模拟，不能替代Broker或真实网络故障。补充执行前和claim后的冻结结果计划检查，已有Prepared/Aborted/DB错误均不能被当作授权直接重新计算；精确Committed事实恢复不重新写业务或发送半消息。首次原生JSON夹具缺失decision kind导致业务绑定拒绝的失败及Actions v4旧runtime门禁失败均保留，修正夹具/增加V2显式runtime拒绝并使用仓库批准v7，后续门禁独立记录。PR412仍草稿，当前头完整CI继续；新独立qs-evaluation-intake工作区接入pending→submitted CAS与共享owner，尚未合并。进度仍9/36；[T10证据](evidence/rocketmq-m3-qs-evaluation-20261020.json)。

- 2026-10-20：T10基础de7db811当前头完整CI 28项成功、1项API生成同步不适用；与后续源码分开记录。评分请求批次bb1f0910（含真实Broker夹具head d12f1b5c）已加入显式Submitter：共享qs.mysql原主库/运行时，预冻结完整提交计划，原pending→submitted CAS，保留不可变conducting/model身份，重复读取原wire/首次时间，Unknown不改调用方、不降级旧Stage。目标race、固定lint、Broker标签构建及87项文档门禁通过；QS PR412已推进到该头，完整CI重验中。infra PR49固定0dcf812新增隔离MySQL/Broker真实应用门禁，44项harness自测通过，run39399548063两档正在执行；评分输入是确定性夹具，不冒称system、生产RPC、进程退出或网络丢包。失败/未来重试和完整装配尚待后续，T10未勾选，总计9/36，生产CD只读回读仍暂停。

- 2026-10-20：真实Broker首轮39399548063两档均失败且已保留报告、私有输出摘要及完整清理回执：请求原根/witness已通过此前断言，在原wire比较处误把Received.Payload（已解开传输信封）当作Received.Wire。248c5a0d分别校验完整Wire及解包正文，未弱化身份/内容校验。另a67956fb保留原宿主提交写facade，避免新适配器绕过已有失效处理；恢复继续只读主库，constructor/目标race/lint通过。新候选168a7e79与infra f98f97f绑定，required Broker run39401207681及源码CI继续；旧失败不改成成功，T10仍进行中/9项完成，无生产操作。

- 2026-10-20：Broker第二轮39401207681请求已进入原生验证后，在生成第二个测评时被答卷唯一约束拒绝，两档失败报告/摘要及清理回执均保留。756185f6为每个测试测评提供独立答卷来源，不更改业务约束，候选7ea473a7标签构建通过，先在Mac mini固定缓存镜像/私有项目复验。Mac初次启动因infra验证副本仍指旧远端而在CLI参数校验失败，未启动Docker业务；显式拉取新公共分支并核对两源码SHA后重跑，旧日志保留，未调整任何现有服务。T10继续，仍9/36。

- 2026-10-20：Mac mini固定QS7ea473a7/infra f98f97f/已发布SDKtx.2、RocketMQ5.5.1缓存镜像050426c6、MySQL8.4.11隔离项目，真实评分请求/成功原事务6项0失败/0跳过/无race。请求CAS+witness、原wire和解包正文、重复首次时间、评分根提交前半消息不可消费、已有Run上的新Outcome关闭准入保护、精确冻结结果恢复全部通过；原始报告23ce587e与客户端输出摘要已核对，容器/进程/私有数据目录清理回执完整。该证明使用确定性输入与直接应用入口，不冒称system、生产RPC、网络丢包、进程退出或失败/调度验收。源码PR412与infra PR49固定该候选继续云端重验。下一个T10子批次为失败事件与未来重试原职责；尚不打勾，仍9/36。

- 2026-10-20：T10请求/成功真实Broker云端39402695692两档各6项0失败/跳过，infra72b3全13项CI通过，报告按原7ea源码记录。扩展失败事件、未来重试原授权与精确历史Run后，原生夹具从application迁入container，修正真实架构门禁失败而未增加豁免；5cb全仓race6967通过。新增显式模块装配，复用原主库/owner/写facade；缓存失效改由原根事务提交后钩子执行，提交前不调用Redis，回滚/未知根提交不跑钩子。ce2f5a124全仓race6973通过/0失败/60既有可选依赖跳过。9项首轮39407063585两档失败为独立fanout订阅收到前组夹具，报告/摘要/清理回执保留，已增加精确事件与业务ID过滤，并将失败验收改用实际Module.WorkerService；Mac隔离新一轮进行中，不冒称system或故障矩阵通过。T10尚不勾选，仍9/36，生产未变更。

- 2026-10-20：ce2f5a124固定Mac mini隔离Broker5.5.1/MySQL8.4.11真实模块9项全部通过，0失败/0跳过/无race，原始报告b8eb3246及private输出摘要已核对、临时资源完整清理。失败验收通过Module.WorkerService进入原失败流程，证明Assessment/Run/witness原根提交、future原due/授权/wire保留，以及重复投递不增加输入调用/attempt；不冒称模型调用、SIGKILL、网络故障、system或T13调度交接。缓存契约文档未同步导致一次docs事实拒绝，现已阅读修订并验证87项自测/hygiene/facts通过；固定lint2.5零问题。最终36aa0741f相对该测试源码仅变更缓存说明与验证标记，PR412及infra49固定该候选执行当前头云端门禁，仍9/36不提前勾选，生产CD回读true。

- 2026-10-20：T11 前置源码核对发现初始规划/T02清单的报告 owner 标记偏差：实际36aa0741f模块使用 Mongo Generation/Run/Report/CatalogProjector 及 NewMongoRunner（start/commit/retry），并非 MySQL 原事务。按已批准“借用原业务根事务、业务与witness同库提交”约束，报告生成/失败及未来报告retry dispatch修正为qs.mongo；评分仍qs.mysql。不追加存储迁移、不改四owner或36项总数，原错误保留为执行偏差记录；T11/T13未实现，不提前勾选。责任清单同步修订；[源码预核对证据](evidence/rocketmq-m3-report-preflight-20261020.json)。

- 2026-10-20：真实Broker云端39410103140固定36aa0741f，MySQL8.0.36及8.4.11两档各9项全部通过，0失败/0跳过/无race，下载报告38a4799f、fb6ddb9f及完整清理回执已核对。源码全仓39410100401出现两个新增单元断言失败：time.Local与JSON恢复time.UTC表示同一时刻但结构不同，已保留日志摘要并本地TZ=UTC复现；25501aac7仅修订两个单元测试，精确比较时间点及全部非时间重试字段，新增UTC/东8/西5时区覆盖，UTC和Asia/Shanghai包race及固定lint2.5通过。生产/原生夹具/依赖源码相对36aa完全相同，不重标原生报告SHA；完整UTC源码race与当前头CI继续，T10仍未勾选。

- 2026-10-20：固定候选25501aac7完整TZ=UTC全仓race6977通过、0失败、60既有可选依赖跳过，原报告77f38e01；精确diff仅两个单元测试，生产/native/依赖字节与双档9项Broker验收36aa一致。原生报告保持原SHA，不冒称新测试头已重新运行Broker。当前头源码CI及infra完整回归继续，T10未合并/未勾选。

- 2026-10-20：25501aac7源码CI的文档门禁指出单元测试源码更新后source_baseline仍指13fb912e6；本地复现并将标记更新为精确25501aac7，87项文档自测/hygiene/facts再次通过。最终5a1f489bb仅增加该文档标记，相对已通过Broker的36aa共两个单元测试和一份文档标记差异，生产/native/依赖均未改；原255文档失败保留，不冒称已通过。新头CI继续，仍9/36，无生产变更。

- 2026-10-20：infra PR49精确aff3dd31当前头13项完整检查全部成功（含双档9项原生与SDK/故障回归），2026-10-20T11:08:59Z合并a4547f83。源码PR412当前头5a1f489bb暂无失败，尚待全仓测试/运行时E2E及后续构建结束，未合并，不提前勾选T10；生产未变更。

- 2026-10-20：T10完成并勾选，总进度更新10/36。QS最终5a1f489bb当前头28项CI成功，1项API生成同步不适用；精确head与生产CD暂停true核验后，PR412于2026-10-20T11:15:49Z合并db9b4918。infra PR49的13项完整门禁此前通过并合并a4547f83。原生36aa双档各9项通过，后续仅两个单元测试/文档基线差异，原生报告保持原源码；完整UTC25501aac7 race6977通过/0失败/60既有可选跳过。所有源码/架构/夹具/UTC/文档失败历史保留。T11进入实施准备，沿用已核对Mongo原事务/qs.mongo；未来调度交接仍T13，生命周期/跨实例/真实故障仍T22/T23，生产/system/48h观察均未执行，M3-2继续进行中。

- 2026-10-20：T11首批模型源码6eb704e64（文档head d0b23a6a0）已提交到独立qs-report分支。保留旧V1字段，新增独立V2，不把事务证据冒充旧Outbox；拒绝混合/错事件/错完成时间，BSON保留原SDK引用bytes，生成状态写入要求原活跃session，clone不丢V2。7包UTC race159通过/0失败/5既有AgainstMongo缺依赖跳过，固定lint2.5和87项文档检查通过；这不是原生Mongo原子性或Broker验证。共享owner/原guard、报告成功失败发送/恢复、显式安装和真实验收仍待实现，T11不勾选，总进度10/36。另T10源码squash后main39413704472仅文档SHA祖先门禁失败，PR413独立修复两处元数据，缓存生产blob与原验证完全相同，87项文档及相关CI通过，完整CI/合并另记，未修改验证规则或生产。

- 2026-10-20：T11共享原Mongo owner/封闭回调上下文1071d1364及公共冻结编码ff38c15aa已通过定向race/lint，保留原答卷构造入口并新增借用同owner入口。精确eae97334b云端答卷回归39419280081完整16项0失败/跳过，报告2facef77及资源清理核对；精确f47a1b0bd云端评分回归39420340015两档各9项0失败/跳过，报告be47b056/dd5eac52及清理核对。它们是T09/T10回归，不冒称报告链路原生验收。00e76c383增加失败Run独立V2、保留未来授权/旧调度证据、完整clone原lease恢复历史、四类核心写构造不建索引及显式安装器；目标race/lint/87项文档通过，报告Sender/终态恢复及原生验收仍待实现，T11不勾选，保持10/36。另T10文档元数据PR413以28项CI通过/1不适用合并c691fcfc，main39417393541完整CI成功；原squash后失败保留，未放宽规则。

- T11基础回归补记：候选da6d5c630（源码00e76c383）13包race247通过、0失败、8项既有环境依赖跳过；逐项名称与报告摘要已入证据。先前7包5跳过与本次13包8跳过范围不同，均不作为报告原生验收。T11仍进行中，总进度10/36。

- T11继续：f54eb444f完成原claim冻结CAS及六类无DDL构造；b98f452cb新增报告成功/失败Sender、原事务和未知结果恢复，候选6fe3e1522七包race239通过/0失败/5既有Mongo跳过，固定lint与87项文档通过。QS PR414草稿维护源码。infra PR52首轮真实Docker验证在owner构造阶段因Topic配置键误作解析名而失败，报告和清理证据已保存；修正为qs.evaluation.lifecycle并增加实际V2权威审计（14项）后重验。T11未勾选，10/36。

- T11补记：a702707bf完成只读V2权威审计，候选b43538fee通过定向race、固定lint、原生tag编译与87项文档门禁。完整源码race仍运行；infra候选45cd015已固定该SDK宿主源码并要求14项原生证明（含成功/失败V2审计），run 39426436790排队中。实现不等于原生验收，仍10/36。

- T11修复记录：报告第二轮真实验证到重复恢复时拒绝SDK已隐藏token的只读执行；9737db449改为仅依赖精确引用/权威证据，不重建执行权限，并保留原始BSON直接比较。旧CI的新增V2类型穷尽夹具缺失由05bc0fda7补齐，原断言保留；lint失败为上游schema下载超时。最终候选f8566a830定向race、固定lint、原生tag编译与87项文档通过，第三轮原生14项及最终完整CI待结果，仍10/36。

- T11验证通过项：最终候选f8566a830完整源码race7050通过/0失败/60既有可选跳过；第三轮真实RocketMQ/Mongo report专用14项0失败/0跳过/无race，通过精确源码与固定Go SDKtx.2核对，Compose/进程/私有目录均已清理。覆盖首次wire、半消息、原事务成功/失败、原claim保护、客户端提交回复丢弃、真实Mongo重入、V2权威审计及新实例只读恢复。相关完整CI/合并尚未闭环，仍10/36；不表示生产或system验收。

- T11完成：2026-10-20T13:37:37Z，相关源码与infra均合并，最终当前头CI门禁全部通过。回表勾选T11，总进度11/36；M3-2仍需T12/T13，不提前标完成。T12开始只读追踪与基线验证，生产部署/正式SDK发布/system验收均未执行。

- 2026-10-20：T12首批候选2b84bd69提交QS PR415，infra PR54固定787d61e7维护隔离11项原事务/NORMAL双fanout门禁。目标race229通过/0失败/3既有可选MySQL跳过；87项文档自测、pinned lint及50项infra单测通过。手动开放半消息在原归属事务之外，业务根内再次锁定当前归属；未知结果复用首次计划、不重新生成入口、不回退旧Outbox。完整源码race进行中，真实依赖双档排队。消费者复核发现开放时钟截断与既有MySQL舍入规则不一致，待补边界修正，T12未完成，总进度11/36；无生产变更。

- 2026-10-20：T12精度问题以5个边界点先复现（4点错误抑制），c0f39d42改为与既有消费者一致的MySQL微秒解析/毫秒舍入，保持首次wire与原提醒策略。相关race146项0失败/跳过。首轮2b84bd69实际MySQL8.0.36/8.4.11+Broker各11项0失败/跳过且全部清理；不冒充最终候选证据。最终源码2626fd90全仓race7081通过/0失败/60既有可选跳过，native编译及pinned lint通过，87项docs/facts通过。infra 56eed1b1把原行写入后回滚、旧调度CAS与精度纳入14项门禁，运行39439182533待验。PR415/54尚未合并，总进度11/36，生产CD回读仍为true暂停，无生产或system验收。

- 2026-10-20：T12最终2626fd90/infra56eed1b1的双档真实RocketMQ/MySQL各14项0失败/跳过，报告绑定SDKtx.2摘要、实际镜像digest及全部清理结果。MySQL8.0.36报告ea126c6e、8.4.11报告9cb7b37e；运行39439182533。新增original_write_abort_atomic实际原任务SQL更新后再抛受控异常，证明业务与witness共同回滚；该夹具异常不声称网络故障。PR54曾在push后仍显示旧head，关闭/重开后已刷新为56eed1b1，最终检查不得使用旧head。PR415/54转ready，完整CI/合并尚待完成，总进度11/36。

- 2026-10-20：QS PR415最终2626fd90的28项CI成功/1项API同步不适用，生产CD回读暂停后合并36a81acc；合并main文档facts通过。infra PR54最终56eed1b1全部16项CI成功并合并472fbbee。收尾复核发现关闭新提醒会跳过旧执行恢复，committed/unknown两种情形已先复现；QS PR416候选63595a52把owner协议选择与新提醒开关分离，旧未知继续拒绝新入口，普通新开放保留原事务归属guard。153项目标race0失败/跳过、native编译/lint/docs通过，扩展15项真实门禁与完整源码CI待验。因此T12仍不勾选，总进度11/36；保持生产暂停。

- 2026-10-20 更正：此前“63595a52 native编译通过”的记录不成立，本地连续命令把随后lint的成功误作整体成功。15项新增夹具两档均在业务测试前构建失败：可变参数底层UOW不符合应用Runner；运行39443596014两份失败报告和全部清理结果已保留。8d6c05bb改用原宿主NewMySQLRunner，原生编译与pinned lint分别确认exit0；最终f37afca0/infra c27ef043重跑39445253355。63595a52默认源码全仓race7087通过/60既有可选跳过只证明其默认源码，不代替native构建或最终候选。T12继续不勾选，11/36。

- 2026-10-20：修正后的f37afca0/infra c27ef043在实际MySQL8.0.36和8.4.11各15项0失败/跳过，清理全部通过；报告601fd17e/eb5baec7绑定精确源码、SDK和镜像digest。新增用例经真实TaskManagementService，在关闭新提醒且无Plan/Enrollment夹具表的情况下恢复已提交执行、拒绝未知执行，证明恢复先于新业务规划。首轮构建失败与修复历史继续保留；全仓7087通过/60既有可选跳过，完整CI及合并仍待完成，T12未勾选，11/36。

- 2026-10-20：T12闭环，进度12/36。最终QS f37afca0的28项CI成功（仅API生成同步不适用），PR416合并f0499e60且main docs facts通过；infra c27ef043九项CI全部成功/0跳过，PR57合并7487c740。实际双MySQL+RocketMQ各15项0失败/跳过，7087默认源码race通过/60既有可选跳过；初版PR415/54、时钟红绿回归、首轮新增夹具编译失败及更正均保留。未发布稳定SDK、未执行生产迁移或provider切换。按序进入T13，M3-2待T13完成及相关合并后才关闭。

- 2026-10-21：T13首批ee080e0d冻结业务重试授权、first wire和原due，纯模型及架构65项目标race0失败/跳过。双存储初版借原SQL Tx/活跃Mongo session，拒绝错误连接/普通handle，索引时间向上取整；Prepared路径保留原wire，101项合同race0失败/跳过。存储/schema/Prepared代码尚未提交，证据保存逐文件SHA及明确scope；MySQL107/Mongo42仅源码模板，真实DB原子性及业务dispatcher门禁未通过，T13仍不勾选，12/36。Docker本机daemon未运行，后续沿用infra隔离CI，不启动或改动现有依赖与生产。

- 2026-10-21：T13存储子批次d789337e/文档头6ffd4d90已推送；207项race与新增原生标签编译通过，52项infra自测通过。显式107/42加入完整版本对，混合对拒绝，构造无DDL。扩大integration lint发现迁移包17项既有问题；新增代码scoped与普通迁移包固定lint分别通过，保留失败。文档首次因两处迁移说明验证标记过期被拒绝，阅读修订后87自测及facts通过。隔离CI即将对固定源码执行两种原库Run/计划共同提交回滚；尚不声称实际DB、到期发送或旧调度交接通过，T13不勾选，总进度12/36。

- 2026-10-21：首轮真实存储CI39457187250固定6ffd4d90，三档均失败并清理自有资源；脱敏报告定位MySQL原生夹具冻结计划被拒绝。源码核对发现新校验和合成夹具误用Assessment聚合，真实评分领域为Evaluation。补真实领域构造器红绿回归，修复前失败/修复后通过，保留报告；尚未取得新的原生通过证据。到期dispatcher及原根精确证明/授权校验初版新增72项目标race和48架构通过、原生标签编译及固定scoped lint通过；该批尚未提交，完整源码回归运行中。显式中止后的dispatch重试、活动写入口替换、治理/交接与真实到期消息仍待后续，T13不勾选，12/36。

- 2026-10-21：修正源码9e18668b与文档头c1e6a137f71373cf7132c9f924d808ec1b11b0af已冻结。完整UTC源码race7144通过、0失败、60既有可选依赖跳过；新增dispatcher/密封原根/计划72项、架构48项均零失败/跳过，原生标签编译、固定scoped lint与87文档自测/facts通过。PR417旧6ffd头28CI成功/1API同步不适用保留原SHA，不冒充修正后候选结果。infra PR61固定新头重跑三档原库存储；新dispatcher还未取得Broker到期证明，也未接管现行授权/暂停/交接，T13仍进行中，12/36，生产未变更。

- 2026-10-21：c1e6a137真实存储三档全部通过，CI39459759364第二次尝试完成；每档MySQL+Mongo共14项、零失败/跳过/无race，精确报告摘要、正式SDK模块及完整资源清理已核对。8.4第一次尝试在Docker镜像获取阶段失败、未产生structured报告，保留原日志摘要且不编造清理回执；仅重跑失败档后通过。新增pre-Compose失败报告/临时目录清理与真实到期成对harness，56本地单测通过，尚未提交/上线。自动授权新V2调度与旧V1责任兼容199项目标通过/5既有可选Mongo跳过；新报告用例合成Topic偏差已更正，原生Broker用例目前仅编译/lint通过，完整源码回归运行中。T13整体仍不勾选，12/36。

- 2026-10-21：自动授权源码37896a33、文档候选558898741e37d29e0454627cc2cd02bc21f154f6冻结并推送PR417。新失败事件在原根保存V2未来计划，首次wire/due/授权保留，V1旧赢家继续其原Outbox责任、稳定input hash不变；完整UTC源码race7147通过/0失败/60既有可选跳过，原生标签编译及固定lint、87文档自测/facts通过。infra准备三档31项实际宿主/Broker到期门禁，另重跑最终同源码14项存储矩阵；56项harness自测通过，Broker/MySQL初始镜像获取失败现在有受限报告与精确临时清理。以上尚未完成新的真实Broker验收，不勾选T13，12/36。

- 2026-10-21：558898741三档实际宿主+真实到期Broker门禁39462312786全部通过，每档31项、零失败/跳过/无race。验证实际评分失败与报告终态根事务新V2调度，真实等待due后发送，原wire与dispatch witness、原Run/attempt及重复空扫描均通过；原生Mongo callback重入/原根回滚/客户端提交回复丢弃等既有14项报告门禁保持通过。三份报告源码、正式SDK模块、private输出摘要和完整清理回执已核对；observer仅ACK，不冒称真实后续业务消费者、provider invocation、system、进程退出或网络故障。源码/harness未合并，人工/force、暂停、显式中止重试、旧责任交接仍待完成，T13不勾选，12/36。

- 2026-10-21：人工/force工作批次在独立qs-retry工作区推进，尚未提交。评分与报告入口先冻结完整私有授权/首次wire，在原根内竞争计划并复核原Run/Generation；提交回复不明使用fresh持久化读取，不回退旧Stage或重做业务。217项目标race通过、5既有可选Mongo跳过，新增真实双库人工授权用例仅编译、固定native lint及56项harness自测通过；完整源码race运行中，required原库门禁尚未执行。原夹具状态/模型遗漏、report内部包别名编译失败、缺少Failure.Code的修订均保留日志，不能把模拟root作为DB提交证明。T13仍未勾选，12/36。

- 2026-10-21：人工/force源码c6654eeb9、文档候选130184912524caae0f8d5cfbf830f49ca5104620冻结推送PR417。实际应用入口及原根计划/Run/Generation保护、完整私有授权档案、自动旧codec字节兼容和精确dispatch时间证明均进入本批。完整UTC源码race7157通过/0失败/60既有可选跳过；217目标通过/5既有可选Mongo跳过，原生标签编译与固定lint、87文档自测/facts及56项infra自测通过。required双库人工门禁扩为每后端15项、每档30项并固定新候选待CI；旧5588三档31项仍只归其原源码，不冒称人工或新头原库验收。暂停、中止后显式恢复与旧调度/Replay交接尚未完成，T13不勾选，12/36。

- 2026-10-21：130184912人工/force原库首轮39469858549三档失败，脱敏报告均定位TestM3RetryMySQLStore共享治理夹具入口，0跳过/无race；每档自有容器、进程组与临时目录清理完整，保留报告/private输出摘要，人工门禁不得计通过。新增显式Aborted dispatch恢复与自动暂停合同30项race零失败/跳过，原生标签编译与固定lint通过；真实恢复门禁仍待运行，不冒称网络故障或业务consumer验证。T13不勾选，12/36。

- 2026-10-21：修正候选3b465b52c26a587f62278529a2cb87b82776eecb人工/force真实原库39471075323三档全部通过，每档30项、零失败/跳过/无race；报告源码、正式SDK、private输出摘要和完整清理均核对。首轮夹具对预分配ID调用Save进入更新路径、未插入初始Assessment，改为显式Create及原事实回读后通过；保留失败历史。新增显式Aborted协议恢复与自动暂停源码f33923b88，全仓7166race通过/60既有可选跳过、30项目标零失败/跳过、原生编译/固定lint及87文档自测/facts通过；真实恢复矩阵仍运行中。交接适配实现中，T13未勾选，12/36。

- 2026-10-21：f5084f77旧未来交接真实矩阵39472161154三档各42项零失败/跳过/无race，原根业务计划与旧责任held标记共同提交/回滚、保留first wire/due、重复单一责任、已尝试/已到期拒绝、旧Relay/Replay拒绝及清理均核对；独立冻结工作区完整UTC race7197通过/60既有可选跳过。复核发现旧状态读取器需识别精确交接held标记，兼容修正和新原生状态用例仍待验证。显式恢复首轮39471083111三档失败，原宿主正确保留回调错误Unknown；修正测试等待真实lease和ReconcileOnce，再用精确历史Checker核对旧fence，SQL/Mongo实际标签分别编译/lint通过，5582e030修正门禁39472781411运行中。T13继续12/36；T22须完成实际调度/恢复策略生命周期装配、启动schema就绪及已消费RocketMQ暂停任务共享预算恢复，不能通过普通消息重发到事务Topic。

- 2026-10-21：5582e030真实暂停/lease回收/显式恢复39472781411三档各41项零失败/跳过/无race，源码、报告、首次wire/selectedAt、旧精确Aborted witness及清理核对完成。2cc8fdf90完整UTC race7197通过/60既有可选依赖跳过、全仓固定lint零问题；当前5ed29545/de6289e46相对该普通源码仅原生标签断言和文档变化。状态原生首轮39473548719三档在四个零计数桶的夹具断言失败，修正后原生编译/lint通过；曾与冻结工作区全仓lint争用全局锁退出3，顺序重跑已通过。旧5582云端lint下载官方schema超时、没有代码诊断，保留日志摘要且未关闭门禁。最终de6289e46待44项状态/交接、41项恢复和当前头完整CI；PR417/61仍草稿，T13不提前勾选，12/36，生产CD回读true。

- 2026-10-21：最终源码7e8aba25/文档头fd985a12223a52b0201501b82b72ca60624a3ba9增加业务提交前完整dispatch大小门禁，600KB授权边界红绿回归及100KB最长合法时间/版本对照通过，有效冻结编码不变。239项定向race通过/5既有可选Mongo跳过，独立精确候选完整UTC race7198通过/0失败/60既有可选依赖跳过、全仓固定lint零问题，87文档自测/facts通过。infra1332c57通过显式qs_ref验证最终源码，39475640062三档各44项零失败/跳过、清理完整；41项最终Broker恢复39475640759及完整云端CI仍运行，不勾选T13，12/36。两个本分支已被替代的旧CI39474368285/de628与39473594924/2cc8已取消，不冒称完成或替代最终门禁。

- 2026-10-21：fd985a122最终真实Broker39475640759三档各41项全部通过，0失败/跳过/无race，first wire/selectedAt、真实lease竞争Aborted、新fence及旧精确witness、observer和完整清理均核对。原库最终39475640062三档各44项亦全部通过。infra1332c57的22项当前头CI全部成功，PR61已按精确head合并d4324a87（2026-10-20T18:48:26Z）；默认历史候选de628保留，最终fd985通过显式qs_ref且报告严格匹配，不能混淆其来源。源码PR417尚有Seeddata Retirement and Current Runtime E2E长流程运行，当前24成功/1API同步不适用/1运行；实现和原生验证完成不等于全部合并，T13仍12/36，不提前开始T14代码接入。生产/system/下一业务consumer、网络或进程故障及正式SDK发布均未执行。

- 2026-10-21：T13闭环并勾选，进度13/36，M3-2完成。最终fd985a122当前头28项CI成功、仅Docs/API同步不适用，最后真实数据库/runtime E2E完成；合并前生产CD回读true。QS PR417于2026-10-20T18:55:54Z按精确head合并133fc073，infra PR61当前头22项CI成功并已合并d4324a87。最终原库三档44项、Broker三档41项0失败/跳过，完整UTC race7198/固定lint/文档门禁及全部清理/失败历史核对完成；完整closure索引不重绑定历史报告。按序进入T14，先保留原QS→AI聚合序列/首wire及业务receipt责任，再替换发布型Outbox。未发布稳定SDK、未执行生产DDL/provider/NSQ切换或system验收。

- 2026-10-21：T15首批源码21c13967651e4c5c92fa93daaca41f439d52fcd7保存于独立qs-ai-events工作区：冻结原入站wire及首次ACK身份/时间/Seal；共享qs.mysql原根guard先于Inbox/投影/ACK档案与witness；真实commit回复不明保持Unknown。新receipt借用原连接核对精确archive/witness，真实历史缺席才沿用旧Outbox结算；新事务路径不启动旧command/ACK Relay，保持订阅在途预算1。单元race797通过/0失败/7项既有可选依赖跳过，固定lint2.5零问题；infra新增脚本62项单测通过，完整race及三档真实Broker/MySQL验证尚待完成，T15不勾选、总计14/36。历史Inbox不重包装为新事务证明，原责任留待交接门禁；本批不计为AI成对、网络提交故障、system或生产验收。

- 2026-10-21：T15最终候选4fed2b588b9d16c11e76304edb3d9762f1a7933f（实现b1776025f）已提交QS PR419；infra137c5465维护PR72，三档17项真实Broker/MySQL门禁39498223478运行中。独立冻结工作区完整UTC race7326通过/0失败/60既有可选依赖跳过，完整固定lint2.5零问题；相关包799通过/7既有可选跳过，87文档自测/hygiene/facts及62项infra自测通过。Prepared ACK的幂等键属于入站事件，已用有界精确分支足迹补齐其历史Payload回退保护；故意红回归及初始protobuf夹具编译失败均保留。组合integration标签lint六项既有fixture清理errcheck提示另列，不冒称整个历史集成标签lint无问题；本批新增代码lint零问题。两PR尚未合并，T15保持进行中、14/36。生产CD回读暂停true，未发布稳定SDK、未操作生产或system验收。

- 2026-10-21：T15首轮真实Broker39498223478的8.0.36、8.0.44、8.4.11均在签名receipt夹具173/270断言失败：遗漏必须指向原command_id的correlation，现有契约在进入接收器原根之前正确拒绝。各档0跳过/无race/无超时，临时容器、进程组和私有目录均完整清理；三个报告、私有输出摘要和源码4fed2b588分别保留。修正7a4c942ac只改测试，增加空/错/正确correlation及冻结ACK回归；最终文档头762c2db0d业务字节与b1776025f一致。两个包298race通过/7既有可选跳过，完整7327通过/60既有可选跳过、全仓固定lint零问题，87文档门禁通过。infra3f2af604仅更新固定候选，Python源码/62项单测仍137c5465；新三档17项39500000104已启动。PR419/72仍草稿未合并，T15保持验证失败后复验中、14/36，不将失败或旧SHA门禁改标为新候选通过。

- 2026-10-21：T15最终762c2db0d/infra3f2af604真实Broker39500000104三档8.0.36、8.0.44、8.4.11各17项全部通过，0失败/0跳过/无race。已下载核对精确源码、Go SDKtx.2及Sum、镜像ID、实际事务参数、私有输出摘要和完整资源清理；报告分别0d8e3f08、3f40a886、b1d50a13，原始报告不重绑定。验证了真实原根Inbox/解释与评测投影/receipt/ACK档案/witness、提交前不可见、首wire认证与复用、Prepared ACK不公开、服务端拒绝整根回滚、精确Aborted显式Retry/Replan及历史责任不伪造。签名AI输入为受控夹具，observer仅ACK，不计为完整AI producer或模型/网络提交故障/进程/system验收。原生和本地完整实现已完成，源码/infra剩余CI及合并仍待完成，T15暂不勾选、14/36；T16仅保留只读预研。

- 2026-10-21：T15源码当前762c2db0d完整CI28项成功、1项API生成同步不适用；独立当前候选命令回归39502117806三档各15项均0失败/跳过/无race，已核对源码、报告与清理，确认共享SQL根抽取保留全部五类command语义。生产CD合并前回读暂停true，PR419于2026-10-20T21:45:55Z按精确head合并be22b927。infra PR72当前回归仍待最后作业，不提前勾选T15、14/36。AI下一批仅只读预研：main c321a694与10687a1业务树一致，26项基础纯测试通过，无业务入口修改；生产未变更。

- 2026-10-21：T15闭环并勾选，进度15/36。源码PR419精确762c2db0d当前头28项CI成功/1项API同步不适用，已合并be22b927；infra PR72精确3f2af604当前头28项检查全部成功（含既有普通消息、SDK、双存储、跨语言和真实故障回归），已合并db183399f21d39ae481121e893d6c73626b45a41（2026-10-20T21:51:42Z）。最终事件三档各17项及当前候选命令三档各15项0失败/跳过，全部清理、原始报告SHA、失败历史及完整source gate已核对。T16开始独立AI admission/receipt接入；M3-3仍进行中，不提前标完成。生产CD在源码合并前回读暂停true，未发布稳定SDK、未执行生产DDL/provider/NSQ切换、system或48小时观察。

- 2026-10-21：T16第一批源码本地提交至2a225d956ba5f863a758b1fef29fa4181bc9a801，冻结原认证command bytes、稳定input hash、完整receipt/state首次wire计划；保持archive/v1与SDK协议不变，验证state与receipt精确关联。解释入口及Inbox可借用原根前预分配身份，旧默认入口保持原分配行为。完整纯单元2294通过（859项integration/interop按标记未选择，不计真实依赖验收）、定向122通过、Ruff及mypy360源文件零问题。预期red测试与修复保留于[T16证据](evidence/rocketmq-m3-ai-admission-20261021.json)。T16尚未接入真实事务receiver，未推送/CI/合并/部署，总进度15/36。

- 2026-10-21：T16原根基础批次推进到b37f9734cc5c1daf40b62d32180b945d74192f49，AI草稿PR159保留未就绪。新Inbox事务决策不创建旧Outbox责任；AdmissionRoot先guard、精确比较实际业务结果与冻结receipt、共同写档案/witness，并仅由宿主提交；HELD无业务调用。116项纯契约通过，新增4项真实MySQL HELD根用例已收集、尚待CI，不计为实际receiver/Broker验收。完整纯单元初次32失败/2294通过暴露Dishka自动注入job_id，现改为显式普通UoW provider，150项受影响测试和mypy361通过，完整回归重跑。失败日志及修复均保留，T16未勾选、15/36，未执行生产操作。

- 2026-10-21：T16候选80805fb完整CI39512001863共12项成功。下载八份分片报告，MySQL8.0.36/8.4各3242项0失败/跳过，完整相同收集、无遗漏/重复；每档包含v1/v2原根8项和配置2项证明。报告实际PR合并测试SHA为daa79e80，不冒充源码head；原失败b37报告合并测试SHA710c10d7及其父提交保留，原生夹具遗漏冻结时间和随机测试参数身份均已修复。完整本地8fe05c7纯单元2371通过、869依赖未选择，mypy362/lint/格式/文档通过，后续clock补充80项通过。只读START/原根资源/状态转录本地批次ddca829尚待新原生CI及完整receiver接入，不计为已完成业务。总进度15/36、T16未勾选，源码/稳定SDK/部署/system/48小时状态独立，生产未改。

- 2026-10-21：T16 新 START 候选 f45a9ed 本地完整纯单元2459通过、874项真实依赖按标记未选择，mypy366源文件通过；真实两档MySQL CI暴露预览间接取得配额行锁与测试清理误调用SDK属性，失败报告和精确SHA保留，不计通过。cd57d8c保持原根锁默认值、只对预览关闭嵌套锁并修复清理，32项定向测试通过；新384a440候选正在重跑完整CI39520264316。CHANGE目标绑定授权组件5项通过，实际命令/Receiver/Broker仍待完成；T16未勾选，总进度15/36。

- 2026-10-21：T16 START修复384a440两档MySQL各3339项0失败/跳过，八份分片报告完整无重叠；实际合并测试SHA f907af2c父提交已核对。完整12检查及M7两档成功，M7每档schema3、unit119、storage85分别通过（子集不叠加作完整计数）；每档含8项HELD根、2项只读START、3项完整业务START，先前失败保留。CHANGE62f5053完成只读原answer/cancel、冻结首次消息、精确主体/目标和60秒观察、原根/witness组装；本地完整纯单元2502通过/878真实依赖未选，mypy371源文件通过，最后锁等待后读取时钟的25项定向通过。新增4项真实CHANGE原根正在CI39521665607验证，不沿用START成功；SDK/Broker与其余三类命令未完成，T16仍不勾选、15/36，无生产变更。

- 2026-10-21：T16 CHANGE62f5053完整12检查与消息兼容2检查成功，两档MySQL各3381项零失败/跳过，八分片无遗漏/重复，新增各4项CHANGE业务原根通过。测试合并SHA091bd048父提交已核对，M7每档schema3/unit119/storage85报告分别保留。RETRY8264093完成共享原风险/CAS/档案规则、无锁只读规划、冻结Run/job/state/时钟、原参与者观察、源档案摘要及原根witness；本地完整2527通过/881真实依赖未选，mypy374源文件通过，3项新原生重试用例收集完成待CI39523138592。共享上下文保留CHANGE原bytes摘要向量，SDK协议/schema未改；两类评测/receiver/Broker仍未完成。总进度15/36，未合并AI源码、未发布/部署。

- 2026-10-21：T16 RETRY8264093完整12检查与消息兼容2检查成功，两档MySQL各3408项零失败/跳过，八分片覆盖完整无重叠，新增各3项重试原根通过；冻结首次模型请求/重试档案、源变化整根中止、unknown风险未确认仅提交拒绝均已证。实际合并测试SHA b41e4a52父提交与各报告摘要已核对。评测基础本地9435de7复用原转移/CAS、视图、容量、取消及未知工作drain，显式原根当前读取模式与宿主默认不污染的新native用例仅收集待跑；完整评测规划/序列/原根、receiver和实际Broker未完，T16不勾选、15/36，未合并AI代码或执行生产变更。

- 2026-10-21：T16评测冻结原根候选fbb1bbdea447a2901866aebde83a9b45753f6486已推送，代码ee7f9e8。复用原启动/取消/容量/审计/drain，冻结源与序号/首次wire，原根先guard、组织准入锁和当前CP/Run复核，再原子提交业务/序号/档案/witness；不新增旧Outbox发布责任。本地完整2596通过，891项integration/interop未选择、不计真实依赖；mypy379、926文件格式、75文档/1315链接通过。新增9项原生评测和1项显式隔离/池默认用例仅收集待CI39530725568及M7 39530725484；不借用8264093已通过结论。此前两处新测试夹具错误均已修正并保留记录。AI PR159仍草稿未合并，receiver/Broker未完成，15/36及生产状态不变。

- 2026-10-21：评测候选fbb1bbd完整CI39530725568结束，两档各3485通过/2失败/0跳过；失败仅新archive/witness故障触发器以应用账号创建遇到MySQL1419，八份报告和实际合并测试SHA58d12fea父提交均已核对，M7两档成功独立记录。98f4bf9改为现有显式隔离管理员DDL连接并严格同库校验，保留应用账号/连接池，不改权限或生产。独立事务receiver f7fbc89本地全量2624通过、mypy381、52定向通过；实际v2路由/原认证、先查赢家、精确提交后ACK、旧Inbox不冒充witness、物理失败不授予业务重试均已实现。61c1cda补齐技术HELD独立空状态转录，51定向通过，全量复验中。新原生4项与实际SDK/Broker尚未通过，不勾选T16、不合并AI源码，总进度15/36。

- 2026-10-21：T16修复候选2bfbb65d8aff3ea6dce69fe170827c8164e470db完整CI39534228137的12检查和M7 39534228024两检查全部成功；八份报告已下载，MySQL8.0.36/8.4各3520项0失败/跳过、完整收集且分片无遗漏/重复。实际测试合并SHA5ce8b7cd父提交已核对，每档新增评测9项和receiver4项全部通过；M7每档schema3/unit119/storage85独立保留。此前30b3d32每档3519项的预算原事务失败、技术HELD失败及publication清理连带4项错误均保留，已修复显式技术读取事务、显式fixture依赖/原清理顺序；未放宽校验、关闭外键或增加应用权限。新infra76a0b1e/PR83在隔离Compose中验证固定发布wheel的真实SDK/Broker，Python3.11/3.13与三档MySQL共6组合、8宿主用例/15检查，目前排队，不提前计通过。源码两PR仍草稿，T16不勾选、总进度15/36，生产未变更。

- 2026-10-21：真实SDK/Broker首轮39535745152六档均失败，全部临时容器/目录/进程组完整清理，报告原始摘要保留；各档固定SDK wheel0.4.0a1/client5.1.2及两个typed Topic/三个最小角色已回读，不能因此计业务通过。8用例均在控制QS输入freeze_branch337处缺原时间；本地复现SDK字段校验ValueError，cde36ea仅扩展测试构造器显式传入首次签名前时间，旧默认仍空、不改应用/SDK、不重新签名冻结wire。6协议回归与合计36定向通过（9interop未选）。新源bdbaa30、infra8ad7f7a已固定并启动Source39538869956/M7 39538869952与Broker39539009218；此前infra同候选31项既有回归成功与6项新Broker失败分别保留，不重绑定。总进度15/36、T16未完成、两源码草稿，生产未改。

- 2026-10-21：T16最终9485f28完整CI39540533886与M7 39540533753共14检查成功；八份分片/JUnit与测试合并父SHA已核对，MySQL8.0.36/8.4各3531通过、零失败/跳过。真实SDK/Broker39540599454的Python3.11/3.13×三档MySQL六组均15项协议检查/8宿主用例通过，实际事务参数、固定wheel/client、first wire和完整清理已回读，报告摘要保留；最后确认回复客户端丢弃不计为网络级故障。此前两轮失败均保留。AI PR159合并e8392c05，infra PR83精确21be02d共37检查成功并合并b770ed68；T16勾选，总进度16/36。未发布稳定SDK、未修改生产，system/48小时观察未开始。T17新独立工作区基于该AI main推进，共享原根保护继续覆盖取消/未知提交，不因阶段结束启用尚未完成的生产装配。

- 2026-10-21：T17 的0be8755源码14项检查通过，两档MySQL各3633通过、零失败/跳过，分片与JUnit完整集合和测试合并父SHA已核对，各含5项实际worker原事务测试。实际worker/预检/发布SDK/Broker六档39551357301均13项协议检查、3宿主用例通过，首次wire、半消息门禁、源冲突回滚、LocalCommitted/FinalUnknown及完整清理报告已核对；infra PR88精确62a90f2共43检查成功。证明范围为worker预检及事件观察者，不代表完整治理入口、QS成对链路、真实模型、网络级提交丢回复或生产。下一批已本地修正原准备/dispatch一次事务多版本的最终状态冻结，并抽出定稿/重开纯投影；尚未原生验收或合并。T17继续不勾选，总进度16/36。

- 2026-10-21：T17部分验收工具PR88已合并46bb54e2，43检查成功，0be8755的六档worker/Broker证据保持不变。下一候选3cf74b5新增原准备/dispatch原生表征在MySQL8.4分片失败：误将PreparedStep.cp保留快照断言为dispatching，数据库final版本v5及提交探针已通过；失败报告摘要保留。断言修正4b32439、文档候选cbc47d9重新执行39559277637/39559277604，旧失败运行已请求取消，未计通过。治理冻结计划移至独立codex/rocketmq-m3-ai-governance分支，0f787c5本地2765单元通过、388源文件类型通过，定稿/重开及显式RR根保护已实现，8原生用例只收集、未验收；尚未接入实际RPC或合并。T17仍未完成，16/36。

- 2026-10-21：已核对cbc47d9完整八分片/JUnit及合并父SHA，两档MySQL各3649零失败/跳过，修正原子提交用例各通过；14项检查成功，M7两档六份报告均非空/零失败跳过。使用infra已有workflow_dispatch.ai_ref绑定精确CBC，真实六档Broker39560981646仍在执行，不套用旧0be证据。治理计划8b44358的12项源码检查成功，两档各3680通过，新增定稿/重开原根各8项全部通过；新c2ebf08发送编排与显式RPC适配器本地2788通过、390源文件类型通过，12项原生用例/当前CI39561117309仍待执行完成，不将原8项证明替换为12项。生产装配不启用，T17仍进行中、16/36。

- 2026-10-21：cbc47d9精确六档真实SDK/Broker39560981646各13协议检查/3宿主用例通过，零失败/跳过与完整清理已核对；首次报告下载EOF已重试，未跳过报告验证。AI PR160合并2342eb6b，候选/合并tree均8c3f97e，AUTO_DEPLOY_ENABLED=false，代码合并不记为部署或任务完成。治理分支基于新main整理为ecdb144，整理前后tree均fcf3847，旧c2 CI已取消，当前39562163112重新验收；不能用旧8b的8项原生替代当前12项。评审只读规划PR162为b696b3e，原writer保持原锁和CAS，本地50目标/390文件类型通过，新增单项/35项实际MySQL用例仅收集。T17继续进行中，总进度16/36，生产/system/观察未开始。

- 2026-10-21：治理ecdb144当前39562163112的12项检查全部成功，八份分片/JUnit完整集合、无重叠覆盖及测试合并父SHA均已核对；MySQL8.0.36/8.4各3707通过、零失败/跳过，各包含12项治理原事务及直接RPC适配验证。DB-only runtime测试不替代真实治理Broker、网络丢回复、进程退出或生产验收。评审冻结输入/首次时间codec本地44项目标与391文件类型通过；新增测试误用SDK不存在字段已修正，源码仍未提交，不冒充PR162当前源码证明。评审SDK编排与其他活动写入口仍待完成；T17不勾选，总进度16/36。

- 2026-10-21：治理PR161精确ecdb144合并6a3adb8e，合并tree与候选同为fcf3847，部署开关仍false，未计生产部署。评审只读候选b696b3e的39562531850共12检查成功，八分片/JUnit与父SHA已核对，两档各3711零失败/跳过，各2项只读原生通过。新评审执行候选2681062（代码ed04d58）持久化完整输入摘要和首次时间向量，在原guarded根中复用原前后审核、写入完整35项评审并共同提交archive/witness；共享发送编排及显式RPC适配已接通，默认装配仍关闭。96目标、392源文件类型及75文档/1330链接通过；12项真实MySQL用例仅收集，完整本地回归2826通过/933集成排除，当前CI待完成，不复用旧只读证明。T17不勾选，总进度16/36。

- 2026-10-21：评审精确2681062/39598394073的12检查全部成功，八分片/JUnit完整集合及父SHA核对完成，两档MySQL各3759零失败/跳过，单项/35项共12原根及直接RPC用例各通过。PR162已合并4a8993c9，候选/合并tree同为2c15d495，部署开关仍false。评审更正只读抽取PR163（eba5d53，代码b282b5a）保留精确command ID重放先于当前CAS，覆盖归档更正；本地30目标、2836全量、392文件类型和970格式检查通过，4真实只读用例仅收集，39599193045运行中。真实Broker扩展源PR164（9394c37）和infra PR93（1d4a73c）共6宿主用例/20必需证据，工具76单元通过，六档39600072506待完成；不把旧3用例/13项证明移用到新批次。T17仍不勾选，16/36，生产/system/48小时观察未开始。

- 2026-10-21：9394c37扩展真实SDK/Broker六档39600072506全部通过，每档6宿主用例/20必需证据、零失败/跳过、完整清理；逐份源码、固定wheel/client、原生/JUnit摘要、两项工具hash及测试合并父SHA已核对。源12检查、两档各3759通过，PR164合并ce82d314且tree一致，部署开关false；infra PR93的19项检查全部通过并合并72ee1295，4项实际工具文件与已验证候选一致。更正只读eba5d53/39599193045的12检查和八分片/JUnit已验证，两档各3773/各4原生通过。新更正事务代码84d80d2结合已验证Broker源码后形成6e5919a/PR165：完整输入/首次审核时间、原根与RPC发送、历史重放及主库精确输入冲突证明已实现；本地169目标、2881全量、395文件类型、980格式及75文档/1335链接通过。14原生仅收集，当前39603140689待验收，不将旧Broker证明套用给新更正事务。旧PR163的实现将随PR165合并后收尾，不丢弃其验证记录。T17不勾选，总进度16/36，生产、system及48小时观察均未开始。

- 2026-10-21：更正精确6e5919a/39603140689共12检查全部成功，八分片/JUnit和源父SHA已核对，两档各3832零失败/跳过，各含9项原更正/RPC和5项主库输入冲突原生验证。PR165合并e0e0e206，候选与合并tree同为58a11ecd；只读PR163因祖先代码已包含而自动标记合并，历史3773/4项证明保留。默认生产装配仍关闭，未发布稳定SDK或部署。创建调用链补充发现Solution Prepare经prepare_assets在同一资产注册事务调用create_run；它是既有间接状态写入口，将纳入T17门禁，不能因迁移而拆开原子性，也不新增M3任务数。新独立创建工作区从e0e0e206追踪并建立基线；T17继续不勾选，16/36。

- 2026-10-21：创建只读计划948837b/候选cb46a56（PR166）保留原definition精确SHA256=93d94137…a277708、首次时区时间、原执行模式、SQL顺序及调用者原事务；独立创建与Solution资产注册仍同根。本地42目标、2889全量、395文件类型、982格式和75文档/1336链接通过；4原生仅收集，39607704140执行中，尚无创建Sender。提取前两条基线测试误用物理表名，已按真实schema修正并在应用改动前重验2通过，原失败日志保留。更正真实Broker源ede6a9d（PR167）及工具528d17d（infra PR97）要求8宿主用例/25证据，工具77单元通过、八用例仅收集，六档39608564906待验收；旧9394的6/20报告不移用。T17不勾选，16/36，生产未变更。

- 2026-10-21：整批Solution资产规划9541305/39617243516的八分片/JUnit、零重叠完整覆盖与测试合并父SHA已核对，两档各3983零失败/跳过、各4原生；12检查成功，PR171合并954eb2a，tree同为f742613a。借用原根a864895/39618480075各4000/各4原根报告通过，但最终作业状态尚未结束，不提前合并。新SDK层冻结源/草稿/完整资产/首次业务回执摘要，原guard后在同一根提交事实、首wire与witness；Sender用精确新读取证明区分历史回执、Prepared、Committed及FinalUnknown。56目标通过、27原生仅收集（10原根、17实际Prepare处理入口、并发及回滚），未计原生成功；默认生产装配未启用，T17仍不勾选，16/36。

- 2026-10-21：新Solution事务候选f87af32（代码e1e7b6e，PR173）推送后启动39623720568；本地56目标、3061非集成/非interop、403源类型、1014格式及75文档/1352链接通过，27原生仅收集。首次本地命令漏排interop而缺固定Go探针，3061通过/9失败/3跳过，该轮保留为失败，不记门禁通过；重跑原单元范围后零失败/跳过。实际原生和Broker仍分别验收，不因单元通过启用默认装配或勾选T17，16/36。

- 2026-10-21：Solution真实Broker档源9eaac0a/PR174及infra工具0b702f6/PR104已推送，工具78单元通过、10宿主用例仅收集；六档39624273750待执行完成，新增30项精确证据，旧8/25报告不能代替。ResolveUnknown原写入口先完成7项原始行为表征，再抽取只读不可变计划f925cfa/候选06ac709（PR175），保留CP→Run锁、原裁决时间、恢复预算、原CAS及management容量/根提交归属；36目标与3071完整单元通过，4原生仅收集，尚无resolution SDK入口。未勾选T17，16/36，生产与默认装配保持关闭。

- 2026-10-21：PR172精确a864895的suite/workflow和要求全部分片成功的coverage作业均已完成成功，八份报告各4000/各4借用原根通过；单个作业列表仍in_progress的状态差异单独记录。正常标记ready后合并b0f1004（未使用绕过选项），候选/合并tree同b9d36f9。完整SDK候选f87在两档各2个成功处理入口用例的最后回执比较断言失败：领域content含tuple，原RPC JSON编码成数组；业务、version、模式、调用次数及Checker前置断言通过，但该运行仍记失败。5948cc9修正实际RPC边界比较，56目标通过，db2b989启动39625934747待完整验收。真实Broker9ea首档同类断言963失败，清理完整；旧运行39624273750取消请求已提交，修正源码f572612将与工具重新绑定，不沿用旧报告。T17仍不勾选，16/36，生产未变更。

- 2026-10-21：RPC比较修正后的SDK精确db2b989/39625934747、Broker源f572612/39626084626与工具d0f61bd/六档39626265764已固定并启动重验；工具78单元继续通过。原失败记录与首档完整清理已保留，不能将旧源成功阶段或先前其他链路报告当作本批通过。ResolveUnknown原规划仍独立追踪，未启用统一装配，16/36。

- 2026-10-21：ResolveUnknown源码c44499b/候选73ee3b8（PR176）实现首次人工裁决/源摘要codec、原容量只读预检及显式原宿主绑定；SDK guard后持有原组织锁，原resolver借用同一根，保留CP/Run锁、原预算/模型/配额配置和裁决响应。缺绑定在协议读取前拒绝；本地Committed/FinalUnknown仍需精确证据，不授权自动重试。27目标、3098完整单元零失败/跳过、405类型、1021格式及75文档/1357链接通过；12原生仅收集，包括真实第二个Run争夺宿主容量和并发原裁决，39627648431待验收。原只读规划候选随修正父级整理为440461f/39626904176，原应用源未变。已在原库存中的可信主机semantic-contract-recovery维护写入口继续纳入后续原根/装配审计，不调用生产工具，T17仍不勾选、16/36。

- 2026-10-21：维护语义契约例外只读计划代码ece2b21/候选b820bf6（PR177）已推送39628837038；抽取前7原实现表征、抽取后25目标/3106完整单元零失败跳过、405类型、1023格式及75文档/1358链接通过。新增2原生仅收集，原CLI的预览回滚、apply根提交及旧写入口仍保持原归属；不宣称已接通维护SDK或执行生产工具。失败f87的报告明确为已观察的6/8报告、各档2个RPC比较失败，未将未完成分片视为成功；修正验收独立运行。T17仍不勾选，总计16/36。

- 2026-10-21：修正精确db2b989/39625934747的八分片/JUnit、零重叠完整集合及测试合并父SHA核验通过，两档各4083零失败/跳过，均含10项Solution SDK原根和17项实际处理入口。12检查全部成功，生产CD仍false，PR173正常合并6feb352，tree同a650de27。独立Broker源f572612/工具d0f61bd六档39626265764各10宿主用例/30必需证据、零失败跳过、完整清理；两工具hash、源lock及测试infra合并648ac0b的父SHA均已核验。源PR174与工具PR104其余CI仍待完成，不提前合并或将其计作T17完成。worker原准备的10项原始行为表征已在改动前通过，首次断言误把统一CompletionRecords当独立表已按真实kind作用域修正；只读规划28目标和405类型通过，4原生仅收集，完整本地回归执行中。T17继续16/36，未发布稳定SDK或部署。

- 2026-10-22：Broker源f572612/39626084626八分片与JUnit、完整集合及测试父SHA已核对，两档各4083零失败/跳过；12检查全部成功，生产CD仍false，PR174合并e483f8f，tree同53599a62。infra PR104精确d0f61bd的13检查全部成功并正常合并91a4e76，三项实际工具文件与已验收源逐字节一致；六档10/30真实Broker证据保留。串行worker原准备规划22c95b6/候选46d2697（PR178）本地28目标、3117完整单元、405类型、1025格式与75文档/1359链接通过，4原生仅收集，39631039661待验收；原双CAS prepare+dispatch根未拆开，也未接通worker SDK。T17继续不勾选，总计16/36，生产未改动。

- 2026-10-22：只读候选440461f/39626904176首次8.0.36各4097通过，8.4为4096通过/1失败/零跳过：既有Go发布互操作在publication_grpc:286返回DeadlineExceeded，固定QS2b62432的5秒预算未改，4项新增只读原生两档均通过。8份报告与失败摘要保留，并只请求一次同源失败分片重验。更完整候选73ee3b8/39627648431已通过12检查、完整八分片/JUnit、两档各4136零失败跳过（4只读/12原根与入口）；全部4097旧用例均包含并通过，原实现/探针/锁/工作流逐字节一致，原超时用例两档成功。以完整候选收口原规划与SDK，PR176正常合并0e92008、PR175祖先自动标记合并，tree同004bc993，生产CD仍false；旧失败/重验历史不抹除。

- 2026-10-22：原ResolveUnknown真实Broker扩展源1442bf5/候选74f9d35（PR179）与工具cbe1d9d（infra PR108）已推送；12宿主用例仅收集，35项精确证据要求及79工具单元通过。新增半消息不可见、首审核/wire/witness、FinalUnknown、同调用不重发/不重做模型与竞争裁决回滚；旧10/30报告不能替代。串行dispatch预算/不可变记录只读提取本地19目标/405类型通过，尚未完成原生、提交或发送接线。T17仍不勾选，总进度16/36；未发布稳定SDK、未操作生产。

- 2026-10-22：PR177精确b820bf6/39628837038与PR178精确46d2697/39631039661全部12检查成功；八分片JSON/JUnit及完整不重叠集合、测试合并父SHA已核验，双MySQL各4146/4161零失败跳过，分别含2维护只读与4串行准备原生。生产CD仍false，正常合并24e3326/eb1189e，源码tree一致。原Go发布超时的同源单次失败分片重验39626904176 attempt2完成success，首轮失败与未修改5秒预算记录保留，不覆盖原报告。dispatch只读代码82b403f/候选ceea84b（PR180）完成6原行为表征、19目标、3125完整单元零失败跳过、405类型及75文档/1360链接；4原生仅收集待CI。新Broker六档39635351591仍排队，维护原CLI、完整worker模型容量/终态/恢复及默认装配未转换；总进度16/36，T17未勾选。

- 2026-10-22：ResolveUnknown真实Broker39635351591六档报告、35精确证据、12宿主用例/档及全部清理已核验；wheel0.4.0a1/client5.1.2、两工具hash、source lock和测试infra虚拟合并9118fc9父SHA均匹配。该报告只绑定74f9d35/cbe1d9d，不替代后续worker源码，也不代表成对QS、真实模型、进程/网络故障或system验收。源PR179完整4136双档报告通过，但覆盖汇总尚排队且与后续main文档冲突，等待精确整理和CI；工具PR108其余门禁待完成。完整串行SDK dispatch本地实现中：29原表征及60目标通过，13原生仅收集，继续验证原双CAS、首次模型输入和提交后唯一容量移交；终态、candidate、恢复及默认装配仍未完成。T17仍进行中，总计16/36，未操作生产。

- 2026-10-22：完整串行dispatch源码f1dc4a4加外部调用前Run/owner/version/invocation交接校验9ac16de、文档候选764415c（PR181）已推送；原模型输入加载提取保留旧准入/渲染/提交次序，新路径在同一主库快照读取schema，源会话关闭后才Seal。原根SDK guard后连续两次原CAS，首次CP/输入/账本与最终投影共同验证，witness/首次档案和业务共同提交；只有精确新读取提交证明才能移交原ModelCapacity，重复/未决不授权模型重做。29原门禁、65目标、3157完整非集成/非interop单元零失败跳过、407类型、1032格式及75文档/1362链接通过；15真实MySQL用例仅收集、完整CI待执行，不以模拟sender计作实际Broker或DB网络故障。ResolveUnknown原74f9的12检查已全部成功；因后续main仅文档冲突，保留双方只增内容和源catalog合入为f60f61f并重新验CI，旧Broker报告仍仅绑定74f9。T17未完成/不勾选，总计16/36，默认装配和生产保持原状。
