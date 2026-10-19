# M3 完整实施规划：业务事务接入、稳定发布与生产切换

本文件是 M3 唯一进度总表，维护已批准规划、任务、证据和交付状态。M2 保持 [24/24](rocketmq-m2-execution.md)，不重复计数。最初状态为 0/36；任务通过实现与验证后才勾选，合并、发布、部署和业务验收分别记账。

## 当前执行快照

- 进度：**3/36**；T01–T03 实现及本地验证已完成，仓库CI重跑中（保留初次文档门禁失败）；T04 进行中。
- 隔离工作区：`/Users/yangshujie/.codex/worktrees/rocketmq-m3/{infra,sdk,iam,qs-server,qs-ai}`，各仓库分支 `codex/rocketmq-m3`；原工作区不改动。
- 源码合并：未发生 M3 合并。稳定 SDK 发布：未执行。生产部署/DDL/Topic/ACL/provider 切换：未执行。system 验收与 48 小时观察：未开始。
- 生产前置：QS MySQL 105（旧 Task entry_token 退役）须独立完成原有保护、恢复及验收。源码开发不受阻；T30 及后续生产任务受此门禁约束，不把 105 上线伪装成本批完成项。
- 运行事实使用执行时的只读核验，不从 main、CI 或部署文档推断生产已升级。

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
| 报告生成/失败 | TRANSACTION / qs.mysql | Generation、Report、冻结输入与恢复 |
| Task 开放提醒 | TRANSACTION / qs.mysql | 任务状态、提醒事件与外部提醒幂等 |
| 未来评分/报告重试 | 到期 dispatch 的 TRANSACTION | 原授权、due、attempt、冻结事件与唯一调度责任 |
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
| M3-P | 基线、清单与接入基础 | T01–T04 | ☐ 进行中 | 责任、迁移契约、实现验证与合并 |
| M3-1 | IAM | T05–T08 | ☐ 待开始 | 原事务、幂等与双订阅 |
| M3-2 | QS 领域及调度 | T09–T13 | ☐ 待开始 | 双存储和未来重试 |
| M3-3 | QS↔AI | T14–T20 | ☐ 待开始 | 档案、回执、安全、模型恢复 |
| M3-4 | 故障与运维 | T21–T25 | ☐ 待开始 | 真实故障及切换工具 |
| M3-5 | 稳定发布及候选 | T26–T29 | ☐ 待开始 | 正式制品及最终镜像演练 |
| M3-6 | 生产切换 | T30–T33 | ☐ 待开始 | 105 前置、实际部署及 system 验收 |
| M3-7 | 观察与退役 | T34–T36 | ☐ 待开始 | 48h 观察及责任退出 |

| 完成 | ID | 任务及验收结果 | 状态/证据 |
| --- | --- | --- | --- |
| ✅ | T01 | 执行总表、独立工作区、完整 SHA 基线、证据格式及 PR 台账 | 2026-10-19；实现8e5c9a9；[基线与36项/8里程碑验证](evidence/rocketmq-m3-baseline-20261019.json)；本地提交，PR待创建 |
| ✅ | T02 | 全部生产者/消费者/订阅/Outbox/调度/恢复清单及105前置 | 2026-10-19；[责任清单](rocketmq-m3-inventory.md)/[源码核验](evidence/rocketmq-m3-inventory-20261019.json)：17目录事件、9协议kind、39文件、IAM12版本调用文件、QS8 Stage文件；生产盘点另属T30/T32 |
| ✅ | T03 | 三库预发布依赖、显式配置、owner、准入、预算、生命周期基础 | 2026-10-19；[源码/依赖/审计/验证](evidence/rocketmq-m3-foundation-20261019.json)；IAM e50686c7 / QS98645d817 / AI81db026；race63/56、AI45通过；PR130/407/158草稿；IAM门禁通过，QS/AI文档修复后CI重跑中；真实依赖另属T22/T23 |
| ☐ | T04 | 宿主迁移、索引、档案、V2业务证据与兼容/安装边界 | 进行中；先验证显式schema安装及原始档案与旧Outbox隔离 |
| ☐ | T05 | IAM 所有授权写入口 planner 与精确版本/业务 CAS | 待开始 |
| ☐ | T06 | IAM 原 GORM 事务业务/版本/witness 原子提交 | 待开始 |
| ☐ | T07 | IAM 幂等键/操作查询，重复/冲突/越权/未知验证 | 待开始 |
| ☐ | T08 | IAM 与 QS 双订阅、乱序、freshness 回归 | 待开始 |
| ☐ | T09 | QS Mongo 答卷，202/幂等/callback/未知提交 | 待开始 |
| ☐ | T10 | QS 评分请求、结果和失败，Run 与幂等 | 待开始 |
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
| AI | invocation不增加，frozen/checkpoint/artifact/receipt及unknown原治理保持 |
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
| infra | codex/rocketmq-m3 | [PR37](https://github.com/FangcunMount/infra/pull/37)，草稿 | M3生产变更未执行 |
| SDK | codex/rocketmq-m3 | 无M3变更 | 仍为M2固定预发布 |
| IAM | codex/rocketmq-m3 / e50686c7 | [PR130](https://github.com/FangcunMount/iam/pull/130)，草稿，CI待完成 | 生产未切换 |
| QS | codex/rocketmq-m3 / 98645d817 | [PR407](https://github.com/FangcunMount/qs-server/pull/407)，草稿，CI待完成 | 生产未切换 |
| AI | codex/rocketmq-m3 / 81db026 | [PR158](https://github.com/FangcunMount/qs-ai/pull/158)，草稿，CI待完成 | 生产未切换 |

### 执行记录

- 2026-10-19：批准M3完整规划；已从各仓库origin/main建立五个独立工作区。首次状态0/36，生产前置105独立处理，尚未核验完成。
- 2026-10-19：T01完成。提交8e5c9a9建立完整规划、五库SHA/工作区与证据格式；36个连续唯一任务、8个里程碑、5个隔离分支及diff检查通过；进度1/36，尚未合并或生产变更。
- 2026-10-19：T02完成，进度2/36。全目录与协议kind覆盖核对、39个源码文件摘要及版本/Stage调用扫描通过；IAM维护工具的写入口已显式纳入，sessionrevocation、业务调度、AI未知调用治理继续保留。T03窄基线：IAM授权/原UOW及options通过，QS options/答卷/证据通过，AI29项通过。初次uv因PATH缺失exit127，改用已安装的绝对路径后成功；不隐去该工具失败，不据此声称真实依赖故障或生产验收已通过。
- 2026-10-19：T03源码基础完成，进度3/36。三库固定M2预发布；显式owner/store/epoch/v2/预算与无网络、无DB查询的构造通过。宿主准入与SDK最终关闭分开，暂停保留Checker，ShutdownIncomplete继续Wait；旧Relay装配拒绝事务配置。IAM63/QS56目标race节点、AI42项均0失败0跳过，QS679回归通过，IAM96通过/1既有MySQL依赖跳过；后者不计为原事务证明。Go vet、Python lint/type和文档门禁通过；SDK失败交接重审与失败历史留证。PR130/407/158草稿已提交，合并/真实Broker验证/生产仍未完成。本机Docker未运行，不启动已有依赖；后续真实存储用隔离CI。
- 2026-10-19：T03自审补充81db026，关闭预算为负数/NaN/无穷时在封准入之前拒绝，AI最新45项0失败0跳过；初次42项证据保留历史。infra PR37建立，全部PR仍草稿，仓库CI排队/运行中，未创建稳定tag或生产变更。
