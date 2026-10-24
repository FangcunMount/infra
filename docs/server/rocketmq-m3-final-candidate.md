# M3 最终候选准备与验收边界

唯一任务进度见[M3总表](rocketmq-m3-execution.md)。本页细化原T29，不增加任务数。T28正式制品宿主门禁已完成；以下为最终候选准备，不表示T29完成或生产授权。

| 子项 | 当前状态 | 完成证据 |
| --- | --- | --- |
| 镜像及维护二进制 | 修复后五候选构建/归档核验通过 | 五个原Dockerfile实际构建、源码SHA/模块/wheel身份、image config ID/归档摘要、UID及恢复工具排除清单 |
| 配置、资源与执行包 | 待开始 | 实际所需M3 events/routes/owner绑定、禁自动DDL、封新写配置、ACL/TLS/资源摘要和原维护命令逐项绑定 |
| 原范围恢复、启动与窗口 | IAM、AI组件已合并；QS双库9/9及完整CI已合并，七进程复验中 | 最终候选实际恢复/启动和切换演练，具名步骤及耗时证明30分钟目标；不能用进程sentinel代替实际runtime |

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

QS441合并20cd2184，当前镜像源码b75d4a52与main完整tree一致；新三个QS归档来自固定构建器835c/40092281533，原IAM/AI归档复用。Mongo44保留原提交幂等唯一约束并显式离线安装，SQL105前置不变。新双库40093627714为9/9；七进程仍受worker关闭Exit2阻断，未验证完零DDL/完整关闭，原因和恢复演练尚待新试验。

[新44份输入索引](evidence/rocketmq-m3-candidate-input-index-mongo44-20261024.json)与[46成员源审阅包回执](evidence/rocketmq-m3-source-review-packet-mongo44-20261024.json)替代前述旧42份包。当前archive为私有source review，实际目标配置、受审镜像交付、完整C1/30分钟、生产清单及system仍未完成；不能执行或作为具名生产批准。
