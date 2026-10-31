# 宿主工程退役 M4/M5

2026-10-31 开始实施。本文的 M4/M5 是宿主工程退役，与此前 infra RocketMQ 迁移的同名阶段分开计数。M1–M3 的代码/上线记录不等于 M2 所有历史业务证据已验收，也不自动批准删除数据库对象。

## 本轮证据与范围

[依赖清单](../evidence/2026-10-31-host-retirement-m5-dependencies.json)逐项绑定六仓最新 main 源码。它是本轮源码核对，不是现网表存在性、数据计数或责任关闭证明。初始清单不包含生产核验；本轮新增的实际部署与只读结果见[运行与逐对象复核](../evidence/2026-10-31-host-retirement-m4-runtime-m5-review.json)。此前 M3-C 14 项通过和 51 条历史操作的审计结果继续归属原运行，不因本次回读而重标为重跑。

M4 候选为 [QS #471](https://github.com/FangcunMount/qs-server/pull/471)、[IAM #173](https://github.com/FangcunMount/iam/pull/173)，精确提交见依赖清单。候选修改 QS/IAM：迁出无运输/数据库所有权的消息映射、wire、Reference/指纹校验；删除当前宿主的 NSQ 双提供者分支、无调用的标准 Profile/Relay 执行装配。旧 Stager/NSQ 回归仅在明确的历史测试夹具或固定历史源码中运行。三个 QS 进程与 IAM 可执行文件的实际依赖图不得链接 NSQ、发布型 Relay 或测试夹具；不删除 SDK 的公开兼容能力。

QS AI bridge 的当前预检不再依赖 `ai_messaging_outbox`，但继续检查当前业务准入、operations 约束、Inbox、失败/隔离及技术观测。IAM 迁移 33/35 所需的历史 bootstrap 适配仍保留，使用分离的纯消息映射；当前运行和维护写入仍要求事务 owner。

## 当前正式 SDK 的原生复验入口

既有 `rocketmq-iam.yml` 增加显式 `host_retirement=true`，仅允许 `runtime=true` 的独立运行/双宿主 fanout 验收，禁止混用旧 protection/native-limit/fault/readable 阶段。固定 SDK 源码 `48dfcdafbf29b44e99a5ac8b1ae01e5173138560`、正式 Go `v0.6.1` 与精确 module/GoMod sums，拒绝 replace、错误版本或哈希；IAM/QS 各自要求完整、干净的提交。默认历史入口继续固定 v0.5.0，不将旧证明升级为当前验收。原生 MySQL 完整矩阵、实际 Broker、版本传播、订阅就绪及排空均须通过，不能通过放宽旧版本校验造绿。

QS 当前恢复继续使用既有 `m4-qs-runtime.yml` 的 `recovery_qs_ref`，固定精确候选，14 个 M3-C 场景必须实际执行并零跳过；同一工作流的旧 native 控制具有自己的固定源码归属。

## M5 逐对象决策

| owner / 对象 | 本轮源码结论 | 进入删除前仍需完成 |
|---|---|---|
| iam.mysql / domain_event_outbox | 保留；启动/就绪及新建库迁移仍依赖 | 收口原历史责任检查与 bootstrap 升级路径；验证新建库不遗失通知责任 |
| iam.mysql / rm_outbox | 保留；启动/就绪及责任审计仍依赖 | 当前检查与迁移后 schema 的兼容方案；逐条责任关闭/原文保全 |
| qs.mysql / rm_outbox | 保留；结果证据、反向一致性和历史恢复仍依赖 | 保全原 Reference/wire 并替代所有当前读取，不能把表缺失当作空表 |
| qs.mysql / ai_messaging_outbox | M4 已部署；原表零行及原 DDL/空流已核验，SQL111 候选 PR #474 | 最终 CI、固定执行器/镜像与只读预览、具体维护窗口和回退边界审查；其余五对象保留 |
| qs.mongo / rm_outbox | 保留；v1 答卷/混合热榜/一致性及历史恢复仍依赖 | 提供同等原文证据读取路径并完成历史与当前混合场景验收 |
| ai.mysql / messaging_outbox | 保留；当前 0043 启动及发布预检要求其存在 | 追加新版本 schema/layout，保持严格校验；旧责任/正文导出、维护兼容及回退下限 |

候选不是执行清单。保留 `interpretation_result_outbox`、`identity_session_revocation_outbox`、原事务 execution/guard/witness、archive、Inbox、receipt/业务 ACK、业务历史及调度。表名含 outbox 不构成删除理由。

## 实施顺序和验证边界

1. 完成 M4 精确提交上的既有主 CI、消息字节/指纹兼容、架构/配置回归，以及当前原生 RocketMQ 业务证明。历史 NSQ 验证固定历史 SHA 并明确归类，不能为清理代码关闭或放宽当前验收。
2. 保持发布冻结合并；核验 main CI，固定新镜像 SHA/digest、配置和可兼容回退版本，再按 API 就绪优先的既有顺序部署。回读运行版本、四个事务 owner 与消费者健康。未完成部署不进入 M5 执行。
3. 在只读事务/有界预算内核实候选对象身份、结构、原文、责任和引用，检查所有当前及计划回退版本。记录完整导出/备份的内容哈希、范围、可读性和恢复验证。未知、缺失、冲突或截断不算零责任。
4. 仅对已解除全部依赖的精确对象追加迁移。先在隔离的全新库、当前版本升级库及含 pending/unknown/NULL/冲突历史的负向样本验证；禁止修改旧迁移伪造新库结果。MySQL DDL 自动提交、Mongo 与 MySQL 无共同事务，不能用普通 BEGIN 承诺跨对象/跨库原子回退。
5. 删除后验证启动/就绪、当前指标与读取失败语义、v1/v2/混合恢复、原生重投/重启及完整业务无重复效果，并核对所有保留资产的内容/数量未变。缺依赖应失败，不跳过必需验收。
6. 生产执行前列出实际库绑定、精确名单、冻结/无写者证据、责任关闭与导出哈希、预期行数/对象变化、逐步执行/失败停止点和回退下限供审查。此前“不操作现有数据库”的约束继续生效；此页不授权 DROP、清空或批量 retired。

## 尚不能关闭的证据缺口

QS 51 条缺原 command 发布事务锚点的历史操作，不能由 Inbox 字节一致、admission receipt 或后置业务投影补成原 witness。不能填造档案、重做模型、清空 ACK/业务历史或批量标记 retired 来使 M5 门禁变绿。它们是否与某个具体候选对象相关，须按精确引用单独证明，不能简单推导“全部可删”或“所有对象永久不能删”。

M4/M5 验证结果按通过、失败、跳过、未执行记录；源码、CI、镜像、实际运行和业务验收分开登记。原始依赖清单没有生产删除回执。本轮已追加尚未执行的 SQL111 候选，仅处理空 `qs.mysql.ai_messaging_outbox`；普通 down 拒绝，保留原 DDL/空流及独立恢复证明，失败可能留下 dirty111，不能自动 force。

## 2026-10-31 运行与只读复核

M4 的 IAM、QS API、Worker 三副本及 Collection 两副本已按固定镜像部署；独立快照运行 [41175362334](https://github.com/FangcunMount/qs-server/actions/runs/41175362334) 与监控观察 [41175364496](https://github.com/FangcunMount/infra/actions/runs/41175364496) 验证九个业务容器的镜像/源码和显式就绪。四个事务 owner 的观测可用且新鲜，准入保护均为 0；这不代表业务责任已关闭。QS 业务观测不可用、待处理计数缺失，不能解释为零；AI 业务观测可用且 ACK 等待为 0。

Worker 与 Collection 首次部署后的治理步骤分别因 Prometheus 尚未出现指标族失败。新鲜公网回读确认完整副本数后，只重跑失败治理步骤通过，未再次部署应用。[QS #473](https://github.com/FangcunMount/qs-server/pull/473) 将指标族出现条件放进既有就绪重试循环；保持原预算、阈值和失败条件，候选 29 项 CI 通过、1 项条件跳过，已合并到 `249dc683…`；main 同样 29 项检查通过、1 项条件跳过。四仓发布工作流已恢复 active，核实无额外部署，业务镜像保持不变。

只读运行 [41175524009](https://github.com/FangcunMount/qs-server/actions/runs/41175524009) 在独立有界只读事务中确认 IAM 两张、QS MySQL 两张候选表均存在且各为 0 行，事务与连接池释放均成功，完整身份及结构哈希见 JSON。AI 初次分支失败且未留下有效回执；分类复验确认探针在导入阶段因基础解释器缺少应用依赖而停止，尚未查询数据库。已改用镜像启动解释器与应用 UID，最终只读运行 [41176790709](https://github.com/FangcunMount/qs-server/actions/runs/41176790709) 的审计步骤成功，完整回执确认 `0043_native_transaction_limit` 与 `messaging_outbox=0`。同一最终源码下 IAM/QS 四张表复验仍各 0 行，三个 owner 作业全部成功。结果历史 `interpretation_result_outbox=125`、Inbox=57，均保持原状；Mongo 尚未读取。以上不包含写入、清空、迁移或删除，不证明业务/引用关闭、正文备份恢复、无写者或回退兼容。

IAM 原生 Broker 夹具在独立新库完整迁移后，显式清理其生成的旧发布表种子通知；该历史测试结果不能当作“新建库已无旧初始化责任”的退役验收。AI 当前已部署源码的严格运行时 schema 校验仍要求旧 `messaging_outbox`：必须新增有版本的布局与升级路径，不能修改冻结旧布局或放宽集合校验以允许缺表。

最终只读运行 [41178025856](https://github.com/FangcunMount/qs-server/actions/runs/41178025856) 在 `7d6f2daa…` 四个 owner 全部成功：六张候选表/集合均为零行，IAM MySQL45、QS MySQL110、QS Mongo44、AI0043；MySQL head 均 clean。该 source 的29项 CI通过、1项原条件跳过；认证 Mongo 两个 required selector 和新增 MySQL head负向场景均实际通过且零跳过。数量和版本证据不关闭现有读取/初始化/schema依赖。

首批候选 [QS #474](https://github.com/FangcunMount/qs-server/pull/474) 仅追加 SQL111，退出 QS 空 `ai_messaging_outbox`，使用既有配对驱动和窄批准范围 `110/44 → 111/44`。其余五对象保留。首版原生隔离用例完成锁内零行/拒绝非空、原 DDL恢复、触发器和锁竞争控制；原/恢复结构哈希与实际旧表结构哈希相同。它是夹具恢复证明，未证明真实导出或生产回退。最终 source另加依赖视图保护，主 CI、M3-C14、实际原结构/空流材料及具体生产执行包尚待完成；当前没有生产迁移或删表回执。

## 当前首批代码与运行证据

M4 已按固定镜像上线并独立回读，控制器跟进 #473 main CI 通过。只读工具 #472 已合并为 `36846135cf6def4b80ff2d374886660dbda6d6db`，合并前29项检查通过、1项原条件跳过；合并后 main CI 另行记录。QS 自动发布当前以 workflow disabled_manually 冻结，IAM/AI/后台保持原状态，线上继续固定 M4 镜像。

#474 原基线 `51323979c7ee38b5288f5a3422209f7589cef5dc` 已通过29项检查、1项原条件跳过；追加完整原账本材料、三进程启动和恢复演练后，最新草稿 `75f567a8dc6697b0929c72cbafe5368b93a1002f` 的最终 CI 正在运行。现网默认只读离线预览已在 `d3c977740cdb2e063fde0db49dcc05bfca6cbfe2` / run41183082546 成功，二进制摘要 `c80049fd1d0b1ec9fc8d28444b6e004a8c3f48eba0e8e147f738b6d3887e9913` 与归档原字节一致；实际110/44、目标111/44、资源摘要 `b8c09d87a02432f9c4f01fdbf01d7fa2dd7ecbf3ebdaf3576b2e61f02e7ea6de`。最后仅修正身份输出重定向的 ShellCheck SC2129，执行器源码不变。前一源码 `704ee8ddb82b3094a2b469b4f5506cfb274521c4` 的完整 CI、原生 MySQL 删除/恢复保护和14项 M3-C 当前业务恢复均已通过。生产 Go、module、配置及迁移资源逐字相同；最后新增内容仅维护 CLI 连接选择和只读运输。此等价核对不冒充候选上的新14项执行；业务证明使用受控 IAM/provider，不宣称完整 Collection 或生产系统登录。实际原 DDL 哈希与隔离成功恢复哈希相同，仍不表示生产恢复或停写已发生。具体结果、失败记录和原运行归属见运行复核 JSON。

首批生产写执行仍未批准。完整进程集合的隔离启动回执、固定新 main 镜像、真实停写与同窗口重读/材料责任尚未完成，不能用受控业务测试替填这些字段。原执行器的私有批准、一次消费、30天材料保留、30分钟窗口及首个 runtime 启动提交点规则保持。

新增进程夹具首轮47b7 / run41184781027失败：原分配器的 qs_runtime_closure 数字后缀与新增包装要求 test 字样发生确定冲突。严格前缀修正8183源正在复验，不记为14项已通过。诊断代码拆为独立 #418（3份 Python 文件、74项本地协议测试），本 #417保持文档与证据范围；源码行号和固定技术标签可公开，原私有子进程输出不上传。新材料另要求保全实际完整两列版本账本原 DDL/单行原值；恢复只演练独立审定的原账本事务回放，不是 Force/按数字改版本或清 dirty。
