# 可读候选镜像的固定发布

T12 已完成：Go `v0.6.0`、Python `0.5.0`、三库正式接入及五份固定镜像均已发布并验证。[唯一进度总表](rocketmq-readable-names-execution.md)；[发布索引](evidence/rocketmq-readable-names-t12-release-20261028.json)；[五镜像摘要](evidence/rocketmq-readable-names-t12-image-publication-20261028.json)。T13–T16也已完成：五固定镜像/八实例已上线，合法system、新答卷及新AI与30分钟开放后检查通过，旧资源具名退役且自动CD恢复。[最终生产索引](evidence/rocketmq-readable-names-t16-closure-20261028.json)。

`readable_publish_candidates.py` 复用原 M3/M4 的 TLS Registry 运输与 manifest/config digest 回读，不改写旧发布器或历史证据。它不构建镜像、不启动应用、不执行 DDL 或业务切换。

发布前逐项核验：原始计划摘要、现有固定 ACR 与五个仓库、全部精确源码与归档、固定 v3 路由摘要、成功的原构建 workflow 和实际八实例 18 项启动 workflow。原生报告必须摘要一致，八实例预算、身份、只读挂载、退出、无运行时 DDL 和完整清理全部通过；五份 inventory 与归档在任何 Registry 写入前复核。T12 还独立完成同五份归档的 25 项切换与前向修复验证；该空输入配置演练不代表生产排空、数据库恢复或业务验收。

RC 计划可离线审阅，执行路径在任何 Registry 写入前拒绝 RC。`readable-stable` 固定 Go/Python 版本、共同源码 `559c735b2ceb11827ffbbd1279808b4164bba3d1` 与 wheel 摘要；回读两个轻量 tag 及官方非预发布 Release，核对实际资产 URL 和 GitHub digest。稳定 tag 与已发布资产不移动、不覆盖。

五个目标 tag 均先核对未占用。新 tag 使用 `readable-candidate-<run>-<attempt>-<source>`，不覆盖原有对象。网络、认证、标签查询失败直接保留失败；运输失败保留 current_target 及已发布精确对象，不能当作目标不存在、自动回滚或盲目整批重试。发布后验证 config 等同已测归档，再按不可变 `repository@sha256:…` 回读 manifest 原字节。

receipt 只含源码、制品摘要和阶段，不含凭据、正文；运行报告0600，临时下载由所属目录清理。执行只允许 GitHub-hosted Linux 隔离 runner，凭据借用现有 IAM 手动 workflow 的 ACR Secrets，通过 stdin 写入临时0600 authfile，并在结束后移除；MacBook 不启动 Docker。

已冻结的输入计划为 [stable1](evidence/rocketmq-readable-image-publication-plan-stable1-20261028.json)，其字节保持不变。镜像入库不会恢复公众准入、更新生产容器、授权删除旧资源或恢复自动 CD；这些分别在 T13–T16 执行并记账。
