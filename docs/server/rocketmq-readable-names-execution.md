# RocketMQ 可读资源命名执行总表

**当前进度：5/16。** 本表是本批唯一进度总表；M2/M3/M4 原计数保持。

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
| N-P 基线与命名 | T01–T02 | 实现与验证完成，待合并 | 完整盘点、旧新映射及规则冻结 |
| N-SDK 双语言路由 | T03–T05 | 实现、验证及预发布完成，infra文档待合并 | 双语言契约和真实SDK通过、预发布 |
| N-HOST 三库接入 | T06–T09 | 待开始 | 业务、历史读取和调度保持 |
| N-VERIFY 演练与发布 | T10–T12 | 待开始 | ACL/完整故障演练/正式制品通过 |
| N-PROD 切换与退役 | T13–T16 | 待开始 | system及新业务验收、退役闭环 |

## 任务

| 完成 | ID | 内容 | 状态与证据 |
|---|---|---|---|
| ✅ | T01 | 建立总表、独立工作区、完整 SHA 基线及生产责任盘点 | 2026-10-27：五库完整SHA与八实例/12 ACL主体/协议及调度只读盘点通过；[基线证据](evidence/rocketmq-readable-names-baseline-20261027.json)，源码待提交/合并 |
| ✅ | T02 | 冻结十个 Topic、九个 Group、v3 manifest 与共享向量，验证命名冲突 | 2026-10-27：v3命名4项、v2回归3项通过；12路由/10Topic/9Group；共享向量已提供，待合并 |
| ✅ | T03 | Go SDK 命名方案、可信路由解析和活动/历史边界 | 2026-10-27：make check完整通过；活动/历史隔离、Aborted显式Replan及原wire保护通过；[本地证据](evidence/rocketmq-readable-names-sdk-local-20261027.json)，SDK PR60已合并d719b6fb，10个PR CI全过 |
| ✅ | T04 | Python SDK 对应能力与生命周期保持 | 2026-10-27：Python48/0/0、ruff/mypy通过；历史不注册、生命周期/取消和原wire通过；SDK PR60已合并d719b6fb，10个PR CI全过 |
| ✅ | T05 | 跨语言真实 Broker 验收与固定 SDK 预发布 | 2026-10-27：SDK5c2e3cd，两个公开SDK矩阵各31/0/0、存活恢复5/0/0；三档存储各29/0/0、两档Python源码与wheel各159/0/0；Go v0.6.0-rc.1 / Python0.5.0rc1已发布，18资产重新下载校验；[发布证明](evidence/rocketmq-readable-names-prerelease-20261027.json) |
| ☐ | T06 | IAM 授权事务、普通消息、幂等查询与双订阅接入 | 本地实现中：五包race通过；等待固定预发布依赖与真实双订阅重验 |
| ☐ | T07 | QS API/collection/worker 双存储与合并订阅接入 | 本地实现中：options、共享owner及答卷codec通过；AI桥接/调度/deferred未完成 |
| ☐ | T08 | AI command/receipt/state/ACK 及正文安全接入 | 待开始 |
| ☐ | T09 | 历史事实、未来调度、deferred consumption 与显式 Replan | 待开始 |
| ☐ | T10 | infra 新资源、精确 ACL、CD 配置及具名退役工具 | 待开始 |
| ☐ | T11 | 最终宿主端到端、故障与维护/恢复演练 | 待开始 |
| ☐ | T12 | 稳定 SDK、三库正式依赖及固定镜像重新安装验收 | 待开始 |
| ☐ | T13 | 生产核验、暂停 CD、预置资源权限及冻结清单 | 待开始 |
| ☐ | T14 | 维护内排空旧责任、切换八实例与新订阅/Checker 验证 | 待开始 |
| ☐ | T15 | 合法 system/新答卷/新 AI 验收及开放后 30 分钟检查 | 待开始 |
| ☐ | T16 | 按责任清零清理旧资源、恢复 CD、合并发布索引 | 待开始 |

每项勾选须实现及必须验证均通过，附完成时间、源码SHA、报告/CI/PR；合并、发布、部署、业务验收分别记账。里程碑须所属任务完成、相关PR合并及门禁通过才完成；失败不删除，未结责任不改状态隐藏。

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
