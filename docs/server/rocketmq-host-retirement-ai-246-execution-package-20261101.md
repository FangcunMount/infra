# AI #246 同窗口保护、44前向恢复与数据库执行审查包

**结论：本包提交具体执行审查，当前执行为No-Go。** AI #246及排空修复#248已仅合并源码，受核main为`c6359b441de48fde5b295529fe9c10f50e4c53f5`（精确main检查14项成功），生产仍43；用户本轮明确要求保持发布冻结、不实际停业务、不执行生产DDL。没有签发或消费生产批准。数据责任人、恢复责任人均为shujie。源码工具、原生资格、现场只读事实和未来窗口材料分别绑定，未发生的窗口回执保持待生成。

入口：[结构化执行包](../evidence/2026-11-01-host-retirement-ai-246-execution-package.json)、[AI #246](https://github.com/FangcunMount/qs-ai/pull/246)、[上一轮审查](rocketmq-host-retirement-ai-empty-publisher-review-20261101.md)。本包只处理`ai.mysql.messaging_outbox`，其余四个候选、所有业务/模型历史、事务凭证、Inbox、ACK、archive、治理和调度记录全部保留。QS已发布的111/44不回放110；AI本包不执行SQL111。

## 当前镜像与剩余执行门槛

准备材料已补齐：[管理员原回执](../evidence/2026-11-01-ai246-administrator-observation.json)、[实际不可变44镜像资格](../evidence/2026-11-01-ai246-44-image-qualification.json)、[当前源码恢复资格](../evidence/2026-11-01-ai246-main44-restore-qualification.json)。精确main检查[41310278495](https://github.com/FangcunMount/qs-ai/actions/runs/41310278495)12项、[M7 41310404873](https://github.com/FangcunMount/qs-ai/actions/runs/41310404873)两项成功。恢复专项两种MySQL各21项；[实际镜像41311886021](https://github.com/FangcunMount/qs-ai/actions/runs/41311886021)13项成功、0失败、0跳过，含完整44隔离备份恢复、真实SDK/Checker、只读根两次启动/无错误排空、首启动后新增ACK与旧二进制事实保留、启动全过程0 DDL/0模型请求。两个关闭耗时5.037/4.766秒仅属空闲且准入暂停的隔离实例，不是生产活跃工作排空或RTO证明。

| 绑定 | 已验证原值 |
| --- | --- |
| 受核源码 | `c6359b441de48fde5b295529fe9c10f50e4c53f5` |
| ACR不可变digest | `sha256:e6afea10afbd5aca74d1eb67f5a3af417759cc0a754bcac668ccd5ed81d9470e` |
| 两份archive的原始config SHA | `sha256:a0eba52391dd24273ef2437cec10d224913e31a484a1c8b0294dd1f71882130c`；全部diff_ids逐字相同 |
| 生产prepare archive | `9042ce559f7d3bcb6df19915972830d566b1c60e8eeb0abd1ba9050cf8434507`，117,694,528字节；prepare release `c6359b441de48fde5b295529fe9c10f50e4c53f5-41311879954-1` |
| 独立离线恢复archive | `1256b4781619aa866b1c3a023a76c9b3db2280b935826049f934a50439d7a180`，131,626,551字节；MacBook/ServerA私有副本逐字回读，ServerA已实际docker load，未创建新业务容器 |
| ServerA两种engine ID | 生产prepare为`sha256:e6afea10afbd5aca74d1eb67f5a3af417759cc0a754bcac668ccd5ed81d9470e`；恢复load为`sha256:b68cfe164b829a5b542dc2ebc0c5f9fad19ce88dc33dedd42528313ca6f81b97`；engine/manifest ID不冒充config SHA |
| 准备范围 | 同一受核44代码的重启/配置修复；未知代码缺陷须保持停止并另审新44补丁。不能回到f9/43、重放旧ledger或覆盖旧全备 |

目前生产执行仍No-Go，剩余条件逐项如下；此次未签发、消费批准或创建真实window：

| 剩余门槛 | 尚须取得的实际材料 |
| --- | --- |
| DB03 | 完整写者/旁路库存、真实准入关闭和210秒无错误排空，原事务/调用无active或unknown；Broker待办和历史保留 |
| DB04 | 同窗口frozen保护、原目标/完整ledger/49表原件及独立完整备份或PITR可恢复性资格；binlog30天配置和隔离fixture恢复均不能替代 |
| DB05/DB08 | 当次保护材料二地回读、原执行UID持久消费目录、shujie独立签发的当前有界生产review及SHA；现有模板不可消费 |
| DB07/DB10 | 固定实际DDL执行账户/权限、当次W04管理员重采及writer排除签收；先写首次业务重开屏障后才发启动命令 |

最新管理员[41312407017](https://github.com/FangcunMount/qs-server/actions/runs/41312407017)再次成功：24条只读、完整43/原DDL空表、会话4、活跃/事务/修改事务/AI锁/全局待锁及目标依赖均0，原库身份相同且连接完整释放。`freeze_verified=false`、`observations_atomic=false`保留原值；这些时点观察不证明已停写。

## 已取得的事实与生产执行缺口

| 项目 | 本轮实证 | 对执行的意义 |
| --- | --- | --- |
| 发布冻结 | 06:01UTC将AI AUTO_DEPLOY_ENABLED从true改false并回读；QS Production Deploy仍disabled_manually；无正在执行的AI发布 | 阻止自动发布；人工入口仍须窗口排除，不能单凭变量宣称停写 |
| 实际AI | f9f24abdf98535295c4e3d223675ef6be62115e2；原容器f2f43c57…仍healthy、restart0、StopTimeout210秒 | 没有停机/替换；main c6359b4与运行镜像身份分开记录 |
| 只读全量复验 | 2026-11-01 13:39:20UTC；完整43，目标0行，另49表8,502行/91,768,306原字段字节，全部保留定义和内容指纹与此前相同 | REPEATABLE READ只读一致快照，逐表定义/列顺序/内容指纹；不是停写备份 |
| 数据库身份 | `04f119402a8b7704f84df45bd3e3fb182eaf1ea05febe7fbad38f66c76740fc3` | 由server_uuid和DATABASE原值的固定JSON编码散列，窗口重读 |
| 原目标DDL | `a4e7e09941d249faa1a2a4c100eadbdd53c3be42181a148c74ba8c256cb508ff` | 生产SHOW CREATE原字节已捕获；只有结构，无业务内容；精确DDL进入两种原生MySQL隔离恢复 |
| 权限及可见性 | 当前连接有PROCESS/复制读取以及ai/iam/qs等schema广泛权限，实读20会话；不读取SQL INFO；未GRANT/REVOKE | 可观察跨会话但不能据此宣称所有写者已排除。最终审查必须固定实际执行账户与权限边界，不在当前准备工作中改权限 |
| 恢复基础 | log_bin=true、binlog_expire_logs_seconds=2592000 | 只证明30天保留配置，不证明完整备份链、PITR实际可恢复或RTO |
| AI管理员锁观察 | QS #479受核入口以main7899ffce执行24条只读查询，AI身份/全局权限验证、完整43/原DDL/空表及14项计数完成，连接与database均释放 | 此前应用账户1142仍留存。新管理员时点观察已补齐，窗口须重采且独立排除写者；未改权限、未KILL会话 |
| 不可变生产/恢复制品 | c6359b4固定ACR digest完成build-only和prepare-only；实际镜像13项通过，两个离线archive两地回读，恢复副本在ServerA实际离线load | 准备资格已补齐。独立archive同为受核44代码，适用于重启/配置修复；代码缺陷仍须另审新44补丁。未启动生产44 |
| 窗口与审批 | 未停写、未生成frozen保护/实际writer排除回执、未签发production review/forward review | **执行阻断**。当前材料仅可审查，不得把live.json改名为frozen.json |

关键保留计数：model_calls40、result_outbox128、Inbox58、业务ACK29、archive29、binding1、request22、execution22、witness29、native_limit_notices0。49表原件还覆盖评测completion/dispatch/response、lease/job、publication和quota调度；摘要比较覆盖全表，不能仅用这些计数替代。51条历史旧协议责任仍独立保留，未补造事务锚点或清零指标。

## 源码契约与保护格式

新候选在原0044方案上增加以下固定入口，43及更早迁移字节不变：

- `qs_ai.maintenance.publisher_window capture`：不启动应用/SDK/模型，单连接、无overflow；显式原库URL从已有受审配置注入。只读snapshot默认frozen=false、execution_approval=false。
- `publisher_material.snapshot`：先后完整结构校验，只允许严格43、严格44，或独立离线验证的“43 ledger+44物理布局”。预算20,000总行/128MiB原字段字节/60秒，外层进程90秒；超限报错，不截断为成功。
- `empty_publisher_retirement`：v2批准验证同源/同库/同operation、原目标DDL与空表、同窗口writer回执、完整保留基线和绑定DDL的隔离恢复/前向资格；普通现库upgrade、v1散列声明、live保护均拒绝。
- `publisher_window reconcile`：独立显式写入口，仅在已证实DROP提交、43ledger未更新且全部保留定义/字节一致时，单独批准后条件更新一行ledger至44。正常服务启动仍拒绝43缺表；工具不重放DROP、不恢复业务行、不调用模型。

指纹编码为MySQL逐列CAST AS BINARY后HEX，NULL标记0，非NULL标记1+8字节大端长度+原字节；每行SHA256，行摘要排序后再次SHA256，保留重复行。它保留二进制/空值/字段边界，**不包含可用于重建业务数据的正文，不是全库备份**。同窗口保护snapshot保存完整原目标DDL、空行证明、原ledger定义及完整43原行、全部49表定义/内容摘要。目标只允许0行；变非空即退出本批，不迁走、清空或复制到别处后继续删除。

writer回执是shujie对原始入口清单/实际停机与排空证据的批准声明：source、operation、DB身份、候选image digest、停止容器完整ID、库存摘要、当前一小时内时间、running_writers=0、unfinished_work=0、business_reopened=false、Broker待办保留。工具验证其字节和语义，不能自动发现任意旁路写者。unfinished_work只指当次活跃调用/未收口事务，不要求删除持久待办或历史blocked记录。可消费批准及consumed必须在宿主持久0700目录、执行UID所有；文件0600、非符号链接。消费采用固定父目录FD、EXCL、文件及目录fsync；不得使用容器/tmp作为唯一消费凭证。

## 停写与排空清单：正式窗口前逐项审查

当前只有一个AI统一业务容器，但这不自动等于全部写者。需逐项核对并记录入口责任与排除证据：

| 写者/入口 | 源码与实际边界 | 正式窗口的退出条件 |
| --- | --- | --- |
| AI HTTP/gRPC治理、发布、原请求写入口 | `bootstrap/server.py`，同一进程；包括管理员/脚本直连 | 先关闭准入并公告本窗口，既有请求按原根完成；不创建额外业务请求 |
| RocketMQ命令与ACK订阅 | `bootstrap/messaging.py`，COMMANDS/ACKS；AI停止时QS可能继续产生持久Broker待办 | 停止新claim，保留原wire、ACK、Broker offset/队列；不得清队列或将积压写成0 |
| generation/evaluation及持久调度 | server/daemon现有循环与原租约/派发证据 | 停止新准入，等待现有调用/根事务结束；unknown先读原证据，不取消/补发模型；持久blocked/重试/调度记录保留 |
| 事务owner/Checker | mq_transactions最后等待其他业务组件，SDK close宽限5秒 | 保留至原业务终结/ACK交接完成；prepared、未决half/final结果、活跃根须为0，不能只凭最终进程exit=0 |
| 人工/其他主机/维护/CI旁路 | 实际PROCESS/innodb_trx/metadata lock及完整工具清单 | 全部人工发布/迁移/脚本入口排除；无同库写连接、DDL或长事务；只保留当次审核的只读/执行连接 |

现配置generation shutdown_seconds=190，容器宽限210；生命周期会记录drain_timeout/component_stopped_with_error/transaction_shutdown_incomplete，超时后仍可能退出，故“容器停止”不能替代无错误排空日志及原事务原件复验。任何上述事件、活跃/unknown调用、prepared/未决事务或旁路未排除，取消DDL资格，保留原材料和原记录。不得KILL未知会话、强制将租约/状态改终态或清Broker后继续。

未来停止命令仅能针对窗口逐字核验的当前完整容器ID，以SIGTERM及210秒宽限；本轮没有运行。窗口须同时持有既有主机部署/镜像保留锁和AI发布串行锁，沿既有取锁顺序，不替换锁inode、不在持锁会话里再嵌套同锁。锁会话断开即停止后续动作并重新盘点。

## 正式窗口步骤与命令清单（当前禁止执行W03以后）

单一操作目录未来才创建：协调端`~/.codex/m5/windows/<独立AI246操作ID>`，ServerA持久目录`/var/lib/fangcun-m5-protection/ai246/<operation>`，运行工具以执行UID拥有的0700子目录挂载到`/run/m5`；原件和消费凭证两地复制。每步必须记录脚本SHA、主机/UID、源码/镜像、开始结束/退出码和原始输出，不把SSH无输出视作未执行。

| 步骤 | 具体动作、命令及产物 | 预算与停止点 |
| --- | --- | --- |
| W00 | 复验冻结与无在途deploy；固定受核main、main CI、完整工具字节清单。仅`operation=build`构建主线ACR，再以`operation=prepare`固定候选和另审44前向镜像/离线archive；核schema_policy=require-existing | 准备工作可独立审查；不得调用deploy/rollback。当前c6359b4 build/prepare和13项隔离资格已补齐，W03以后的真实窗口仍禁止执行 |
| W01 | 审查完整写者/准入/事务排空方案、实际执行账户、原库身份、目标DDL及唯一DROP范围；审查隔离恢复和44前向启动资格；签收准备材料 | 任一制品/权限/路径不明，No-Go，不进入窗口 |
| W02 | 新operation取现有锁，复验完整容器/镜像/配置，记录冻结、入口清单、Broker持久待办及PITR/备份资格；记录取消/恢复责任人 | 受审协调准备期；本轮不创建真实window或批准 |
| W03 | 关闭AI新准入，按上表停claim/排空；原owner保留至业务/ACK完成。只对核验ID执行正常停止，记录前后状态及日志 | 210秒；任何超时/强杀/未决/新实例取消DDL |
| W04 | 读取PROCESS、innodb_trx、metadata_locks和原事务/模型原件；确认无其他写者/无旧DDL会话；形成writers.json及原始inventory摘要 | 30秒，权限/不明状态阻断；不能用时点Sleep替代写者排除 |
| W05 | 固定维护镜像仅运行下方capture，输入当次writer回执。输出frozen.json、目标DDL/空数据原件、ledger完整原件、保留指纹、完整schema校验；双副本回读SHA+fsync | CLI90秒/内部60秒；预算超限重新审查，不截断或调整为成功 |
| W06 | shujie审查原件与二地读取、目标DDL隔离恢复资格、44前向镜像、停写有效期；签发精确review/v2批准及SHA | 一小时内且短于writer有效期；此文/模板/CI均不能作批准 |
| W07 | 专用受核工具执行下方Alembic命令，仅DROP messaging_outbox及正常43→44ledger前向记账。5秒有界目标表锁；批准消费持久化先于DDL | 外层90秒；任何未知结果进入只读分类，不重试原批准或stamp |
| W08 | 用新连接capture+verify，必须strict44/目标缺席、全部保留定义/字节与W05相同，事务/连接池释放；保存结果和consumed两地副本 | 90秒；发现变化保持停止、独立审查 |
| W09 | 先独占持久写入原批准路径的review.json.business-reopen-issued并fsync/另机复制，再发启动命令；仅require-existing44镜像、原TLS/SDK绑定启动单一AI runtime，逐步核readiness/原历史/ACK/调度；持久记录“重开已发出”先于命令 | 原受审启动预算；任何结果未知查询原实例，不创建第二执行器 |
| W10 | 观察当前新事务/业务ACK与原凭证、历史责任、Broker积压分别记录；自动发布继续false，QS继续禁用；原件至少30天且未结延期 | 不用旧51历史完整性缺口掩盖当前情况，也不写全局全绿 |

维护命令的执行环境为固定镜像`/app`、UID10001、只读根、仅所需TLS原挂载/数据库网络，无业务CMD。显式`QS_AI_PUBLISHER_WINDOW_DATABASE_URL`由受审配置注入，禁止在参数/输出打印URL。`QS_AI_RELEASE_SHA`必须由镜像给出，与批准源码逐字一致。下列尖括号为未完成审查绑定，故意不能直接执行：

```sh
/app/.venv/bin/python -m qs_ai.maintenance.publisher_window capture --operation-id <operation> --writer-receipt /run/m5/writers.json --writer-sha256 <writers原件SHA> --output /run/m5/frozen.json
/app/.venv/bin/alembic -x empty_publisher_review=/run/m5/review.json -x reviewed_sha256=<review原件SHA> upgrade 0044_empty_publisher
/app/.venv/bin/python -m qs_ai.maintenance.publisher_window verify --baseline /run/m5/frozen.json --baseline-sha256 <frozen原件SHA> --output /run/m5/after.json
/app/.venv/bin/python -c 'import json; from pathlib import Path; p=json.loads(Path("/run/m5/after.json").read_text()); raise SystemExit(0 if p["state"] == "44_complete" and p["retained_identical"] is True and p["transaction_released"] is True and p["pool_released"] is True else 2)'
```

## 恢复决策表与未知结果

| 实读状态/触发点 | 允许的受审路线 | 明确的保留边界 |
| --- | --- | --- |
| R0：43完整、目标原DDL空表，DROP尚未提交 | 记录取消、永久废止当次批准；复验原43全目录/原件，按单一重开屏障恢复原容器。若已有consumed也不可复用，下一窗口另审 | 所有业务/协议原件不回放；本轮未实际停止，故无需启动原容器 |
| F1：43ledger、目标确实缺席 | 保持业务关闭；确认原DDL会话结束且无锁/事务在途，独立离线pending布局验证；读取原review及持久consumed，逐表比较W05原件；重新审查当前writer有效期，另发forward review/v1 | 严格43+44物理布局以外一律拒绝；若retained字节/结构漂移或业务已经重开，禁止自动收敛 |
| F1执行 | 下方reconcile锁ledger原单行，仅条件UPDATE 43→44；新批准EXCL持久消费先于写；commit后新连接strict44复验和全保留比较 | 无DROP/CREATE、无业务DML、无43ledger回放；原目标DDL只作为审计/隔离恢复材料 |
| F1 commit/SSH回复未知 | 保留原输出及两个consumed，重新只读分类。44完整则只做验证；43缺表则保持停止，独立审查新恢复批准，原批准不可重用 | 禁止因无回执重复UPDATE、直接stamp或重放DROP |
| F2：44完整但应用启动失败 | 使用已预审且固定的44兼容前向版本/配置；require-existing读完整44后，沿单执行器屏障修复 | 原f9/43镜像不能回退；无新44映像资格则保持停止并修复准备 |
| F3：首次业务重开已发出或任何新事实出现 | 只采用44兼容前向代码/配置修复；核原业务请求/模型响应/ACK再恢复，不重试供应商unknown | 不覆盖全备/43ledger、不重建旧表、不删新事务/历史/ACK/调度，不用旧hash要求回放现库 |
| 其他head、多行ledger、目标重现/非空、结构漂移或原件缺失 | 独立数据库故障审查；保留当时现场，不执行本包任何写命令 | 不能“修正”材料/状态以进入允许分支 |

```sh
/app/.venv/bin/python -m qs_ai.maintenance.publisher_window capture --operation-id <operation> --output /run/m5/unknown-result-readonly.json
/app/.venv/bin/python -m qs_ai.maintenance.publisher_window reconcile --review /run/m5/forward.json --reviewed-sha256 <新恢复批准SHA> --output /run/m5/forward-result.json
```

## 数据库审查签收单

当前签收状态`prepared_for_review / execution_authorized=false`。结构化包包含每个门槛状态及未来原件，不生成可以消费的生产review.json。

审查人逐项核对：①唯一目标及实际空表/完整43；②43份旧迁移与保留全目录；③生产候选和44前向镜像/离线文件/实际启动资格；④所有writer范围、210秒排空、原事务和unknown处理；⑤W05当次原件及两份可读/消费持久性；⑥原DDL隔离恢复和F1真实DROP后单行前向资格；⑦锁/DDL/事务观察权限与实际执行账户；⑧重开屏障、无43回放、记录保留；⑨精确批准SHA/一小时有效期/每次独占消费；⑩未知结果分类及停止点。任一证据缺失仍为No-Go；不能用“计划已写完”填为执行已批准。

当前已核源码、管理员入口、原生资格与W00不可变制品可进入准备材料签收；W03～W06同窗口事实及生产执行批准尚未发生。全部生产变更继续冻结，51历史、其余四对象和独立原生超限恢复不随本包结案。

重开屏障的具体文件动作由固定维护镜像、原执行UID在`/app`运行（只在正式W09或R0取消后恢复原业务之前；本轮未执行）：

```sh
/app/.venv/bin/python -c 'from qs_ai.maintenance.publisher_material import write_private; write_private("/run/m5/review.json.business-reopen-issued", b"issued-before-business-start-command\n")'
```

迁移和F1入口均在消费批准前检查该固定标记，任何存在（包括符号链接）永久拒绝首启动前操作。标记先于实际启动命令，失败/结果未知也不删除；原43取消后重开也标记并永久废止原operation。


## 原AI246 PR源码与原生资格绑定（历史原件保留）

AI246原PR审查源码`90e64f36737de60f9148ba0169eeadf3bce6f8c4`，43份原迁移与e711逐字相同；现已仅合并源码至main abc700f，未发布。最新专项MySQL8.0.36/8.4各21项成功，包含首次重开标记拒绝，原ZIP/JUnit已逐字下载校验。两份原生专项耗时分别48.612/57.115秒（这是整组测试耗时，不是生产RTO）。完整矩阵与M7结果以结构化包的精确run状态为准，不把已通过的专项或前一中间HEAD当作最终完整CI。

最新现场只读复验时间06:31:31UTC，执行代码与候选publisher_material逐字一致，经原f9业务容器UID10001的stdin运行，没有创建新业务/维护容器或安装候选。16.604秒完成、事务/池释放；43、原DDL空表、49表8,502行/91,768,306字节与06:13两次快照的全部定义/内容指纹相同。两时点一致不能证明期间停写或连续无变化。原采集脚本、实际stdin代码和原JSON全部私有保全。

[不可消费的审查表模板](../evidence/2026-11-01-ai246-review-forms-TEMPLATE.json)列出migration/forward/writer字段；schema故意为TEMPLATE、未知摘要/有效期为null、writers_excluded=false，现有工具必须拒绝它。正式窗口由责任人审查真实原件后另行签发正确版本批准，不能直接把模板变为当前执行授权。


DB07的[管理员只读查询清单](../evidence/2026-11-01-ai246-administrator-readonly.sql)固定AI库范围，列出身份/完整ledger、全会话/事务/前台thread、AI或全局metadata锁、目标入向FK、trigger和event，不读取SQL INFO、routine定义或业务正文。该SQL文件继续作为查询清单；已验收的实际执行器为独立QS #479 Go入口，最新原回执见下方固定链接。原应用账户1142原件保留，管理员可见范围、deadline、AI身份和完整释放已有独立验证，正式窗口仍须重采。动态SQL/视图/旁路入口仍按写者清单审查，不能凭查询返回0填writer排除。


`verify`的职责是保留对象比较，单凭其exit0不代表迁移完成；W08必须执行上述独立JSON断言`state=44_complete`并签收strict44缺表和全部保留一致，43完整/43缺表均不能进入重开。原43取消路线使用独立R0复验，不借用W08的44重开资格。


最终精确HEAD90e64f3的[完整checks41281012903](https://github.com/FangcunMount/qs-ai/actions/runs/41281012903)12项和[M7 41281012842](https://github.com/FangcunMount/qs-ai/actions/runs/41281012842)2项全部success，共14项，包含8完整分区与覆盖汇总、两种旧工具备份恢复、受限镜像及两种M7。前一d389完整run在加入重开屏障后取消，原日志ZIP保留，不作最终资格。当前本地37项针对性测试、Ruff/format、mypy455源文件及76文档/1281链接检查通过。上述为原PR历史资格；当前main及实际不可变44镜像已独立取得资格，见本文当前绑定表，未用PR临时镜像填生产digest。


完整审查原件归档2,745,835字节，SHA256为`9ec4eebcf3be7e90e447ee79769f73f785c6c6160c12a69e340a446027537518`，包含56份原件及索引，MacBook/ServerA两份逐成员回读与fsync一致；复制回执另存两处，SHA256为`55b9151f7b2f3ab23f7678fba53f33d7a5d5c0e96d603de40fb7e735bfc95619`。目录0700、文件0600，至少30天且未结责任延期，无自动清理。归档保护源码增量bundle、实执行采集代码、生产只读/权限原件、原目标/ledger、原生ZIP/JUnit及完整/取消CI原日志；复制回执在归档完成后产生，作为外部签收，不伪称位于其自身归档内。该包不是同窗口数据库备份，也不是生产执行批准。


## 管理员只读观察补充（2026-11-01）

[QS #479](https://github.com/FangcunMount/qs-server/pull/479)已仅合并源码；[生产只读run41307710356](https://github.com/FangcunMount/qs-server/actions/runs/41307710356)成功，精确源码`7899ffce168bac0097b733dd874ab97d87f10db0`。固定AI传输身份`83cd3186…`与固定原库身份`04f11940…`分别校验。采样为完整43、目标存在且0行、原DDL摘要不变；AI会话4、活跃会话/事务/修改事务0、已授予/待授予AI元数据锁0、全局待授予元数据锁0、AI event/trigger/routine/view及目标入向/外向FK/视图依赖均0。全局SELECT/SHOW VIEW/TRIGGER/EVENT权限和PFS映射经过独立验证；24条查询完成并完整释放，只输出固定计数及摘要。原安全回执逐字SHA和全部字段已进入结构化包。

`freeze_verified=false`、`observations_atomic=false`保持原值；上述零值不是连续锁观察、全局停写或无动态SQL的证明。实际DDL执行账户、人工/主机/CI旁路仍逐项审查；正式W04须重新执行同一固定AI入口并结合实际writer排除材料。原应用账户1142未被覆盖，旧QS范围回执也没有借用为AI证据。


## 实际44镜像排空发现与修复审查

abc700f生产镜像固定digest `sha256:d848a92f5cff63c9eb25a9f4a59b6db5a484d5d9d78bab236ce9b03344e16727`，实际config ID `sha256:cd956b7802ae42b980fdf4239484080fd13f99e6f2b86074302ac6970d906032`，离线archive SHA `d2da50421c15b0246442730fe7cba4ab25dc9c8bdabb25a19d8a6c69fc4e3773`、117,693,641字节。build-only41305184442与prepare-only41305814053成功，ServerA原业务容器未替换。registry manifest digest、宿主engine ID和config SHA分别记录，不互相冒充。

[首次实际验证41306319525](https://github.com/FangcunMount/qs-ai/actions/runs/41306319525)与[带诊断复验41308014765](https://github.com/FangcunMount/qs-ai/actions/runs/41308014765)均未通过严格排空。后者证明实际默认CMD、UID10001/只读根/完整44备份恢复/原二进制ACK、真实SDK/Checker与paused readiness已通过；约4.998秒退出0且无OOM，但两个mq_subscriber记录component_stopped_with_error。退出0不能替代本包无错误排空条件，因此没有生成合格前向镜像原件。失败回执/完整CI原日志保留。

[AI #248](https://github.com/FangcunMount/qs-ai/pull/248)将主动Stop成功与固定SDK0.5.0的无cause停止通知衔接；真实传输cause、提前退出、取消和Stop失败仍失败，通用监督器/原严格镜像资格检查未放宽。受控driver仅替代网络启动/阻塞调用，真实固定SDK wait/stop方法验证；26项生命周期、24项文档与退役边界以及Ruff/format/mypy通过。这些后续要求已由c6359b4精确main、固定新digest和两次实际隔离44启动/排空补齐；DB02/DB06/DB09按当前绑定表签收准备资格。旧prepared镜像继续作为失败候选证据保留，不用于生产。


## 修复合并后的精确主线核验

AI #248已仅合并源码至`c6359b441de48fde5b295529fe9c10f50e4c53f5`；PR完整checks41308643839的12项及同源码M7 41309046783的两项成功。精确main CI41310278495的原目标DDL恢复与前向专项已在MySQL8.0.36/8.4各21项通过，原ZIP/XML按当前main重新取得并校验，没有把90e64f3的旧回执重标为当前资格。完整main CI41310278495的12项及M7 41310404873两项均已成功；随后build-only41311659072与prepare-only41311879954成功。不可变镜像由隔离run41311886021取得13项实际资格，原严格排空门槛未放宽。

未来writer回执的`candidate_image_digest`按源码契约使用不带`sha256:`前缀的64位十六进制；原registry digest仍以`sha256:…`格式另存并相互核对。模板所有源码/镜像/窗口/有效期未知字段保持null，TEMPLATE schema不能消费为生产批准。


## 准备完成后的冻结与现库回读

2026-11-01 13:53:19UTC回读：AI AUTO_DEPLOY_ENABLED=false、QS发布disabled_manually、无在途AI release工作流；自动跟随main的41311618873已条件跳过。当前生产仍原f9容器f2f43c57…/原image18a39e86…，started_at仍为2026-10-30T18:37:03.255198256Z、healthy/restart0/无OOM，state.current仍为原release。prepare和离线load没有替换业务实例。

13:39:20UTC最终一致只读快照18.268秒完成，事务及池完整释放；完整43、原目标0行，49表8,502行/91,768,306字节，全部定义/内容指纹与06:31原件相同，原JSON SHA `c349610b24433a5f96fc6df25229e323985a4f50e3630e2f7a08a11347a097c4`。最新管理员只读41312407017也已取得独立原件；时点一致不改写为停写证明或冻结备份。源库没有执行DDL/DML，SQL111没有重跑。


## 本轮完整原件保全与审查结论

本轮最终原件归档262,238,611字节，SHA `025c3296773cbca2bd3ad4fb21539c49b9092c91a4672efeec05d81ddf1fb6f3`，包含139个原件/脚本成员及索引。MacBook与ServerA逐成员SHA/长度、整包回读与fsync一致，31份已取得原始ZIP的CRC通过；0700目录/0600文件，至少30天且未结责任延期，无自动清理。当前两份合格镜像archive按上表独立保全，旧失败镜像原件只用于审计，不列恢复候选。归档包含da65审查包快照、精确main/管理员/资格/失败与取消CI原日志、实际采集代码、两版MySQL原ZIP/XML及带明确基线的增量bundle；归档复制回执和本段的最终保全声明在归档完成后产生，作为外部签收，不声称包含于自身归档。复制回执也已另存两地，其SHA见结构化包。

DB01/DB02/DB06的静态与隔离资格、AI管理员观察能力和44离线恢复制品均已补齐；DB03/DB04及DB05/DB07/DB08/DB10中依赖真实窗口、实际账户、冻结保护/备份PITR与独立批准的部分继续No-Go。未停生产业务、未执行生产DDL/DML、未签发或消费生产批准，事务凭证、历史、ACK、调度和Broker待办均未因本包修改/删除。当前发布继续冻结；M5生产发布没有完成。
