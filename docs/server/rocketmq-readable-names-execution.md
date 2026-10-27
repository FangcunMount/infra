# RocketMQ 可读资源命名执行总表

**当前进度：7/16。** 本表是本批唯一进度总表；M2/M3/M4 原计数保持。

## 已确认契约

同时迁移 Topic 与 ConsumerGroup；Topic 为 `场景--normal或tx--owner--route_revision`，Group 为 `逻辑Topic场景--逻辑订阅`。点号转连字符，输入只接受小写字母/数字和单个点号或连字符，拒绝空段、双连字符、超64字节结果、归一化碰撞；禁止随机后缀及哈希兜底。

引入 manifest v3 与独立命名方案 readable-v1，原 v1/v2 不变。逻辑Topic/订阅、消息ID/首次wire/正文/签名、消费幂等、业务授权、route_revision=m3-1、writer epoch和witness格式保持；不执行DDL或凭据轮换。历史映射仅提供精确证据读取，不授权发布、订阅或业务重做；Prepared/Unknown先沿旧链路收敛，Aborted跨路由须宿主显式Replan。未来尚未绑定执行的计划到期走新路由，原授权/attempt/期限/wire保留；deferred按数据库原责任处理。

五库为 SDK、IAM、QS、AI、infra；Broker/NameServer/Dashboard不重启、不改版本拓扑、原worker资源和并发不变。无本机Docker集成；真实验证使用隔离CI依赖。

## 基线

| 仓库 | main SHA |
|---|---|
| sdk | `067bc80b8be9ed73d16ec680484d8ca694088eda` |
| infra | `2c5821a939a3fca09f8151ff08e2d3753f2fb711` |
| iam | `55193a9d8f43baf00e67ff51a407ca8ee43dbcad` |
| qs-server | `8296eb9c9d0278c44510dfc37a7bcaba55825478` |
| qs-ai | `570bfde7a5b494b38fbe3c948ce89cee467ae8b4` |

## 里程碑

| 里程碑 | 任务 | 状态 | 完成门禁 |
|---|---|---|---|
| N-P 基线与命名 | T01–T02 | ✅ 已完成 | 完整盘点、旧新映射及规则冻结 |
| N-SDK 双语言路由 | T03–T05 | ✅ 已完成 | 双语言契约和真实SDK通过、预发布 |
| N-HOST 三库接入 | T06–T09 | 进行中：T06、T08专项通过，源码待协调合并 | 业务、历史读取和调度保持 |
| N-VERIFY 演练与发布 | T10–T12 | 进行中：T10精确权限并集与隔离验证 | ACL/完整故障演练/正式制品通过 |
| N-PROD 切换与退役 | T13–T16 | 待开始 | system及新业务验收、退役闭环 |

## 任务

| 完成 | ID | 内容 | 状态与证据 |
|---|---|---|---|
| ✅ | T01 | 建立总表、独立工作区、完整 SHA 基线及生产责任盘点 | 2026-10-27：五库完整SHA与八实例/12 ACL主体/协议及调度只读盘点通过；[基线证据](evidence/rocketmq-readable-names-baseline-20261027.json)，infra PR352已合并5d6c4294 |
| ✅ | T02 | 冻结十个 Topic、九个 Group、v3 manifest 与共享向量，验证命名冲突 | 2026-10-27：v3命名4项、v2回归3项通过；12路由/10Topic/9Group；共享向量已提供；infra PR352已合并5d6c4294 |
| ✅ | T03 | Go SDK 命名方案、可信路由解析和活动/历史边界 | 2026-10-27：make check完整通过；活动/历史隔离、Aborted显式Replan及原wire保护通过；[本地证据](evidence/rocketmq-readable-names-sdk-local-20261027.json)，SDK PR60已合并d719b6fb，10个PR CI全过 |
| ✅ | T04 | Python SDK 对应能力与生命周期保持 | 2026-10-27：Python48/0/0、ruff/mypy通过；历史不注册、生命周期/取消和原wire通过；SDK PR60已合并d719b6fb，10个PR CI全过 |
| ✅ | T05 | 跨语言真实 Broker 验收与固定 SDK 预发布 | 2026-10-27：SDK5c2e3cd，两个公开SDK矩阵各31/0/0、存活恢复5/0/0；三档存储各29/0/0、两档Python源码与wheel各159/0/0；Go v0.6.0-rc.1 / Python0.5.0rc1已发布，18资产重新下载校验；[发布证明](evidence/rocketmq-readable-names-prerelease-20261027.json) |
| ✅ | T06 | IAM 授权事务、普通消息、幂等查询与双订阅接入 | 2026-10-27：IAM9b9bb9f1 / QS1c2eccc3，正式RC依赖；168本地测试包、11源码CI；三档MySQL真实readable根事务/双IAM及QS fanout各22/0/0，[证据](evidence/rocketmq-readable-names-iam-fanout-20261027.json)。IAM PR160为草稿未合并；infra PR354全部65项CI成功后已合并54387b9 |
| ☐ | T07 | QS API/collection/worker 双存储与合并订阅接入 | [QS PR455](https://github.com/FangcunMount/qs-server/pull/455)草稿2149b4a2：正式RC，382测试包及定向race已通过。答卷真实失败40541357738确认是隔离夹具漏装线上既有Mongo治理schema43，导致host admission_closed；仅补显式安装/原生读取/Ready检查，生产无DDL。最新infra PR356/6079d1c、运行40551016815重验四入口×三档：目前答卷/MySQL8.0.44、评价/MySQL8.4、报告/MySQL8.4三档成功，均0失败/跳过且清理；[部分证明](evidence/rocketmq-readable-names-qs-partial-20261028.json)，其余9档待完成。保留此前失败、取消及完整清理证据，未打勾 |
| ✅ | T08 | AI command/receipt/state/ACK 及正文安全接入 | 2026-10-28：六档readable宿主验证170项实际pytest/390项报告检查，0失败/跳过且清理；[原生证据](evidence/rocketmq-readable-names-ai-native-20261028.json)。最新合并历史接入候选62f3aa3的源码CI运行40543071317全部12项成功（8档SQL、镜像、2档退役备份恢复、完整coverage）。[源码门禁](evidence/rocketmq-readable-names-ai-source-gate-20261028.json)。原生固定aae96db与最新源码的范围分别记录；父PR232旧head剩余coverage待完成、子PR233仍草稿，未合并/部署。独立成对故障及v3夹具PR234属于T11，未借此标为完成 |
| ☐ | T09 | 历史事实、未来调度、deferred consumption 与显式 Replan | [IAM PR161](https://github.com/FangcunMount/iam/pull/161)、[QS PR456](https://github.com/FangcunMount/qs-server/pull/456)、[AI PR233](https://github.com/FangcunMount/qs-ai/pull/233)均为草稿；QS最新d97853af为历史deferred新增只读边界，旧路由不授权新HoldDelivery，原未来写入器使用owner可信codec。该候选本地383测试包/7574测试通过、60项外部依赖选配测试跳过（不是required native通过）；四包race通过。IAM168包、AI4320纯单元及452 mypy分别已有证明。infra PR362/241f05c运行40547695960在固定d97853af上要求两档各12项（原7+历史5），均0失败/跳过且清理；PR362全部17项CI成功，已合并33808532，[证明](evidence/rocketmq-readable-names-history-native-20261028.json)。当前QS历史候选eb0e6dca已合入schema43原生夹具，文档通过、3包仅做integration编译；未来调度矩阵及最新三库源码CI仍待完成；跨路由Replan纯协议与真实存储CAS分别记录，不冒充完整宿主切换 |
| ☐ | T10 | infra 新资源、精确 ACL、CD 配置及具名退役工具 | infra PR359全部13项CI成功、已合并cacfdae0；真实精确旧新并集134/0/0、清理通过。PR361现为141970f：此前5f86bfd专项138/0/0验证classic retry/DLQ sentinel保留；新核对Broker deleteTopic在clearRetryTopicWhenDeleteTopic=true时可能伴随删除POP retry，已增加完整元数据/伴随资源拒绝保护，并扩展POP v1/v2 sentinel，增强native仍待完成。415项本地MQ单元通过，既有CD四角色真实v3材料复制/历史映射/源字节/不激活边界24项通过；剩余源CI待完成。原CD开关只读核对；未应用生产资源或暂停CD，具体生产责任观察及实例配置清单交由T13冻结 |
| ☐ | T11 | 最终宿主端到端、故障与维护/恢复演练 | 准备中：[infra PR364](https://github.com/FangcunMount/infra/pull/364)提供独立readable-rc1镜像依赖/清单/归档校验及手动构建入口，412本地单元和actionlint通过；原M3/M4默认SDK门禁保持。2026-10-28已dispatch隔离镜像构建40566443986（五镜像，尚无成功结果）；八实例启动入口已补齐（严格可读清单、原配置打包器和暂停Checker/关闭检查，416项本地验证），实际启动/切换/故障及发布器适配待完成；没有把构建或只读归档检查标为演练通过 |
| ☐ | T12 | 稳定 SDK、三库正式依赖及固定镜像重新安装验收 | 准备中：SDK草稿PR65/8d99c8b只改版本/项目lock及说明，make check、Python检查通过；候选wheel/sdist独立安装各128/0/0，16份实现及43项外部lock不变。[候选证明](evidence/rocketmq-readable-names-stable-candidate-20261028.json)。未合并/发布稳定版、未修改宿主正式依赖或生产镜像；等待宿主RC门禁与精确最终SHA门禁 |
| ☐ | T13 | 生产核验、暂停 CD、预置资源权限及冻结清单 | 待开始 |
| ☐ | T14 | 维护内排空旧责任、切换八实例与新订阅/Checker 验证 | 待开始 |
| ☐ | T15 | 合法 system/新答卷/新 AI 验收及开放后 30 分钟检查 | 待开始 |
| ☐ | T16 | 按责任清零清理旧资源、恢复 CD、合并发布索引 | 待开始 |

每项勾选须实现及必须验证均通过，附完成时间、源码SHA、报告/CI/PR；合并、发布、部署、业务验收分别记账。里程碑须所属任务完成、相关PR合并及门禁通过才完成；失败不删除，未结责任不改状态隐藏。

## 进行中子门禁（不增加16项总数）

| 任务 | 已验证 | 尚未通过的完整门禁 |
|---|---|---|
| T07 | 固定RC源码/路由接入；真实失败已定位并保留 | 修复后12档中已有3档成功；剩余9档及最终源码CI |
| T08 | ✅ 六档真实readable矩阵；✅ 最新62f3aa3全部12项源码CI，含完整coverage | 实现与验证已完成；PR232/233协调合并及后续T11/T12/T14分别记账 |
| T09 | 三库历史读保护；旧fence与新HoldDelivery拒绝；Go最新全量/定向验证；✅ 两档原MySQL历史消费各12项 | 未来计划、最新三库源码CI及完整切换闭环 |
| T10 | ✅ 精确旧新并集134项；✅ 具名空资源删除138项（classic sentinel）；PR359已合并 | ✅ CD四角色v3只读材料24项；PR361新增POP伴随删除保护的native及剩余CI/合并 |
| T11 | 固定SDK镜像profile/协调归档验证及手动构建入口 | 镜像实际构建、八实例启动/真实故障/切换恢复演练；见PR372/373与40566443986（均待真实结果） |

## 生产切换及删除门禁

维护目标15分钟、上限30分钟。提前预置10 Topic/9 Group与最小ACL，保持每Topic一读一写队列；权限仅允许具名旧新并集。暂停CD并记录原状态；封新写/自主任务、旧消费者/Checker排空责任，停旧实例，确认新Topic为空后先启消费者，再受限system验收，最后开入口和调度。不得跨Topic复制offset、双写或批量重放。新execution/半消息/消费事实产生后只前向修复，不覆盖数据库备份或重做模型；超30分钟不得静默延长。持现有部署锁、遵守镜像保留。

原写者/消费者、积压/in-flight/不可见重试、未决事务、需要旧Broker的未来执行/回执逐对象清零，导出配置/ACL/进度/证据后清理并回读Broker/NameServer/Dashboard。保护系统Topic、事务half/op和未结retry/DLQ、历史数据库证据；不得按前缀批量删除。保留对象登记责任人与阻塞，该项未完成。开放后30分钟检查，不新增48小时门禁；恢复CD原状态。

## 验证与证据

纯命名和冲突、v1/v2回归、原字节和旧事实读取、同逻辑订阅共享预算；真实半消息/确认丢失、退出回查、部分部署与前向恢复；宿主授权双订阅、答卷→评分→报告、AI command→receipt/state→ACK且不增加模型调用。required CI非空、零失败零跳过；正式Go tag/Python制品无replace/editable重新安装。

证据位于 `docs/server/evidence/rocketmq-readable-names-*`；私密运行盘点只以摘要与脱敏计数进入仓库，禁止正文/wire/凭据。

## 执行记录

- 2026-10-27：接受规划，完成五库独立worktree与main SHA冻结；基线测试及生产只读盘点进行中。生产未修改。

- 2026-10-27：T01、T02完成，2/16。协议快照SQL/Mongo均Committed，当前未来计划/deferred为0；10旧版Topic/12旧版Group已登记，未宣称可删除。T03/T04进行中。此前中断未产生生产变更。

- 2026-10-27：T03/T04实现及本地必需验证完成，4/16；SDK PR60、infra PR352已提交。Go make check/48 Python/395 infra纯测试通过；真实Broker与发布未完成，生产未变更。

- 2026-10-27：SDK PR60已合并d719b6fb，10个PR CI通过。初次双档真实v3验收各5通过/1失败：真实Python存活Producer在Broker SIGKILL后回查与消费通过，报告旧v2用例名断言失败；[失败证据](evidence/rocketmq-readable-names-initial-native-20261027.json)保留。已修正命名断言并将完整public与live恢复分三档独立验收，固定预发布候选SDK996e34cd（PR61）；T05仍未完成。IAM仅本地接入开发，正式固定依赖重验未完成，T06不打勾。生产未变更。

- 2026-10-27：SDK PR61已合并bfe6dba5，候选996e34cd两档源码与独立wheel各159/0/0、制品逐字节一致；实际readable存活Producer恢复专项5/5。完整公开SDK首档29通过后NORMAL探针缺命名方案而失败，失败和清理证据见[报告](evidence/rocketmq-readable-names-public-native-retry-20261027.json)。SDK PR62仅修正探针为复用manifest Inputs，新候选5c2e3cd；T05未完成、版本未发布。IAM五包race通过；QS可信owner解析、MySQL/Mongo私有计划与答卷路由本地通过，仍属接入开发，不标成宿主完整验收。生产未变更。

- 2026-10-27：T05完成，总进度5/16。SDK PR62已合并eebdf1c5，两个固定预发布tag同指5c2e3cd；完整公开SDK两档各31、恢复专项5、存储三档各29、Python两档源码/安装wheel各159，均0失败/跳过且清理通过。每Release9资产均重新下载并核对GitHub digest；Go模块193份Go源码/模块文件等同源码，模块缓存三个race包通过；wheel/sdist各128纯测试通过，本地31项真实依赖明确排除，真实证明由CI承担。IAM本地168、QS382测试包通过；当前正在用正式Go tag、GOWORK=off且mod=readonly重新验收。三库源码尚未合并或部署；生产未变更。

- 2026-10-27：infra PR352在62项CI全成功后合并为5d6c4294；SDK发布证明PR63合并e1d8b589，N-P/N-SDK闭环。IAM PR160（9b9bb9f1）、QS PR455（1c2eccc3）为草稿，未合并或触发生产切换。QS初次CI四项失败保留：文档source_baseline过旧、三档MySQL原事务夹具未注入受信路由；已拆开计划路由与runtime生命周期并更新文档源码基线，当前等待真实CI重验。T06/T07继续未完成。自动生产CD配置、数据库、MQ资源和业务容器未改变。

- 2026-10-27：T06专项验收完成，总进度6/16；三档真实隔离验收各22/0/0，两个IAM实例撤权、QS通知与两主体缓存驱逐及primary证明通过，全部清理。IAM源码CI11成功；QS修复后的全部适用CI通过（未选择的API生成同步job为N/A），原事务三档失败已修复并保留旧记录。宿主PR160/455继续为草稿，未合并；infra PR354其余回归待完成。AI仅固定SDK/config基础45项通过，业务路由尚未完工。生产/CD/数据库与容器保持未变更。

- 2026-10-27：infra PR354全部65项CI成功并合并54387b9。QS readable四入口×三档由PR356执行；AI command/ACK/状态与原生夹具路由接入已提交草稿PR232，4313本地非依赖单元通过，当前定向23/0/0、mypy452及文档75份/1272链接通过。AI原生105项仅收集，独立readable admission/state/five-path finalization由PR357验证。总进度保留6/16，T07/T08等待实际门禁；保留本地旧夹具/缺依赖的失败记录，未把缺运行环境用例记为通过。宿主PR均未合并，生产/CD/DDL/容器保持未变更。

- 2026-10-28：总进度仍6/16，T07/T08等待真实门禁；T09三库历史保护已实现并分别通过本地验证，T10精确旧新ACL过渡/134项真实专项已启动。旧QS答卷失败为进入原事务前等待，新增提前返回诊断，不降低验收标准；旧评价/报告夹具原先显式使用legacy reader已修正。已取消本分支被新head取代的作业以释放队列，取消不计成功。三库源码保持草稿，CD、生产资源、数据库和容器未改变。

- 2026-10-28：ACL过渡真实专项40540910673为134/0/0，原五账号旧新精确并集、幂等、130项原生ACL/TLS及四冲突控制通过，清理完整。AI finalization首档40535268126为32/0/0，实际独立进程恢复及清理通过，其余五档待完成；T08不勾选。PR361加入空资源具名删除/回读验证（生产拒绝），414本地测试通过、native138项未执行完成。历史deferred的实际MySQL两档由PR362执行，源码39项SQL夹具只做收集不冒充运行。SDK PR64只修正预发布状态的过期说明。总进度仍6/16；生产/CD/DDL/凭据/业务容器未变更。

- 2026-10-28：保持6/16。PR359以13项CI全通过合并cacfdae0，134项ACL准备及138项具名删除均在隔离环境通过且清理完整。AI真实矩阵5/6档通过；各报告分别记录pytest数量与验收计数，不将二者混作独立测试数。QS答卷失败由缺失既有治理schema43引发的准入关闭确认，仅修复隔离夹具并固定2149b4a2重验，无生产DDL。历史deferred收紧为既有记录恢复只读权限，d97853af全量383包/7574通过，60本机外部依赖选配测试跳过已披露；required native仍须独立0跳过。镜像profile/来源校验PR364已准备，未构建/发布/部署。自动CD开关、业务数据库及生产容器未变更。

- 2026-10-28：AI六档真实readable宿主矩阵全部通过：170项实际pytest、390项组合报告检查分别记账，0失败/跳过且全部清理，T08保留最新源SQL CI门禁。PR364/8ff56cd已提供独立readable八实例启动入口，416项本地验证通过，尚无镜像或真实启动结果。已取消7项被新源码取代的旧PR作业，取消不计通过；当前候选必需门禁保留。稳定版本提交开始准备，未发布，生产/CD/数据库及容器未变更。

- 2026-10-28：T12提前完成稳定候选准备，SDK PR65/8d99c8b；make check/ruff/mypy通过，候选wheel/sdist各独立安装128项纯测试通过。30项integration显式排除、NSQ集成文件未在MacBook执行；实现和外部依赖不变。没有发布tag或Release，T12未完成、总进度仍6/16。

- 2026-10-28：保持6/16。历史消费两档各12项成功且清理，PR362全部17项CI通过并合并33808532。QS答卷8.0.44/评价8.4/报告8.4三档成功，未将部分成功打勾。SDK文档PR64全部CI通过并合并c40509e；稳定候选8d99c8b的三档存储40562961443及精确可读SDK矩阵40563448176已启动（infra PR369），未发布稳定版。PR361新增POP伴随删除保护，旧138项仅覆盖classic sentinel，增强验证待完成。生产只读确认9Group/15客户端ACTIVELY，普通零指标不能单独证明POP排空；8个revive尾部各一条ACK已精确只读核对，进度稳定、Broker未变更，仍不作为封写后的完整排空（工具草稿PR370、窗口草稿PR368）。生产资源、CD、数据库与业务容器未改变。

- 2026-10-28：接续执行，保持6/16。进度证据PR371已合并a2c5835；新增[POP控制PR372](https://github.com/FangcunMount/infra/pull/372)，409项MQ纯测试、4项POP边界通过，精确稳定候选8d99c8b的真实控制运行40566337005待完成；原public31项加4项持有/确认后责任检查，live恢复独立5项。实际生产只读核验显示8条revive尾记录均为ACK，但此结论不替代封写后的完整排空，未宣称生产责任为零。
- 2026-10-28：固定IAM91aee79/QSeb0e6dc/AI62f3aa3源码，运行40566443986开始五类隔离RC镜像构建；未推生产registry、未运行八实例、未修改生产。新增[成对故障PR373](https://github.com/FangcunMount/infra/pull/373)，保留原五条基线+两条真实故障/40项报告检查，并同时验证两个可读RC版本；405项本地MQ测试、actionlint及实际QS race探针编译通过。AI夹具[PR234](https://github.com/FangcunMount/qs-ai/pull/234)只保留v3文件版本，7条pytest仅完成收集，真实门禁待执行。
- 2026-10-28：保留旧版成对回归40551016733中的编译失败；同一冻结旧源码b75d4a52本地race编译通过，尚不足以判断CI故障原因。其余5档仍运行/排队，GitHub不允许对未结束的运行重试；未取消、豁免或记作通过。当前生产CD、业务容器、资源、数据库和凭据均未改变。

- 2026-10-28：T08完成，总进度7/16。最新AI历史接入候选62f3aa3全部12项源码CI成功，结合原六档实际宿主门禁分别登记；父PR232在较早7045671上的重复coverage仍排队，不将它表述为成功。宿主PR仍草稿、生产CD保持，N-HOST里程碑尚未完成。
- 2026-10-28：增强退役运行40560478215失败，已在删除前停止且完整清理；普通管理入口不能创建含`+`的POP v2内部名称。PR361/741da4d改为真实SimpleConsumer持有一条owned NORMAL运输消息，不ACK、关闭本地客户端，由Broker revive生成未选中的v2哨兵，保持四哨兵与原138项门禁；418纯测试通过，真实重验待完成，T10不勾选。成对真实故障运行40567171604已启动，未通过；五类镜像40566443986仍待结果。
