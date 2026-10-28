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
