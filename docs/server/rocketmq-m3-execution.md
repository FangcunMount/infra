# M3 完整实施规划：业务事务接入、稳定发布与生产切换

本文件是 M3 唯一进度总表，维护已批准规划、任务、证据和交付状态。M2 保持 [24/24](rocketmq-m2-execution.md)，不重复计数。最初状态为 0/36；任务通过实现与验证后才勾选，合并、发布、部署和业务验收分别记账。

## 当前执行快照

- 进度：**9/36**；T01–T09 实现与任务必需验证完成。T09最终源码/同包策略及本地、云端16项原生验收通过，PR411及infra PR46的当前头完整CI通过并合并，合并记录独立保存；M3-2尚未完成。生产切换未执行。
- 隔离工作区：`/Users/yangshujie/.codex/worktrees/rocketmq-m3/{infra,sdk,iam,qs-server,qs-ai}`，各仓库分支 `codex/rocketmq-m3`；原工作区不改动。
- 源码合并：IAM PR134/135、QS PR409及SDK修复/索引PR46/47已合并；infra PR41已合并d544918f。固定Go修订预发布tx.2已发布并重验；稳定SDK配对发布未执行。生产部署/DDL/Topic/ACL/provider切换未执行；system验收与48小时观察未开始。
- 生产前置：QS MySQL 105（旧 Task entry_token 退役）须独立完成原有保护、恢复及验收。源码开发不受阻；T30 及后续生产任务受此门禁约束，不把 105 上线伪装成本批完成项。
- 运行事实使用执行时的只读核验，不从 main、CI 或部署文档推断生产已升级。
- 当前批次：T09实现与验证完成并勾选，原事务入口[QS PR410](https://github.com/FangcunMount/qs-server/pull/410)已合并3afc76a6；装配[QS PR411](https://github.com/FangcunMount/qs-server/pull/411)源码race6909通过/60既有可选依赖跳过，16项原生验收本地及云端0失败/0跳过。同包策略修复及当前头完整CI通过，PR411合并733ce4d8、infra46合并1f2c2ad7。下一项T10在独立qs-evaluation工作区推进；生产CD仍暂停。[本批证据](evidence/rocketmq-m3-qs-answer-20261020.json)。

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
| M3-2 | QS 领域及调度 | T09–T13 | ☐ 进行中 | 双存储和未来重试 |
| M3-3 | QS↔AI | T14–T20 | ☐ 待开始 | 档案、回执、安全、模型恢复 |
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
| ☐ | T10 | QS 评分请求、结果和失败，Run 与幂等 | 进行中；三个原事务入口/共享owner装配完成。25501aac7完整UTC race6977通过/0失败/60既有可选跳过；与原生36aa仅两个单元测试差异。两档真实Broker各9项通过/0失败/跳过/race。[证据](evidence/rocketmq-m3-qs-evaluation-20261020.json)含失败历史；当前头CI/PR412及infra49合并待完成，不提前勾选 |
| ☐ | T11 | QS 报告生成/失败，冻结与终态恢复 | 待开始 |
| ☐ | T12 | QS 提醒事务、最终 NORMAL 与 fanout | 待开始 |
| ☐ | T13 | 到期 dispatcher、重试授权、交接和 Replay 边界 | 待开始 |
| ☐ | T14 | QS command/档案，Operation/Payload新旧兼容 | 待开始 |
| ☐ | T15 | QS AI事件 Inbox/投影/首次ACK/witness原子提交 | 待开始 |
| ☐ | T16 | AI command admission/receipt 原事务与根提交归属 | 待开始 |
| ☐ | T17 | AI interpretation/evaluation计划冻结，退出commit hook编排 | 待开始 |
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
