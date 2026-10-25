# M3 最终生产发布索引与M4移交

M3按2026-10-25用户最新决定完成：**36项闭环＝35项实现/验证完成＋T34用户豁免**。48小时观察未完成、未宣称通过；原heartbeat已取消。业务生产链路使用RocketMQ，旧生产NSQ服务已停止且不自动重启；历史数据和恢复资产保留。唯一任务状态见[M3总表](rocketmq-m3-execution.md)，[最终回执](evidence/rocketmq-m3-production-closure-20261025.json)绑定实际核验。

## 已交付

| 层面 | 实际结果 |
| --- | --- |
| SDK | Go v0.5.0 / Python0.4.0，双tag同`1345266aa0e864c46de5d1e3e3c939dd8002a890`；正式Release各9资产，原下载/安装/摘要门禁已过 |
| 业务源码 | IAM `ca59dec47fe4e544cd06bf52f9e3c64fbbdad211`；QS `b75d4a52ec261275a0ffb588eeb31fd6496966d0`；AI `ddff86cad27d03c95dad28490d6cccbc1ce5b15f`，均已合并main；运行代码与当前main一致，差异仅workflow/docs |
| 数据升级 | IAM45、QS MySQL110/Mongo44、AI0043_native_transaction_limit；最终只读回读clean，构造/启动无DDL |
| 运行 | serverA五应用实例、serverD三worker；五种固定镜像见下表，原预算不变；四事务owner ready、10监控target up、四公网健康/就绪入口200且TLS有效 |
| RocketMQ | serverD Docker 5.5.1，infra维护；v2资源/精确账号/TLS、原参数、有限回查及原主库保护沿既定证明；监控仍在旧Mac mini，serverD不新增常驻采集代理 |
| 真实业务 | 唯一新答卷202→评分→规则报告；system空角色创建/改名及IAM/QS双订阅；合法小程序新深度解读→5事件/5首次ACK、11条精确Committed witness/wire hash；新AI Job done/attempt1，持久化模型响应记录1条 |
| 生产NSQ | nsqd/nsqlookupd/nsqadmin均停止、restart=no；无监听/活动连接，旧启动guard真实拒绝；三个容器ID/镜像/挂载、1519数据文件和配置保留且摘要一致 |
| 运维合并 | PR295的12检查/10报告451/0/0、双OS各15 profile/firewall项通过；PR298的4检查含双OS各7边界项及实际Compose证明通过；实际运维安装已回读 |

[稳定发布](rocketmq-m3-stable-release.md)、[固定镜像发布证据](evidence/rocketmq-m3-acr-publication-20261025.json)、[T33验收](evidence/rocketmq-m3-system-ai-acceptance-20261025.json)、[T35实际退役](evidence/rocketmq-m3-nsq-retired-20261025.json)分别记录源码/制品、部署及业务，不以健康或CI代替消费效果。

## 固定生产镜像与实际profile

镜像前缀为`crpi-x3r4i68cpfmwtcll.cn-beijing.personal.cr.aliyuncs.com/fangcunmount/`，按以下`@sha256`使用，不改用latest：

| 镜像名 | digest | 实际部署/预算 |
| --- | --- | --- |
| iam | `55aec5c5a36072d4e87df9c7b29e51554c12a09064f1f5b60441e3ec2a6e777e` | serverA×1，1GiB/1CPU |
| qs-apiserver | `85ac6f5cd3bc75326f6d827393bf1dab7b9e85f305aaf03acefd3a174faec150` | serverA×1，1GiB/2CPU |
| qs-collection-server | `c4c3584fc5a4b11f20344c9e353ffe17f72203c1dff363dd9729e1053b1fde14` | serverA×2，各320MiB/1CPU |
| qs-ai | `38080355322cc342c5b80e06da1ffdbc00549e391824d7be5e54179ea2d45e5b` | serverA×1，768MiB/0.75CPU |
| qs-worker | `052758537916756515f9897238dcc2c8e2c3c598e997859724345ea2993b2d84` | serverD×3，各768MiB/1CPU/并发48 |

[实际profile清单](rocketmq-m3-runtime-profiles.md)是再次部署的配置依据：API使用修正IAM订阅ID的v3；worker使用v2消费专用profile，publish_enabled=false且无事务owner；IAM/AI/collection保留受验acceptance配置。不因目录名sealed关闭worker消费，也不再次部署旧错误acceptance配置。四owner为iam.mysql、qs.mysql、qs.mongo、ai.mysql；原数据库绑定、路由和writer epoch不变。

serverD RocketMQ运维current为`/opt/infra-rocketmq/releases/m3-firewall-f144da7956e5`，仅持久化既有worker bridge到私网8081规则，旧release和原锁保持。旧serverD Compose的NSQ服务仅保留手动profile/restart=no；通用Mac mini开发NSQ不受影响。

## 当前交付边界

- **自动生产CD保持暂停**：IAM/QS的PRODUCTION_DEPLOY_PAUSED=true，AI的AUTO_DEPLOY_ENABLED=false。GitHub provider变量为RocketMQ、发布变量仍封闭；它们不是当前生产运行配置。恢复CD必须先审核真实profile、owner/route/Secrets、worker消费专用与共享预算，重新绑定最终候选；本次不自动解除暂停。
- 第一个新runtime启动屏障仍有效，不能用旧全量备份覆盖新事实；失败以前向修复为主，不自动翻回NSQ/Outbox，不更换事件ID或重做模型。原生超限保持封新写/Checker和具名人工处置；[高级手工恢复未完项](rocketmq-native-recovery-followups.md)仍独立未完成，不冒充本批能力。
- 原30分钟维护目标未达到，实际主要窗口82分46秒；用户批准了延长和先开放后AI验收顺序。T34在实际短时检查后被用户豁免，不形成48h稳定性保证；历史真实时间和失败保留。
- 本次使用正常临时量表新答卷；TaskID正向验收继续原PL-R007移交，不代签通过。Task外部提醒producer保持原关闭，未发送外部验收通知；规则报告不冒称AI，AI由独立正常新解读证明。
- 旧7个blocked模型请求未重做；额外未发布的AI评测草稿/待启动任务未启动。保留现状，不为清理而发起模型评测或外部通知。

## M4 移交与保护清单

M4保持**0/8**，已接收本索引但C01完整盘点尚未通过。本次没有旧代码、表、卷、容器或备份删除。建议先C01冻结对象与保护清单，再优先C06整理生产部署入口/配置和防误启动，随后按依赖完成C02–C05，C07按保留期限/具名批准处置，最后C08回归与合并。

| M4责任 | 已移交对象与限制 |
| --- | --- |
| C01 / 完整盘点 | 三库/SDK固定SHA、五镜像、实际profile、四store、T34豁免及T35退役回执；逐项核对调用者/当前业务责任，不能凭legacy/outbox名称删除 |
| C02–C04 / 旧实现 | 已退出运行的生产NSQ provider、发布型Outbox/Relay、旧reader/格式/中间协议及孤立工具/夹具；保留SDK对其他宿主的通用兼容包、隔离测试和Mac mini开发NSQ |
| C05 / 当前业务事实 | 保护Inbox/业务receipt、QS/AI不可变档案及首次wire/密文、消费幂等、业务retry/未来due/授权、AI response/checkpoint/artifact、rm_tx_binding/request/execution/witness与Checker；result_outbox仍有当前业务ACK职责，不整表删除 |
| C06 / 部署入口 | 原生产NSQ容器已停/restart=no、serverD手动profile与guard已安装；旧手工安装入口、配置/环境变量/监控/恢复脚本的全面删除及新链路可重建验证尚未做，业务CD恢复另行审核 |
| C07 / 资产 | serverD三个原NSQ容器、`/data/infra/nsq/{data,*.conf}`、1519数据文件、原离线444授权缓存channel/4364历史副本及完整备份；它们不是待重放业务任务。历史表/卷/wire/旧镜像及私有证据按原政策至少保留30天，无自动GC或prune；处理前再次核对未决责任和具名范围 |
| C08 / 回归与闭环 | 清理后重新证明最终事务链路、固定版本/启动/回查/幂等/配置可重建及文档/依赖，合并并生成清理发布索引；不能用本次M3验收替代清理后的回归 |

Mac mini已核对三主机原完整保护副本、T35原源码/状态补充和第五阶段546成员私有证据的SHA/0600；公开材料仅保存聚合及摘要。数据/恢复责任继续为原批准人，保留资产不构成可自行恢复旧数据、撤销退役或删除的授权。
