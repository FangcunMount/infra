# M4 执行总表：生产切换后的旧链路清理（已完成）

本文件只维护 RocketMQ M4 的**当前最终状态：38/38子任务、8/8父任务、三个里程碑全部完成，C06门禁4/4通过**。八个最终生产实例已部署，合法system及新答卷/新AI业务验收通过，公共入口已恢复。收尾[PR344](https://github.com/FangcunMount/infra/pull/344)于2026-10-27 09:27（北京时间）合并，该收尾合并提交为`9a73fa3c78d8a135afb9795b581d278674a1f8a7`。

阶段计数、失败及执行过程全部移至[历史执行记录](rocketmq-m4-execution-history.md)；历史内容不再混在当前任务表中。完整镜像、部署和验收证据见[最终发布索引](rocketmq-m4-production-release.md)。用户随后授权的历史资产处置与自动CD恢复也已完成，最新结果见[追加操作总表](rocketmq-m4-post-closure.md)。M2保持24/24，M3及其48小时观察豁免见[M3总表](rocketmq-m3-execution.md)。

## 目标与执行边界

M4 删除已失去生产责任的 NSQ/发布型 Outbox/Relay 实现、历史兼容分支、废弃配置和运维入口，并在保留期限及具名处置范围内处理历史资产。最终系统只支持本次首发协议，不建设新旧版本在线共存能力。

M3 必须先完成最终新链路、旧责任处置、停止旧生产组件及system验收；2026-10-25用户已明确豁免T34的48h观察，交接保留豁免与短时检查记录，不伪称观察通过。M4 可以提前只读盘点，清理实施须等待这些证据通过；不能为了删除旧实现而延迟 M3 已具备的生产切换。

以下内容继续保留：当前业务 Inbox/receipt、首次 wire/签名/密文、模型 response/checkpoint、消费幂等、业务 retry/未来计划及其授权、事务 witness/Checker 和恢复责任。表名带 outbox 或字段名带 legacy，不等于可以删除。qs-ai 当前业务 ACK 仍校验并更新 result_outbox 中的业务事实，必须先识别并保护这些依赖；不为消除旧名称重写存储模型。

不处理 Mac mini 开发 NSQ、隔离测试依赖、SDK 面向其他宿主的通用 NSQ 兼容包，不改写已发布 tag、wheel 或旧验收证据。生产删除仍按执行时的具名清单、数据保留政策及已有批准机制进行；本规划不授权立即删表、删卷或清空备份。

## 里程碑

| 里程碑 | 内容 | 任务 | 状态 | 完成门禁 |
| --- | --- | --- | --- | --- |
| M4-P | 清理对象与依赖冻结 | C01 | ✅ C01实现/验证完成；已合并，M4-P完成 | [18责任单元/699文件/存储字段与保护清单](rocketmq-m4-inventory.md)及基线/生产只读证明齐全 |
| M4-1 | 旧实现与配置退出 | C02–C06 | ✅ 全部实现/验证与源码合并完成 | 最终新链路回归通过，不存在旧运行入口或误删当前业务职责 |
| M4-2 | 历史资产与闭环 | C07–C08 | ✅ 已完成，源码及发布索引均已合并 | 批准范围处置、数据保护、合并和发布索引齐全 |

## 任务表

| 完成 | ID | 任务及验收结果 | 状态 / 证据 |
| --- | --- | --- | --- |
| ✅ | C01 | 接收M3发布/T34用户豁免/旧责任处置记录；逐项冻结代码、服务、表、字段、卷、配置及明确保护对象 | 2026-10-25；源码97c4551、PR300已合并c56448a27ec0e7dfeb8b830306b0ba097a019544；四仓库独立worktree、18责任单元/699去重源码摘要、46表466列/9Mongo集合只读元数据、Go目标/Python31/infra7门禁0跳过与当前8实例健康通过；[清单](rocketmq-m4-inventory.md)/[证据](evidence/rocketmq-m4-c01-inventory-20261025.json)。该盘点未修改生产/数据，PR300已合并 |
| ✅ | C02 | 删除三库已停用的生产NSQ provider及发布型Outbox/Relay运行入口、旧启动分支和无调用代码 | 2026-10-26；三库最终运行装配均已合并，三库汇总/真实故障门禁通过；[汇总receipt](evidence/rocketmq-m4-c02-runtime-aggregate-20261026.json)。隔离旧helper与读取清理由C03/C04/C05完成，最终版本已随C08部署并回归 |
| ✅ | C03 | 删除旧Payload/ACK/Operation reader fallback、历史格式互通与恢复兼容分支 | 2026-10-26；4/4叶子、QS PR451/AI PR229/infra PR329及PR331已合并，正式SDK下完整原生矩阵通过。[receipt](evidence/rocketmq-m4-c03-current-readers-20261026.json)。保留新协议RPC/鉴权/receipt，最终版本已随C08部署并回归 |
| ✅ | C04 | 删除未投产的宿主中间协议及对应孤立夹具/临时工具，收敛最终协议文档 | 2026-10-26；3/3完成，IAM PR155、QS PR452、AI PR230均完整CI通过并合并；三档API/worker/dispatch、三档QS原根、六档AI/mTLS及六档最终成对故障通过。[完整receipt/替代映射](evidence/rocketmq-m4-c04-final-protocol-20261026.json)。当前责任解耦已由C05完成，最终版本已随C08部署并回归 |
| ✅ | C05 | 梳理旧命名下仍承担当前receipt/调度/业务历史的职责，保留或最小解耦，再移除确定废弃字段/依赖 | 2026-10-27；3/3闭环。AI当前存储与发布职责已拆分并保留state/ACK/history；QS PR453完整29项CI后合并11c106aa283bcd1e3f442da928985b3744fe54e8，当前摘要改读Committed档案/witness。三档原根及两档MySQL非空确定性恢复通过；[receipt](evidence/rocketmq-m4-c05-current-responsibilities-20261027.json)；无生产数据/模型动作 |
| ✅ | C06 | 删除旧生产NSQ部署/CD/自动启动/环境变量/监控及恢复脚本入口，核验新配置可完整重建 | 2026-10-26；12/12叶子、4/4门禁通过，八实例重建18项与四角色真实权限拒绝50项通过；三库主机保护完整CI并合并，配置契约随PR320合并冻结。[宿主保护证据](evidence/rocketmq-m4-c06-host-guard-20261026.json)/[固定契约](evidence/rocketmq-m4-c06-config-contract-20261026.json)。生产固定工具、宿主保护及材料启用已随C08完成；自动CD已由追加操作恢复，开发依赖保留 |
| ✅ | C07 | 按具名清单处置旧资产并保护当前事实 | 初验政策保留证据已合并；2026-10-27用户豁免等待后，退役NSQ三容器/专属镜像/1519文件/三配置、11份旧备份及5882条旧发布终态记录均清理完成；必要表结构与当前证据保护。见[最新资产台账](rocketmq-m4-retained-assets.md)/[追加receipt](evidence/rocketmq-m4-post-closure-20261027.json) |
| ✅ | C08 | 完成废弃依赖/文档审计、清理后新链路回归、源码合并与清理发布索引，关闭8项任务 | 2026-10-27；5/5，最终8实例部署、合法system/新答卷/新AI实际回归、公共入口恢复及资产保留通过；[最终索引](rocketmq-m4-production-release.md)/[机器可读receipt](evidence/rocketmq-m4-final-release-20261027.json)。PR344已合并，8/8父任务与全部里程碑闭环；自动CD已由追加操作恢复 |

执行顺序为 C01 → C02–C06 按实际依赖小批推进 → C07 → C08。某类不存在可删除对象时，先提供盘点与保留理由，再按“核验无需操作”记录，不能仅为提高进度打勾。

## 与 M3 的交接

| 原任务 | M3 保留门禁 | M4 接收部分 |
| --- | --- | --- |
| T18 | 当前协议确定性finalization、真实恢复与模型请求不增加 | 中间协议残留清理；无需为未投产版本建设兼容 |
| T19–T20 | 新Payload/receipt/RPC、最终QS＋AI成对验收、旧Relay不运行 | 旧reader、格式互通和不可达兼容代码删除 |
| T25 | 旧未决责任处置、未来计划精确交接、启动前恢复/启动后前向修复 | 旧共存/回退工具删除 |
| T35 | 旧写者/扫描/活动连接退出，NSQ停止且不会自动重启 | 旧代码、配置、部署入口及物理资产清理 |
| T36 | M3生产索引、合并、业务/观察验收、具名移交 | 全面废弃依赖与文档清理审计 |

旧未决任务须在 M3 切换前排空或按原授权规则具名处置。未决模型请求不因“不做历史兼容”重新调用，未来计划不能静默丢弃或被双重调度。M4 不承担让 M3 生产故障恢复功能事后才可用的责任。

## 进度与证据规则

当前正式任务全部已完成。下方38项子任务和8项父任务只展示最终验收状态，日期、源码SHA、PR/CI及证据分别保留。阶段计数和失败原文仅在历史记录中保存；不把源码、部署和业务验收混记，不删除失败任务或改变分母。

M4 完成要求八项闭环、相关变更合并、必要制品发布、清理后最终链路验证通过及资产处置结果可复查。若对象按政策继续保留，要注明位置、用途和后续责任，不能伪称已删除。

## 38项可验收子任务（2026-10-26落表，38/38）

本节记录用户已确认规划的最终验收结果，沿用C01—C08八个父任务、三个里程碑及C06-A/B/C/D四门禁。38项只计算本节叶子任务一次；父任务8/8、叶子38/38和C06门禁4/4分别记账，不相加。已有8项完成沿用原实现/验证/合并证据，不把本次写规划计为新增完成。C06-A/C的阶段门禁汇总已归档，当前状态以本节38项唯一子任务为准。

| 里程碑 | 父任务 | 叶子完成 | 完成门禁 |
| --- | --- | --- | --- |
| M4-P | C01 | 3/3 | 源码、对象、当前责任和M3移交冻结完成 |
| M4-1 | C02—C06 | 26/26 | 最终配置可重建，旧活动入口退出，保留责任及新链路回归通过 |
| M4-2 | C07—C08 | 9/9 | 资产处置/保留责任闭环，最终候选部署、业务回归和发布索引完成 |

<!-- M4 leaf tasks begin -->
### C01：接收与冻结（3/3）

| ID | 状态 | 子任务 | 必达验收 / 证据 |
| --- | --- | --- | --- |
| C01-01 | ✅ 已完成 | 冻结源码与候选对象 | 四仓库完整SHA、入口/调用链、18责任单元与699候选摘要可追溯；沿用PR300及[C01清单](rocketmq-m4-inventory.md) |
| C01-02 | ✅ 已完成 | 冻结存储和保护责任 | 表/字段/集合/索引与当前职责有清单，候选不等于整表可删；沿用[C01证据](evidence/rocketmq-m4-c01-inventory-20261025.json) |
| C01-03 | ✅ 已完成 | 接收M3生产移交 | 版本、system验收、T34豁免、NSQ停用及保护资产齐全；沿用[M3发布索引](rocketmq-m3-production-release.md) |

### C02：旧生产运行实现（4/4）

| ID | 状态 | 子任务 | 必达验收 |
| --- | --- | --- | --- |
| C02-01 | ✅ 已完成 | IAM旧provider/Outbox/Relay装配退出 | 2026-10-26；[IAM PR154](https://github.com/FangcunMount/iam/pull/154)候选9203ad1802da2cf07daaf380a7c3613930b52134以11项完整CI通过并合并0420222b7a3f3861d6769919926010e5a67a0aa2；三档MySQL各16项required源码原生、35项宿主存储/HTTP（含子用例）及22项Broker场景均0失败/跳过，真实IAM双实例/QS订阅及同进程新owner关闭/Checker通过。旧装配/自动Topic创建和旧NSQ镜像workflow退出，3脚本6组无副作用拒绝；原事务/业务/Redis职责不改。[范围与替代映射](rocketmq-m4-iam-runtime-cleanup.md)/[完整receipt](evidence/rocketmq-m4-c02-iam-runtime-20261026.json)。随PR321合并生效；已随C08最终候选部署并回归 |
| C02-02 | ✅ 已完成 | QS旧NSQ及扫描发布装配退出 | 2026-10-26；[QS PR450](https://github.com/FangcunMount/qs-server/pull/450)固定9850d15f0fdc385ca8c5a6dd30e394145ee7a89c，29项CI通过并合并ca1158ca472d42e7c58e067e170b116364b1d8ea（生成文档条件job未触发）；[infra PR322](https://github.com/FangcunMount/infra/pull/322)15项CI通过并合并18ad52057dbf3859198b9a9e274da333330df443。[真实矩阵40314640918](https://github.com/FangcunMount/infra/actions/runs/40314640918)三档各API13/worker11/dispatch41、0失败/跳过、完整清理。264项相关race、374项infra单测通过；首两轮失败、专项14及三档worker11、删除映射和原责任保留于[receipt](evidence/rocketmq-m4-c02-qs-runtime-20261026.json)/[范围](rocketmq-m4-qs-runtime-cleanup.md)。进度记录已合并；已随C08最终候选部署并回归 |
| C02-03 | ✅ 已完成 | AI旧NSQ/MQRelay/M1装配退出 | 2026-10-26；[AI PR228](https://github.com/FangcunMount/qs-ai/pull/228)候选9a48509e777b4b0a819308dd05b7db7fff9af42f，12项CI/两档各5724用例0失败错误跳过后合并a2f192733312fef591bb9be24e5e3892e470420e；[infra PR326](https://github.com/FangcunMount/infra/pull/326)六档真实QS↔AI各5测试/25事实通过并合并8c798db7c5f71c968740e6f0bcb7e5179392e811。82项本地/13关键函数AST保持，旧选择拒绝及历史责任见[范围](rocketmq-m4-ai-runtime-cleanup.md)/[receipt](evidence/rocketmq-m4-c02-ai-runtime-20261026.json)。C04文档收敛及C08最终镜像部署均已完成 |
| C02-04 | ✅ 已完成 | 三库入口与生命周期回归 | 2026-10-26；当前合并版本三档IAM/QS各35存储/HTTP测试、22 Broker事实，六档QS/AI各7测试/40事实，均0失败/跳过、完整清理。复用同源码树QS三档API13/worker11/dispatch41；旧选择拒绝、空闲Checker、真实在途、失败清理和关闭见[精确映射及receipt](evidence/rocketmq-m4-c02-runtime-aggregate-20261026.json)。AI受控owner关闭、实际SDK订阅线程和真实进程故障分别记账，未冒充八镜像或生产验收 |

### C03：旧读取与格式兼容（4/4）

| ID | 状态 | 子任务 | 必达验收 |
| --- | --- | --- | --- |
| C03-01 | ✅ 已完成 | QS Payload/Operation旧fallback退出 | 2026-10-26；QS当前operation/Payload仅认事务计划或精确Committed档案，缺适配先于资源拒绝，缺记录NotFound；历史身份不能授权新执行。QS PR451已合并，三档command各15事实/0失败跳过。[证据](evidence/rocketmq-m4-c03-current-readers-20261026.json)。源码与验证已完成，最终版本已随C08部署并回归 |
| C03-02 | ✅ 已完成 | QS receipt/ACK历史互通退出 | 2026-10-26；QS当前command receipt缺原Committed档案时原root回滚/隔离，不确认旧投递；当前Inbox/投影/首次ACK/witness与重复事件首wire保留。三档event各17事实通过。[证据](evidence/rocketmq-m4-c03-current-readers-20261026.json)。源码与验证已完成，最终版本已随C08部署并回归 |
| C03-03 | ✅ 已完成 | AI Payload reader旧fallback退出 | 2026-10-26；AI当前Payload缺档案NotFound、ACK缺原档案拒绝；保留result_outbox当前状态核验/历史。AI PR229已合并；两档各5725源码用例、六档各15 MySQL+mTLS测试/21事实通过。[证据](evidence/rocketmq-m4-c03-current-readers-20261026.json)。源码与验证已完成，最终版本已随C08部署并回归 |
| C03-04 | ✅ 已完成 | QS与AI最终协议契约验收 | 2026-10-26；正式稳定SDK下当前QS/AI六档各5测试/25事实通过；正文鉴权、错误身份/引用拒绝、重复command/receipt/ACK不重Seal/新执行，首次wire保持。infra PR329全部25项检查通过并合并。[证据](evidence/rocketmq-m4-c03-current-readers-20261026.json)。源码与验证已完成，最终版本已随C08部署并回归 |

### C04：中间协议、孤立工具与文档（3/3）

| ID | 状态 | 子任务 | 必达验收 |
| --- | --- | --- | --- |
| C04-01 | ✅ 已完成 | 无当前责任维护入口退出 | 2026-10-26；三库源码已合并：旧IAM切换CLI固定拒绝，AI mutating handoff退出，QS旧NSQ/中间Relay/Stage/ACK rearm及闲置工厂删除；当前准入、只读审计、离线正式预检保留；[receipt](evidence/rocketmq-m4-c04-final-protocol-20261026.json) |
| C04-02 | ✅ 已完成 | 中间夹具和临时互通测试清理 | 2026-10-26；孤立旧协议夹具/探针退出，历史拒绝只直接预置事实；逐组替代映射、27份严格原生报告及失败历史齐全。SDK通用兼容/开发依赖保留；当前Inbox/receipt/首wire/业务恢复不删 |
| C04-03 | ✅ 已完成 | 当前操作文档收敛 | 2026-10-26；三库当前操作/协议文档、有效命令和源码基线收敛；QS88检查器测试及事实/链接、AI75页/1270链接、IAM文档门禁通过；完整CI/合并均完成；旧阶段材料有明确历史范围 |

### C05：当前业务责任与废弃依赖（3/3）

| ID | 状态 | 子任务 | 必达验收 |
| --- | --- | --- | --- |
| C05-01 | ✅ 已完成 | 保留/删除/最小解耦职责映射 | 2026-10-26；[11项责任/26份源码摘要及冻结SHA](evidence/rocketmq-m4-c05-responsibilities-20261026.json)、[当前调用与最小解耦边界](rocketmq-m4-inventory.md#c05-01当前责任与最小解耦映射2026-10-26)已核对；[PR308](https://github.com/FangcunMount/infra/pull/308)已合并c212b93f3111eb8e715890cce257efc33c5b5fcd，源码2b3f7f4ab2efd3bbedf49b51d77c1692d2264bc3。职责映射阶段未删除代码/字段；后续解耦及恢复验证由C05-02/03完成 |
| C05-02 | ✅ 已完成 | 必要解耦和废弃依赖清理 | 2026-10-27；AI当前7个store方法/sequence/10夹具保持，发布依赖移除，result_outbox当前ACK/history保留；QS Store不再持有发布队列，当前运行摘要不依赖旧表，保留字段明确不可用而非模型预算；PR453已合并，29项完整CI通过；[receipt](evidence/rocketmq-m4-c05-current-responsibilities-20261027.json) |
| C05-03 | ✅ 已完成 | 非空事实与确定性恢复证明 | 2026-10-27；三档实际MySQL command原根增加GetRuntime/Backlog和Prepared证据拒绝断言，0失败跳过；AI两档各5668测试中的10类非空receipt/history/确定性finalization与不重派发恢复已核对，受控gateway计数不冒充在线模型；未来dispatch三档各41事实保留，当前责任/原attempt不变 |

### C06：部署配置与重建（12/12；门禁4/4）

| ID | 状态 | 子任务 | 必达验收 / 当前证据 |
| --- | --- | --- | --- |
| C06-A | ✅ 已完成 | infra旧生产入口源码退出 | 旧Compose/Make/安装启动入口清理；拒绝先于副作用，开发NSQ保留；PR301/35项CI |
| C06-B01 | ✅ 已完成 | IAM最终事务打包 | 原身份/完整预算/只读文件/关闭默认准入经真实decoder验证；PR151/8项CI |
| C06-B02 | ✅ 已完成 | worker消费专用打包 | 无owner/发布关闭，三个worker原并发和资源保持；PR443/29项最终组合CI |
| C06-B03 | ✅ 已完成 | QS API双owner打包 | 原身份、独立凭据、固定IAM订阅保持；错误参数先于包替换拒绝；PR446/29项CI |
| C06-B04 | ✅ 已完成 | API与AI桥接绑定一致性 | 2026-10-26；领域/桥接原qs.mysql、预算/准入与固定IAM订阅经真实decoder一致性验证；17类冲突拒绝。本地Go/race271、PR447完整29项检查及两档MySQL各1053项通过，已合并；[完整SHA/报告receipt](evidence/rocketmq-m4-c06-final-preflight-20261026.json) |
| C06-B05 | ✅ 已完成 | QS API强制主机预检 | 2026-10-26；首次安装及冻结版本复用均强制最终事务原生预检；Mongo凭据等九个文件只读/不自动创建来源，失败先于同步或停止。主机17项、真实标准镜像10项/0失败错误跳过与PR447完整CI通过并合并；D02已预置材料，最终API主机工具及运行配置已随C08安装、启用并完成实机回读 |
| C06-C | ✅ 已完成 | AI最终事务部署入口 | 缺失/禁用/NSQ/M1目标拒绝；七文件、原身份及预算通过；PR225/12项CI/11406执行0失败错误跳过 |
| C06-D01 | ✅ 已完成 | 实际原绑定和材料冻结 | 2026-10-26；四owner的原数据库binding逐字节一致；MySQL只读事务/TLS、Mongo primary/majority；八实例/19处MQ+8处JOSE/5个主体指纹、只读挂载/Unix可读性、原UID/资源与worker48并发通过；[完整摘要/失败历史](evidence/rocketmq-m4-c06-original-bindings-20261026.json)。[PR310](https://github.com/FangcunMount/infra/pull/310)已合并df5a1c0abbce5727ad0bb72440445f7eb8297b96；原D01仅只读核对 |
| C06-D02 | ✅ 已完成 | 版本化部署材料准备 | 2026-10-26；PR311/312源码及14源测试+19真实Unix/锁验证通过；原21份材料预置到root控制的新版本，回读四角色完全一致，当时8实例/活动指针/原锁不变；材料随后在C08以冻结的只读挂载启用，原活动指针保持。[完整SHA/CI/生产材料receipt](evidence/rocketmq-m4-c06-versioned-materials-20261026.json)；已合并记账，不冒充运行版部署 |
| C06-D03 | ✅ 已完成 | 隔离环境八实例重建 | 2026-10-26；[PR315](https://github.com/FangcunMount/infra/pull/315)候选012d1ce4fa24d115a1ad01eb063407cb8c52ef99通过13项CI后合并c0c0818d50aecfe53cad270230c96407f7b1bdf5。真实五镜像/八实例18项、Go实际codec3项、四owner/只读27处材料挂载/原预算、零DDL及全部关闭/清理通过；三个worker另9次重启Exit0。首轮服务键及JSON时长失败保留；[完整receipt](evidence/rocketmq-m4-c06-eight-instance-rebuild-20261026.json) |
| C06-D04 | ✅ 已完成 | 材料错误于替换前拒绝证明 | 2026-10-26；PR318/319及IAM153、QS449、AI227已合并。四角色50项实际部署用户/root工具/Unix权限与锁验证全部通过，23源保护+27真实Linux基础回归、IAM8/QS29/AI12完整CI通过；AI两档MySQL共11428执行/0失败错误跳过。[完整SHA、报告和失败历史](evidence/rocketmq-m4-c06-host-guard-20261026.json)。不依赖旧来源、不重建锁或切指针，生产固定新工具及宿主保护已由C08安装验证 |
| C06-D05 | ✅ 已完成 | 合并和冻结C06配置契约 | 2026-10-26；[固定契约](evidence/rocketmq-m4-c06-config-contract-20261026.json)关联D01—D04、四材料收据、五阶段镜像、八实例预算、固定工具与三库完整SHA/CI/合并；随PR320合并生效。D04未改运行源码/镜像输入，最终清理镜像、生产工具安装及逐角色回读/启用已由C08完成，自动CD已由追加操作恢复 |

C06-B由B01—B05汇总，C06-D由D01—D05汇总。源码/隔离重建与生产部署分别取证；C08已完成最终材料启用和生产部署。详细输入见[八实例重建边界](rocketmq-m4-config-rebuild.md)。C06阶段只验证配置/部署入口；清理后的最终镜像由C08重新冻结。

### C07：历史资产处置（4/4）

| ID | 状态 | 子任务 | 必达验收 |
| --- | --- | --- | --- |
| C07-01 | ✅ 已完成 | 具名处置清单冻结 | 原盘点及保护对象已冻结；10月27日追加范围固定旧窗口11份备份、退役NSQ及五SQL表/Mongo队列终态数据，当前表/未决事实明确排除。见[最新资产台账](rocketmq-m4-retained-assets.md) |
| C07-02 | ✅ 已完成 | 保护副本与恢复边界核对 | 初验归档可读及原摘要证明保持于旧receipt；10月27日按用户授权删除具名旧保护副本，保留审计元数据。首启动屏障与禁止旧全量覆盖新事实继续有效。见[追加receipt](evidence/rocketmq-m4-post-closure-20261027.json) |
| C07-03 | ✅ 已完成 | 到期处置或政策保留登记 | 原保留期已由用户明确豁免；具名资产删除和旧发布终态清理已完成并回读不存在/剩余0。原目录为bind挂载，无独立命名卷；未执行DROP、泛化prune或当前业务数据删除 |
| C07-04 | ✅ 已完成 | 资产责任台账闭环 | 最新具名范围、删除结果及保护对象已写入[资产台账](rocketmq-m4-retained-assets.md)和追加receipt；不再等待11月25日。当前事实/未决证据不自动过期，原历史receipt保持 |

### C08：最终候选与生产闭环（5/5）

| ID | 状态 | 子任务 | 必达验收 |
| --- | --- | --- | --- |
| C08-01 | ✅ 已完成 | 最终依赖和文档审计 | 2026-10-27；QS PR454/AI PR231完整CI后合并，实际移除AI旧客户端依赖/无调用CI服务，当前文档与历史范围明确；保留5组例外有责任依据。两档各5668源码用例、18份真实报告及最终八实例18/codec3验证通过；[完整审计与失败历史](evidence/rocketmq-m4-c08-final-audit-20261027.json)。制品/部署/业务另计，infra PR338已合并a58a6e9aebc42087f1c97534a547a10df6400e8a |
| C08-02 | ✅ 已完成 | 最终应用候选冻结 | 2026-10-27；[ACR run40371739428](https://github.com/FangcunMount/iam/actions/runs/40371739428)5/0/0；五类原归档在A/D预置，真实保存config/rootfs/关键配置相同、实际engine ID与ACR摘要分记。五项目Compose及环境/原21份材料的27处挂载冻结，API正式离线原生预检/重复冻结/3错误参数拒绝通过；[完整receipt](evidence/rocketmq-m4-c08-final-freeze-20261027.json)。稳定SDK不变；最终八实例已按本候选部署，实际验收见C08-04；由[infra PR339](https://github.com/FangcunMount/infra/pull/339)记账，已合并记账 |
| C08-03 | ✅ 已完成 | 生产执行与恢复演练 | 2026-10-27；PR340/341/342合并、最终Linux/macOS各27项通过；五项目真实CLI预览及10次普通镜像UID/GID检查、原锁/材料/入口验证通过。实际在途零、7 blocked保护；唯一v3包、首启动屏障及仅前向恢复冻结。[执行包receipt](evidence/rocketmq-m4-c08-window-ready-20261027.json)/[精确目标源码](evidence/rocketmq-m4-c08-window-operator-20261027.py.txt)。源包已由PR343合并，实际窗口和部署已由C08-04完成 |
| C08-04 | ✅ 已完成 | 受控部署与真实业务回归 | 2026-10-27；09:05:31—09:22:52统一维护，8实例固定镜像健康/0重启；system空角色及双订阅、新答卷→评分/规则报告、新AI解读/4事件及ACK全部通过，13条业务witness精确Committed，旧模型事实未变。[实际部署receipt](evidence/rocketmq-m4-c08-production-deployment-20261027.json)。四HTTPS200/10目标up、D可用1218MiB，CD已由追加操作恢复；已合并记账 |
| C08-05 | ✅ 已完成 | 发布索引及任务闭环 | 2026-10-27；[正式发布索引](rocketmq-m4-production-release.md)分记源码/依赖、ACR/engine、实际部署、业务、保留及CD；[receipt](evidence/rocketmq-m4-final-release-20261027.json)绑定C08-04源码e3ce7d4f38c2c5798d0203a481351cbb7a27d917及全部阶段摘要。文档JSON/链接/38项一致性检查通过，PR344已合并，M4正式闭环；未覆盖失败或历史快照 |
<!-- M4 leaf tasks end -->

## 统一验收与依赖

- 配置：原store/epoch按字节比较；qs.mysql桥接/领域一致，Mongo独立账号，IAM精确订阅，worker无owner及发布权限；NORMAL/TRANSACTION路由类型保持。
- 事务与业务：保留原根事务/witness/Checker、首次ID/wire/密文、Inbox/receipt/首次ACK、幂等、未来due/attempt/授权及模型response/checkpoint。缺记录或未知结果不触发旧fallback、假回滚或业务重做。
- 生命周期与资源：空闲Checker/真实在途/队列上界/取消/关闭正确；构造启动无DDL，主机DB/loop归属不变；八实例原预算和worker共享消费预算不放大。
- 安全与材料：鉴权、Prepared保护、只读文件、Unix权限、固定审核root工具、Mac mini固定SSH、原部署锁inode、CA及镜像保留范围保持。
- CI：required报告非空，0失败/错误/跳过，缺依赖失败；条件workflow未触发与用例skip分记。删旧测试必须映射最终协议覆盖，失败历史保留。沿现有固定SDK/客户端/宿主矩阵，不重复发布未修改SDK；宿主变化通过真实宿主入口验证。
- 故障：执行与本批变更相关的真实半消息/提交不确定性/进程退出/跨实例Checker回归；网络、数据库和进程故障只在隔离环境注入。R01—R03高级原生超限恢复仍在[独立台账](rocketmq-native-recovery-followups.md)，不加入M4。
- 生产：按冻结最小合法用例回归IAM双订阅、答卷/评分/报告及QS—AI回执链；通知/模型调用范围写入执行单，不重做原7个blocked请求。PL-R007/008移交项不冒充通过；不重新设置48h观察门禁。
- 资产：保留期内可登记政策保留及责任，不要求现在删完；物理处置仅限具名对象，不做泛化prune/GC。

依赖顺序：C01 → C06-B04/B05 → C06-D01—D05；C05-01职责确认可同时推进，并作为C02/C03删除动作的前置。其后按IAM → QS → AI责任链小批完成C02—C05；C08-01/02/03准备最终候选，再执行C08-04生产回归。C07按政策完成处置或保留登记，最后C08-05闭环。C06配置合同与C08最终镜像分别冻结，避免把阶段镜像冒充清理后的发布候选。

每个叶子任务完成：保存实现与验收证据 → 勾选并写完成日期/完整SHA/测试报告 → 分记PR、镜像、生产及业务状态 → 会话报告完成项/进度/阻塞/下一项。父任务在所属叶子验收和PR合并、相应门禁满足后完成，里程碑在父任务闭环后完成。新增/拆分显式改分母，不用删失败提高进度。

## 保留资产与独立后续项

M4正式任务已全部完成。以下事项按原决定保留或独立跟进，不计入M4未完成任务：

| 事项 | 当前状态及责任边界 |
| --- | --- |
| 历史资产处置 | 用户已豁免等待期；具名资产及终态数据清理完成，当前事实/必要结构继续保护。见[资产台账](rocketmq-m4-retained-assets.md) |
| 自动生产CD | 已恢复：IAM/QS暂停开关false，AI自动部署true；事务绑定及发布准入与当前运行基线一致，未额外触发新部署 |
| IAM角色授权详情读取 | 既存服务端错误单独登记，未冒充该接口验收通过；本轮空角色创建及双订阅有独立证据 |
| R01—R03、PL-R007/008 | 沿用原独立移交；高级原生超限恢复见[后续台账](rocketmq-native-recovery-followups.md) |
| M3的48小时观察 | 用户已豁免，未执行或声称通过，不重新设为M4门禁 |

## 历史过程与证据

[历史执行记录](rocketmq-m4-execution-history.md)保存原始C06内部批次、早期“进行中/未部署”快照、全部失败历史以及C08逐项推进记录。历史计数不代表当前状态；本页38项子任务为唯一当前进度表。原始JSON receipt及其摘要未改写。追加处置以独立receipt记账。
