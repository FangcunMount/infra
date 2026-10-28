# T09：宿主显式跨路由 Replan 验证

这是[执行总表](rocketmq-readable-names-execution.md)中的验证子项，未完成真实 CI 前不勾选 T09。

原有纯契约验证了旧路由不得普通 Retry/Execute、首次 wire 保持及新计划身份；真实 SDK 存储验证了原执行必须 Aborted、CAS 和旧证据保留。本专项将这些条件在实际 QS MySQL Committer 和 RocketMQ 上连起来，不修改业务写入链路或生产管理 API。

`rocketmq-readable-replan.yml` 使用固定 QS 源码、正式 SDK RC 和隔离依赖。先运行原评价/失败宿主 9 项，再在同一隔离环境复制一份已审阅的测试文件到原宿主包，运行并删除；原源码 SHA 和测试文件摘要分别记录，最后要求源码重新干净。原材料仅增加精确历史映射，并在验证结束后恢复原字节，不新增旧路由生产者或消费者。

额外 5 项必须证明：Prepared/Unknown 不能 Replan；历史普通 Retry 被拒绝；显式 Aborted Replan 保留消息/首次 wire/旧终态并产生新 fence；新活动路由经原 GORM 根事务提交业务与 witness、实际 Broker 消费相同 wire；Committed 或已被替代的执行不能再次 Replan，业务回调和业务事实仍各一次。MySQL 8.0.36/8.4 每档须 14 项、零失败零跳过及完整清理。

这是测试宿主显式调用 SDK 存储授权后通过原 Committer 发送的证明，不提供新的自动重试或生产解保护入口。不宣称真实 provider/system 验收、旧半消息恢复或生产迁移完成；这些仍有独立门禁。
