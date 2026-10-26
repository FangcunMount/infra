# M4 执行规划：生产切换后的旧链路清理

本文件是 RocketMQ M4 的唯一里程碑、任务和证据总表。用户于 **2026-10-22** 确认：不需要历史兼容，M3 专注生产切换，M4 专门清理。M3仍由[M3总表](rocketmq-m3-execution.md)维护；M2保持24/24。当前M4 **7/8父任务、33/38叶子**，C01—C07均已完成，C06门禁4/4；剩余C08最终候选、受控部署与真实业务回归。代码、合并、制品、部署和数据处置分别记账。

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
| M4-2 | 历史资产与闭环 | C07–C08 | ☐ C07政策保留完成，C08待最终候选 | 批准范围处置、数据保护、合并和发布索引齐全 |

## 任务表

| 完成 | ID | 任务及验收结果 | 状态 / 证据 |
| --- | --- | --- | --- |
| ✅ | C01 | 接收M3发布/T34用户豁免/旧责任处置记录；逐项冻结代码、服务、表、字段、卷、配置及明确保护对象 | 2026-10-25；源码97c4551、PR300已合并c56448a27ec0e7dfeb8b830306b0ba097a019544；四仓库独立worktree、18责任单元/699去重源码摘要、46表466列/9Mongo集合只读元数据、Go目标/Python31/infra7门禁0跳过与当前8实例健康通过；[清单](rocketmq-m4-inventory.md)/[证据](evidence/rocketmq-m4-c01-inventory-20261025.json)。无生产/数据变更；随本盘点PR合并生效 |
| ✅ | C02 | 删除三库已停用的生产NSQ provider及发布型Outbox/Relay运行入口、旧启动分支和无调用代码 | 2026-10-26；三库最终运行装配均已合并，三库汇总/真实故障门禁通过；[汇总receipt](evidence/rocketmq-m4-c02-runtime-aggregate-20261026.json)。隔离旧helper与读取清理归C03/C04/C05，未部署 |
| ✅ | C03 | 删除旧Payload/ACK/Operation reader fallback、历史格式互通与恢复兼容分支 | 2026-10-26；4/4叶子、QS PR451/AI PR229/infra PR329及PR331已合并，正式SDK下完整原生矩阵通过。[receipt](evidence/rocketmq-m4-c03-current-readers-20261026.json)。保留新协议RPC/鉴权/receipt；未部署 |
| ✅ | C04 | 删除未投产的宿主中间协议及对应孤立夹具/临时工具，收敛最终协议文档 | 2026-10-26；3/3完成，IAM PR155、QS PR452、AI PR230均完整CI通过并合并；三档API/worker/dispatch、三档QS原根、六档AI/mTLS及六档最终成对故障通过。[完整receipt/替代映射](evidence/rocketmq-m4-c04-final-protocol-20261026.json)。未部署，当前责任解耦归C05 |
| ✅ | C05 | 梳理旧命名下仍承担当前receipt/调度/业务历史的职责，保留或最小解耦，再移除确定废弃字段/依赖 | 2026-10-27；3/3闭环。AI当前存储与发布职责已拆分并保留state/ACK/history；QS PR453完整29项CI后合并11c106aa283bcd1e3f442da928985b3744fe54e8，当前摘要改读Committed档案/witness。三档原根及两档MySQL非空确定性恢复通过；[receipt](evidence/rocketmq-m4-c05-current-responsibilities-20261027.json)；无生产数据/模型动作 |
| ✅ | C06 | 删除旧生产NSQ部署/CD/自动启动/环境变量/监控及恢复脚本入口，核验新配置可完整重建 | 2026-10-26；12/12叶子、4/4门禁通过，八实例重建18项与四角色真实权限拒绝50项通过；三库主机保护完整CI并合并，配置契约随PR320合并冻结。[宿主保护证据](evidence/rocketmq-m4-c06-host-guard-20261026.json)/[固定契约](evidence/rocketmq-m4-c06-config-contract-20261026.json)。生产新工具/宿主保护安装和材料激活留C08，自动CD仍暂停、开发依赖保留 |
| ✅ | C07 | 按保留期限及具名清单处置旧容器/卷/表/镜像/备份；执行前核对未决责任及保护资产，完成后回读验证 | 2026-10-26；4/4政策保留闭环：三容器/1519文件/三配置保持，三份Mac mini归档完整流式可读、原摘要/0600一致。46 SQL表/9 Mongo集合具名登记；保留至2026-11-25后复核，当前/未决事实不自动过期。[台账](rocketmq-m4-retained-assets.md)/[receipt](evidence/rocketmq-m4-c07-retention-20261026.json)。无物理删除，随本PR合并生效 |
| ☐ | C08 | 完成废弃依赖/文档审计、清理后新链路回归、源码合并与清理发布索引，关闭8项任务 | 进行中；最终五镜像已构建，八实例18项/codec3项通过并由PR335合并；固定ACR发布、主机工具安装、受控部署及真实system回归待完成 |

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

状态采用待开始、进行中、验证失败、受阻、已完成。每项实现和必需验证完成后打勾，记录日期、完整源码 SHA、PR/CI/报告、对象清单和处置结果。代码、合并、发布、生产动作分别记账；保留失败历史，不删除失败任务或改分母提高进度。

M4 完成要求八项闭环、相关变更合并、必要制品发布、清理后最终链路验证通过及资产处置结果可复查。若对象按政策继续保留，要注明位置、用途和后续责任，不能伪称已删除。

## 38项可验收子任务（2026-10-26落表，33/38）

本节落实用户已确认的细分规划，沿用C01—C08八个父任务、三个里程碑及C06-A/B/C/D四门禁。38项只计算本节叶子任务一次；父任务7/8、叶子33/38和C06门禁4/4分别记账，不相加。已有8项完成沿用原实现/验证/合并证据，不把本次写规划计为新增完成。C06-A/C在后文门禁汇总重复展示，状态必须一致。

| 里程碑 | 父任务 | 叶子完成 | 完成门禁 |
| --- | --- | --- | --- |
| M4-P | C01 | 3/3 | 源码、对象、当前责任和M3移交冻结完成 |
| M4-1 | C02—C06 | 26/26 | 最终配置可重建，旧活动入口退出，保留责任及新链路回归通过 |
| M4-2 | C07—C08 | 4/9 | 资产处置/保留责任闭环，最终候选部署、业务回归和发布索引完成 |

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
| C02-01 | ✅ 已完成 | IAM旧provider/Outbox/Relay装配退出 | 2026-10-26；[IAM PR154](https://github.com/FangcunMount/iam/pull/154)候选9203ad1802da2cf07daaf380a7c3613930b52134以11项完整CI通过并合并0420222b7a3f3861d6769919926010e5a67a0aa2；三档MySQL各16项required源码原生、35项宿主存储/HTTP（含子用例）及22项Broker场景均0失败/跳过，真实IAM双实例/QS订阅及同进程新owner关闭/Checker通过。旧装配/自动Topic创建和旧NSQ镜像workflow退出，3脚本6组无副作用拒绝；原事务/业务/Redis职责不改。[范围与替代映射](rocketmq-m4-iam-runtime-cleanup.md)/[完整receipt](evidence/rocketmq-m4-c02-iam-runtime-20261026.json)。随PR321合并生效；未部署 |
| C02-02 | ✅ 已完成 | QS旧NSQ及扫描发布装配退出 | 2026-10-26；[QS PR450](https://github.com/FangcunMount/qs-server/pull/450)固定9850d15f0fdc385ca8c5a6dd30e394145ee7a89c，29项CI通过并合并ca1158ca472d42e7c58e067e170b116364b1d8ea（生成文档条件job未触发）；[infra PR322](https://github.com/FangcunMount/infra/pull/322)15项CI通过并合并18ad52057dbf3859198b9a9e274da333330df443。[真实矩阵40314640918](https://github.com/FangcunMount/infra/actions/runs/40314640918)三档各API13/worker11/dispatch41、0失败/跳过、完整清理。264项相关race、374项infra单测通过；首两轮失败、专项14及三档worker11、删除映射和原责任保留于[receipt](evidence/rocketmq-m4-c02-qs-runtime-20261026.json)/[范围](rocketmq-m4-qs-runtime-cleanup.md)。本次进度记录合并后生效；未部署 |
| C02-03 | ✅ 已完成 | AI旧NSQ/MQRelay/M1装配退出 | 2026-10-26；[AI PR228](https://github.com/FangcunMount/qs-ai/pull/228)候选9a48509e777b4b0a819308dd05b7db7fff9af42f，12项CI/两档各5724用例0失败错误跳过后合并a2f192733312fef591bb9be24e5e3892e470420e；[infra PR326](https://github.com/FangcunMount/infra/pull/326)六档真实QS↔AI各5测试/25事实通过并合并8c798db7c5f71c968740e6f0bcb7e5179392e811。82项本地/13关键函数AST保持，旧选择拒绝及历史责任见[范围](rocketmq-m4-ai-runtime-cleanup.md)/[receipt](evidence/rocketmq-m4-c02-ai-runtime-20261026.json)。未部署，C04文档收敛/C08最终镜像另计 |
| C02-04 | ✅ 已完成 | 三库入口与生命周期回归 | 2026-10-26；当前合并版本三档IAM/QS各35存储/HTTP测试、22 Broker事实，六档QS/AI各7测试/40事实，均0失败/跳过、完整清理。复用同源码树QS三档API13/worker11/dispatch41；旧选择拒绝、空闲Checker、真实在途、失败清理和关闭见[精确映射及receipt](evidence/rocketmq-m4-c02-runtime-aggregate-20261026.json)。AI受控owner关闭、实际SDK订阅线程和真实进程故障分别记账，未冒充八镜像或生产验收 |

### C03：旧读取与格式兼容（4/4）

| ID | 状态 | 子任务 | 必达验收 |
| --- | --- | --- | --- |
| C03-01 | ✅ 已完成 | QS Payload/Operation旧fallback退出 | 2026-10-26；QS当前operation/Payload仅认事务计划或精确Committed档案，缺适配先于资源拒绝，缺记录NotFound；历史身份不能授权新执行。QS PR451已合并，三档command各15事实/0失败跳过。[证据](evidence/rocketmq-m4-c03-current-readers-20261026.json)。源码完成，未部署 |
| C03-02 | ✅ 已完成 | QS receipt/ACK历史互通退出 | 2026-10-26；QS当前command receipt缺原Committed档案时原root回滚/隔离，不确认旧投递；当前Inbox/投影/首次ACK/witness与重复事件首wire保留。三档event各17事实通过。[证据](evidence/rocketmq-m4-c03-current-readers-20261026.json)。源码完成，未部署 |
| C03-03 | ✅ 已完成 | AI Payload reader旧fallback退出 | 2026-10-26；AI当前Payload缺档案NotFound、ACK缺原档案拒绝；保留result_outbox当前状态核验/历史。AI PR229已合并；两档各5725源码用例、六档各15 MySQL+mTLS测试/21事实通过。[证据](evidence/rocketmq-m4-c03-current-readers-20261026.json)。源码完成，未部署 |
| C03-04 | ✅ 已完成 | QS与AI最终协议契约验收 | 2026-10-26；正式稳定SDK下当前QS/AI六档各5测试/25事实通过；正文鉴权、错误身份/引用拒绝、重复command/receipt/ACK不重Seal/新执行，首次wire保持。infra PR329全部25项检查通过并合并。[证据](evidence/rocketmq-m4-c03-current-readers-20261026.json)。源码完成，未部署 |

### C04：中间协议、孤立工具与文档（3/3）

| ID | 状态 | 子任务 | 必达验收 |
| --- | --- | --- | --- |
| C04-01 | ✅ 已完成 | 无当前责任维护入口退出 | 2026-10-26；三库源码已合并：旧IAM切换CLI固定拒绝，AI mutating handoff退出，QS旧NSQ/中间Relay/Stage/ACK rearm及闲置工厂删除；当前准入、只读审计、离线正式预检保留；[receipt](evidence/rocketmq-m4-c04-final-protocol-20261026.json) |
| C04-02 | ✅ 已完成 | 中间夹具和临时互通测试清理 | 2026-10-26；孤立旧协议夹具/探针退出，历史拒绝只直接预置事实；逐组替代映射、27份严格原生报告及失败历史齐全。SDK通用兼容/开发依赖保留；当前Inbox/receipt/首wire/业务恢复不删 |
| C04-03 | ✅ 已完成 | 当前操作文档收敛 | 2026-10-26；三库当前操作/协议文档、有效命令和源码基线收敛；QS88检查器测试及事实/链接、AI75页/1270链接、IAM文档门禁通过；完整CI/合并均完成；旧阶段材料有明确历史范围 |

### C05：当前业务责任与废弃依赖（3/3）

| ID | 状态 | 子任务 | 必达验收 |
| --- | --- | --- | --- |
| C05-01 | ✅ 已完成 | 保留/删除/最小解耦职责映射 | 2026-10-26；[11项责任/26份源码摘要及冻结SHA](evidence/rocketmq-m4-c05-responsibilities-20261026.json)、[当前调用与最小解耦边界](rocketmq-m4-inventory.md#c05-01当前责任与最小解耦映射2026-10-26)已核对；[PR308](https://github.com/FangcunMount/infra/pull/308)已合并c212b93f3111eb8e715890cce257efc33c5b5fcd，源码2b3f7f4ab2efd3bbedf49b51d77c1692d2264bc3。未删除代码/字段，不提前完成C05-02/03 |
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
| C06-B05 | ✅ 已完成 | QS API强制主机预检 | 2026-10-26；首次安装及冻结版本复用均强制最终事务原生预检；Mongo凭据等九个文件只读/不自动创建来源，失败先于同步或停止。主机17项、真实标准镜像10项/0失败错误跳过与PR447完整CI通过并合并；D02已预置材料，最终API主机工具及运行配置启用仍待后续 |
| C06-C | ✅ 已完成 | AI最终事务部署入口 | 缺失/禁用/NSQ/M1目标拒绝；七文件、原身份及预算通过；PR225/12项CI/11406执行0失败错误跳过 |
| C06-D01 | ✅ 已完成 | 实际原绑定和材料冻结 | 2026-10-26；四owner的原数据库binding逐字节一致；MySQL只读事务/TLS、Mongo primary/majority；八实例/19处MQ+8处JOSE/5个主体指纹、只读挂载/Unix可读性、原UID/资源与worker48并发通过；[完整摘要/失败历史](evidence/rocketmq-m4-c06-original-bindings-20261026.json)。[PR310](https://github.com/FangcunMount/infra/pull/310)已合并df5a1c0abbce5727ad0bb72440445f7eb8297b96；原D01仅只读核对 |
| C06-D02 | ✅ 已完成 | 版本化部署材料准备 | 2026-10-26；PR311/312源码及14源测试+19真实Unix/锁验证通过；原21份材料预置到root控制的新版本，回读四角色完全一致，8实例/活动指针/原锁不变、未激活。[完整SHA/CI/生产材料receipt](evidence/rocketmq-m4-c06-versioned-materials-20261026.json)；本PR合并后生效，不冒充运行版部署 |
| C06-D03 | ✅ 已完成 | 隔离环境八实例重建 | 2026-10-26；[PR315](https://github.com/FangcunMount/infra/pull/315)候选012d1ce4fa24d115a1ad01eb063407cb8c52ef99通过13项CI后合并c0c0818d50aecfe53cad270230c96407f7b1bdf5。真实五镜像/八实例18项、Go实际codec3项、四owner/只读27处材料挂载/原预算、零DDL及全部关闭/清理通过；三个worker另9次重启Exit0。首轮服务键及JSON时长失败保留；[完整receipt](evidence/rocketmq-m4-c06-eight-instance-rebuild-20261026.json) |
| C06-D04 | ✅ 已完成 | 材料错误于替换前拒绝证明 | 2026-10-26；PR318/319及IAM153、QS449、AI227已合并。四角色50项实际部署用户/root工具/Unix权限与锁验证全部通过，23源保护+27真实Linux基础回归、IAM8/QS29/AI12完整CI通过；AI两档MySQL共11428执行/0失败错误跳过。[完整SHA、报告和失败历史](evidence/rocketmq-m4-c06-host-guard-20261026.json)。不依赖旧来源、不重建锁或切指针，生产新工具尚未安装 |
| C06-D05 | ✅ 已完成 | 合并和冻结C06配置契约 | 2026-10-26；[固定契约](evidence/rocketmq-m4-c06-config-contract-20261026.json)关联D01—D04、四材料收据、五阶段镜像、八实例预算、固定工具与三库完整SHA/CI/合并；随PR320合并生效。D04未改运行源码/镜像输入，最终清理镜像及生产工具安装/逐角色回读/启用仍归C08，不能解除CD暂停 |

C06-B由B01—B05汇总，C06-D由D01—D05汇总。既有源码完成不表示材料已安装或已部署；详细输入见[八实例重建边界](rocketmq-m4-config-rebuild.md)。C06阶段只验证配置/部署入口；清理后的最终镜像由C08重新冻结。

### C07：历史资产处置（4/4）

| ID | 状态 | 子任务 | 必达验收 |
| --- | --- | --- | --- |
| C07-01 | ✅ 已完成 | 具名处置清单冻结 | 2026-10-26；具名三容器/配置/数据、三归档、46 SQL表/9 Mongo集合及全部当前保护对象冻结；位置/用途/原责任/政策均见[台账](rocketmq-m4-retained-assets.md) |
| C07-02 | ✅ 已完成 | 保护副本与恢复边界核对 | 2026-10-26；三份Mac mini保护归档原摘要/字节/0600一致，完整流式读完普通文件而不解包；原源码副本与退役pre-state可读。首启动屏障与禁止旧全量覆盖新事实保持；[receipt](evidence/rocketmq-m4-c07-retention-20261026.json) |
| C07-03 | ✅ 已完成 | 到期处置或政策保留登记 | 2026-10-26；采用政策保留；实际回读三NSQ停止/restart=no、1519文件及原配置/挂载不变，无监听/活动连接，读取前后容器运行身份一致；不删除或清理资产 |
| C07-04 | ✅ 已完成 | 资产责任台账闭环 | 2026-10-26；具名数据/恢复及infra维护责任、最早2026-11-25复核时间、原未决责任/依赖保护与独立处置触发条件齐全；当前事实/未决证据不自动过期，无自动GC；随本PR合并闭环 |

### C08：最终候选与生产闭环（0/5）

| ID | 状态 | 子任务 | 必达验收 |
| --- | --- | --- | --- |
| C08-01 | ☐ 进行中 | 最终依赖和文档审计 | 活动入口、构建/配置/workflow/依赖与文档一致，所有保留例外有理由 |
| C08-02 | ☐ 进行中 | 最终应用候选冻结 | 完整CI通过，固定源码SHA/依赖/镜像digest/配置/材料摘要；不改已发布SDK标签 |
| C08-03 | ☐ 进行中 | 生产执行与恢复演练 | 八实例/准入/关闭/启动/兼容恢复边界明确，实际配置与候选重建一致 |
| C08-04 | ☐ 待开始 | 受控部署与真实业务回归 | 回读逐实例版本/健康；合法最小用例核对业务事实/witness/消费/receipt，恢复重投不增模型调用 |
| C08-05 | ☐ 待开始 | 发布索引及任务闭环 | 八父任务门禁满足，合并/镜像/部署/业务/资产/CD最终状态分别记账 |
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

## 执行记录

- 2026-10-22：按用户最新决策建立M4，进度0/8；只建立清理范围与移交表。未删除业务代码/历史记录/容器/卷，未更改生产配置，M3完成数仍17/36。

- 2026-10-25：M3已按用户豁免48h后的修订范围闭环，生产NSQ服务/restart责任退出。接收最终发布索引、保留对象、CD暂停与人工恢复限制；C01仍需完整对象盘点，M4保持0/8，未执行代码/物理删除。

- 2026-10-25 C01：责任链与独立基线盘点完成，1/8。当前数据和业务事实、SDK通用兼容、开发NSQ及迁移历史链明确保护。C06进入源码批次，未删除业务代码/表/卷/备份，未重启业务或启用自动CD。


## C06 内部执行批次（同一正式任务，4/4）

以下子门禁不增加8项分母。实现及对应验证/合并通过后才勾选；生产安装/业务验收单列，不自动启用CD。

| 完成 | 子批 | 验证及状态 |
| --- | --- | --- |
| ✅ | C06-A infra旧生产入口 | 已删除源码中的旧serverD NSQ Compose、旧Make初始化/启停/销毁/重建及生产专用recreate；生产NSQ/all安装和启动/重启、RocketMQ主机旧initializer在副作用前拒绝。通用开发NSQ保留。新红绿入口保护7项＋原有界patch/marker7项、监控7项及migration/proxy本地回归通过；[PR301](https://github.com/FangcunMount/infra/pull/301)源码778ffec5d3026b333bc7001e26f9d77baadbbc25、35项CI全部成功，合并06fa8bbfd0d1309a859af524542549e76bbeb1ba。未安装生产源码，无数据/容器删除 |
| ✅ | C06-B IAM/QS最终配置 | B01—B05全部源码/验证完成并合并；IAM PR151、worker PR443、API包PR446及最终预检PR447通过完整CI。原身份/预算、固定IAM订阅与worker消费专用保持；真实标准API镜像十项离线验证通过。实际材料与八角色重建留C06-D |
| ✅ | C06-C AI最终配置 | [PR225](https://github.com/FangcunMount/qs-ai/pull/225)候选b2c1015beb292c22ff6ed48ea011f5b88fd1e732通过12项完整CI后合并eaa22cd92828d7f1c0286339e620c6c087763e0c；生产打包/prepare/apply/restore只接受完整最终事务绑定，在镜像/迁移/替换前拒绝缺失、禁用、NSQ及M1目标。387项本地通过；两档MySQL各5703、合计11406执行/0失败/0错误/0跳过，八份制品同用例集且无重复，原美元字节真实容器环境证明通过。原PR224与失败历史保留。实际私有材料及完整重建留C06-D；未部署 |
| ✅ | C06-D 配置可重建及收口 | D01—D05全部实现/验证，相关三库与infra源码已合并，契约随PR320合并冻结。原权威绑定、21份未激活材料/27挂载、八实例18项及四角色同步/停止前50项拒绝验证通过。C08仍须安装新固定工具和宿主保护、核对最终候选后受控部署；自动CD继续暂停 |

2026-10-25 C06-A当前为源码/本地验证阶段：历史M3-NSQ首次退役的Compose验证改用有界fixture保留原语义，新增实际旧入口无副作用保护；当前流水线验证源码已移除生产栈、通用dev Compose仍可渲染，不启动任何容器。原M3报告/提交不改写。


2026-10-25 C06-A完成：35项源码CI全部成功后合并PR301，内部进度1/4；M4正式进度仍1/8。历史NSQ原始卷/容器/配置、备份及Mac mini开发依赖未删除。IAM PR151和AI PR224分别进入完整CI；新只读挂载目录、实际原绑定及八角色配置重建必须在恢复CD前验证，不因源码合并而自动打开发布。


C06-B IAM CI首轮失败保留：实际Compose规范化JSON省略 `create_host_path=false`，测试直接索引导致KeyError；已按Compose有效语义读取缺省false，生产Compose源码的显式false未改变。后续CI必须重跑成功，失败不计为完成。


### C06-B 仓库组件明细（不增加正式任务分母）

| 组件 | 源码/验证 | 生产状态 |
| --- | --- | --- |
| IAM | ✅ PR151已合并；8项CI成功，真实配置与Compose验证通过；140个本地Go测试事件/0失败/0跳过 | CD主线构建成功，Deploy to Production明确skipped；新资产目录和原绑定重建仍待核验 |
| QS worker | ✅ 源码/CI已完成并合并 [PR443](https://github.com/FangcunMount/qs-server/pull/443)候选3a5dd847774175fdaf2fe3adaba2d1948f88e62d：消费专用、无owner、48并发、固定三个只读文件已实现；103个Go/race测试事件及原CD/锁/镜像保护回归通过；真实Compose已通过，独立候选33项检查通过；与最新main组合为ddf5eb4d68165b42af37e283346cbefb72d2db2a，五包race 210测试事件通过，组合候选29项检查成功，已合并2c2133d71f7d544c42bc1ee5668039e0fb7b7e7d | 未部署；实际材料/重建留C06-D，当前三worker和配额保持 |
| QS API/AI bridge/IAM订阅 | ✅ [PR445](https://github.com/FangcunMount/qs-server/pull/445)领域点号owner保留修复已通过32项检查并合并0c83378e2a65eaa60e0429b751a5af8f85d334b4，107个Go/race测试事件通过。[PR446](https://github.com/FangcunMount/qs-server/pull/446)打包子批已通过29项CI（另1条件job未触发）并合并5480895b8a3f7a11f06489f8b2ccbeea585fcf39，249个Go/race测试事件、三类服务包和文档88项通过；双owner原身份/完整预算、凭据分离、固定IAM fanout及无效输入于包替换前拒绝已实现。最终[PR447](https://github.com/FangcunMount/qs-server/pull/447)候选5c322de8d47756e4de374ff399c3c2af08e57d39通过29项检查后合并25318edf88982be040639202295d1966cec72437，真实标准镜像十项、主机17项及两档MySQL各1053项通过。实际材料重建留C06-D | 自动CD继续暂停 |

2026-10-25 C06配置批次：[本地验证/源码/失败历史receipt](evidence/rocketmq-m4-c06-source-progress-20261025.json)。IAM合并与镜像构建、AI/QS候选和CI、实际生产部署分别记账。QS现行 `durable_outbox` 事件分类仍被事务订阅使用，不因命名删除；尝试不受支持的新分类被真实loader拒绝，已在提交前恢复现行协议，失败报告保留。原NSQ资产及备份未处置，M4总进度仍1/8、C06内部1/4。


2026-10-26 C06后续验证：AI候选更新8b9bfeeef3c1756cd31f0af2a9e2e919c56e4544，本地153通过，两个真实Compose用例继续交CI；已下载MySQL8.4分片0的1422项/0失败/0错误/0跳过报告，其中实际“仅创建、不启动”的无网络容器环境证明原store/epoch美元字节保持。完整CI仍待结束，不提前合并。

QS worker更新3a5dd847774175fdaf2fe3adaba2d1948f88e62d，保留首轮三个CI失败：旧Go fixture不接受长格式挂载、生产fixture未注入endpoint、actionlint变量未登记；已保留原资源/DNS/日志断言并更新真实契约，本地三包race 103测试事件/0失败/0跳过与actionlint通过。独立前置[PR444](https://github.com/FangcunMount/qs-server/pull/444)只排除可信文件读取自身更新的atime，仍校验九个稳定字段，35+5+9项本地保护通过，实际Mongo native CI通过；完整CI/合并待完成，未修改生产SSH设置。

API配置子批[PR445](https://github.com/FangcunMount/qs-server/pull/445)，候选01f1743dde1329c1c07a5b98f4828d747b57938c，修复AI overlay将原领域点号owner展开的问题。真实Render→宿主decoder及options两包race 107测试事件/0失败/0跳过通过，原身份、两个凭据、预算和准入关闭保持；完整CI及全部最终CD配置收敛仍待完成。所有失败及原始私有报告摘要继续保留在同一receipt，不删除失败记录来提高进度。


2026-10-26 合并记录：AI PR224在12项CI全成功后合并20ceaae60df72d0e201a97039aab6f46722fb786；8个JUnit分片已下载复核，两档MySQL各5688项、合计11376执行/0失败/0错误/0跳过，各自无重复且覆盖集合相同。原153项本地及两项真实Compose的证据边界分别保留。SSH读取前置PR444的32项检查成功（另1条件job未触发），已合并d983284ec26e32507e4914bb89fbb575e8f58536。QS worker/API overlay仍待各自完整CI；源码合并不打开生产CD，不代表C06已完成。


2026-10-26 API overlay PR445的32项检查成功（另1条件job未触发），已合并0c83378e2a65eaa60e0429b751a5af8f85d334b4。Worker独立候选3a5dd847774175fdaf2fe3adaba2d1948f88e62d的33项检查全过（另1条件job未触发）；同步最新main仅两份文档/源码基线冲突，已同时保留worker与renderer的受验修改。组合候选ddf5eb4d68165b42af37e283346cbefb72d2db2a，源码基线ea17805fd，五包race 210测试事件/0失败/0跳过与文档/actionlint通过，完整CI重新验证后才合并。自动CD继续暂停；实际原绑定、只读材料版本/权限、缺材料于替换前拒绝及八角色完整重建均未提前打勾。


2026-10-26 worker子批闭环：[PR443](https://github.com/FangcunMount/qs-server/pull/443)最终候选ddf5eb4d68165b42af37e283346cbefb72d2db2a在[CI 40212566834](https://github.com/FangcunMount/qs-server/actions/runs/40212566834)的29项检查成功后合并2c2133d71f7d544c42bc1ee5668039e0fb7b7e7d；另1项 `Docs & API Generated Sync` 是未触发的条件job，不冒充测试用例0跳过。原完整单独候选33项、组合210个Go/race测试事件和所有首轮失败均保留。无生产安装/服务重启/数据删除，生产CD暂停标志仍为true。

本批已合并：infra旧serverD入口清理、IAM最终事务生产包、AI事务包/七文件/最终路由预检、QS领域owner overlay及worker消费专用配置；整体C06尚未完成。下一批继续QS API完整CD配置、AI最终生产入口收敛，再做原绑定/材料与八角色重建；M4维持1/8，C06内部维持1/4。


2026-10-26 本轮只读配置输入：8角色挂载/配置摘要/Unix身份已采集，IAM、QS双owner原身份的打包预览及AI原完整预算校验通过；Go纳秒与YAML时长只做单位比较，原store/epoch不规范化。生产8应用/4owner/10监控目标/4公网健康检查通过，serverD约1236 MiB可用。该快照不代表最终候选或48h观察。具体输入及剩余既有门禁见[八角色重建边界](rocketmq-m4-config-rebuild.md)，C06-D不提前勾选。没有生产安装、DDL、业务写入或服务重启。

2026-10-26 本轮源码闭环：C06-C已完成，内部进度 **2/4**，M4正式进度保持 **1/8**。AI PR225的完整报告已下载验证，测试checkout08457bc49346df99fdc0b14e799924765fd161f1与候选b2c1015的源码树相同；12项检查与11406执行均通过后才合并。QS API打包PR446已合并，但AI桥接/主机预检和实际材料重建仍未完成，不提前关闭C06-B或C06-D。新采集19处MQ文件引用的摘要/权限/只读属性，仍只作为实际输入证据。IAM/QS暂停开关true、AI自动部署开关false；生产保持原M3受验版本与资源，未执行M4部署/DDL/业务请求/模型重做/资产删除。

2026-10-26 C05-01：在C06 CI期间并行核对11项当前责任，固定IAM/QS/AI完整SHA与26份源文件摘要，明确保留、后续删除及最小解耦边界。IAM会话撤销Outbox仍负责Redis任务；AI result_outbox仍承担精确state/ACK和业务历史，均不整表删除。责任映射实现/验证完成，随本PR合并后叶子进度9/38；C05父任务和M4正式1/8不提前完成。没有业务数据读取、DDL、模型执行或生产动作。

C06-B04/B05已形成[QS PR447](https://github.com/FangcunMount/qs-server/pull/447)候选5c322de8d47756e4de374ff399c3c2af08e57d39；本地Go race271/主机17项通过，真实标准镜像离线10项通过，两档MySQL各1053/0失败跳过。完整CI及源码合并仍待收尾，B04/B05保持进行中，C06仍2/4。

2026-10-26 C06-B完成：B04/B05由[PR447](https://github.com/FangcunMount/qs-server/pull/447)合并闭环，候选5c322de8d47756e4de374ff399c3c2af08e57d39，合并25318edf88982be040639202295d1966cec72437。29项CI成功，另1项条件Docs同步未触发，不冒充测试skip；真实标准镜像十项、两档MySQL各1053项/0失败跳过、本地Go/race271及主机17项通过。实际测试checkout6728f09f5685f10ed03c7a1c7656ca6c9c49728c与候选源码树93744ca06e359b8a3e95cb36f587c13ca1108f4d相同。[报告、摘要及失败历史](evidence/rocketmq-m4-c06-final-preflight-20261026.json)齐全。

本轮完成C05-01、C06-B04/B05；叶子进度 **11/38**，C06内部 **3/4**，正式进度仍 **1/8**。C06-D01仍进行中：下一步权威绑定核对、版本化原材料、八实例隔离重建、错误材料提前拒绝及配置契约冻结。C05-02/03、C02—C04及C07/C08均未提前完成。合并前回读QS生产暂停为true；新root工具/材料未安装、生产应用未部署、没有DDL/业务或模型调用/资产删除，未恢复自动CD。

2026-10-26 C06-D01完成：沿固定Mac mini SSH入口只读核对三个MySQL和一个Mongo权威binding，与当前配置原store/epoch按字节相同。MySQL借用镜像实际Python依赖建立独立短连接、显式READ ONLY及ROLLBACK；Mongo只读majority元数据，不读业务正文。再次冻结八实例/27处文件引用（19 MQ+8 JOSE）、五个Broker主体指纹及原Unix身份/预算，三个worker仍48并发。初版配置嵌套假设和解释器选择失败均保留，未据此改生产。随本PR合并后 **12/38**、C06内部仍 **3/4**，正式仍 **1/8**；D02开始准备版本材料，不修改活动运行配置。

2026-10-26 C06-D02源码开始：受限材料预置工具只新增不可变版本，固定四角色路径和Unix身份，不切换current/运行配置。14项本地源文件/路径/权限/原资产/复制故障保护及原7项退役入口回归通过；required Linux root/普通UID/共享锁19项待CI。D02保持进行中，未执行生产材料写入，当前12/38不变。

2026-10-26 D02目标机首轮预览拒绝应用UID2000拥有的 `/data` 祖先目录，生产尚无材料复制/激活。保留该失败，新增版本根调整为root控制的 `/var/lib/fangcun-m4-materials`；严格目录保护不放宽，不改旧目录/运行配置/共享锁。新根与receipt联动重新验证后才预置；三库最终CD来源路径将在D03/D04/D05同步，D02仍进行中、12/38不变。

2026-10-26 C06-D02完成：PR311候选39d210dc9edd48485d1438523d6c7464e48a5c05合并62a841fcd52e5e59a51bfa868402d0b161f89ee6；首次目标预览拒绝UID2000祖先目录，未复制/激活材料。PR312候选4f516c811bb293479edfdb223643f532d62c876d重新通过14源测试与19 Linux原生权限/锁用例后合并38d724421c2fb7996d253ba55f5c2ecac47a574a，采用独立root目录 `/var/lib/fangcun-m4-materials`，严格保护不放宽、旧目录不变。已预置 `m4-c06-20261026-v1` 的21份原材料，四角色回读均already-staged且完全一致；八实例fingerprint/活动指针/共享锁不变。新增root工具和私有计划、未激活材料分别留证，无业务部署/DB变更/凭据轮换/模型调用/旧资产删除。随本进度PR合并，当前 **13/38**、C06仍 **3/4**、正式仍 **1/8**。下一步D03联动三库宿主来源路径与八实例隔离重建，CD仍暂停。

2026-10-26 C06-D03路径合同子批：[IAM PR152](https://github.com/FangcunMount/iam/pull/152)通过8项检查后合并48182c39424573060fda0e27ed6670d2b326f42d；[QS PR448](https://github.com/FangcunMount/qs-server/pull/448)通过29项检查后合并d20436edb363c17f0b177126aebe43a44bc5e082（另1项条件Docs同步未触发），标准镜像10项离线预检通过；[AI PR226](https://github.com/FangcunMount/qs-ai/pull/226)通过12项检查后合并61ef88ac95800dfd3c0c90fd56c102f7c0e77e8f，八份JUnit报告已下载核对，两档MySQL各5703项、合计11406执行/0失败/0错误/0跳过，组内无重复、两档用例集合一致。QS/AI实际CI checkout与候选及合并源码树相同。三库宿主材料来源统一为root控制的新根，容器内约定保持；AI首轮打包器/主机路径不一致及本地无Docker daemon的失败保留，实际容器用例经完整托管CI通过，不启动MacBook Docker补测。[完整receipt](evidence/rocketmq-m4-c06-root-material-paths-20261026.json)。

已按三库合并SHA发起[五类阶段镜像构建](https://github.com/FangcunMount/infra/actions/runs/40282528557)，只用于隔离重建，不推送生产registry或启动生产业务。八实例实际重建、全宿主D04保护和D05契约冻结未完成，**13/38、C06 3/4、正式1/8均不变**；源码合并未恢复自动CD、未激活材料或变更运行实例。

2026-10-26 C06-D03完成：阶段五镜像构建成功，三库及builder SHA、运行SDK与制品摘要固定。PR315候选012d1ce4fa24d115a1ad01eb063407cb8c52ef99通过13项CI（另6项镜像阶段条件job未触发）后合并c0c0818d50aecfe53cad270230c96407f7b1bdf5。[原生运行40287252113](https://github.com/FangcunMount/infra/actions/runs/40287252113)18项/0失败/0跳过，八实例真实UID/GID、原CPU/内存、四owner Checker、21份合成材料的27处只读挂载、三个worker48并发及9次重启通过；所有进程Exit0且无OOM、MySQL/Mongo运行期DDL均0、原有容器/网络不变及本次隔离清理完整。Go实际codec另3项通过，源码本地46项保护通过。原服务键映射错误与Go绑定JSON时长编码错误均有失败报告和清理证明；修正后的源文件投影/实际Go解码前移到容器启动前，过时候选取消不计为验收。[完整SHA/报告摘要](evidence/rocketmq-m4-c06-eight-instance-rebuild-20261026.json)。当前 **14/38**、C06叶子 **10/12**，门禁仍 **3/4**、正式仍 **1/8**；本次是隔离配置证明，不是生产/业务验收。

同时推进C06-D04共用基础：[PR316](https://github.com/FangcunMount/infra/pull/316)候选5e12934e2acce531714fa1532ebcf71af54c4d68通过[CI40289126508](https://github.com/FangcunMount/infra/actions/runs/40289126508)后合并2f05980469b1c316263875ed1aafb6740452a4ad。只读入口验证已安装版本及root收据，不依赖旧M3来源、不重复获取父部署锁、不复制或激活材料；18项源保护、7项旧入口回归及23项真实Unix/锁用例通过。D04仍进行中：三库主机调用与同步/停止前完整拒绝证明未完成，生产工具未安装。合并前重新回读IAM/QS暂停为true、AI自动部署为false，未执行生产部署、DDL/凭据轮换/业务或模型调用/旧资产删除。


2026-10-26 C06-D04宿主保护进入完整CI收尾：root安装plan查找PR318已合并，23项源保护与27项真实Linux权限/锁回归通过。IAM PR153通过8项CI并合并ece67552793eee849d035b514d4be672eb4c3c8a；QS PR449与AI PR227待完整CI。infra PR319固定三库候选后，真实部署用户→固定root工具→宿主同步前门禁的50项故障验证全部通过、0失败/错误/跳过、完整清理，已合并d7f8edd189d7dd3532dbf54d2fd867f4285a3857。首轮GitHub runner `/opt` 0777导致正确拒绝，改用私有mount namespace提供本次独立祖先，不放宽生产保护；失败报告保留。AI新增主机预检引出的旧prepare/restore/镜像夹具缺口已修正，本地133项通过，完整CI重新运行；没有删除原镜像、锁和schema拒绝断言。D04尚未勾选，仍14/38；D05机器契约仅为候选。生产工具未升级、原材料未激活、自动CD仍暂停，未执行生产部署或业务/模型调用。


2026-10-26 C06-D04/D05收口（随[PR320](https://github.com/FangcunMount/infra/pull/320)合并生效）：IAM PR153、QS PR449、AI PR227分别以8/29/12项完整CI通过并合并；QS额外一项生成文档条件job未触发，不是用例skip。AI八份分片报告逐项验证同一精确候选/测试merge、每档5714唯一用例、完整互斥覆盖，MySQL8.0.36/8.4共11428执行、0失败/错误/跳过。infra PR319的四角色50项真实部署用户/root入口保护通过并合并；原锁inode/bytes及四活动指针保持、原来源删除后仍可校验、临时mount/材料全部清理。所有首轮权限环境和旧夹具失败保留，未删原镜像/schema/锁拒绝断言。[宿主证据](evidence/rocketmq-m4-c06-host-guard-20261026.json)与[配置契约](evidence/rocketmq-m4-c06-config-contract-20261026.json)固定原身份/预算、四材料收据、五阶段镜像和工具摘要。当前 **16/38**、C06叶子 **12/12**、门禁 **4/4**、正式 **2/8**。新工具/主机保护尚未生产安装，原材料未激活；最终应用候选及生产验证归C08，自动CD不解除。本次无SSH、生产部署、DDL/凭据轮换、业务/模型调用或旧资产删除。下一项C02-01已完成只读调用链预查，IAM平台/启动包97项race基线通过，尚未实施删除，不计任务完成。


2026-10-26 C02-01完成（随[PR321](https://github.com/FangcunMount/infra/pull/321)合并生效）：IAM PR154固定9203ad1802da2cf07daaf380a7c3613930b52134，11项CI通过后合并0420222b7a3f3861d6769919926010e5a67a0aa2。普通发布Outbox/Relay和NSQ装配、自动Topic准备、旧/新NSQ镜像workflow退出，三个旧proof脚本在外部命令前拒绝。删除的三个装配专项有明确当前测试映射，不再验证已退出的schema40/NSQ回退。相关本地237项race通过、1项MySQL条件用例在required原生CI补验；三档MySQL源码门禁各16顶层命名用例通过。真实[矩阵40303004302](https://github.com/FangcunMount/infra/actions/runs/40303004302)固定IAM、QS及稳定SDK源码，三档各35存储/HTTP用例（含子用例）及22 Broker场景全部通过、0失败/跳过、完整清理；双IAM实例与独立QS订阅、原witness/业务结果、同进程新owner Checker/关闭通过，不冒充完整API进程SIGKILL或system验收。原事务/journal/CAS/Checker、消费处理、失败审计、Redis撤销和C06配置输入按源码逐项未改。完整[receipt](evidence/rocketmq-m4-c02-iam-runtime-20261026.json)保留红绿测试、过时源运行取消及文档修复记录。本次进度 **17/38**，C02 **1/4**，父任务仍 **2/8**、C06门禁 **4/4**；C03/C04/C05宿主孤立helper/历史维护与职责解耦继续单列，不重复计数。无SSH、生产部署、生产DDL/凭据轮换、业务/模型调用、资产删除或恢复CD。下一项C02-02 QS，已只读定位标准发布Supervisor与事务/未来调度的责任边界，尚未修改QS源码。

2026-10-26 C02-02验证进度：QS PR450已退出API旧NSQ/标准发布Outbox选择及worker旧channel/发布/hold replayer装配；264项本地race通过，infra374单测通过，当前事务、NORMAL、原48预算、到期dispatch、hold/attempt/授权保留。首轮真实三档各API13/worker11通过，但报告夹具漏装原Mongo43治理schema，准入按保护规则拒绝；显式补齐后报告专项14通过，第二轮8.0.36/8.0.44各65项通过，8.4 worker在第二条输入等待处超时。原失败诊断在恢复实例清理后读取暂停实例，现补齐恢复实例的真实接收就绪屏障并提前采集活跃诊断，保留五物理输入、共享1和60秒断言；三档worker专项各11项通过、0失败/跳过、完整清理。最终完整矩阵及源码CI仍运行，C02-02不勾选，总进度维持17/38、C02 1/4、父任务2/8和C06 4/4。证据记录区分FF/FD中间源码与当前9850候选；无生产、SSH、模型、资产或CD操作。

2026-10-26 C02-02完成：QS候选9850d15f0fdc385ca8c5a6dd30e394145ee7a89c以29项完整CI通过后合并ca1158ca472d42e7c58e067e170b116364b1d8ea；infra验收候选854af825ca7a2d17a781e8f0f5a76a5402b4f55a以15项CI全通过后合并18ad52057dbf3859198b9a9e274da333330df443。最终三档MySQL各65项（双owner13、worker11、真实到期dispatch41）0失败/跳过；九报告与三summary的源码/SDK固定身份、摘要和四项清理逐一核验，原容器/网络一致性断言通过。前两轮schema夹具缺项及恢复就绪观察失败保留；只修正隔离fixture，生产运行代码保持原退役改造。门禁与合并完成后，进度更新为18/38、C02 2/4、M4-1 15/26，父任务2/8/C06 4/4不变。源码合并不代表部署；自动CD暂停，原48 worker预算、原事务/witness/Checker、业务重试/hold/NORMAL及历史资产保持。本批无SSH/生产DDL/凭据轮换/业务或模型调用/资产删除。下一项C02-03 AI；已完成只读调用链审计及51项改造前基线，尚未修改AI源码。


2026-10-26 C02-03完成：AI PR228及infra PR326均通过全部门禁并合并；源码两档MySQL各5724项/合计11448执行、六个原生配置各5项测试/25项事实，均零失败/跳过，摘要、固定稳定SDK与清理结果已核对。本地82项及13关键函数AST保持；原fixture/docs失败与四页needs_review保留，后续C04处理。进度记录合并后19/38、C02 3/4、M4-1 16/26，父任务仍2/8、C06仍4/4。无生产部署、DDL、模型调用或资产删除，CD仍暂停。C02-04已用当前合并版本发起[三档IAM/QS](https://github.com/FangcunMount/infra/actions/runs/40326990299)与[六档QS/AI进程/Broker故障](https://github.com/FangcunMount/infra/actions/runs/40326981798)，当前仅进行中。


2026-10-26 C02闭环：IAM/QS当前合并版本三档真实35存储/HTTP+22 Broker事实，QS/AI当前合并版本六档各7测试/40事实通过，生产者SIGKILL与Broker重启分别有实际退出/首次wire/新Checker/零模型调用证明。三库根入口拒绝、空闲Checker、在途排空/失败清理/关闭结合源码CI及同树QS原生报告核对，完整清理无失败跳过。[汇总receipt](evidence/rocketmq-m4-c02-runtime-aggregate-20261026.json)区分真实SDK线程、受控owner与真实进程故障。合并后20/38、C02 4/4、父任务3/8、C06 4/4；生产CD保持暂停、未部署或处置资产，C03—C05继续按边界清理。


2026-10-26 C03实施中：[QS PR451](https://github.com/FangcunMount/qs-server/pull/451)固定bb8e20e38562b31c6e9b01de99250e1eb70a6f16，[AI PR229](https://github.com/FangcunMount/qs-ai/pull/229)固定354e3465ef91b23ee7d5ade966a11b28089e059c。当前Payload/operation不再缺档案回退旧发布表；缺当前Committed档案的业务receipt/ACK拒绝，旧身份不能授权新执行。QS32项目标race、native tags编译及文档通过，AI51项/类型/lint通过；QS宽回归96通过7个缺依赖跳过明确不作为required门禁，原资料保留。当前成对门禁[40329911040](https://github.com/FangcunMount/infra/actions/runs/40329911040)及新增原事务/非空旧记录拒绝/MySQL+mTLS矩阵与源码CI尚未完成。隔离旧存储reader移入test-only夹具，由C04继续清理；当前业务历史、首wire/ACK、模型响应/恢复证据和生产资产不删除。C03尚无新勾选，20/38与3/8不变，生产CD继续暂停。


2026-10-26 C03闭环：QS PR451（29项成功、1条件Docs未触发）、AI PR229（12项成功，两档各5725测试/11450执行零失败错误跳过）、infra PR329（25项成功）已合并。当前QS三档各command15/event17事实、AI六档各15 MySQL+mTLS测试/21事实、当前配对六档各5测试/25事实通过，固定SDK/源码/镜像摘要与清理已核对；[完整receipt](evidence/rocketmq-m4-c03-current-readers-20261026.json)保留先红后绿、非required本地缺依赖skip及docs修正边界。进度记录合并后24/38、C03 4/4、父任务4/8、M4-1 21/26、C06 4/4；无生产部署/DDL/业务模型调用/资产删除，CD暂停。C04已独立推进[IAM PR155](https://github.com/FangcunMount/iam/pull/155)的旧切换工具/无生产调用Relay清理，72本地测试通过，完整CI尚未完成，不提前勾选C04/C05。


2026-10-26 C04三库源码子批：IAM [PR155](https://github.com/FangcunMount/iam/pull/155)的旧切换CLI/维护包及孤立探针已退出，72项本地race、原事务原生门禁和10项完整CI通过，合并4609d4542d9303130ab94ed67593d0a69d0d010d。当前原根授权维护、首次空库bootstrap、会话撤销和全部schema/历史材料保留。

AI [PR230](https://github.com/FangcunMount/qs-ai/pull/230)拆出当前Inbox/决策/技术失败与evaluation sequence声明，移除旧MQRelay、StateEventRecorder编排、mutating handoff及旧协议夹具；result_outbox当前state/ACK和模型response/checkpoint不变。158项本地目标测试、类型/文档检查通过；六档原生故障和六档MySQL+mTLS当前读取已在a83候选通过，后续仅CI/文档与旧测试参数修正，最终be5e806eedb73d92936c70fb7e5f9762e4bf2f91重新绑定完整源码及原生验收，尚未合并。M7残留文件路径、workflow源码摘要和三个旧decide测试参数的失败均保留，不恢复旧生产实现来迎合退役测试。

QS [PR452](https://github.com/FangcunMount/qs-server/pull/452)候选2a56f956edac647e822a953a38b8c7dba042e7d6移除旧NSQ/中间普通消息Relay、Stage/ACK rearm/旧正文helper、不可达标准Outbox组合器及孤立探针；保留原业务guard、当前事务receiver、负向历史ID排除、只读资产审计与离线预检。真实拒绝场景直接SQL预置历史事实，不调用退役写者。当前领域目录分类名保持，存储契约改为最终owner/显式迁移证据；旧SDK通用兼容和开发依赖留在明确隔离范围。本地8包783项race通过，7项既有可选数据库用例跳过，明确不作为required；88项文档检查器、全仓integration标签仅编译、文档事实/链接及发布工具通过，正式CI/原生门禁待完成。

C04仍0/3、C05仍1/3、总计24/38、父任务4/8；不把源码候选计为完成。修正本页父表C03的旧“待CI”文字，使之与已合并的4/4叶子/receipt一致。生产CD继续暂停；没有M4部署、生产工具安装/材料激活、DDL、历史资产删除、消息补发或模型调用。


2026-10-26 C07完成政策保留：沿固定Mac mini SSH入口只读核对serverD原三个NSQ容器、1519文件/155529092 bytes、三配置及原源码保护副本，身份/镜像/挂载/字节完全保持，无NSQ监听/活动连接，核验前后容器运行身份不变。Mac mini三份保护归档逐份核对原SHA/大小/0600，并流式读完全部普通文件，无解包/导入。C01的46 SQL表/9 Mongo集合仅复用具名schema盘点登记，不冒充新业务数据快照。本批未连接数据库、修改生产或恢复旧数据。

C07四项实现/验收与责任台账完成，随本PR合并后 **28/38、5/8**；采用保留至2026-11-25以后复核，未决/当前事实与引用依赖始终保护，不要求现在物理删除。详见[台账](rocketmq-m4-retained-assets.md)/[receipt](evidence/rocketmq-m4-c07-retention-20261026.json)。C04/C05源码及最终矩阵、C08最终镜像/工具安装/受控部署/system业务验收继续推进，不提前完成M4。


2026-10-26 C04完成：IAM PR155（10项CI）、QS PR452（29项CI成功、1条件生成文档未触发）、AI PR230（14项CI、两档各5668项/共11336测试0失败错误跳过）均已合并。三档QS API13/worker11/未来dispatch41事实、三档command15/event17事实、六档AI15测试/21事实和六档最终成对7测试/40事实全通过，零失败/跳过、完整清理。QS独立m3_ai_paired标签探针漏检的首轮编译失败已修正并前移编译门禁，失败保留。source2a56与最终3bf在产品运行路径相同，最终成对门禁已直接使用3bf，不能拿旧编译失败冒充通过。

C04三项随本PR合并后闭环，当前 **31/38、6/8**，M4-1为24/26。完整SHA、源CI、27份原生摘要与删除替代映射见[receipt](evidence/rocketmq-m4-c04-final-protocol-20261026.json)。C05的当前运行摘要仍连旧队列问题已由PR453单独修正，三档原根验证通过，最终源码CI待收尾，不提前勾选C05。

C08同时准备隔离五类候选：首次构建40351033230仅为候选，QS后续测试关闭检查修正将由40352408582重建三镜像；最终候选/实际部署尚未冻结，不冒充上线。生产CD保持暂停，原工具/材料未安装或激活，未执行M4应用部署、DDL、凭据轮换、补发或模型重做。


2026-10-27 C05完成：AI的发布队列与当前业务Inbox/决策/技术账本、state/ACK/history职责已最小拆开，所有原事实/模型恢复输入继续保留。QS发现当前Runtime摘要仍INNER JOIN旧发布表，现改为当前operation/immutable archive/精确Committed分支的元数据读取；Prepared或矛盾返回未知，不伪造零积压。旧command_attempts保留但明确command_attempts_available=false，不代表没有发送或模型调用。新增mock Close返回检查的CI失败已修正，最终29项CI成功、1条件文档job未触发后合并PR453；没有新增迁移。

实际三档原command根/current view/Prepared拒绝验证通过，受验路径与最终1f38源码一致；AI两档各5668测试、其中10类非空receipt/history/确定性finalization/reclaim/不重派发恢复逐项核对，全部0失败错误跳过。模型计数来自受控gateway，不宣称付费在线模型验收；原未来dispatch三档41事实受验路径未变。完整来源见[C05 receipt](evidence/rocketmq-m4-c05-current-responsibilities-20261027.json)。

随本PR合并，C01—C07闭环，当前 **33/38、7/8**，M4-1为26/26完成。剩余C08五项：PR335新增明确当前候选/同builder及八实例隔离重建，原C06固定历史profile不改；最终IAMfixture不再调用已退役切换CLI，而只在空的GitHub隔离数据库中显式迁移/安装当前绑定。合法system会话已请求用户准备；继续镜像/重建与部署清单工作。尚未安装生产新工具、激活材料、部署M4镜像、执行DDL或新模型调用，不恢复自动CD，不重置48h观察门禁。

### C08推进记录（2026-10-27）

最终候选由[独立清单](../../components/rocketmq/m4-final-image-candidates.json)冻结；[PR335](https://github.com/FangcunMount/infra/pull/335)固定6f7532cca8e85ecb317e8f4896b2a02965f5c712全部检查结束无失败后合并09c1d8984a22a7c6b9135f26b0e568ac54944a50。[真实八实例报告](evidence/rocketmq-m4-c08-eight-instance-native-20261027.json)为18项、零失败/跳过、八实例Exit0、零DDL及完整清理；[实际Go codec](evidence/rocketmq-m4-c08-binding-codec-20261027.json)3项通过。原C06阶段候选另行验证，未替换其历史默认值/证据。

五类镜像已构建，不等于已上传ACR或部署。M4发布采用独立18项报告profile，复用既有传输校验/不可变摘要回读及IAM既有生产环境凭据；不重建应用、不移动SDK标签、不弱化M3完整切换门禁。最终依赖审计、精确生产清单/同协议恢复、root工具安装和system真实业务回归尚未完成，C08五项均不提前勾选。合法system会话待用户解锁并正常登录；其余准备继续。

### C08主机与最终依赖补充（2026-10-27）

[固定材料工具主机准备](evidence/rocketmq-m4-c08-host-preflight-20261027.json)已实际完成：新36f3046e工具root/0555安装到A/D，四角色root与普通deploy正向校验、8项错误host/revision拒绝通过；原工具/规则保留。八实例镜像/配置/启动/重启/资源及原锁元数据前后相同，三worker实际HTTP ready；serverD可用内存1220MiB。未启用材料或部署应用，API原生冻结工具仍待安装，自动CD仍暂停。

实际原主库只读回读：IAM45/QS MySQL110/Mongo44/AI0043_native_transaction_limit，均clean，四owner原字节binding匹配；私有报告摘要f1408d7704e69ca38bb834c401258247b5cd7d58fa4fac160e3a018c8e82f798，无业务/模型调用。

C08审计补正：[QS PR454](https://github.com/FangcunMount/qs-server/pull/454)将当前阅读入口指向最终协议，旧四页显式标历史参考；[AI PR231](https://github.com/FangcunMount/qs-ai/pull/231)移除无调用的NSQ extra及CI服务，原wheel/SDK版本、JOSE和所有业务源码保持。离线锁仅移除pynsq/tornado，本地实际同步后当前导入有效且两客户端不存在，41项纯合同通过（9项跨语言用例明确未在本机执行，等待required CI）。需重新构建并验证AI候选；此前f83472c7镜像和发布计划为阶段材料，禁止作为最终生产包调度。

总表仍33/38、7/8，C08最终审计/制品/执行与真实system门禁未完成，不提前勾选。完整发布器PR337已通过10项CI后合并；其传输合同可复用，但必须重新固定最终AI归档和新启动报告。
