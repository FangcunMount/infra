# M5 首批执行包：空 QS AI 发布表

**当前状态：2026-11-01 03:58:04 CST 首批生产发布完成，clean111/44，六实例就绪、原入口恢复、自动CD继续冻结。** [实际发布回执](rocketmq-host-retirement-m5-production-release.md)及[结构化事实](../evidence/2026-11-01-host-retirement-m5-production-release.json)为最新结果。首次业务启动后禁止回放旧110账本；其余五对象及全部历史凭证保留。

以下为 01:55 CST 的原审查包快照。原待执行项和阻断项保留用于审计，不再描述当前生产状态，不是可复用批准或可重放窗口。

本包已形成具体执行审查稿，**实际窗口门禁尚未通过，不可开始停写/SQL111**。用户随后明确要求“继续执行，直至 M5 完成发布”，本任务据此继续完成隔离验证、固定制品及真实窗口；这是目标授权，不能代替当次事实、机器可消费批准或首次启动屏障。数据责任人、恢复责任人均为 **shujie**。截至2026-11-01 01:55 CST，业务、入口和数据库保持原状。

唯一拟删除对象为 `qs.mysql.ai_messaging_outbox`，转换为 `110/44 → 111/44`。另五候选继续保留；事务 execution/guard/witness、原 wire/archive、Inbox、业务 ACK、历史及重试/hold/调度全部保留。此文、附属 JSON 和命令样式均不是 `qs_schema_pair_offline_upgrade` 批准，不生成可消费批准文件。

审查索引：[结构化执行包](../evidence/2026-10-31-host-retirement-m5-execution-package.json)、[交接与历史证据](rocketmq-host-retirement-m4-m5.md)。表中“待执行”是未来独立获批窗口中的动作。

## 1. 审查结论与执行阻断项

| 门禁 | 当前结论 | 关闭方式 |
| --- | --- | --- |
| G01 独立暂停 | 原生13+9项已通过；最终forward扩展与真实交接待完成。已实现原配置/身份绑定、关闭新发送的独立维护owner候选；生产尚未注册 | 先独立交付/验证该机制；保持原预算、无新增业务发送，不把进程内方法伪装成 HTTP 接口。选定独立维护owner接管最后Checker；实现和真实原生验证见下文，未通过前不停止原owner |
| G03 发布/恢复镜像 | 阻断。最终受核main runtime三镜像和同111兼容的前向恢复候选尚未在目标主机固定 | 在不解冻 CD 的独立构建/制品流程中补齐来源、digest、config ID、本地 engine ID、配置、原生/启动证明；没有获批替代入口则保持阻断 |
| G04a 完整保留资产基线 | 真实隔离已通过，生产只读预算复验进行中。QS #477已补齐完整SQL列/BSON多重集基线及原材料导出候选；真实隔离和生产只读耗时仍待通过 | 先审定只读导出命令、类型保真编码、全量覆盖、实际权限和耗时预算；只在真实W06获取同窗口材料 |
| G07 服务器DDL/锁观察 | 既有管理员路径与实际只读110观测已通过；窗口逐步重读待执行 | 使用固定m5-activity-admin入口取得14项独立观测；不擅自扩大权限、不把时点零值视为冻结 |
| G05 实际恢复运输 | 真实独立Go CLI隔离验证已通过；最终main绑定及生产材料待执行。生产路线改选同一Go维护二进制的独立原状恢复入口；原Python依赖探测只保留历史归属 | 用同镜像/UID/TLS/材料格式演练中断、拒绝和提交未知；审核原账本回放字节、耗时和首启动屏障后再关闭 |

G02 实际排空/自主过期与 G04 同窗口保护必须在未来真实窗口取得，当前不能预填通过。G06已有继续至发布的用户目标授权，实际停写、迁移、必要恢复和新runtime启动仍须把当次事实绑定到独立受控步骤；不再重复询问目标授权，也不提前签发可消费批准。G07现业务账号1142的原记录保留；已通过既有管理员Secret/可信SSH路径取得有效观测，未GRANT或激活角色。窗口必须重新读取，不把历史观察作为停写证据。任一门禁缺失即不进入维护窗口。包内有缺口不会自动放宽标准。

## 2. 已固定的源码、只读事实与现网对象

QS 源码 `be2e4e8d7fe5a9cb5be3763ac51e64bc3fe00399`，精确 main CI41204413865 成功；本包基于 infra #417 head `6ddbb851280a3f2f59778441b90e7fcc187a8cba`。QS Production Deploy 实读 `disabled_manually`，本轮未启用。其他库的发布开关不在本包中擅自改变；所有可能部署 QS 写者的人工/自动入口仍须窗口排除。

[只读41209690150](https://github.com/FangcunMount/qs-server/actions/runs/41209690150) 的reader和四owner成功；五份原ZIP、原二进制与JSON/DDL/EOF均在MacBook校验。六候选为零行，IAM45、QS110/44、AI0043；QS两owner各未决项为零、native-limit未激活。AI结果历史125、Inbox57。它们均是未停写时点的观察，不是同窗口保护/无写者证明。原51条缺失发布事务锚点和QS业务观测缺口仍独立保留。

| 固定项 | 值 |
| --- | --- |
| 执行器 SHA256 | `8ab07b2616c65fba6ad8f9c6f21777e3a2568ecc93cc131664a4255c001cb0ac` |
| 嵌入资源 SHA256 | `b8c09d87a02432f9c4f01fdbf01d7fa2dd7ecbf3ebdaf3576b2e61f02e7ea6de` |
| QS MySQL 身份 | `833eb55bdcba767dc66f0b02da8315f5ba1fc7c52848fc517edb4a5bd4bf7b32` |
| QS Mongo 集群身份 | `318f0d870223acb5a967888e425ee93650567cf1260d5023081889286966762d` |
| 原目标 DDL SHA256 | `1950d488e5e83afdacce15b2bc47fb1126a9d622519c5da3a3b8bbaf672735da` |
| 原账本 DDL SHA256 | `e663736774931e5f988b7fa72a0849fa725ae3ba97f083df404b676d64b616ee` |
| 原完整账本 | 两列 `version,dirty`；完整单行 `110,false`，0900 collation原DDL |
| 原 body/wire JSONL | 0字节EOF，SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |

本轮22:47左右直接只读核对A/D：以下六QS实例均running、0重启，源码均为 `a792c60162d2cb8435b5a9c7e04ecf963330c7dc`。完整64位容器/镜像ID、实际Compose路径、配置摘要在结构化包中，窗口必须重新逐字匹配。

| 主机 | 容器 | 当前 engine ID 前缀 | 现网配置 |
| --- | --- | --- | --- |
| A | qs-apiserver | 4185fd2487b8 | `/opt/qs-server/qs-apiserver/ai-mq-releases/a792c60162d2cb8435b5a9c7e04ecf963330c7dc/apiserver.json` |
| A | qs-collection-server-1、2 | 21fe0619dfb8 | 当前部署生成的Compose与原配置挂载 |
| D | qs-worker-runtime-1、2、3 | ae7f6d5fe260 | `/tmp/qs-deploy-worker-3146535/docker-compose.prod.yml` |

API实际Compose project是 `qs-deploy-apiserver-3703660`，不是旧文档的 `servera-migrated`；API和Worker当前StopTimeout=510，Collection未设置。旧 `m4_runtime_start.py` 绑定2026-10-27的另一组镜像/目录，本批不复用它。回到原M4只复用本包冻结的原容器ID与原配置，不能调用旧固定启动器或让临时Compose路径自动选择新对象。

维护容器为 `qs-m5-maintenance-41209612364-1`（完整ID `d281c02c94821efba06013e36a8fca561e8c502e076a812dddbf5d387da91720`），Image4185fd…，UID2000、仅sleep、healthcheck NONE、仅infra-network、借用挂载全部RO。本轮未复用operation或清理私有标记。

## 3. 单一协调位置、锁与时间预算

未来操作目录固定为 MacBook `/Users/yangshujie/.codex/m5/windows/<当次数字operation-id>`，0700、文件0600，不复用既有操作。不在本轮创建窗口目录或填写T0。操作开始前把固定源码/脚本/镜像/配置清单、保护范围、恢复和启动回执绑定为独立审查摘要。

复用 `scripts/rocketmq/start_boundary.py` 与 `scripts/ops/m3_operator_step.py` 的现有单一屏障，但**仅在W06实际保护材料取得后initialize**，绑定真实同窗口protection摘要；不能在W00用未产生的保护哈希初始化，也不能把旧演练材料假充同窗口材料。W07之后每个SSH步骤绑定原字节脚本摘要、主机、预算；所有业务启动（包括R1恢复原M4）先持久化first-runtime标记，再发命令。W06之前仅执行独立受审的入口/暂停/排空步骤，没有数据库写入；如走R0，先在当次准备目录持久化`window-cancelled`和`runtime-restart-issued`原件再启动原容器，永久取消该operation、不再尝试初始化迁移或回放账本。

A/D两个持续受控的操作会话分别持有既有 `/var/lib/fangcun-image-retention/deploy.lock` 原inode至窗口结束；不创建、替换、chmod锁。会话内直接执行已审定命令，不能再套会重复取同一锁的旧启动器造成自锁。跨A/D不宣称分布式原子锁：两端排他持有回执、CD冻结和人工入口排除必须同时存在；任何端会话中断或锁失效停止全部后续动作，重新盘点而非自动接续。锁会话的实际启动/保持/中断行为也须随G01隔离验证，不宣称本轮已部署协调器。若触及AI部署锁，仍沿既有顺序；本批不部署AI/IAM。

屏障步骤类型必须匹配现有状态机：W08的apply与W09的全部post-check合为一次`pre-start-maintenance`受审脚本，只有全部通过才返回maintenance_returned。失败/断线留maintenance_failed/issued；R1以**独立、一次性摘要的`pre-start-repair`**执行精确原材料恢复和完整110/44复验，成功回到maintenance_returned后才允许runtime-start。R1失败不重用原repair批准。现有`pre-start-restore`返回restore_returned后不允许直接start，本批不选这条无法闭合重启的组合，也不编辑state.json绕过限制。此实际组合须纳入G05隔离验收。

正常窗口上限1800秒，自第一次实际关闭写入口T0计时；最少900秒用于新runtime启动与回读，SQL111只能在 `T0+900秒` 之前进入且批准仍有效。排空、材料生成或检查未在预算内完成就取消本次迁移，不延长窗口、不缩短原回查/租约预算。恢复自决策起最多3600秒，超出视为恢复失败并升级处置；隔离毫秒结果不承诺生产RTO。保护材料至少保留30天，未结责任延期，无自动清理。

## 4. 写者清单和未来停写/排空步骤

| 写者/入口 | 窗口动作与证据 | 禁止替代证明 |
| --- | --- | --- |
| QS/Collection公网HTTP、WS、直连端口 | 精确两站点维护503；停接WS新连接，核对既有请求/长连接完成；排除旁路与本机入口 | 修改DNS、关闭单个location或只看503 |
| Collection两个副本 | 准入关后优雅排空，确认原ID退出、无在途gRPC/RPC | 只看HTTP ready失败 |
| Worker三个副本 | 停止新增消费/hold/deferred动作，完成已接受handler/RPC，原ID退出及成功关停回执 | 自动重试开关false、消费offset、ACK为零 |
| API外部/内部gRPC、直接维护调用 | 排除所有调用者；保留处理已接受请求所需的RPC和原owner依赖，最后确认活动为零 | 提前封内部端口导致在途提交失败 |
| API内部调度 | 计划/错过过期、统计同步、评估一致性、租约恢复、报告catalog、retry dispatch、模块消费者逐项关闭新调度并等待原执行完成 | 仅关闭plan_scheduler或automatic-retry |
| 手工/自动维护 | qs-operator prepare/recover/selected/orphan、qs-ai-messaging admission、迁移器、部署、定时器/cron、独立脚本逐一登记并排除 | 仅以QS CD disabled证明全部工具停写 |
| IAM/AI/Broker及其他调用者 | 本批不重复部署；Broker/回查服务保持。若会继续写QS受保护资产，须具体隔离该写路径并证明在途完成；做不到就取消本窗口 | 把未停的其他进程自动视为无关 |
| MySQL EVENT、Mongo TTL/自主过期 | 同窗口读取实际定义、作用集合和将到期对象，证明不修改本批保护资产 | 只停容器；自行关全局TTL、改删除预算 |

当前API配置实读启用 `plan_scheduler`（含missed expiration）、`statistics_sync`、`evaluation_consistency_audit`、`evaluation_lease_recovery`、`interpretation_lease_recovery`、`report_catalog_audit` 和modelcatalog消费者，手动动作也启用；migration.enabled=false/autoseed=false。不能据此假定API静止。

执行顺序（用户已授权推进至发布；各步仍须实际事实与独立步骤回执，当前全部未执行）：

| 步骤 | 动作 | 通过条件/停止点 |
| --- | --- | --- |
| W00 | 复读精确源码/镜像/配置/六实例/维护容器，持原锁；排除所有人工/自动发布与其他写者 | G01/G03/G05关闭；身份漂移、未知调用者或原材料不可读立即停止，T0不开始 |
| W01 | 持久记录T0；只替换A的QS与Collection两站点为独立审定closed字节；nginx -t成功才reload | 真实HTTP/HTTPS新请求503；其他域名/TLS和原内部排空依赖保持；失败恢复两份原字节并验证，不停服务 |
| W02 | 先启动固定Go维护owner，使用原配置/双库/原binding、关闭新发送；验证两个真实Checker已注册且观测可用新鲜 | 原API仍运行；记录重叠资源/并发上界，不修改每实例或Broker预算；失败保留原owner，不进入停止步骤 |
| W03 | 有界排空Collection/Worker的已接受请求/handler，先结束生产方与消费者的新工作，再优雅退出这五个原实例 | 保持API owner与必要RPC存活；不使用自动SIGKILL的默认10秒stop、rm、down、改规模或purge。任何非零退出/超时不签排空 |
| W04 | 在维护Checker已接管且五实例成功退出后，优雅停止原API及其全部调度/业务入口；维护owner保留原DB池和Checker | 原API退出0，正常业务/provider回调终结；超时/失败不强杀、不签排空；直接主库、实际SDK及正常退出分别取得回执 |
| W05 | 维护owner持续完成原Broker确认/回查；真实排除全部业务写者后，提交绑定真实停写回执的独立stop.json | 主库全部未决/年龄零、native-limit=false、SDK在途/运行/排队零且可用新鲜；仅在实际SDK与进程成功退出后捕获静态保护。SIGTERM/deadline本身不关闭最后Checker；失败保留其依赖并走R0受控移交 |
| W06 | 确认六实例均停止、无旁路与自主事实变化，捕获第5节同窗口完整材料 | 任何未知、缺失、冲突、截断、预算不足均取消本次迁移；不清理记录造零 |
| W07 | shujie完成具体审查后，另行生成一次性0600批准，重新核过期/源码/身份/资源与剩余900秒启动预留 | 本包自身不提供批准；首次尝试/未知回执和消费标记永远保留 |
| W08 | 在原维护容器内仅执行固定qs-migrate-offline的`--apply --approval-file --approval-sha256`入口 | 仅SQL111的目标WRITE锁内完整COUNT=0才删除；Mongo44不变。非零/未知立即R1；不重试DROP/Force/down |
| W09 | 独立读实际clean111/44、目标确实缺失、保留资产与身份一致 | 旧组合材料清单要求110/44，不能拿它在111上的失败或缺表当通过；使用standalone canonical与独立保留资产校验 |
| W10 | 写入不可逆first-runtime标记；启动已固定111兼容API，再Worker3/Collection2，保持外部维护 | 新启动命令发出即进入R2；即使未ready也禁止R1旧账本回放。验证六实例源码、镜像、迁移关闭、owner/consumer、真实业务观测 |
| W11 | 在1800秒预算内完成业务验收与保护材料归档，单独批准恢复入口/发布 | 任何业务观测不可用不得放行；不自动解冻CD，不把本批完成等同另五对象或51条历史责任关闭 |

API/Worker代码中的关停回调有30秒等待及失败exit1语义；Docker StopTimeout510不是“业务已经排空”的证明。a792→be2的相关API/Worker关停、Container/Subsystem及TransactionRuntime生命周期文件本轮diff为0，源码边界可沿用；仍不能替代生产实际退出。计划的非强杀终止应先核目标Docker CLI语义，再使用只发SIGTERM且不自动强杀的受审方式，操作者超时只停止等待，不证明服务器操作已结束；本包不签发未经验证的stop命令。

## 5. 同窗口保护材料：范围、格式、获取点

此处定义未来W06必须产生的材料，**当前没有同窗口材料**。本轮22:25只读材料作为结构/身份对照保留，不能改名成为T0备份。

位置提案：A `/var/lib/fangcun-m5-protection/<operation-id>/`、MacBook操作目录下`protection/`各一份；目标目录/文件0700/0600、属实际受审操作者，不允许symlink、覆盖旧operation或把凭据放argv/日志。生产创建/复制这些位置仍是未来受审步骤，当前只存在MacBook本地审查材料。两份分别计算原字节哈希、完整读取验证和fsync回执；保留原始批准/消费标记、所有失败输出。SQL凭据与材料分开，不进入GitHub或本包。

| 文件/集合 | 具体要求 |
| --- | --- |
| `freeze-receipt.json` | W01–W05原步骤/时间、六原容器ID/镜像/退出、A/D原锁身份和排他回执、全部写者排除、原业务/provider结清、主库事务/活动、TTL/EVENT影响与责任签收；runtime_frozen只能据事实为true |
| `pair-before.json` | 原clean110/44、完整资源/二进制/源码及双库身份、原两binding摘要；独立读取时间，禁止伪造跨库原子快照 |
| `ai_messaging_outbox.original.sql` | SHOW CREATE原字节、不自动加改定义，含原charset/collation/索引；哈希/原对象身份/依赖可见性一起保存 |
| `ai_messaging_outbox.original.jsonl` | 同一只读事务中的COUNT=0与body/wire原流真正EOF；文件恰0字节。任何一行/无法读取均停止，不导出后删除非空记录 |
| `schema_migrations.original.json` | SHOW CREATE原字节、明确两列规格与完整单行原值110/false，原DDL哈希；不是只存version数字。Mongo原head完整BSON/类型/字段/身份也保全且不回放 |
| `retained-catalog.json` | 实际QS MySQL全部表/视图/程序/事件及Mongo全部集合/options/有序索引/UUID清单。缺失必需对象或未知新增对象独立审查，不能排除后继续 |
| `retained-baseline/` | 对以下保留范围和实际catalog中的其余业务对象，保存DDL/索引、完整行/文档计数和确定性全量内容摘要（类型/NULL/二进制/顺序保真）；不只取前10000条、不用估算row_count或分区汇总当内容证明。冻结后两次基线相同才继续 |
| `operation-evidence/` | 工具/镜像/配置清单、全部步骤stdout/stderr私有原件、退出与服务器活动回执、首启动屏障、批准原文/摘要/消费标记。公开台账仅保存摘要、数量和分类 |
| `protection-manifest.json` | 逐文件路径/字节数/SHA256/捕获时刻/原库和operation绑定/完整性与可读性；独立副本摘要、data/recovery owner、实际保留期限；缺字段/截断为不可用 |

最低具名保留集：`rm_tx_binding/request/execution/witness`（含execution内guard状态）、`messaging_native_limit_notices`、`ai_messaging_archive/inbox/admission`、`rm_outbox`、`qs_retry_schedule_schema/qs_retry_schedule`、`task_opened_reminder_batch/delivery`、现有业务状态/ACK/transport evidence、Mongo原事务/notice/Outbox/答卷/报告/重试与恢复材料，以及catalog所有其他业务对象。名称以实际catalog与固定迁移/SDK源码核对；不能从本列表推断未列对象可丢弃。IAM/AI原凭证、ACK、历史、调度原位保留；继续运行的库不伪造静态全库内容哈希。

差异白名单只有两项：成功111路径的目标表由原空表变成缺失，MySQL完整版本账本由原110/false变成111/false；Mongo44完整原head不变。R1步骤5比较时暂保留已知中断账本111/真实dirty值，只有最后账本事务可回放110/false；步骤8要求全部回到原基线。除这两个明确、按阶段审核的对象外，其余结构/完整内容摘要不得变化，不能因为版本账本必然改变而放弃比较其他资产。

诊断 `system.profile` 单列原UUID/options/索引/当前状态，允许其按既有策略自然增长，既不恢复也不改配置；这不是允许其他集合变化的通用例外。TTL或其他任务若触及受保护业务事实，不能仅声称“影响小”；保持原策略并取消本次资格，另行设计隔离。

原清单入口可以产出目标DDL/EOF/完整SQL账本和canonical预览，但**没有覆盖以上全部保留资产内容基线**。W06前须补齐受审的只读全量基线导出命令、权限、确定性编码、实际行数/大小和有界预算；超预算取消窗口，不能偷偷缩样。这里定义的是验收要求，不宣称导出器已安装或材料已取得。

## 6. 已选定的生产恢复运输与会话约束

当前路线为[QS #477](https://github.com/FangcunMount/qs-server/pull/477)候选`7f8390c74aec46954d3fd2578e32dd06629400d3`中的同一个静态Go维护二进制，最终生产必须重绑定合并main、实际原生CI、二进制摘要与同窗口材料。aa1387b79的真实CLI门禁已通过；最终候选完整CI及forward owner扩展仍待通过，未通过不使用。原迁移资源字节保持不变。

- 同窗口只读：`--retained-baseline --timeout=2m`两次完整覆盖SQL所有列和原BSON/所有定义；预算或非空业务TTL集合失败，不截断。`--capture-original-operation`输出原目标DDL、完整单行110/clean账本及完整基线，0600保存原字节。
- 中断只读：`--restore-original=<私有原材料> --restore-original-sha256=<原字节摘要> --timeout=2m`读取实际111 dirty/clean或原110，复核所有保留资产。目标、账本两个阶段白名单之外任何变化拒绝；Mongo44从不回放。
- R1实际动作另加`--restore-apply --restore-approval-file --restore-approval-sha256`。独立批准kind为`qs_m5_original_empty_restore`，绑定实际state/原材料/源码/停写及首启动边界/审查回执、shujie双责任和至多一小时恢复预算。重新实读后独占消费；只恢复缺失的精确原空表，再校验保留资产，SERIALIZABLE根内锁定完整实际111单行并回放捕获的完整原110/clean单行。
- DDL部分成功、事务失败、commit未知分别保留；不自动重试、不清dirty。新增真实隔离CLI覆盖三中断、首次启动/停写及事实变化拒绝、实际INSERT权限失败后DELETE回滚。外层仍负责服务器活动/排他和`pre-start-repair`，启动后只准111前向路线。
- 原维护容器UID2000、借用挂载只读、原VERIFY_IDENTITY/CA及显式QS库不变；无业务Container/调度/新发送。登记同一版本原生CI与实际耗时后再关闭G05。独立批准格式及全部字段以QS类型为准，不从本文生成占位批准。

### 6a. 历史Python候选探测（未被当前路线采用）

本包选用独立、固定客户端会话，不把测试函数搬到生产。客户端基于A已有镜像 `sha256:18a39e862a82bfb9b503a3dd93639688bc45016caa2c7f1bf9081953b4523fa0`，源码f9f24ab…，入口`/app/.venv/bin/python`，Python3.11.18/asyncmy0.2.14；本轮在实际镜像内以UID2000只导入依赖并核CA可读，未连接数据库。未来由受审脚本创建独立客户端容器，替换原应用入口；不在运行AI业务进程内恢复。

未来Docker参数固定为：本地engine ID、`--pull=never`、infra-network、UID2000、`--no-healthcheck`、`--entrypoint /app/.venv/bin/python`、借用原QS维护容器挂载`:ro`、只读挂载当次材料/会话脚本、仅传QS MYSQL字段的私有env-file。不传Mongo写凭据，不运行AI Settings/业务启动/模型/消费者/调度。不复用旧客户端或私有标记；会话输出私有保存。具体operation名称/脚本哈希/材料挂载UID权限必须在G05演练并审定，当前没有创建该客户端。

MySQL连接严格使用QS原 `MYSQL_HOST`（host:port）、显式database=qs、原username/password、VERIFY_IDENTITY和原CA。Python必须显式构造`ssl.create_default_context(cafile=...)`，保持hostname check与CERT_REQUIRED，禁止tls降级/自动选择其他库或打印DSN。客户端设置有界连接/读取/锁等待、单连接，当前元数据与行数逐步回读；DDL不承诺事务原子性。端到端TLS/实际权限尚需G05验证。

会话前先读取 `@@server_uuid,DATABASE()`，按canonical源码的紧凑JSON数组 `["mysql_server_selected_v1", uuid, "qs"]` 计算SHA256并匹配当次保护manifest/本包身份。Mongo身份/44 clean与原head由独立只读reader核对，不能让SQL客户端擅自修改。恢复期间持原部署锁和同一首启动屏障；只有真实、未损坏且没有任何启动尝试的屏障允许R1。屏障丢失或任何带外启动按已启动处理。

## 7. 恢复决策表与精确 SQL 会话步骤

| 分支 | 触发状态 | 唯一路线 |
| --- | --- | --- |
| R0 DDL前取消 | W07前或确认从未消费批准/未发SQL111；原110/44及保留资产仍完整 | 不做任何数据库恢复；确认排空失败原因/活动已稳定，关闭本窗口，先写首启动屏障再恢复本包固定原M4容器；验证健康后独立恢复入口。批准不得复用 |
| R1 首启动前恢复 | 已消费批准，111 dirty/clean或删除结果未知，但从未发任何业务runtime启动命令 | 全部QS写者保持停止；先核服务器真实DDL/锁/事务和当前结构；只恢复原空表，最后独立批准完整原账本回放。通过110/44及保留资产验证才可起原M4 |
| R2 首启动后失败 | 已发第一个业务runtime启动命令，包括失败/未ready/带外启动 | 保持111、关闭外部准入；保留新事实，用已固定111兼容候选/补丁前向恢复。禁止原110账本回放、旧备份覆盖或在111启动只认110的M4 |

R1使用当次原材料的受审会话，顺序不可交换：

1. 记录恢复决策时间及独立批准摘要。确认同一operation、原双库/原锁、六业务实例确已停机、无重生或旁路、无first-runtime标记。读取实际进程/metadata lock/事务状态，确认原迁移会话已结束；权限不足或不能排除服务器DDL仍执行，保持停止，不KILL未知连接，也不重试迁移。
2. 验证原材料两份可读且哈希一致；完整账本DDL必须为原两列0900定义，原完整单行必须为110/false。任何材料截断/新列/第二行或identity漂移停止，不能回退成数字改head。
3. 只读盘点当前状态。仅允许已知中断111（dirty true/false）或完全原110/false；其他版本、Mongo非44 clean、目标非空/DDL不符或保留资产变化均停止独立审查。
4. 若原空表仍存在：核原DDL和完整COUNT=0，不DROP/TRUNCATE/覆盖。若确实不存在：仅执行当次捕获并独立审核的完整`CREATE TABLE ai_messaging_outbox ...`原字节；不使用`IF NOT EXISTS`掩盖冲突，不执行旧迁移/全部up/down。该DDL可能已自动提交，失败后保留部分状态，重新只读分类，不自动重试。
5. 再读原DDL/零行EOF、Mongo原head/身份、完整保留资产基线。只有一致才进入账本事务。先重查无写者/无启动标记；失败不得提前把账本标clean。
6. 在同一个专用SQL连接中执行下述受审事务，操作员/客户端逐步检查真实返回，任何断言失败或事务前后身份/屏障变化均ROLLBACK并停止。不是允许复制粘贴整段后忽略结果：

   ```sql
   START TRANSACTION;
   SELECT version,dirty FROM schema_migrations FOR UPDATE;
   -- 必须恰一行，且与步骤3刚观察的111/dirty原值完全一致。
   -- 若已经是原110/false，不执行DELETE/INSERT，ROLLBACK后走独立验证。
   DELETE FROM schema_migrations WHERE version=111 AND dirty=<刚锁定的真实布尔值>;
   -- 客户端要求affected_rows恰1；否则ROLLBACK，禁止继续。
   INSERT INTO schema_migrations(version,dirty) VALUES(110,FALSE);
   -- 值来自当次原完整单行，不接受任意目标版本参数。
   SELECT version,dirty FROM schema_migrations;
   -- 必须与捕获的完整单行逐值相同；客户端要求恰1行。
   COMMIT;
   ```

   SQL中尖括号故意不能直接执行。最终会话脚本必须绑定当次完整原行/当前锁定行，并在审查中冻结脚本字节及参数，G05实际断言affected_rows、失败ROLLBACK和提交未知。这里是完整原单行回放，不是Force、手工清dirty或普通版本UPDATE；它只在单独批准的R1路径允许。

7. COMMIT结果未知：不重发DELETE/INSERT；保留原输出，建立新只读连接读取全表/原DDL/资产。仅当实际完整原110/false、原空表和Mongo44/保留事实全匹配才登记恢复已验证；任何其他状态继续停止并独立复核。
8. 用固定canonical默认只读CLI核原clean110/44、资源/身份，并独立核保留资产；释放所有恢复/检查连接。签收恢复回执与实际耗时，R1受审pre-start-repair仅在全部验证成功后返回maintenance_returned；确认原M4镜像/配置仍在，再经runtime-start持久化首启动标记，按原API→Worker3/Collection2恢复原容器。这里恢复的是当前a792原容器，不是旧2026-10-27固定启动器。

R1真实客户端演练必须覆盖：dirty_before_ddl、dirty_after_drop、clean_before_runtime、原表非空/错DDL、身份或账本结构漂移、第二行/提交失败/提交未知、保留资产变化、任一runtime启动标记（含损坏标记）。前3成功，所有拒绝场景均不提前改账本，Mongo44与其他资产保持。旧Go隔离测试仅作对照，不替代此路线验收。

R2没有已安装通用“恢复API”。其具体可用候选必须在G03固定并通过111构造/就绪/业务与无重复效果验证，否则不批准W10，更不能用“届时向前修复”填空。原凭证/ACK/调度禁止reconcile、重投或删除来消除观察缺口。

## 8. 入口字节和回读/放行标准

只涉及A两文件：`/data/apps/nginx-configs/qs.fangcunmount.cn.conf`、`collect.conf`。原SHA256分别 `26efeedd9f41e913b751f355977635efb8ab693eab179ec47b6f78a9ef85a156`、`bb122f4c320c1f6f9532b0ee232dba4971e26409f63133accb01c8b0b513b8d5`。保持现有condition-retirement gate及其他原指令；IAM/AI/后台/Metabase等不切入口。

本轮仅在MacBook用既有纯渲染器`m3_nginx_gate.render(original,'closed')`生成两份closed候选，各在两个精确server块新增503；原/closed字节和摘要私有保存。未修改主机文件、未reload，也没有把纯渲染当作当前组合`nginx -t`通过。W01前必须用当前固定Nginx镜像/其余原配置，在非活动组合验证语法，再保存真实原字节/owner/mode、精确替换两文件、`nginx -t`成功后reload；失败立即恢复原字节并复测。

回读分三层：原主库协议观察；真实进程SDK/Checker活动；实际业务/provider/ACK责任。任何一层不可用都不能用其他层零值替代。原报告的`no_observed_unresolved`不证明Broker积压为零，不删除计划或重做模型。技术指标来自源码`internal/pkg/messagingruntime/transaction_metrics.go`，其active_sends/running_checks/queued_checks与observation_available/fresh分别保留；累计outcomes/checks不是当前积压。

本轮附加尝试读取A `http://127.0.0.1:19090/metrics`被对端关闭，无有效回执；不解释成技术状态为零。最终受审metrics/业务读取端点与授权方法须以实际部署配置和成功原始回读固定，不能臆造该端点可用。

## 9. 初始审查轮交付、验证与接续（23:02历史记录）

本轮产物为本文件、结构化JSON、私有A/D只读快照、原/closed候选、既有41209690150原ZIP与校验清单、本地完整审查归档。原仓库main均未覆盖；infra独立分支`codex/m5-execution-review-local-20261031`，当前尚未推送或修改远端#417。

本轮验证：实际六实例/维护身份和配置只读核对、关停源码a792→be2相关文件零差异、固定Python客户端两UID依赖/CA探测、JSON解析/范围一致性、入口纯渲染与原字节哈希、git diff检查。没有新真实恢复、完整停写、同窗口备份或新镜像生产验收；各项结果按原执行归属保留。

本地额外验证现有屏障/适配器/入口渲染26项单测全部通过（5+17+4）。另用任务独占临时目录实际执行本包所选状态组合的5项断言：apply未知→failed、failed拒绝start、独立R1 repair→maintenance_returned、start前持久标记、start后拒绝所有旧恢复路径，全部通过；回调仅本地空操作/受控失败，没有SSH或数据库调用，不计为G05实际恢复运输验收。生产恢复脚本、保护材料和业务验收仍未提升状态。

下一工作批次已经明确：先解决G01的运维能力与成功业务/技术观测入口、G03固定制品、G05实际客户端隔离证明及W06全量只读基线命令；这些准备可以继续在隔离环境完成。然后提交具名停机/数据库执行审查。当前不请求开始维护窗口，也不解冻发布。


## 10. 2026-11-01 继续至发布的进展

QS #477补齐维护owner、完整保留基线/原材料、独立恢复CLI及不解冻CD的固定镜像构建入口。候选本地race、集成编译、docs-facts/hygiene及actionlint已通过；精确CI41219365688与原生Broker/独立CLI run41219211994仍在运行。后者源为QS c62621ded4fb2ff1c2aa5284076c97496a5b4ae7、infra18b6a67ae222126e0f337ec15317ef0724155994，不冒充后续main验收。仅取消了本任务被新提交取代的旧QS CI，取消不计通过；最终全部必需门禁保留。

00:22–00:23只读复查A/D六实例仍为原a792、running且无重启；00:26独立原TLS/身份只读事务显示57条当前operations均accepted/rejected，awaiting/held为0，但原事务锚点缺失仍为51，原观测仍不可用，不补造witness。QS Inbox2780条stored、quarantine0；原MySQL未观察到其他InnoDB事务，7个所见会话均Sleep。该结果是未停写时点的分类，不能作为停写证据或完整历史关闭。

独立探针读取performance_schema.metadata_locks返回MySQL1142，现库版本8.0.36且performance_schema=1；不能签无metadata锁或DDL。已请求现有管理员/只读诊断配置路径，不更改数据库权限。调度/提醒分类按当前notification源码的confirmed/rejected/suppressed/reviewed及pending/claimed/sending/manual_required分别解释；最初探针使用通用terminal列表误将confirmed计入“external call not generic terminal”，原输出和失败谓词保留，不能因此宣称存在一个活动调用或修改该记录。原一次confirmed投递、frozen批次与三suppressed批次均保留，frozen是批次冻结身份，不代表仍在发送。

成功技术读取端点已核为A `http://127.0.0.1:8081/metrics`；原19090是gRPC映射，失败保留原归属。原两owner sdk_ready=1、active/running/queued为0，正式业务观测仍不可用。没有停业务、reload、SQL111、恢复、应用首次启动或CD启用。只在既有idle维护容器内放入并执行固定只读诊断二进制，私有原源码/二进制/回执按SHA256保全；没有新维护容器或业务写操作。

关停命令语义已核对[Docker官方说明](https://docs.docker.com/reference/cli/docker/container/stop/)：`docker stop --timeout=-1`让daemon无限等待，不由daemon超时强杀。生产仍须核当前CLI支持该参数、原StopSignal和实际退出；操作者超时/断线不等于服务已停，失败不进入SQL111。原有默认10秒stop不采用。

首次原生CLI run41219211994失败原消费者fixture line564；已保全ZIP并核对SHA256。修正为先独立运行全部原13项、再运行独立CLI8项，run41220540652绑定QS657734fba/infra92c92a7，真实结果待回读。没有改业务代码、SDK或半消息不可见断言，第一次失败不重标为通过。

生产顺序的原生门禁进一步固定为9项：维护CLI真实注册时，两个原SDK仍须ready；原SDK正常停止后维护SDK继续ready，再证明未决时信号拒绝退出及实际Broker正向审计/SDK进程退出。源码审查QS549ad91a9/infrae760d25，真实新回执未通过前不关闭G01。先跑原消费者13项，再跑独立CLI9项；8项旧回执不能消费为新9项资格。

00:45隔离Nginx第三次验证通过完整配置。前两次分别因人为cap-drop导致原私钥不可读、只读scratch缺少/tmp缓存写目录而失败，原结果均保全；验证环境改为实际原用户/capabilities和独占tmpfs，未改主机证书权限。三个独占验证容器均已自行移除，原Nginx进程、两个线上文件字节和原restart时刻均保持，无reload。


### 01:55实际验证更新

- 原生owner交接run41222119780已通过：原13项、实际独立CLI9项（包含原owner仍ready时注册维护owner）全部成功，无skip。原ZIP SHA256为`ac9e2304d535b2b14f0ab21da8e955cee951b74c83416456bbc9d5222919b250`，QS源25a4b36b999568806f73335b8824a588f9865338、infra源e760d25a1c279fe7d6f5bac5995801db89d15f10；不冒充后续forward111扩展资格。
- aa1387b79 CI41225761018中真实完整保留基线、三中断独立原材料恢复CLI、权限拒绝后事务回滚及原有schema-pair/协议110/111门禁均成功；该次整体Run Tests因新增只读任务未登记在固定16任务契约中失败。最终候选将固定17任务全部纳入operation/database互斥和pre-checkout门禁，不放宽业务/DDL断言；本地configcontract race已通过。
- 既有管理员元数据profile41222747868成功；独立M5活动入口41225913119成功读取同一canonical MySQL身份及clean110，7个QS会话，active/事务/修改事务/metadata granted/pending/启用EVENT均0。14项读取非原子、freeze_verified=false；凭据经既有Secret与私有SSH信封，不导出凭据、不GRANT。CI的真实持锁与pending ALTER正向观测也通过。此读数不证明停写。
- 新增显式`--owner-drain-forward`只接受clean111/44，默认原owner仍只认110/44，dirty111拒绝。R2可在新API异常时先注册111兼容Checker再做业务runtime前向替换；不回放旧账本。最终候选7f8390c74，独立扩展run41227966209待回读。
- infra e760d25全部84个实际检查成功、2个原条件skip，无失败。最终镜像、现库全量只读预算、同窗口保护、真实排空/迁移/启动仍未执行。
