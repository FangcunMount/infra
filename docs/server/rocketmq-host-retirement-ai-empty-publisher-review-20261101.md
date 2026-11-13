# P. 代码分析报告

## 分析目标

架构梳理：为F04准备AI空旧发布表的独立版本化退役变更和隔离验收；不执行生产发布或DDL。

## 分析范围

AI main e7111890，实际运行镜像f9f24abd；两者应用/迁移/依赖字节相同但版本身份分别记录；现库0043与单个messaging_outbox。既有业务历史、模型响应、Inbox、ACK、事务凭证、native-limit治理全部保留；QS/IAM四对象不在此批变更内。数据与恢复责任人均为shujie。

## 入口与调用路径

bootstrap.server.preflight / database_check → require_runtime_schema → _require_layout：0043完整表集包含messaging_outbox。messaging_audit → schema_layout按版本定位旧表；旧handoff入口已拒绝执行。migrations/env的目标metadata仍包含旧表，单独DROP会使原启动及alembic check失败。

## 当前职责与依赖

0040名字转换/备份契约独立冻结；0041～0043加入原生事务、ACK和保护表。旧表为空只表示无当前发布行，不意味着完整schema依赖解除。生产AUTO_DEPLOY_ENABLED当前为true，代码候选必须保持未合并，避免main检查完成后触发部署。

## 行为 / 契约 / 不变量边界

新增0044独立布局，0043继续要求原表，0044明确要求其不存在；禁止无版本地允许任意缺表。既有迁移字节不改，历史转换白名单不扩展。新空库可在一次完整安装中完成；既有库须同窗口保护/恢复材料及精确审批，普通alembic upgrade不得自动删除。非空、版本/身份/DDL漂移、外部引用、缺失/过期/重复审批均拒绝。首写后前向修复，禁止旧ledger/备份覆盖新事实。

## 测试与可观测性现状

现有test_transaction_schema保护0043完整布局与原生根；test_initial_transaction_binding保护原安装责任；test_mq_inventory保护缺表不可用及只读。本轮已追加真实MySQL新建、0043升级、缺审批/非空/漂移拒绝、保留历史/ACK及新库初始绑定验收；精确候选完整14检查通过，见后附实际回执。当前MacBook Docker未运行，不重建用户旧测试环境；使用仓库PR CI的MySQL8.0.36/8.4隔离矩阵。

## 分析指标与判定

| 指标 | 判定及证据 |
| --- | --- |
| 入口路径清晰度 | 绿：启动、版本、layout、审计及Alembic metadata五入口已定位 |
| 行为边界清晰度 | 绿：0043表存在/0044表缺席和旧转换契约分别固定 |
| 依赖方向 | 黄：版本常量横跨启动/维护/绑定，需一起验证 |
| 测试保护 | 绿（本轮源码/布局）：两版MySQL各13项新旧边界及完整矩阵通过；生产执行仍独立审查 |
| 可观测性 | 黄：退役应明确retired/expected absence，不能缺表冒充零行 |
| 变更放大 | 黄：运行校验、目标metadata、审计、绑定、迁移均受版本变化影响 |

## 主要风险点

在自动部署开启时合并带新head代码；仅删表不改完整schema；把物理缺席伪装为发布零行；原生凭证/业务历史与旧空发布表混同；DDL提交未知后自动重试。

## 初步发现或假设

原业务发送已使用事务archive，旧表剩余依赖主要是完整布局和历史维护入口；因此可通过一个明确新版本解除，不需要重写历史迁移或改业务事件。此结论以隔离矩阵为准，生产尚未删除。

## 下一步建议

0044候选、默认拒绝既有库的审查入口及PR原生矩阵已完成，保留未合并；接续精确生产/前向镜像、同窗口保护/恢复及受控窗口审查。历史51责任及采集两处缺口继续独立台账，不因本批代码准备而关闭。

## 本轮实际回执

[结构化证据](../evidence/2026-11-01-host-retirement-ai-empty-publisher-review.json)绑定实际镜像、现库身份、完整CI和私有原件SHA。[AI #246](https://github.com/FangcunMount/qs-ai/pull/246)保持Draft/未合并；候选HEAD为30b74ae2d5e9afe2655b68a3dfa07eb863ecc126，生产仍为0043及原镜像，未停业务、未执行现库DDL。

两种MySQL的0044五项边界及0043原始根故障用例通过；完整8分区、覆盖汇总门禁、两种旧版backup/restore、受限镜像及两种M7消息/执行恢复矩阵均success。首次本地全单元4462成功，一例依赖真实Docker引擎在本机无法运行；原生CI承担实际引擎证明，未跳过门禁。前两轮测试适配失败保留：新布局的旧表查询改为物理缺席断言；0043和无版本适配器夹具恢复原断言。没有用空结果、放宽head或重建旧表掩盖失败。

当前只读0043完整schema通过；旧发布表0行，保留模型调用40、结果历史128、Inbox58、业务ACK29、archive29、原生execution22/witness29。模型调用40/历史128/Inbox58逐条与真实业务验收后原件相同，43份旧迁移字节保持。原SQL读事务及池均释放，未启动SDK发送或模型。

历史51集合已逐条细分：23条START accepted且工作流completed；5条START accepted/blocked、1条START rejected/blocked；18条EVALUATION_START accepted有评测状态；3条EVALUATION_CANCEL rejected及1条accepted有评测状态。准入回执全部匹配现Inbox，47accepted/4rejected，集合SHA不变。22条“有评测状态”不等于模型/评测终态已核验；6条blocked继续保留。缺失的51份原生锚点未补造，未retired，聚合完整性保护不变。

补读原Nginx日志发现10:27～10:31共112份Prometheus请求，111个200、1个499，最大后端0.141秒、请求0.140秒；原17,552字节片段私有保全。日志无Host，后端角色按当前同源容器IP关联，不能当完整历史拓扑。采样说明该区间有后端快速响应，不能推导Prometheus收到这些响应或业务连续可用；仍需区分采集端调度/网络公共路径，未改网络/时钟/预算或宣布根因关闭。

其余四对象也继续保留：IAM7cd2b02e的transaction_handoff逐表读取，readiness→StandardStatusReader还UNION查询两表；QS5fa0c1f5的AnswerSheet v1、反向一致性及旧维护路径仍引用两rm_outbox。下一轮分别完成其精确新版本/历史读取和原生证明，不以当前空表直接删除。

生产执行门禁仍未签发：AI自动部署开关当前true，候选保持未合并；需先冻结其自动发布、绑定精确主线生产镜像与44兼容前向映像，再收口同窗口排空、原目标/ledger保护、实际恢复及DDL未知结果收敛，最后提交数据库执行审查。本次可审查源码、原始只读与隔离证明不替代上述窗口材料；QS自动CD继续disabled_manually。

## 原件保全

源码、只读/分类、失败日志及原Nginx片段的v1归档SHA为`ce7f96e213e9f1a689b428dc1fb32e0b0df6ed88bf429a5a223d8ae1637a270e`，不包含后完成的完整CI；最终v2追加归档SHA为`5783bd0f3233995fef5262f35b65fd44f8f9e72612eae473fae137cf23f23323`，1025747字节，包含精确完整CI及最终生产只读复验。两份均在MacBook/ServerA回读、fsync一致，目录0700/文件0600，至少30天且未结责任延期，无自动清理。v2保全源码和审计原件，不能当作已停写备份、恢复合格证明或数据库执行批准。


## 同日后续：具体执行包

前文AI自动发布true及30b候选为原审查时点。2026-11-01后续已将AI AUTO_DEPLOY_ENABLED改false并回读，QS仍disabled_manually；业务未停、生产DDL未执行。AI246及AI248排空衔接修复已仅合并源码，补齐v2语义保护、49表完整指纹、原DDL隔离恢复和独立44ledger前向工具；AI专用管理员只读观察已实跑成功。源码/CI、不可变镜像实际资格及同窗口执行缺口统一见[具体执行审查包](rocketmq-host-retirement-ai-246-execution-package-20261101.md)。原43镜像不列为DDL后的恢复路线。原快照与历史CI不覆写为最新候选资格。
