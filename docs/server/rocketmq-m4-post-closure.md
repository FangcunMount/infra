# M4闭环后：历史资产处置与自动CD恢复

2026-10-27用户明确授权：历史资产不再等待11月25日，可立即处理；恢复自动生产CD。这是对原C07等待期及CD暂停决定的追加变更，原M4的38/38闭环和历史receipt保持。

| 事项 | 状态 | 执行边界 |
| --- | --- | --- |
| F01 历史资产处置 | ✅ 已完成；具名删除及不存在回读通过 | 只处理下列退役对象，完成后回读；当前/未决事实不因等待期豁免而可删除 |
| F02 自动生产CD恢复 | ✅ 已完成；17项配置补齐及三库开关回读通过 | 先补齐与当前实例一致的事务绑定/发布准入及材料版本，再恢复三库自动部署开关；不把开关恢复冒充实际新部署 |

具名范围：serverD退役NSQ三容器、仅由这三容器引用的`nsqio/nsq:v1.3.0`镜像、`/data/infra/nsq/data`原1519文件和三份NSQ配置；没有独立NSQ命名卷。三主机M3窗口`20261025081841-2`的8个明确保护归档/原始与派生dump，以及Mac mini同窗口3份保护归档按原摘要删除，保留审计元数据及当前工具/锁/材料。禁止泛化prune/目录递归清理。

五张旧发布表`iam.domain_event_outbox`、`iam.rm_outbox`、`qs.rm_outbox`、`qs.ai_messaging_outbox`、`ai.messaging_outbox`有5806条已published/confirmed记录；Mongo `qs.rm_outbox`有76条published记录。只清理这些已终结发布数据。IAM启动/就绪、QS桥接schema检查及AI/QS观察仍依赖部分结构，因此保留结构，不能直接DROP。当前Inbox/receipt、首次ACK/wire档案、witness、业务调度、模型响应/checkpoint及blocked治理全部保护；本次不新增DDL或模型调用。

预检查八实例健康、四owner无Prepared，38个AI job均done、36个model call均response_received、7 blocked保持。源码审阅使用最新main，未修改用户工作区；IAM详情问题单独交接，业务修复不纳入本操作。

固定资产操作器为[scripts/ops/m4_legacy_disposition.py](../../scripts/ops/m4_legacy_disposition.py)：默认预览、计划摘要绑定、固定旧窗口和对象允许集、原文件hash/inode与容器/挂载/专属镜像引用核对；NSQ变更持有原部署锁，前后核对其他容器身份。新增15项跨平台保护验证覆盖越界、旧政策不能授权删除、活动容器、当前镜像/配置、文件漂移和symlink等拒绝边界。最初macOS临时目录符号链接用例路径被安全拒绝，已将测试目录规范化；没有放宽生产保护。

组织Actions变量/runner列表API目前因CLI缺少admin:org返回403；不扩权、不索要令牌。仓库及production环境变量可读取，后续以仓库明确配置覆盖所需非秘密绑定输入，并沿现有runner与部署脚本验证。现有self-hosted作业确实能启动，仓库runner列表为空不代表组织共享runner离线。

## 实际完成结果

[实际receipt](evidence/rocketmq-m4-post-closure-20261027.json)记录：NSQ三容器、专属镜像、1519数据文件和三配置已删除；11份具名旧备份/原始及派生dump删除共1331413483 bytes；MySQL五张旧发布表5806行、Mongo旧队列76文档已确认清理为0，结构/UUID/索引和当前业务证据保留。没有DDL、泛化prune、当前镜像删除或模型重做。

IAM/QS的PRODUCTION_DEPLOY_PAUSED均为false，AI的AUTO_DEPLOY_ENABLED为true。17项非秘密配置已更新；三库实际renderer与当前原字节owner/epoch、路由、预算、发布准入、材料版本及7个AI只读挂载逐项一致。QS使用既有tarball传输，不要求在云主机复制CI凭据。开关恢复不补跑旧workflow，也未额外触发新生产部署；后续成功main CI按各库原workflow选择发布。

清理后原八实例ID/镜像与0重启/OOM保持；四owner/10目标、4项公网TLS200及clean schema heads通过，D可用1216MiB。原36模型/38 jobs/7 blocked及checkpoint的完整身份快照逐项相同。原C07/M4发布receipt是历史证据，不改写；本页及本次receipt说明最新追加结果。

IAM角色详情的[只读交接](iam-role-detail-handoff-20261027.md)保留原快照；后续已完成[修复及生产验收](iam-role-details-read-fix.md)，源码/CI、实际CD及system页面分别留证。首次实际CD暴露的旧锁sudo调用已由IAM PR159修正，无sudo扩权或锁inode重建。
