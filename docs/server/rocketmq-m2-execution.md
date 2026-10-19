# RocketMQ M2 实施与验证

M2 先验证固定上游客户端，再冻结 SDK 事务 API。业务仍使用 NSQ；本文件不表示 M2 或 M3 已完成，也不授权普通消息的中间业务上线。

## M2-0 可重复验证入口

```sh
python3 scripts/rocketmq/ci-transactions.py \
  --image rocketmq-acceptance:5.5.1 \
  --report rocketmq-m2-transactions.json
```

要求本机 Docker Compose、Go1.25.12、uv 和可用的 Python3.11–3.13。缺少依赖直接失败，不跳过。`--image` 必须已存在；CI 使用原有 SHA512/PGP 验证后构建的5.5.1镜像。MySQL8.0.36仅作为独立验证数据库，镜像实际ID写入报告。可通过 `--mysql-image` 指定已缓存的8.0镜像，但不能传入已有数据库或外部Broker。

Go探针直接固定官方客户端5.1.4；Python通过独立uv.lock固定5.1.2及SQLAlchemy/asyncmy。它们是临时验证程序，不是SDK的公共事务API。MySQL表仅存在于此次Compose项目中，不是未来宿主schema的定稿。

每次执行创建随机Compose项目、私有临时目录、回环端口、TLS证书、应用账号、TRANSACTION Topics与消费组。Broker/NameServer沿用现有资源上限；MySQL使用独立tmpfs。退出只清理该次项目，既不连接生产也不操作qs-dev。应用账号只获各自Topic权限，管理账号只由验收脚本使用。

## 门禁

- Go/Python半消息不可见；业务效果与精确owner/ID/body hash凭证提交后，Commit才使消息可消费；Rollback始终不可见。
- 原生产者在数据库提交后以退出码23真实退出，未发Commit。全新进程通过Broker真实回查读取同一数据库凭证并完成提交；另验证Go/Python相互恢复。
- Commit真实RPC成功后，在客户端边界注入响应丢失：调用方结果Unknown，业务只提交一次，消费者仍能收到。此项不是网络包级故障注入；未发送Commit的进程崩溃由上一项单独覆盖。
- 暂停此次MySQL，真实回查必须返回Unknown且消息不可消费。恢复数据库后原流程可结束。
- 另一owner的已提交凭证不能确认此消息；另一owner的账号也不能获取此Topic的半消息确认。
- 读取实际生效的事务超时、回查间隔、次数和保留时间；缺字段即失败。只导出白名单数值，不输出带凭据的完整Broker配置。
- 在隔离Broker降低回查次数，保持Python真实Unknown，必须在原生`TRANS_CHECK_MAXTIME_TOPIC`查到此消息；只等待超时不算通过。生产参数不随测试修改。

## 证据与后续

报告逐项记录通过/失败、0跳过、镜像ID、客户端版本、有效参数和探针源文件摘要。CI与Mac mini验证分别记录；本地缓存镜像验证不能替代CI的新构建签名证据。

M2-0不能证明宿主事务绑定、执行fence、Mongo callback重入、幂等冻结计划、有界回查队列或生产恢复窗口。这些分别属于后续M2批次。通过之前不发布高级事务API，也不迁移IAM/QS/AI或停用NSQ。
