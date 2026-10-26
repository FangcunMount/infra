# M4 历史资产保留与处置责任

本轮采用政策保留完成 C07，不删除历史容器、卷、表、镜像、wire 或备份。生产只读核验和保护副本可读性已通过；[完整具名清单与摘要](evidence/rocketmq-m4-c07-retention-20261026.json)随本 PR 合并生效。M4 最终应用候选和业务回归仍由 C08 单独完成。

| 对象 | 位置与用途 | 本轮结果 |
| --- | --- | --- |
| 原 NSQ 三容器及引用镜像/挂载 | serverD `nsqd`、`nsqlookupd`、`nsqadmin` | 原身份、镜像和挂载保持；均 stopped/restart=no，无监听或活动连接 |
| NSQ 历史数据 | `/data/infra/nsq/data`；1519 文件、155529092 bytes；原444个离线授权缓存 channel/4364历史副本 | 逐文件与 T35 清单相同；树摘要 `6f72f5614855547ef4bf8d7661846a20c23692065dbe75e66bdc493d5a2171d9`；不是业务重放许可 |
| 三份 NSQ 配置 | `/data/infra/nsq/{nsqd,nsqlookupd,nsqadmin}.conf` | 摘要与原冻结清单一致 |
| 原安装源码/退役记录 | serverD `/var/lib/fangcun-m3/windows/20261025081841-2/T35-retirement` | 三份原字节0600副本及 pre-state 可读，数据清单一致；不重跑旧安装/启动工具 |
| 三主机保护归档 | Mac mini `backups/infra/rocketmq/m3-production-window-20261025081841-2/{serverA,serverC,serverD}-protection.tar.gz` | 三份原摘要、大小、0600权限一致；流式读完所有普通文件，不解包、不导入或执行 |
| MySQL/Mongo 盘点对象 | C01冻结的46张具名SQL表、9个具名Mongo集合，逐项列于 receipt | 全列/全部文档、索引、options/UUID继续保留；本轮不做DDL或业务行查询，不把旧盘点冒充新数据快照 |
| 当前协议与业务事实 | 四owner、Inbox/receipt、首次ACK/wire、调度授权/due/attempt、AI response/checkpoint/artifact、IAM会话撤销等 | 清单明确保护；只要仍承担当前或未决责任，不因日期到达而过期 |
| 镜像、工具、材料与锁 | current/previous/pins、全部容器引用镜像、原工具/审核计划、版本材料、原锁和当前指针 | 保留；不执行 prune/GC，不切指针，不把旧保护归档当作新运行回退许可 |

统一保守保留至 **2026-11-25 23:19:18（北京时间）以后才可重新评审**，不少于原30天政策。该时间是最早复核时间，不是删除时间；当前/未决事实、被 current/previous/pin/容器引用的镜像与恢复依赖不适用到期删除。

数据与恢复责任沿用 M3 的具名生产数据负责人；资产执行责任由 infra 生产维护方承担。后续触发条件为：保留期已满足、未决责任已明确关闭、按精确对象重新盘点、保护副本及 current/previous/工具依赖重新核验，并形成独立物理处置范围。没有自动清理器或已授权的泛化删除。

首个新业务 runtime 启动屏障仍有效。旧全量备份不能覆盖切换后的新事实；本轮证明归档可读，不是再次批准生产恢复。需要修复时沿原事实和业务授权前向处理，不能翻回 NSQ、换事件ID或重做模型。

可复查只读程序为 [NSQ资产核验](../../scripts/ops/m4_retained_nsq_readonly.py)与[归档可读性核验](../../scripts/ops/m4_retained_backup_readonly.py)。它们显式读取冻结清单，仅输出摘要/元数据；SSH沿固定Mac mini入口，原始私有材料不入库。NSQ数据及所有容器运行身份在读取前后保持，本轮没有数据库连接、服务重启、材料激活、生产部署或模型调用。Mac mini开发NSQ、隔离测试依赖和Broker自身48小时消息保留配置不属于本次处置范围。
