# M4 历史执行记录（归档）

本页保存2026-10-22至2026-10-27的原始阶段记录，不作为当前任务状态。文中的“进行中”“尚未部署”和各阶段计数仅表示当时的事实；当前M4已完成38/38子任务、8/8父任务，收尾[PR344](https://github.com/FangcunMount/infra/pull/344)已合并。当前状态只维护在[M4执行总表](rocketmq-m4-execution.md)。

以下原始执行记录逐字保留，失败历史、提交、CI链接及证据范围均未改写。

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

随后[API正式离线冻结工具](evidence/rocketmq-m4-c08-api-tool-install-20261027.json)已按原审核源码安装root/0555，保留旧版本；仅将其可被部署用户替换的`/opt/qs-server`祖先UID收紧为root，原gid/0755及所有子目录/应用权限不递归变更。五个serverA实例及原部署锁保持；未调用工具、未授予新的API执行规则、未切current或部署。源CI最后发现仅Compose环境字节夹具借用了已删除NSQ镜像缓存，已改用现有MySQL服务image ID，仍仅create/inspect/remove测试容器且不启动；AI应用/生产构建输入与b00cf3a完全相同，旧失败两档各一例保留并重跑。

### C08-01完成（2026-10-27）

本次完成最终依赖/文档审计，当前**34/38叶子、7/8父任务**。AI PR231固定48789cdf5d52269221a67ff016d8fec9e5a59ff5通过14项CI后合并570bfde7a5b494b38fbe3c948ce89cee467ae8b4，两档各5668用例/8份JUnit、零失败错误跳过；当前镜像b00cf3a的全部Docker输入与其一致，后续只修测试/CI/closure。QS文档PR454通过29项检查后合并8296eb9c9d0278c44510dfc37a7bcaba55825478（条件Docs Sync未触发）。18份非空原生报告、最终八实例18项与3项实际Go codec均通过；实际镜像不含pynsq/tornado且当前JOSE/事务/宿主导入有效。

[最终v2归档计划](evidence/rocketmq-m4-image-publication-plan-20261027-v2.json)排除旧AI阶段归档，[新八实例原始报告](evidence/rocketmq-m4-c08-final-eight-instance-native-20261027.json)绑定2093c26c056fa0a91d30cd276216d2c509d936db与实际镜像。尚未上传ACR或部署，C08-02/03/04/05不提前打勾。Mac mini新只读回读Prometheus/Grafana200、10target全up，报告摘要2071f89f1fe0c762ae55d2521ff75c184358eb8f9b7e9764bc931be307c1c46c。生产入口仍开放，等待合法system会话准备好再进入受控部署。


### C08-02完成（2026-10-27）

当前**35/38叶子、7/8父任务，C08为2/5**。IAM PR157的固定workflow在d22910071e8e5d21fb411b7c0856c18d8d2aefc6上发布原归档，[40371739428](https://github.com/FangcunMount/iam/actions/runs/40371739428)五项通过、零失败/跳过，未重建或启动应用；[原始发布回执](evidence/rocketmq-m4-c08-acr-publication-20261027.json)保留独立manifest/config摘要。两云主机ACR读鉴权均拒绝，未复制CI推送凭据；改用固定SSH入口上传已验收归档，完整归档SHA、实际Docker保存config、全部rootfs diff IDs及关键配置一致，执行固定实际engine image ID，不将它误写成ACR manifest或config ID。worker大流传输超时后用已验证部分前缀和有界分块完成，未调整网络或worker预算。

五项目的候选Compose/环境、原事件目录、21份材料的27处只读挂载已在主机内冻结，原非MQ服务配置/资源保持。API使用正式ce8b2112工具、精确sudo规则，经普通deploy调用真实镜像的network=none预检，重复冻结一致、三错误参数拒绝；新建的是未来材料binding指针，原活动指针和运行配置不变。四owner保留当前publish=true、worker=false/no-owner，维护仍由外部入口控制；不先冻结closed再用同SHA改写。原始材料、JWK及凭据不重新生成/导出。

[完整候选冻结回执](evidence/rocketmq-m4-c08-final-freeze-20261027.json)记录全部路径/摘要及失败历史。最新只读回读八实例的镜像、配置、开始/重启、UID/GID及预算与操作前相同，原部署锁元数据保持；A五实例healthy、D三worker HTTP ready，可用1215MiB；Prometheus/Grafana200、10target全up；四库head/owner原字节保持且clean。生产CD仍暂停，没有维护、业务部署、DDL、Topic/ACL/凭据轮换、模型调用或资产删除。

C08-03仍需收敛最后的维护/入口、实际在途及前向恢复执行包；C08-04必须使用合法system会话做真实业务验收，当前尚未收到会话已就绪回复。既有Mac锁定/无Qlume会话的快照不冒充当前业务验收；在入口准备好之前不关闭公众服务。C08-05待实际部署与回归后完成索引，不提前结项。


C08-03继续准备：原生产Nginx镜像对三站点的original/closed非活动副本分别真实syntax检查通过（2/0），活动文件原摘要/inode/权限和Nginx身份保持、未reload或关闭公众入口。[入口receipt](evidence/rocketmq-m4-c08-inactive-ingress-20261027.json)保留只读TLS/临时缓存检查的失败与修正，仅在无发布端口的临时syntax进程中使用原证书读取权限和tmpfs，未改生产安全配置。未伪造验收来源或T0。刚重新检查的UI仍返回Mac锁定、Chrome无Qlume会话；待用户正常解锁/login后收敛实际执行包并进入C08-04。C08-03不提前勾选，总数仍35/38。


### C08-03完成（2026-10-27，尚未开始维护）

合法system页面已核对actor10001，用户已准备一份新SNAP-IV18答卷、尚未提交。原生产只读快照为37个job全部done、35个model call全部response_received、39个evaluation checkpoint均无活动phase，7 blocked会话保持；四owner无Prepared。唯一只读浏览器请求与真实TCP交叉核对验收来源，地址不发布。

PR340/341/342已合并，最终a77aa01b6d7ca71bf60fbe5f355c8cfc2c995e0a的[CI40429156660](https://github.com/FangcunMount/infra/actions/runs/40429156660)两系统各27项通过。原AI锁1002:2001/0600/inode400122与www/app别名已按实机保留；维护前错误的root/数字用户假设拒绝记录保留于v1/v2，不覆盖证据。

v3包五项目实际CLI预览和10次network=none的id探针均通过，原八实例与锁未变。[固定包receipt](evidence/rocketmq-m4-c08-window-ready-20261027.json)和[逐字节目标源码](evidence/rocketmq-m4-c08-window-operator-20261027.py.txt)绑定窗口/停止/启动/验收/开门、1800秒期限与540秒验收预留；实际恢复演练沿最终八实例及进程/Broker故障证明，不在生产注入故障。当前36/38、7/8、C08为3/5；C08-04/05尚未完成，CD继续暂停。

## 2026-10-27 C08-04：实际受控部署与业务验收（37/38）

唯一v3窗口09:05:31开始，09:22:52恢复原三站点；约17分21秒，无延期。八实例使用已冻结云端engine ID、原预算/普通UID与只读材料，健康/0重启/无OOM；四owner绑定和数据库head保持。合法system创建一个无grant/member的空角色，IAM/QS两订阅收敛；用户亲自提交一份新SNAP-IV18并发起一次新解读。精确原事务证据、评分/规则报告、1次模型调用/1次job attempt/1个artifact、4个AI事件及首次ACK全部对齐，旧35模型/37 jobs/7 blocked及checkpoint身份未改。

[实际receipt](evidence/rocketmq-m4-c08-production-deployment-20261027.json)分别记录部署、业务、原HTTP字节恢复、公网4项TLS200、10目标up、D可用1218MiB、NSQ停用/1519文件与原备份保留和CD暂停。保留SSH起命令前中断、UI点击无效及只读证据脚本修正历史；没有重复业务。既存IAM角色授权详情读错误单独登记，不冒充该接口通过，也未修改权限。C08-04勾选随本PR合并生效；C08-05收尾发布索引，当前37/38、7/8、C08为4/5。

## 2026-10-27 C08-05：最终发布索引（38/38、8/8）

[最终发布索引](rocketmq-m4-production-release.md)与[机器可读receipt](evidence/rocketmq-m4-final-release-20261027.json)绑定三库真实运行源码、稳定SDK/制品、五类ACR manifest/config/归档/云端engine ID、八实例实际启动、system与用户业务证据、原HTTP恢复、保留资产及CD暂停。C08-04实现/证据提交e3ce7d4f38c2c5798d0203a481351cbb7a27d917，最终文档及索引同一PR交付，合并后C08、M4-2及全部M4闭环生效。历史阶段“未部署”只表示当时快照，不改写旧receipt。

当前保留职责、R01—R03/PL-R007—008独立移交、最早11月25日资产复核、自动CD暂停与既存IAM角色授权详情读错误分别登记，不冒充已完成或擅自新增M4门禁。M3的48小时观察豁免保持；没有重设观察，也没有物理删除或重做旧模型。完成总数38/38、父任务8/8、C06门禁4/4。
