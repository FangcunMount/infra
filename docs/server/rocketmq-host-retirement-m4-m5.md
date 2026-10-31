# 宿主工程退役 M4/M5

2026-10-31 开始实施。本文的 M4/M5 是宿主工程退役，与此前 infra RocketMQ 迁移的同名阶段分开计数。M1–M3 的代码/上线记录不等于 M2 所有历史业务证据已验收，也不自动批准删除数据库对象。

## 本轮证据与范围

[依赖清单](../evidence/2026-10-31-host-retirement-m5-dependencies.json)逐项绑定六仓最新 main 源码。它是本轮源码核对，不是现网表存在性、数据计数或责任关闭证明。生产运行、此前 M3-C 14 项通过和 51 条历史操作的审计结果继续归属原报告，本轮未重跑这些生产核验。

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
| qs.mysql / ai_messaging_outbox | M4 部署后才可继续候选核验 | 未确认记录、正文引用与历史证据完整导出；验证旧回退镜像的 schema 依赖 |
| qs.mongo / rm_outbox | 保留；v1 答卷/混合热榜/一致性及历史恢复仍依赖 | 提供同等原文证据读取路径并完成历史与当前混合场景验收 |
| ai.mysql / messaging_outbox | 当前发布器已退出，仍为候选 | 旧责任/正文导出、维护审计与后续 Alembic head 兼容、回退下限 |

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

M4/M5 验证结果按通过、失败、跳过、未执行记录；源码、CI、镜像、实际运行和业务验收分开登记。当前依赖清单没有生产删除回执，也没有新增删除迁移。
