# RocketMQ M2 实施与验证

## M2 SDK 批次进度（2026-10-19）

本节为本批次唯一进度总表。批准范围为 Go/Python 独立事务 SDK、原事务 witness、Checker、有界生命周期、双存储证明及固定预发布；不包含三宿主改造或生产变更。沿用下文 M2-0 证据，新增任务独立计数。

基线：SDK `fd9c51691d785ced6e27d1ad3509fc4ac99a7b1f`；infra `44c379bedf5d37194aff1c87eccc8c8080cb3b2c`。隔离分支：SDK 协议 `codex/rocketmq-m2-sdk`、存储续批 `codex/rocketmq-m2-storage`；infra `codex/rocketmq-m2-sdk-tracking`。

进度：**16/24**。任务完成表示实现及所列验证通过；PR 合并、发布、部署独立记账。里程碑全部任务及合并门禁满足后才完成。每项任务完成立即更新本表、证据与会话；失败/阻塞保留，不删除或静默减少分母。

| 里程碑 | 任务 | 状态 | 完成门禁 |
| --- | --- | --- | --- |
| M2-0 | 既有批次 | ✅ 已完成 | 20 项真实验证，0 跳过 |
| M2-P | T01 | ✅ 已完成；infra PR21 合并 6fdefde | 基线、任务及证据格式建立 |
| M2-1 | T02–T04 | ✅ 已完成 | 双语言契约及失败状态通过、PR 合并 |
| M2-2 | T05–T09 | ✅ 已完成；SDK 合并 d7d1415 | 四种原事务适配及并发证明、PR 合并 |
| M2-3 | T10–T13 | ✅ 已完成；SDK PR38、infra PR23 已合并 | Go 真 RPC、回查及关闭有界、PR 合并 |
| M2-4 | T14–T16 | ✅ 已完成；SDK PR39、infra PR23 已合并 | Python 线程/loop/取消证明、PR 合并 |
| M2-5 | T17–T20 | T17 实现完成，31 项真实 v2 验收待通过 | 正式 SDK 故障集成 required CI 非空且 0 跳过、PR 合并 |
| M2-6 | T21–T24 | 待开始 | 固定 tag/制品及下载重装通过 |

| 完成 | ID | 任务与门禁 | 完成时间 / 源码 / 证据 / PR |
| --- | --- | --- | --- |
| ✅ | T01 | 执行总表、基线、任务依赖、验证命令和证据格式 | 2026-10-19 +08:00；基线如上；24 个任务 ID 检查与 git diff --check 通过；提交 952d1c7；infra PR21 已合并 6fdefde |
| ✅ | T02 | Sender/Executor/Store/Checker 契约和冻结 codec；双语言 round-trip | 2026-10-19 +08:00；SDK 4943d43；[本地证据](evidence/rocketmq-m2-sdk-contracts-20261019.json)；[SDK PR35](https://github.com/FangcunMount/reliable-messaging/pull/35) CI 全通过并合并为 4c098c5 |
| ✅ | T03 | 请求/计划/执行 fence；重复请求、新执行、显式重建计划契约 | 2026-10-19 +08:00；SDK 4943d43；[本地证据](evidence/rocketmq-m2-sdk-contracts-20261019.json)；[SDK PR35](https://github.com/FangcunMount/reliable-messaging/pull/35) CI 全通过并合并为 4c098c5 |
| ✅ | T04 | 三阶段结果、取消、部分准备与未知提交状态矩阵 | 2026-10-19 +08:00；SDK 4943d43；[本地证据](evidence/rocketmq-m2-sdk-contracts-20261019.json)；[SDK PR35](https://github.com/FangcunMount/reliable-messaging/pull/35) CI 全通过并合并为 4c098c5 |
| ✅ | T05 | schema/索引/显式安装；身份比较、fence 边界、版本拒绝 | 2026-10-19 +08:00；SDK d1a9cf5；[真实依赖证据](evidence/rocketmq-m2-sdk-storage-20261019.json)；[PR36](https://github.com/FangcunMount/reliable-messaging/pull/36) 全部 CI 通过并合并 d7d1415 |
| ✅ | T06 | Go MySQL/sql、GORM 原事务 guard；真实原子性 | 2026-10-19 +08:00；SDK d1a9cf5；[真实依赖证据](evidence/rocketmq-m2-sdk-storage-20261019.json)；[PR36](https://github.com/FangcunMount/reliable-messaging/pull/36) 全部 CI 通过并合并 d7d1415 |
| ✅ | T07 | Go Mongo guard；callback 重入、写冲突、未知提交 | 2026-10-19 +08:00；SDK d1a9cf5；[真实依赖证据](evidence/rocketmq-m2-sdk-storage-20261019.json)；[PR36](https://github.com/FangcunMount/reliable-messaging/pull/36) 全部 CI 通过并合并 d7d1415 |
| ✅ | T08 | Python SQLAlchemy/MySQL guard；根事务/savepoint/AUTOCOMMIT | 2026-10-19 +08:00；SDK d1a9cf5；[真实依赖证据](evidence/rocketmq-m2-sdk-storage-20261019.json)；[PR36](https://github.com/FangcunMount/reliable-messaging/pull/36) 全部 CI 通过并合并 d7d1415 |
| ✅ | T09 | reservation、资格、中止器；迟到提交隔离 | 2026-10-19 +08:00；SDK d1a9cf5；[真实依赖证据](evidence/rocketmq-m2-sdk-storage-20261019.json)；[PR36](https://github.com/FangcunMount/reliable-messaging/pull/36) 全部 CI 通过并合并 d7d1415 |
| ✅ | T10 | Go driver context、回查准入、关闭；源码复现 | 2026-10-19 +08:00；SDK 1846f4d；[驱动与真 Broker 证据](evidence/rocketmq-m2-sdk-driver-20261019.json)；PR37 合并 ab7aa78 |
| ✅ | T11 | Go Sender 多分支准备、本地执行、最终确认 | 2026-10-19 +08:00；SDK c59e08a；[23 项真 Broker 与存储/语言 CI 证据](evidence/rocketmq-m2-sdk-senders-20261019.json)；SDK PR38 已合并 87e0ff2；infra PR23 已合并 4b7ed57 |
| ✅ | T12 | Go 精确 Checker；跨实例、饱和、DB 预算 | 2026-10-19 +08:00；SDK c59e08a；[23 项真 Broker 与存储/语言 CI 证据](evidence/rocketmq-m2-sdk-senders-20261019.json)；SDK PR38 已合并 87e0ff2；infra PR23 已合并 4b7ed57 |
| ✅ | T13 | Go Start/准入/Close/Wait；失败清理、关闭超时 | 2026-10-19 +08:00；SDK c59e08a；[23 项真 Broker 与存储/语言 CI 证据](evidence/rocketmq-m2-sdk-senders-20261019.json)；SDK PR38 已合并 87e0ff2；infra PR23 已合并 4b7ed57 |
| ✅ | T14 | Python 实例级有界 Producer；阻断上游无界队列 | 2026-10-19 +08:00；SDK b9fbad4；[23 项真 Broker 与存储/语言 CI 证据](evidence/rocketmq-m2-sdk-senders-20261019.json)；SDK PR39 已合并 65eae5b；infra PR23 已合并 4b7ed57 |
| ✅ | T15 | Python Sender/Checker/宿主 loop；session 不跨线程 | 2026-10-19 +08:00；SDK b9fbad4；[23 项真 Broker 与存储/语言 CI 证据](evidence/rocketmq-m2-sdk-senders-20261019.json)；SDK PR39 已合并 65eae5b；infra PR23 已合并 4b7ed57 |
| ✅ | T16 | Python 取消、真实在途记账、关闭、多客户端隔离 | 2026-10-19 +08:00；SDK b9fbad4；[23 项真 Broker 与存储/语言 CI 证据](evidence/rocketmq-m2-sdk-senders-20261019.json)；SDK PR39 已合并 65eae5b；infra PR23 已合并 4b7ed57 |
| ☐ | T17 | SDK/infra v2 路由、类型、owner ACL、共享消费预算 | SDK 2903608；Go/Python/infra 共用规范向量、公开消费者多物理输入共享预算、provision 全量预检与拒绝既有冲突；31 项真实双 runtime/MySQL profile CI 待通过 |
| ☐ | T18 | 正式 SDK 跨语言/MySQL、Go/Mongo 真端到端 | — |
| ☐ | T19 | 退出、断网、DB 提交丢回复、Broker 重启故障矩阵 | — |
| ☐ | T20 | 资源上界、指标、超限告警、0600 原生超限审计导出 | — |
| ☐ | T21 | 原事务示例、接入/恢复/关闭文档、API 评审 | — |
| ☐ | T22 | 固定候选 SHA、完整 CI、wheel/sdist/摘要/receipt | — |
| ☐ | T23 | 两语言 tag 同一 SHA，GitHub 固定预发布 | — |
| ☐ | T24 | 下载发布 tag/制品重新安装验收、索引与总表关闭 | — |


本次 T11–T16 的公开 SDK 验收为 23/23、0 跳过；之后仅追加单次半消息 RPC 及回调诊断修复，已通过对应实际 TLS/编排测试和最新源码 CI。SDK Go/Python PR38/39 均已合并。infra 完整工作流曾因旧 SDK 固定引用与新增三分支探针不匹配失败；已统一固定到 SDK main `65eae5b`，精确 SHA 重跑 [公开 SDK 23 项](https://github.com/FangcunMount/infra/actions/runs/39194664066) 与[完整 Docker/普通消息/M2-0 回归](https://github.com/FangcunMount/infra/actions/runs/39194664076) 均通过，infra PR23 已合并 4b7ed57，M2-3/M2-4 里程碑关闭。原失败运行 [39193222448](https://github.com/FangcunMount/infra/actions/runs/39193222448) 保留，不作通过证据。

执行顺序：T01 → T02–T04 → T05–T09 → T10–T13 → T14–T16 → T17–T20 → T21–T24；不跳过前置门禁。

适配矩阵：Go database/sql、GORM、Mongo；Python SQLAlchemy/MySQL。默认验证 profile：发送并发 8、分支上限 16、回查 worker 4/等待 32、DB 回查 2s、RPC 5s、lease 60s、维护每 5s 最多 100 条；宿主显式覆盖，生产预算归 M3。

固定依赖：Broker 5.5.1；Go 客户端 5.1.4 + 可复现补丁；Python 5.1.2；Go 1.25.9/1.25.12；Python 3.11/3.13；MySQL 8.0.36/既有 8.0.44/8.4；Mongo 固定 7.0.37 replica set。所有故障测试仅操作随机隔离项目，缺依赖失败、不 skip，不安排跨云吞吐。

发布候选：Go `v0.5.0-rocketmq-tx.1`；Python `0.4.0a1` / `python/v0.4.0a1`。名称已占用则阻断，绝不覆盖。两个 tag 绑定同一经验证 SDK SHA；只发布 GitHub Release，不新增 PyPI。最终下载的 Go module/wheel/sdist 重新验收，不用 replace/editable。

证据格式：任务 ID、采集时间（含时区）、SDK/infra SHA、验证命令、报告或 CI 链接、结果/失败/跳过数、依赖版本与镜像 digest、隔离项目及清理结果、PR/合并/发布状态。日志不记录业务 wire、正文或凭据；私有审计权限 0600。未决 witness 不自动 GC。

待执行验证：SDK `make check`、`make lint`；Python `uv run ruff check .` / `uv run mypy` / 源码与安装 wheel pytest；真实存储与 Broker 使用 required 隔离 CI。M2-0 探针通过不能替代正式 Sender 验收。

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
