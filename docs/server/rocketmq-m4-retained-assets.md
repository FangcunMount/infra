# M4历史资产处置与当前保护责任

**2026-10-27用户已取消原11月25日等待期，具名历史资产处置已完成。** 当前结果见[追加操作总表](rocketmq-m4-post-closure.md)和[实际receipt](evidence/rocketmq-m4-post-closure-20261027.json)。原[C07政策保留receipt](evidence/rocketmq-m4-c07-retention-20261026.json)是10月26日历史快照，保持原文与摘要，不再作为等待期依据。

| 对象 | 最新处置结果 |
| --- | --- |
| serverD原NSQ三容器 | 已删除nsqd、nsqlookupd、nsqadmin；删除前均停止/restart=no，核对原身份和挂载 |
| NSQ专属镜像 | 已删除nsqio/nsq:v1.3.0的精确image ID；当时只有上述三容器引用，无其他镜像清理 |
| NSQ历史数据与配置 | 原1519文件/155529092 bytes及三份NSQ配置已删除并回读不存在；数据是bind挂载，没有可删除的独立命名卷 |
| M3旧保护备份 | 三主机8份明确原始/派生dump及归档、Mac mini同窗口3份归档已按原hash/inode删除；共11份/1331413483 bytes，回读全部不存在 |
| 五张MySQL旧发布表 | iam.domain_event_outbox、iam.rm_outbox、qs.rm_outbox、qs.ai_messaging_outbox、ai.messaging_outbox共5806条published/confirmed终态记录已原子删除，剩余0；没有DROP或重置自增 |
| Mongo旧发布队列 | qs.rm_outbox的76条published终态文档已在事务内删除，剩余0；集合UUID及索引不变 |
| 当前协议与业务事实 | 四owner/witness、Inbox/receipt/首次ACK/wire档案、业务调度授权/due/attempt、模型response/checkpoint/artifact、7个blocked治理及IAM会话撤销等继续保护 |
| 其他镜像、工具、材料与锁 | current/previous/pins、其他容器引用镜像、原审计记录/审核计划、当前材料和部署锁保留；未执行泛化prune/GC |

C01中的46张SQL表和9个Mongo集合是盘点对象，不是全部可删除对象。部分旧名称结构仍被当前启动/就绪及观察查询使用，因此本次清理终态发布数据并保留必要结构。当前业务、未决责任和恢复输入不因用户豁免等待期而可删除。

首个新业务runtime屏障保持。旧全量备份不能覆盖切换后的事实；此次删除不授权切回NSQ、换事件ID、重新补发消息或重做模型。Mac mini开发NSQ、隔离测试依赖、Broker自身48小时消息保留策略与其他业务备份不在本次删除范围。

固定操作器[源码](../../scripts/ops/m4_legacy_disposition.py)已由PR346通过Linux/macOS各15项验证并合并。MySQL及Mongo的具名终态清理源码和私有证据摘要均在实际receipt关联；原审计元数据保持，不再调用已处置资产的旧恢复/可读性检查。
