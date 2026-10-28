# RocketMQ 批次完成后的 Actions 与临时库清理

截至 2026-10-29（北京时间）：**18 个过时 workflow 已删除并合并 main；另 5 个无源码的失效注册入口已停用。用户具名批准的 14 个临时库已删除并完成回读，原生产备份保留。**

本次不改变 M2/M3/M4 或可读命名迁移的完成计数。代码合并、Actions 注册状态、自动部署、数据库删除分别记账。

## 源码与 Actions 完成记录

| 仓库 | workflow 数量（前→后） | 合并与验证 |
|---|---:|---|
| reliable-messaging | 4→4 | 现行 SDK CI 全部保留，无需修改 |
| IAM | 13→9 | [PR #164](https://github.com/FangcunMount/iam/pull/164)，`b1cbb092513238c6905c6646199a0f609df93183`；8 项检查通过 |
| qs-server | 17→13 | [PR #458](https://github.com/FangcunMount/qs-server/pull/458)，`3a4c048e3a42cbbd242c7f9bd44c7cfc79aadbfa`；29 项通过，1 项按原条件跳过 |
| qs-ai | 6→4 | [PR #236](https://github.com/FangcunMount/qs-ai/pull/236)，`d432a602eff751d25a38507855ed9b0f5a051fdb`；12 项检查通过 |
| infra | 73→65 | [PR #405](https://github.com/FangcunMount/infra/pull/405)，`dcb49a80790cef0c98ff2408a5ff183400c6e16a`；契约检查通过 |
| 合计 | **113→95** | 18 个具名入口删除，无历史运行/制品清除 |

18 个已删除文件对应的注册记录回读均为 GitHub `deleted` 状态，无在途运行。另停用的 5 个失效注册入口为 IAM 的 `reliable-messaging-fallback.yml`、`integration-redis.yml`、`integration-rocketmq.yml`，infra 的 `alertmanager-config.yml`、`rocketmq-qs-native-recovery.yml`；均回读为 `disabled_manually`。动态 CodeQL/依赖安全集成及原来已停用的 9 个历史入口保持原状态。

Sonar workflow 和 `sonar-project.properties` 已删除；QS 仓库专用 `SONAR_TOKEN` 查询为不存在，未触碰共享 Secrets。当前 CI/CD、真实数据库/MQ/故障回归、必要历史读取与恢复工具继续保留。历史 workflow 引用改为不可变源码链接。

本地验证：四库 `actionlint`；infra 476 项契约测试；IAM 文档事实/卫生检查；QS 88 项文档测试及完整 `docs-check`；AI 25 项 schema transport/当前 CD 边界测试，75 个 Markdown 的文档检查均通过。未在 MacBook 启动 Docker 集成依赖。

## 全实例数据库核验与已完成处置

使用 DataGrip 中既有 dbadmin 连接完成只读核验，与应用连接的实例身份一致。全实例共 25 个 schema；其中 15 个为 10 月 8 日旧 AI 数据表迁移的备份、失败副本或演练目标。应用账号最初只能看到部分 schema，不能据此得出“没有临时库”的结论。

| 精确 schema | 表数 | Alembic head | 最终处置 |
|---|---:|---|---|
| `ai_backup_dbrefactor_20261008` | 54 | 0038 | 原生产备份，用户明确保留 |
| `ai_backup_probe_dbrefactor_20261008` | 0 | — | ✅ 已删除并回读不存在 |
| `ai_failed_789955ac857a` | 44 | 0040 | ✅ 已删除并回读不存在 |
| `ai_failed_dbfollowup_20261008_def29f6044cc7757` | 0 | — | ✅ 已删除并回读不存在 |
| `ai_failed_e293b5a44cce` | 54 | 0038 | ✅ 已删除并回读不存在 |
| `ai_failed_rehearsal_dbrefactor_20261008` | 0 | — | ✅ 已删除并回读不存在 |
| `ai_failed_rehearsal_f4f27e221b35` | 0 | — | ✅ 已删除并回读不存在 |
| `ai_refactor_dbrefactor_20261008` | 0 | — | ✅ 已删除并回读不存在 |
| `ai_refactor_followup_f4f27e221b35` | 44 | 0040 | ✅ 已删除并回读不存在 |
| `ai_refactor_probe_dbrefactor_20261008` | 0 | — | ✅ 已删除并回读不存在 |
| `ai_refactor_prompt_16fbf8f263c94da3be4c9826d9843d2a` | 44 | 0040 | ✅ 已删除并回读不存在 |
| `ai_refactor_rehearsal_dbrefactor_20261008` | 54 | 0038 | ✅ 已删除并回读不存在 |
| `ai_rollback_dbfollowup_20261008_def29f6044cc7757` | 54 | 0038 | ✅ 已删除并回读不存在 |
| `ai_rollback_rehearsal_dbrefactor_20261008` | 0 | — | ✅ 已删除并回读不存在 |
| `ai_rollback_rehearsal_f4f27e221b35` | 54 | 0038 | ✅ 已删除并回读不存在 |

15 个对象均验证无活动连接、跨库外键、events、routines 或 triggers；当前生产 `ai` 的 head 为 `0043_native_transaction_limit`。不以 schema 名称或空表作为唯一删除依据。

用户选择“删除14个临时库，保留该生产备份”，已执行上表中除原生产备份外的 **14 个临时库**删除，涉及 348 张旧快照表及 7 个空 schema。`ai_backup_dbrefactor_20261008` 在原迁移记录中的最早删除时间为 **2026-11-07T11:54:59.530182Z**；本次没有豁免保留期。收到动作时确认后，通过 DataGrip 既有 dbadmin 控制台执行具名 SQL；执行前再次确认实例身份一致、15 个候选均无活动连接、跨库外键、events、routines 或 triggers。

保护对象：`ai`（51 表）、`iam`（30）、`qs`（67）、`miniblog`（13）、`statistic_db`（3），以及所有系统 schema 和 `__recycle_bin__`。`statistic_db` 含实际广告统计数据，不属于本次临时库；应用库内部仍被 schema、历史读取或恢复使用的 Outbox/证据表不在本次删除范围。没有删除存储过程、生产业务记录、事务 witness、备份文件或 Docker 卷。

删除后完整目录由 25 个 schema 降至 11 个，14 个白名单对象剩余为 0；保留备份仍有 54 张表且 head 为 `0038_messaging_observations`。五个业务库表数保持 51/30/67/13/3，生产 AI head 仍为 `0043_native_transaction_limit`。12 项只读验收实际值全部匹配期望值，IAM/QS/collection 公网健康接口全部 HTTP 200。没有重放 DROP。

[脱敏删除回执](../evidence/2026-10-29-post-rocketmq-database-retirement.json)记录精确名单、验收结果、私有原始证据摘要。DataGrip 自建控制台最后仅保留只读验收 SQL，其他用户控制台未修改。备份保留是本次最终处置，不作为待删除任务或自动定时删除授权。

## 自动部署与运行核验：独立于清理完成

未修改自动生产 CD 的开关，也未手工重派任何部署。清理合并触发的原 main CI/CD 按既有链路运行。

- IAM main CI 通过，但 [自动部署 #40715072424](https://github.com/FangcunMount/iam/actions/runs/40715072424) 在远端 `remote-deploy.sh` 返回 1；镜像构建成功。当前日志只定位到 CA 校验之后，尚不能断言具体根因；已独立只读验证本机安装的 IAM material receipt 正常。禁止将此项写为部署成功或用盲目重跑掩盖失败。
- QS [自动部署 #40717756139](https://github.com/FangcunMount/qs-server/actions/runs/40717756139) 已完成并失败；AI [main checks #40717738533](https://github.com/FangcunMount/qs-ai/actions/runs/40717738533) 已通过。这些部署结果与本次数据库清理分别记账，未手工重跑。
- 八个业务容器回读均 `running`、restart count 为 0；serverA 五个容器为 `healthy`，三个 worker 未配置 Docker healthcheck。IAM、QS、collection 公网 `/healthz` 均为 HTTP 200。
- Mac mini Prometheus 实际目录当前只有 5 个目标，三个 worker 采集超时，四 owner 指标未出现。原“10 目标全 up”脚本因此失败，不能当作通过。Broker 与 Prometheus 自身目标为 up；这说明监控覆盖需独立跟进，不证明 worker 业务异常，也没有修改生产采集或网络配置。

## 证据

本次私有执行目录为 `~/.local/state/rocketmq-post-rollout-cleanup-20261028`，权限 0700，敏感核验和 UI 证据文件为 0600；不提交凭据或原业务正文。包括源码选择/完整 SHA、GitHub 运行及合并回执、18 个删除注册状态、5 个停用回执、dbadmin preflight/version AX 记录、具名 SQL 和审核截图。数据库具名删除与 12 项验收的私有回执、完整目录结果和完成截图已保存，脱敏摘要随仓库提交。

下文保留动手前的分析快照；其中“应用账号可见元数据”和后续全实例盘点分别反映当时的证据范围。

---

# P. 代码分析报告

分析目标：清理 RocketMQ 各批次完成后过时的 GitHub Actions；仅盘点迁移/演练/验收临时数据库。

分析范围：reliable-messaging、IAM、qs-server、qs-ai、infra 最新 main 的113个workflow；生产RDS当前应用账号可见元数据。五库使用独立worktree，完整SHA见本次证据。

入口与调用路径：push/PR→现行CI；CI成功→原CD；手工旧入口→固定旧候选/NSQ或0038/0040上下文。候选无workflow_call调用，不在分支必需检查中；五库没有在途作业。

当前职责与依赖：移除18个已完成批次的构建/启动/切换/发布入口、旧NSQ专用检查、旧IAM角色迁移及Sonar；infra两项重复纯契约测试仍由rocketmq-contracts的全量test_*.py发现覆盖。保留脚本中被当前发布凭证核验、数据恢复、历史读取和契约测试引用的工具，保留现行CI/CD及真实MQ/数据库回归。

行为 / 契约 / 不变量边界：不变更业务API、消息/事务、现行配置、凭据或数据库schema；不删除旧运行/资产证据，不启用旧候选。过时工作流不再允许从main派发。移除Sonar专用配置。

测试与可观测性现状：读取实际GitHub工作流状态、最近100次运行和main规则；SDK四项CI均保留。AI旧工作流绑定测试改为当前CD锁/权限与拒绝历史维护入口的契约；旧transport协议测试保留。删除后验证YAML、调用/引用、完整infra纯契约和各库文档门禁。

分析指标与判定：入口清晰（绿，逐项绑定触发器与调用方）；行为边界（绿，生产CI/CD及运行代码不改）；测试保护（绿，原纯契约仍有全量发现入口）；可观测性（黄，Actions注册表与main文件不同，需区分动态安全工作流与旧注册项）；数据库可见性（黄，应用账号无SHOW DATABASES权限，全实例临时库结论待维护账号）。

主要风险点：不得把有M3/M4名称的长期回归全部删除；不得把sys过程、statistic_db广告数据、空但仍被schema/恢复检查引用的表认作临时对象。删除旧文件不等于删除Actions历史，也不修改动态CodeQL。

初步发现或假设：IAM四个、QS四个、AI两个、infra八个入口的原批次均完成；QS Sonar仍在main push触发；旧M5检查仍指向已退役NSQ。当前可见库未发现独立临时库；statistic_db有三个广告统计表；48个routine全部属于sys。应用库目录不证明全实例无临时库。

下一步建议：按下表精确移除18个入口及Sonar配置，修正文档与保留边界测试；核验main/运行后处理仅剩注册项。取得维护账号后重新列出全实例schema，只有具名、确认归属且无活动/恢复责任的临时库才可删除。

| 仓库 | 移除的workflow |
|---|---|
| iam | `rocketmq-m3-candidate-publication.yml`, `rocketmq-m4-candidate-publication.yml`, `rocketmq-readable-candidate-publication.yml`, `role-model-migrate.yml` |
| qs-server | `sonar.yml`, `rocketmq-m3-image-cache.yml`, `m5-authz-ephemeral-postcheck.yml`, `m5-authz-outage-preflight.yml` |
| qs-ai | `schema-followup.yml`, `schema-maintenance.yml` |
| infra | `rocketmq-final-images.yml`, `rocketmq-m4-rebuild.yml`, `m4-final-image-rebuild.yml`, `rocketmq-readable-images.yml`, `rocketmq-readable-startup.yml`, `rocketmq-readable-cutover.yml`, `rocketmq-image-publication.yml`, `rocketmq-readable-publication.yml` |
