# M3 最终候选准备与验收边界

唯一任务进度见[M3总表](rocketmq-m3-execution.md)。本页细化原T29，不增加任务数。T28正式制品宿主门禁已完成；以下为最终候选准备，不表示T29完成或生产授权。

| 子项 | 当前状态 | 完成证据 |
| --- | --- | --- |
| 镜像及维护二进制 | 修复后五候选构建/归档核验通过 | 五个原Dockerfile实际构建、源码SHA/模块/wheel身份、image config ID/归档摘要、UID及恢复工具排除清单 |
| 配置、资源与执行包 | 源输入/资源已核验；实际生产绑定尚未冻结 | 实际所需M3 events/routes/owner绑定、禁自动DDL、封新写配置、ACL/TLS/资源摘要和原维护命令逐项绑定 |
| 原范围恢复、启动与窗口 | 当前QS110/44双库9/9、七进程15/15＋九次启停与完整C1 18/18均通过；PR253已合并 | 隔离真实runtime/完整恢复与首标记18/18通过；约47秒仅受控规格，实际生产体量/副本/旧责任与30分钟目标仍须冻结清单 |

## 仅构建路径

`rocketmq-final-images.yml`的默认build阶段只在GitHub托管隔离runner构建原IAM、QS API/collection/worker及AI Dockerfile，保存独立归档与小型inventory报告；不登录registry、不推latest、不SSH、不连接生产、不修改CD暂停、不启动业务入口。PR仅运行离线证明解析测试，实际构建须显式dispatch。

输入是三个已审源码完整SHA和显式Go镜像UID/GID（源码默认2000）；AI原Dockerfile固定10001。必须在T30对照实际主机身份，不把默认值当生产事实。候选归档只使用固定SHA命名，报告记录image config ID、归档SHA256、真实runtime二进制模块Sum或安装包版本。源码/已安装版本不能代替运行健康、业务接受或系统登录。

QS当前runtime镜像没有`qs-migrate-offline`。候选构建从同一固定源码构建原Linux/amd64工具，并注入真实40字节GitCommit，作为独立附件；不写替代DDL工具、不另开数据库事务。原IAM镜像已经带iam-maintenance，AI镜像含原迁移源码。执行包只放明确受审步骤及所需附件，不能全量复制infra工具目录。

实际rootfs只读枚举，不解包到宿主；拒绝路径逃逸及未验收`host-observer`、native_recovery.py、native-resume helper、JavaNativeHalfManaged。原业务恢复代码与SDK Checker继续保留，不能因文件含recovery字样误删。排除镜像内工具不代替执行包审查，二者必须分别通过。

## 仍须完成

镜像inventory不是恢复/启动演练；本路径明确输出`runtime_ready=false`和`cutover_rehearsal_complete=false`。最终配置必须另行挂载M3事件清单与route revision，保持原三个worker资源/并发；不得依赖镜像默认NSQ配置启动。最终镜像、配置、保护范围与执行清单齐全后才提交具名生产确认。

105独立生产前置、T30实际版本/对象身份、合法system登录以及上线后48小时观察继续保留。首次新runtime命令之前按原批准范围恢复；发出后保留不可逆启动屏障，只做兼容前向修复。未决事务/notice/witness和历史保护资产不清理。

## 通用SDK门禁默认版本同步

首次PR238旧源码dedbd391的旧SDK bfaae2b在共享消费预算测试等待received超时，29通过/1失败/0跳过，原声明清理通过。根因尚未确认，[原失败证据](evidence/rocketmq-m3-image-ci-first-failure-20261024.json)保留。已正式发布的1345266在T28两档同类完整故障各48项通过。通用Docker/public/fault/limits/resource CI默认引用同步1345266；所有用例、90秒等待、队列/并发和错误门禁保持原值，独立原生index生成fixture仍绑定其原版本。旧SDK可显式传SHA复现，不把新版本通过称为旧版本bug修复。新head全部门禁未通过前不合并辅助实现、不勾选T29。

镜像inventory另记录实际构建工具的完整infra SHA，并要求等于workflow事件SHA；同时记录原Dockerfile摘要。构建、配置资源冻结、恢复/启动演练分别保留证据。

## 首次构建与配置入口发现

[40071645211](https://github.com/FangcunMount/infra/actions/runs/40071645211)五镜像的元数据与归档均核验通过；标准配置入口随后发现点号owner被Viper层级重建，IAM148修复已合并、QS440完整CI中。因此首次Go归档不能充当最终候选，需包含修复后重建。原生协议/存储测试直接构造配置，不替代这个文件入口证明。详见[当前候选证据](evidence/rocketmq-m3-candidate-progress-20261024.json)；真实启动、恢复与窗口演练仍未完成。

[修复后候选40074229224](https://github.com/FangcunMount/infra/actions/runs/40074229224)五镜像全部通过，IAM148/QS440已合并且完整tree相同，详见[归档及源码证据](evidence/rocketmq-m3-repaired-image-candidates-20261024.json)。实际IAM组件PR241已通过原生8/8与完整CI后合并，尚未完成父T29。

## IAM实际镜像组件（8/8通过，已合并）

`rocketmq-final-images.yml`保留默认build路径，显式iam-start只从指定Actions运行下载已核验IAM归档，在托管runner隔离内部网络启动依赖。原迁移准备完整schema41，AuthZ Bootstrap回调用于受控种子：事件身份/类型和正文摘要在原根内保存到明确fixture archive，不构造待发布消息、SDK witness或业务验收。候选镜像自带原iam-maintenance执行有限范围保护、42–45安装、恢复至41、原事实摘要复核、再次安装及绑定；最后用修复后的标准JSON配置封新写启动原apiserver，核验Checker/采样/预算指标并真实关闭。

这只是T29的IAM组件，不能替代完整五镜像组合、原协调目录首次启动屏障、QS双库/AI原范围恢复、最终执行包或30分钟窗口。只有组件真实报告通过后才更新状态。该路径不SSH、不接生产、不使用外部凭据，不执行模型或system登录；CI原始日志/配置/保护文件不上传。完整schema41准备程序仅是隔离夹具，不进入生产镜像或执行包。

IAM组件初版试图让当前SDK入口排空fresh Bootstrap的legacy行；第六轮确认原handoff门禁正确拒绝，失败不作通过。当前组件改用明确受控输入，不再重演这个已退役入口；不会删除legacy行、改成published、复制业务事实为新半消息或放宽guard。非空旧NSQ/Outbox排空仍由原T25真实工具门禁及生产T32承担。受控种子不是发布型Outbox、业务命令、消息原子性或system证明，原M3任务数和门禁不变。

## 候选输入索引与首发工具清单

**旧索引与源审阅包已被取代。** 131a721按实际QS注册表修正热度投影路由；下列旧索引及其原归档摘要保留作历史，包含旧manifest，不能作为当前执行输入。修正清单的真实资源40087075186已通过134/0/0；最终配置/执行包仍须重新冻结，详见总表最新T29记录。

[候选输入索引](evidence/rocketmq-m3-candidate-input-index-20261024.json)记录5个镜像config/归档摘要、42份精确源码输入（27迁移文件、2宿主事件目录、4资源模板、9工具）及固定repo SHA。工具本地import闭包已核对，仅依赖标准库和清单内模块；首发明确排除后移恢复程序及全部CI夹具，不复制整个工具目录。该索引仅是待审输入，尚未生成最终可执行配置/包，不代替真实宿主/数据库UUID、TLS、worker配额回读或任何具名批准。registry/受审归档交付与目标启动助手的匹配、完整恢复/启动及30分钟窗口仍须验证。

IAM组件[40077501698](https://github.com/FangcunMount/infra/actions/runs/40077501698)全部8项通过，包含DML-only实际运行、0 DDL尝试、原保护恢复及优雅退出；[完整证据](evidence/rocketmq-m3-iam-final-image-20261024.json)。它只覆盖受控种子数据库上的最终镜像恢复/启动，不证明fresh legacy Bootstrap历史入口可直接进入当前SDK；原拒绝及T25/T32旧排空责任保留。

## AI实际镜像组件（原生9/9及完整CI通过，已合并）

使用原0040→0043 Alembic、完整原范围恢复与initial-binding CLI，再启动原只读镜像，保持768MiB/0.75CPU、64MiB tmpfs、210秒关闭及原worker循环/预算。新准入关闭，运行账号只有DML权限。固定Python5.1.2的home日志放入既有/tmp，须在最终配置加入HOME=/tmp并通过实际镜像复验。上游RPC和模型不在本组件验收范围；无法代替QS/成对业务或system。原严格schema拒绝额外测试表的失败保留，复验使用原受控held行，不放宽schema/绑定验证。

AI [40079069646](https://github.com/FangcunMount/infra/actions/runs/40079069646)原生9项通过；原严格schema下的受控held旧记录、完整恢复、原绑定、只读启动/关闭、0 DDL尝试及旧first wire/attempt状态保留分别验收。[证据](evidence/rocketmq-m3-ai-final-image-20261024.json)记录原生9/9、关联10份报告451/0/0及PR243合并032d7c7a；四个变更文件与受验源码逐字节一致。

## QS双库组件（原生9/9及完整CI通过，已合并）

[40082780271](https://github.com/FangcunMount/infra/actions/runs/40082780271)使用原嵌入模板与migrator得到105/40和110/43，journal不force。MySQL全库、Mongo整库包含非空受控事实，新增保护之后的对象后完整恢复；Mongo索引、UUID、文档保持，原维护CLI分别安装/回读两个owner。MySQL原保护bytes保留；严格列元数据及数据/其余DDL保持，只规范化[官方110825](https://bugs.mysql.com/bug.php?id=110825)记录的冗余CHARACTER SET显示。原失败保留，详见[审计](evidence/rocketmq-m3-qs-image-pair-20261024.json)。这不表示生产105完成或业务进程已启动。

五镜像/七进程试验PR246使用真实IAM mTLS与AI，原资源及三个48并发worker。首轮7/1/0在QS读取相对缓存策略失败；原配置纯本地复现后修正fixture挂载路径，未改缓存策略/宿主源码，复验40083039784进行中。完整C1/30分钟仍独立待完成。

QS组件PR245已合并e73fe4aa，5个变更文件与受验e67f2eb相同，关联10报告451/0/0。七进程第二轮7/1/0由原事务owner/标准Outbox互斥保护拒绝；f61f189修正最终provider配置，原保护保留，302工具测试通过，40083809501定向验证中。PR246被修订候选取代并关闭；实际启动通过后才冻结新PR及完整CI，不能用前候选通过证明新候选通过。

## Mongo44候选跟进（当前待验收，不是生产执行包）

QS441合并20cd2184，当前镜像源码b75d4a52与main完整tree一致；新三个QS归档来自固定构建器835c/40092281533，原IAM/AI归档复用。Mongo44保留原提交幂等唯一约束并显式离线安装，SQL105前置不变。新双库40093627714为9/9。此阶段七进程曾受worker关闭Exit2阻断；后续独立v3及完整C1已通过，见下方当前收口清单；旧Exit2根因仍未确认。

[新44份输入索引](evidence/rocketmq-m3-candidate-input-index-mongo44-20261024.json)与[46成员源审阅包回执](evidence/rocketmq-m3-source-review-packet-mongo44-20261024.json)替代前述旧42份包。当前archive为私有source review，实际目标配置、受审镜像交付、完整C1/30分钟、生产清单及system仍未完成；不能执行或作为具名生产批准。


## 当前候选收口清单（T29，尚未完成）

| 输入/证据 | 已固定内容 | 尚待完成 |
| --- | --- | --- |
| 应用源码 | IAM954ad9de、QSb75d4a52、AIddff86ca；均已合并且候选与main完整tree一致 | PR253已合并1465a129、完整C1 18/18通过；实际生产配置另列 |
| 五种镜像 | IAM/AI来自40074229224，QS三镜像来自40092281533；逐项config ID、归档/SDK摘要与builder SHA已核验 | 生产registry/受审归档的真实交付与目标回读 |
| 资源与输入 | 新路由真实134/0/0；当前44文件索引及46成员源审阅包已复核，旧42文件包仅保留历史 | 真实Topic/账号/TLS、原worker配额与DB身份等生产绑定，不能填CI值 |
| 存储 | IAM45、QS110/44、AI0043；新QS9/9实际双库升级/完整恢复及绑定通过 | 完整三MySQL/整QS Mongo保护恢复、原维护/实际启动已过；生产身份/schema待回读 |
| 七进程 | 独立v3为15/15，三worker九次启停通过；完整C1 40103917422为18/18，正常退出及零运行期DDL通过；旧Exit2根因仍未确认 | 实际生产副本/资源回读及最终输入冻结；隔离七进程不替代生产副本证明 |

40095705485准备阶段检查误依赖WARN模板过滤的INFO日志，实际10/1/0、worker仍running；失败保留。08821c6仅在隔离夹具启用原INFO启动日志，生产模板及原预算不变。原生验证通过前不冻结该回执。

生产执行包必须分别绑定封新发布启动、合法system验收及放开新写阶段的原始配置/命令摘要。`publish_enabled=false`没有在线热开关承诺；不能把原生超限resume工具当作正常开准入。若采用重新启动读取启用配置，两份快照及同一协调屏障下的顺序需在首次启动前审阅冻结，并保留真实业务在途/关闭证明。源审阅包不包含这些实际配置，当前`execution_bundle_complete=false`仍有效。


生产落点以执行时只读核验为准。[2026-10-19 serverA记录](serverA-tencent-migration.md)与[IAM记录](iam-tencent-servera-migration.md)登记collection为2副本、IAM为1GiB/1CPU；当前隔离组合只运行1个collection角色、IAM512MiB，因此七进程报告只证明该受控规格，不能声称完整生产副本/资源一比一复刻。实际执行清单必须保留原collection副本数及各服务真实预算，并继续保留serverD的三个原worker；不把CI较小规格直接导出为生产配置。原DB版本、Redis落点及主机私有文件也不能照抄这些历史记录。


## 完整受控C1已通过（18/18，生产配置仍待冻结）

[40103917422](https://github.com/FangcunMount/infra/actions/runs/40103917422)使用原固定五镜像、独立v3启停回执、原维护CLI与唯一协调目录，18/0/0；原范围恢复/不可变交付、四owner Checker/封新写、七进程正常关闭与零运行期DDL逐项通过，[证据](evidence/rocketmq-m3-c1-actual-images-passed-20261024.json)。原生成列/字符集保护保持精确比较；不通过篡改journal、修改成功hash或忽略事实差异取得通过。

当前窗口46.85秒只代表受控数据上的离线维护/启动，不代替生产副本/体量/传输、旧责任排空交接或system。最终配置/执行包仍为未冻结，实际只读核验入口已获准沿用现有SSH；已恢复并完成本次白名单回读，见最新生产核验节，旧快照只作路径参考。

原Go CD脚本已支持显式普通RocketMQ provider/endpoint等选项，但本轮事务owner映射、原事务绑定与分阶段准入以完整M3 JSON及受审环境/命令为准。不能把旧NSQ/provider/Outbox或自动迁移环境变量原样叠在新JSON上；最终参数回读必须核对实际优先级、保留非MQ预算/TLS/存储设置，并分别冻结封新写与验收阶段输入。自动生产CD继续暂停，当前不直接调用旧自动DDL/fallback发布路径。


最终辅助PR253已正常合并至1465a129；17项CI检查、16报告691/0/0、334纯测试及原Go文件读取器通过，[合并回执](evidence/rocketmq-m3-final-candidate-ci-20261024.json)。截至此记录，T29仍缺实际生产输入与完整执行包，不涉及生产部署/DDL/provider变更。


## 生产只读核验入口与待回读清单（2026-10-24）

用户已授权沿用现有SSH做只读核验。保留Mac mini固定生产入口，不改成GitHub托管runner登录。首次连接`mac-mini-old`在SSH密钥交换前关闭；本机Tailscale查询为`NeedsLogin`、本机Online=false。尚未获得远端主机命令结果，不能据此判断Mac mini或生产主机故障；已请求用户恢复本机Tailscale登录。见[连接核验记录](evidence/rocketmq-m3-readonly-entry-20261024.json)。

本次仅准备私有只读检查脚本并检查语法，未在生产执行。远端命令先核对hostname及Docker本机Unix socket，再输出白名单字段：镜像config ID、revision、Compose项目/服务/实例、资源与重启/OOM/health、挂载路径和原锁inode；环境只输出键名，命令只输出摘要，不打印环境值、DSN、配置正文或容器日志。原始私有材料保持目录0700/文件0600。

| 待回读范围 | 冻结所需事实 | 完成状态 |
| --- | --- | --- |
| serverA / serverD业务runtime | 实际镜像与revision、项目/服务集合、collection实际副本、三个worker原预算、IAM/AI/API资源、锁路径与inode、变更前后容器身份 | 待SSH恢复 |
| 三MySQL / QS Mongo | 由实际配置解析的数据库身份/版本、真实迁移journal与dirty、105前置证据位置及状态、当前owner绑定；不读取业务正文 | 待SSH恢复；版本达到105本身不代替前置验收 |
| serverD RocketMQ / NSQ | 实际Broker/Proxy版本与镜像、事务/保留参数、Topic类型及owner授权、TLS身份/有效期、资源/可用内存、有效订阅积压/in-flight/deferred | 待SSH恢复；只查询，不provision或排空 |
| Mac mini监控 | Prometheus/Grafana镜像与健康、targets、规则/告警加载及其摘要 | 待SSH恢复；不reload |
| 最终输入与交付 | 原配置及覆盖项私有摘要、封新写/验收/开准入各阶段输入、目标镜像不可变引用、传输与回读、唯一协调目录和具名执行/恢复步骤 | 前置事实取得后冻结；不填CI值 |

连接恢复后先完成以上事实回读，再生成可审阅生产执行清单。当前生产运行快照未取得、`runtime_configuration_frozen=false`、`execution_bundle_complete=false`、`production_approved=false`；T29不打勾。生产DDL/Topic/ACL/provider/部署仍需按最终具名清单确认，system验收及48小时另记。


## 2026-10-25：生产只读核验后的实际差异

Tailscale/原SSH入口已恢复。本次经`mac-mini-old` ProxyJump，只读核验serverA/B/C/D及Mac mini；[脱敏回执](evidence/rocketmq-m3-production-readonly-20261025.json)与私有原材料摘要分别保存。serverA/serverD核验前后容器ID、image、启动时间、状态、重启计数及原锁均一致。未执行生产部署、DDL、Topic/ACL/provider变更、排空、采集配置reload或Broker启动。

| 范围 | 实际回读 | 执行包处理 |
| --- | --- | --- |
| 业务实例/预算 | serverA为IAM、API、AI及2个collection；serverD为3个worker。IAM1GiB/1CPU、API1GiB/2CPU、AI768MiB/0.75CPU、collection各320MiB/1CPU、worker各768MiB/1CPU；worker并发48 | 保留实际副本、资源与原连接池/预算；旧七进程/IAM512MiB证明不冒充生产八进程 |
| MySQL | 同一Aliyun RDS 8.0.36；IAM40/clean、QS105/clean、AI0040；均VERIFY_IDENTITY TLS连接成功 | IAM新起点需补原工具支持及镜像演练；QS105实际schema通过，原保护/恢复/业务验收记录仍须定位，不能直接勾选前置 |
| Mongo | serverC 7.0.31、rs0可写主库，QS40/clean | 现有7.0.37隔离证明保留；补实际7.0.31候选验证，不擅自升级生产Mongo |
| RocketMQ | 已安装5.5.1；Broker退出143、无OOM，停止时间2026-10-23 21:15:59（北京时间）；NameServer运行；serverD本次可用内存约2GiB | 不将已安装视为健康；停止原因未确认。持久配置48小时保留，实际有效回查参数/ACL因Broker停止未读取；单独冻结恢复步骤并取得具名批准后再操作 |
| v2资源 | 持久Topic快照未发现`rmq2_` Topic | 由infra在批准的T31显式provision并回读；本次没有创建或转换Topic |
| NSQ | 活动worker业务/失败订阅当前depth/in-flight/deferred为0；另有444个无客户端授权订阅有消息，channel depth合计4364 | 该合计包含fanout副本，不是4364个独立事件；逐项责任表私有保存，未认定孤儿、未删除/清空，T32另做具名处置 |
| 监控 | Prometheus/Grafana健康；RocketMQ target down且BrokerUnavailable告警触发；serverD发现文件为空，3个worker target缺失，固定发现SSH探针超时；当前M3协议规则未加载 | 不能勾选监控完成；修复发现入口/加载M3规则另纳入具名变更，不在serverD新增常驻代理 |
| CD | IAM/QS生产暂停=true、AI自动部署=false | 保持暂停；源码合并不触发生产切换 |

IAM [PR149](https://github.com/FangcunMount/iam/pull/149)仅补离线工具40起点：复用原000041，再执行42–45；40保护独立绑定八个新增对象，41仍保留原审计表在范围外；新增审计有任何记录即拒绝40恢复。模板摘要包含41–45，旧计划需重新导出审核。SDK稳定tag/业务写链不变。本地race/vet/编译/文档/actionlint、三档真实MySQL及8项源码CI已过，PR149正常合并0ce9cb21，证据见总表；该源码补丁不代替新固定镜像和完整候选演练。

本次回读Proxy配置时，输出筛选遗漏导致管理员凭据进入工具结果，已按暴露处理。后续提取仅允许精确字段白名单，公开回执校验不包含该凭据；生产凭据尚未改动，**更换与旧凭据拒绝验证须纳入上线前具名清单**，不能仅改初始化JSON后宣称现存用户已完成更换。

当前仍`runtime_configuration_frozen=false`、`execution_bundle_complete=false`、`production_approved=false`，T29不打勾。下一步先收口IAM40原生/合并，再更新候选镜像、实际Mongo/副本演练和最终配置；Broker/监控恢复、原生参数/授权回读及生产具名变更分别记账。

105原独立上线保护/完成回执已在Mac mini复核，14行原保护与摘要匹配、103/40→105/40和6实例原发布记录保留；原QS台账仍有TaskID正向业务验收未完成，本次不代签。新候选演练使用的Mongo7.0.31固定digest已从原镜像回读为`mongo@sha256:43fddee7e532a920f3dfdee9e8f4834398c155c26bcb92d790cc1cd3c630fc40`，生产镜像未变更。

只读续查确认serverD自身Tailscale同样为`NeedsLogin`、Online=false，控制平面连接被重置、无peer状态；Mac mini固定发现入口100.118.164.39的SSH超时与此一致。已恢复的是MacBook连接，不能据此推定serverD已恢复。该私网恢复需要单独具名操作/合法重新认证，尚未执行，不改公网或监控白名单来绕过。


### 待独立确认：仅恢复serverD原Tailnet登录

本清单已准备，**未批准/未执行**。生产只读授权不包含网络状态变更。目标为serverD（82.157.204.239），经Mac mini固定跳板、现有SSH key，以root调用原已安装Tailscale1.104.2；不安装或重启任何服务。原偏好为CorpDNS=false、RouteAll=false、RunSSH=false、NetfilterMode=2（on）、ShieldsUp=false、NoSNAT=false，无advertise routes/exit node；原私有prefs摘要记录在回执中。数字2对on的映射以[该固定版本源码](https://github.com/tailscale/tailscale/blob/v1.104.2/types/preftype/netfiltermode.go)核对，命令flags已用目标机`login --help`只读核对。

批准后先再次比较原偏好和状态；若不符，停止并重新冻结。使用现有控制面和以下显式设置发起合法网页认证（不使用聊天提供的密码/auth key，不删除旧状态）：

```sh
tailscale login --login-server=https://controlplane.tailscale.com \
  --accept-dns=false --accept-routes=false --ssh=false --netfilter-mode=on \
  --snat-subnet-routes=true --shields-up=false --advertise-routes= \
  --advertise-exit-node=false --exit-node= --timeout=2m
```

登录链接仅用于用户正常完成现有Tailnet认证。超时/认证失败保留原状态和错误类别，不循环重试、切换控制面、重置状态或改公网白名单。成功后只读回读Running/Online、原100.118.164.39地址、原偏好、原3worker容器/锁及Mac mini固定发现SSH/Prometheus targets；地址或身份变化时停止，不自动改配置/ACL/防火墙。控制面/ACL配置本次不变；认证可能按Tailnet既有策略分配节点身份，不能事先保证原地址保持。

此次恢复清单仅涵盖主机重新认证和回读。Broker启动、管理员凭据更换、v2 Topic/ACL、数据库迁移及M3业务切换仍按各自具名清单处理；该步骤成功不等于T29/T30完成。
