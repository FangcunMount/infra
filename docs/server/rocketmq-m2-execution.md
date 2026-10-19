# RocketMQ M2 实施与验证

M2 先验证固定上游客户端，再冻结 SDK 事务 API。业务仍使用 NSQ；本文件不表示 M2 或 M3 已完成，也不授权普通消息的中间业务上线。

## M2-0 可重复验证入口

```sh
python3 scripts/rocketmq/ci-transactions.py \
  --sdk /absolute/path/to/reliable-messaging \
  --image rocketmq-acceptance:5.5.1 \
  --report rocketmq-m2-transactions.json
```

要求本机 Docker Compose、Go1.25.12、uv 和可用的 Python3.11–3.13。缺少依赖直接失败，不跳过。`--image` 必须已存在；CI 使用原有 SHA512/PGP 验证后构建的5.5.1镜像。MySQL8.0.36仅作为独立验证数据库，镜像实际ID写入报告。可通过 `--mysql-image` 指定已缓存的8.0镜像，但不能传入已有数据库或外部Broker。

Go探针使用SDK中基于官方5.1.4的私有快照：修复连接/RPC选项透传、释放RPC/拨号取消资源及保持流生命周期，并保留必要格式化，原文件摘要、许可证和补丁随SDK保留。实测发现原版丢弃这些选项，实际RPC连接未使用调用方TLS配置，响应丢失拦截也不生效。禁止靠替换全局factory绕过此问题。Python通过独立uv.lock固定5.1.2及SQLAlchemy/asyncmy。它们是临时验证程序，不是SDK的公共事务API。MySQL表仅存在于此次Compose项目中，不是未来宿主schema的定稿。

每次执行创建随机Compose项目、私有临时目录、回环端口、TLS证书、应用账号、TRANSACTION Topics与消费组。Broker/NameServer沿用现有资源上限；MySQL使用独立tmpfs。退出只清理该次项目，既不连接生产也不操作qs-dev。应用账号只获各自Topic权限，管理账号只由验收脚本使用。

## 门禁

- Go/Python半消息不可见；业务效果与精确owner/ID/body hash凭证提交后，Commit才使消息可消费；Rollback始终不可见。
- 原生产者在数据库提交后以退出码23真实退出，未发Commit。全新进程通过Broker真实回查读取同一数据库凭证并完成提交；另验证Go/Python相互恢复。
- Commit真实RPC成功后，在客户端边界注入响应丢失：调用方结果Unknown，业务只提交一次，消费者仍能收到。此项不是网络包级故障注入；未发送Commit的进程崩溃由上一项单独覆盖。
- 暂停此次MySQL，真实回查必须返回Unknown且消息不可消费。恢复数据库后原流程可结束。
- 另一owner的已提交凭证不能确认此消息；另一owner的账号也不能获取此Topic的半消息确认。
- 两种客户端均必须拒绝不受信CA；SDK另有真实TLS gRPC回归测试，验证可信CA通过、错误CA和错误主机名被拒绝、拦截器到达实际RPC。
- 读取实际生效的事务超时、回查间隔、次数和保留时间；缺字段即失败。只导出白名单数值，不输出带凭据的完整Broker配置。
- 在隔离Broker降低回查次数，保持Python真实Unknown，必须在原生`TRANS_CHECK_MAX_TIME_TOPIC`查到此消息；只等待超时不算通过。生产参数不随测试修改。

## 证据与后续

2026-10-19 对serverD执行只读`getBrokerConfig`并仅解析上述白名单，确认有效值：`transactionTimeOut=6000`、`transactionCheckInterval=30000`、`transactionCheckMax=15`、`fileReservedTime=48`。未修改生产配置。检查次数会受实际扫描和存储状态影响，这些值不能直接解释为固定业务恢复SLA；原生超限丢弃演练在隔离项目执行。

报告逐项记录通过/失败、0跳过、镜像ID、客户端版本、有效参数和探针源文件摘要。CI与Mac mini验证分别记录；本地缓存镜像验证不能替代CI的新构建签名证据。

M2-0不能证明宿主事务绑定、执行fence、Mongo callback重入、幂等冻结计划、有界回查队列或生产恢复窗口。这些分别属于后续M2批次。通过之前不发布高级事务API，也不迁移IAM/QS/AI或停用NSQ。

原生超限主题使用5.5.1 [TopicValidator实际常量](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/common/src/main/java/org/apache/rocketmq/common/topic/TopicValidator.java)，不能使用DefaultTransactionalMessageCheckListener日志中少一个下划线的拼写。验收通过真实消息索引查询确认原始测试key。

## 2026-10-19 交付状态

M2-0 [完整CI](https://github.com/FangcunMount/infra/actions/runs/39184548857)通过：20项真实验证成功、0失败、0跳过。签名构建、普通消息回归、事务验证及镜像导出均成功。[结构化证据](evidence/rocketmq-m2-20261019.json)记录固定版本、有效参数和逐探针事件。测试中的RPC运行时/探针文件与SDK PR33最新head逐文件SHA256一致；后者只比验收引用多出源码复现检查。

- [infra PR20](https://github.com/FangcunMount/infra/pull/20)：隔离Docker验收与记录。
- [SDK PR33](https://github.com/FangcunMount/reliable-messaging/pull/33)：TLS/RPC配置、取消资源和启动失败清理修复；SDK自身CI通过。
- [SDK PR34](https://github.com/FangcunMount/reliable-messaging/pull/34)：M2-1纯协议初版；Go检查/race/lint、Python源码与隔离wheel各21项测试、本地完整mypy通过，PR完整CI已通过（Python3.11/MySQL8.0.36、Python3.13/MySQL8.4，源码与安装wheel均通过0跳过门禁）。

协议区分请求、冻结计划代次与执行fence；旧终态不改写，Checker不以根请求最新版本替代旧证据。数据库原子性、claim/CAS、取消编排、事务发送器、有界回查生命周期及业务接入尚未实现。M2/M3整体未完成，SDK接口保持provisional；没有发布SDK或切换生产provider。下一批为原MySQL/GORM/Mongo/SQLAlchemy事务绑定及真实存储证明。

最终只读核对：serverD现有RocketMQ、NSQ及3个worker均running=true、OOM=false、restartCount=0。测试不作为生产业务验收。SDK协议PR34验证head为`d89584b51ecdcb23aba8a2b4e20dc361e94683f4`；源码、wheel、完整CI均通过，仍未发布正式接口。
