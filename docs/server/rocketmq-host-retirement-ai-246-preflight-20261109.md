# 2026-11-09 AI #246 入窗复验

**当前决定为 No-Go。** 账户、制品、材料比较、Worker 就绪与四 owner 的服务端观测均已复验。Prometheus 集中采集于 11 月 10 日 00:29 完成一段 30 分钟复验，窗口前须再取新鲜证据。受限直读备选仍待独立签收。真实窗口尚待授权和现场签收。AI 自动发布关闭，QS 生产发布工作流仍手动禁用。各项现场签收留空。[窗口签收清单](rocketmq-host-retirement-ai-246-window-signoff.md)

| 项目 | 本轮实际证据 | 判定 |
| --- | --- | --- |
| QS 六实例 | ServerA 的 API 和两个 Collection 与首批发布的容器 ID、镜像一致，均健康、重启 0。ServerD 三份 Worker 的容器 ID 和镜像与首批一致，均 running，具名实例两轮 `/readyz` 均为 200。三台快照的 A/B 分支因 sudo 认证失败，A 由现有个人只读入口补齐。 | 六实例身份及本轮健康／就绪通过。[快照运行](https://github.com/FangcunMount/qs-server/actions/runs/42625037809) |
| QS 与 AI 现库 | 原受核 QS 维护容器内以 UID 2000 使用受限探针，实读 clean 111/44 与两库原身份。探针构建工作树为 `1319d4c`，所用迁移、TLS 及依赖文件与受核 QS main `7899ffc` 一致。AI 管理员复验 24 条查询，原 43、原 DDL、目标 0 行及全局可见性均成立，锁、事务及依赖相关阻断计数为 0。 | 只读现库通过，观察回执保持 `freeze_verified=false`、`observations_atomic=false`。[AI 管理员复验](https://github.com/FangcunMount/qs-server/actions/runs/42625038784) |
| AI 重启 | 同一个 f9 容器重启计数为 1。北京时间 11 月 8 日 04:13:07 记录 `service_failed` 并开始 drain，两个订阅组件退出报错，04:13:10 记录 RuntimeError，04:13:23 再次 ready。当前健康。日志没有保留初始失败原因。 | 后续正常停机须按 W03 单独取得无错误排空证据。 |
| AI 持久状态 | 原库一致性只读时点实读 22 条执行和 29 条见证均 committed，42 个作业均 done，40 次模型调用均 response_received，待业务 ACK 及 held 命令均 0，事务及连接池释放。 | 当前持久状态已核对，真实窗口复验仍待签收。 |
| 当前采集 | 通过现有 Prometheus 路径得到部分 `up` 样本，四 owner available/fresh/protected 及 QS/AI 业务观察查询缺样。后续目标列表超时，后续 HTTP 请求报错。11 月 1 日两处远端抓取共同失败的历史样本再次可查，Prometheus 自身当时仍 up。北京时间 21:39–21:40 分别直读 QS、AI 和 IAM 应用指标，四 owner 各两次均 available/fresh=1、protected=0。 | 服务端观测已取得，集中采集根因及连续可观测性未确认。入窗前恢复集中采集并核对，或由独立审查签收具名端点直读作为窗口等价证据。 |
| 固定 44 制品 | MacBook 和 ServerA 分别重新读取生产与离线前向归档，两份原 SHA 均一致。AI main 仍为 `c6359b441de48fde5b295529fe9c10f50e4c53f5`，预备镜像保持 `sha256:e6afea10…d9470e`。 | 制品字节复验通过。 |
| 实际执行账户 | 使用准备镜像、实际 UID 10001、独立数据库网络、仅公共 CA 和 VERIFY_IDENTITY 完成只读复验。principal 和完整 GRANTS 与原资格相同，直接授予全库读取、目标 DROP、锁表和 ledger UPDATE 能力。前两次旧协调脚本的重启计数断言拒绝，最终验证把计数固定为当前实测值并核对运行实例在探针前后相同。 | 技术范围通过。较宽账户仍待独立审查明确签收，窗口内重新采集。 |

## 隔离验证

- 在本地 MySQL 8.4.13 上，以精确 AI `c6359b4` 运行批准与原生空表迁移两份测试，34 项通过。测试实例绑定本机回环地址并使用独立凭据。第一次运行缺少 Git 元数据，有一项失败，改用该精确提交的隔离检出后全量通过，保留原失败。
- 在合成 51 表材料上串联冻结保护、归档比较、两个私有目录副本、实际 `review/v2` 校验和独占消费文件。模拟锁持有进程退出，演练协调程序拒绝交接。过期批准、principal 漂移、归档 SHA 或内容漂移和重复消费均拒绝。锁连续性仍由实际窗口操作人和独立审查人签收。
- 用 11 月 1 日真实归档对历史只读指纹验证离线比较路径。重算 51 表、8,503 行约 3.23 秒，全部匹配，原备份仍为在线材料。管理员只读工作流本次从派发到完成 65 秒，仅用于估算。正式窗口还须预留调度等待、两地复制、独立审查、验证和恢复时间。
- [离线材料检查器](../../scripts/mysql/ai_window_material_check.py)接入 W05.3，账户能力分类显式检查 `LOCK TABLES`。比较结果使用 `execution_authorized=false`。正式批准继续走原 W06，生产迁移协议和精确批准字段沿用现有契约。

## 其他并行任务

- **F02 已生成 51 条私有签收材料。** 本次现库 58 条非 retired 命令，原 51 条的成员和逐行摘要不变。逐条匹配原 dump 的旧协议 confirmed、原正文和 wire 哈希，并记录当前回执与投影证据。51 条回执匹配 Inbox，29 条有工作流投影，23 条有带原版本事件的终态投影，22 条有评测状态。计数可重叠。逐条分类待数据责任人签收，公开记录只留汇总。
- **F05/F06 依赖复核。** IAM 两表仍有 transaction handoff、状态和 readiness 读取，原 bootstrap 通知路径继续保留。QS MySQL 除原效果和反向一致性还有调度交接及治理写入口，Mongo 除历史读取还有 replay、重试交接及未来调度写路径。后续兼容改动必须分别覆盖这些入口。四个候选仍待实现替代路径及独立原生验证。
- **F07 仍待实现。** 原 QS 双存储 run 40059571496 的原生步骤失败，聚合未满足 23 通过、零失败零跳过断言。当前可见日志没有给出失败子例，原 artifact 列表为空。下一步在原固定夹具上复现并保全逐案例报告，再推进 QS 双存储和 AI SQLAlchemy 原根及故障矩阵。[历史失败运行](https://github.com/FangcunMount/infra/actions/runs/40059571496)
- **运维与 M1。** ServerA 现有 IAM、AI、API、Collection 清理审计均为成功、0 删除。用固定工具实跑预览，显式保护 5 个兼容制品，候选为 AI 1、API 1、IAM 和 Collection 各 0。现有维护容器仍为 idle，核对 UID 2000、无自动重启及原只读挂载，并用于本次 QS 只读采集。其处置及 A/B/D 部署账户精确授权、B/D 预览仍待审查。QS M1 配置、API 与 Worker 入口三组定向测试通过，完整人工启动另待验收。

## 证据保全与后续门槛

本轮 41 份私有原件及索引归档为 25,078,168 字节，SHA256 `16c7be85e28a0265f13aa8e75c3223c29beb020fa174264fdc84808b0af5b168`。MacBook 和 ServerA 两地回读、逐成员校验及 fsync 完成，复制回执外置并两地保存。至少保留 30 天，未结延期。实际全备与不可变镜像继续独立保全。

追加直读和 CI 原件归档为 15,542 字节、7 份原件及索引，SHA256 `3edd5744f0661998b3deff8dff069ca22e5fc0a96c3d8c4fc2549a9c12d91971`。两地逐成员读回和 fsync 完成。精确提交 `d9aae078e07602bb265bbf118331e10ce12345dc` 的合同 CI 25 项测试和编译通过，原始日志 ZIP CRC 通过。[合同 CI](https://github.com/FangcunMount/infra/actions/runs/42627299329)

下次先处理集中采集或签收直读方案，完成账户范围及窗口授权签收，再进入 W02–W03。当前尚无真实排空、当次冻结保护、执行批准、消费或业务重开回执。事务凭证、历史、ACK、调度和 Broker 持久待办均在保留范围内。

[集中采集诊断与固定直读方案](rocketmq-host-retirement-ai-246-observability-20261109.md)记录后续双向握手证据、具名端点实跑及独立签收栏。

追加复验覆盖 ServerA/B/D 的实际 `deploy` 账户与同一固定清理器。A 的四条授权、B 的单条授权精确匹配，交叉服务和任意 Python 的列权检查均拒绝。D 的 Worker 专用规则存在，同时另有 `NOPASSWD: ALL`，有效权限仍允许交叉服务和任意 Python。B/D 以实际账户仅执行预览，候选分别为 0 和 1，运行及停止容器引用均在保留集，前后镜像、容器、卷、部署锁和清理状态文件相同。D 的账户收口和候选处置资格须单独审查。集中采集与清理器复验共 26 份原件，归档 17,391 字节，SHA256 `76a952c4da2860e3f0f4ff7c0896875692c3a94087afe089bef5a4ecc714859f`，MacBook 与 ServerA 逐成员读回并 fsync。

M1 复验发现 `make check-infra` 仍经历史 `all` 检查访问 NSQ，导致无 NSQ 的 `make run-all` 和 `make quick-start` 在进程启动前失败。QS #481 将标准入口指向 MySQL、Redis、MongoDB 数据预检，保留显式历史探测。随后用真实 Redis 复现认证失败仍因客户端零退出码被签为通过。草稿 `6154596d2384b8bc8b37a403453914ab94a1329b` 要求收到 `PONG`。四项回归和文档门禁通过。固定 MySQL 8.4.13、MongoDB 7.0.37 replica set 和 Redis 7.4.12 的隔离实跑共七项符合预期，覆盖成功、三类不可达、Redis 认证拒绝和两个历史探测。三个 QS 入口已构建。[QS #481](https://github.com/FangcunMount/qs-server/pull/481)

隔离 RocketMQ 5.5.1 使用固定发布归档和 PGP 签名构建，ARM64 镜像 ID 为 `sha256:aea7d93f351a64aecf3648e66387401c96ec57abbc7e0d1d0e6e3cb43b76210e`。真实 NameServer、Broker 和 Proxy 启动后，回环端点成功协商 TLS 1.3 与 HTTP/2，错误证书身份被拒绝。两组夹具均按归属清理，既有容器、网络和卷清单前后一致。完整人工开发启动还需接入路由、owner 绑定、实际 IAM 和三个 QS 进程，并验证一条业务链路。全新 IAM clean 45 的两份待发送通知仍由 F05 验证实际交接。

QS #481 精确草稿 `6154596d2384b8bc8b37a403453914ab94a1329b` 的 29 项检查成功、1 项按条件跳过，当前运行时 E2E 已通过。人工开发启动仍按真实配置和依赖单独验收。

晚间 W00 直读与 M1 首次数据实跑共 23 份原件，归档 13,451 字节，SHA256 `1a9ce599565bafa2daea31ad13d2d8160c4b3804b0cd80b95924eb886d57affa`。Redis 拒绝修复前后、固定 Broker 构建和实际 TLS 原件共 20 份，归档 16,560 字节，SHA256 `da8274cefeab820536c383bf9e74eaaca6ef2b8a6d8598868f3d4d3a66816c1a`。两组均在 MacBook 与 ServerA 逐成员读回并 fsync。

F02 已补两份源码草稿。QS 在同一个有界只读查询中单独报告观测到的事务锚点缺失或冲突数量，原业务回执阻断语义保留。MySQL 8.4.13 隔离用例实际覆盖完整锚点、缺档案、见证冲突及后续查询失败。对应面板以独立时序展示计数，缺样保持为空。QS 草稿精确提交 `f4706861ccf56d9b53c68559ce052586f1e11b0d` 共 29 项检查成功、1 项按条件跳过，含当前运行时 E2E。上线需分别签收和受控发布，51 条私有历史分类继续待数据责任人签收。[QS #480](https://github.com/FangcunMount/qs-server/pull/480) · [infra #426](https://github.com/FangcunMount/infra/pull/426)

F05 在 IAM `7cd2b02` 的空 MySQL 8.4.13 隔离库实际通过完整迁移与 bootstrap 测试。最终 clean 45，`domain_event_outbox` 有两条 `iam.authz.version_changed.v2` pending，`rm_outbox` 为 0。下一批先为全新库的两个授权版本通知补持久替代路径及可验证通知效果，再替换当前 handoff 和 readiness 的旧表读取。升级、历史审计与其他对象的依赖仍分别验证。F06 热榜、答卷缺口、原效果、MySQL 和 Mongo 调度交接五个包的定向测试通过，作为替代路径的改动基线。

IAM 测试夹具 `a416f59dae78c8b3b28350d1690a5a10e7c395df` 在空 MySQL 8.4.13 上复用 33 和 35 的原业务事务，将完整 SDK 消息写入隔离暂存表。迁移至 clean 45 后，两张旧表均为零行，暂存表在两个阶段各有一条，消息 ID、生产者、类型、作用域、指纹和策略版本均校验通过。故意在暂存后中止时，策略版本和暂存记录一起回滚。五份原件含增量 bundle，在 MacBook 与 ServerA 逐成员读回并 fsync。归档 8,065 字节，SHA256 `2c496638f36cefea88d6e2913895b3438420527a9c349f95d75ed801499c1185`。

夹具预先建好暂存表，当前 IAM 运行时未接入替代路径。正式方案需要在阶段 33 前建立并验证暂存结构，在原事务中固定消息身份，并记录阶段完成状态。阶段 34 依赖阶段 33 的角色模型迁移回执，启动恢复还要覆盖已越过版本 0、阶段尚未完成的情况。待原生事务 owner 可用后，验证同一消息身份的交接、重试和实际授权通知效果，再审查 handoff 与 readiness 的切换。

另在真实隔离 MySQL 8.4.13 用原 31、33、35 钩子注入六个失败，随后以新连接再次调用现有迁移器。六次均跳过剩余钩子。31 钩子前后与 33 钩子前的三个样本进入 dirty 32 或 34。33 钩子后与 35 钩子前的两个样本到达 clean 45，却都缺阶段 35 应用回执和通知，仅保留阶段 33 的一条待发送记录。35 钩子后的样本到达 clean 45，原两条通知均在。该夹具使用受控钩子报错，阶段 33 内部业务提交至继承归档之间的故障还需单独覆盖。正式续跑必须依据持久阶段证据和同一库身份，区分未提交、已提交但待归档和已完成。

IAM #174 先收口阶段 31。真实 MySQL 在回执插入前注入错误，旧实现的 `CREATE TABLE` 隐式提交使角色变更逃逸。补丁把 InnoDB 准备表 DDL 移至事务外，原授权变更和回执留在同一事务。复验时角色状态完整回滚、回执为零，重试后 SQL32 正常消费回执，再走原钩子至 clean 45，保留两个应用回执和两条待发送通知。三个定向 Go 包及文档事实门禁通过。未改历史迁移 SQL，后续仍需持久续跑和实际通知交接。[IAM #174](https://github.com/FangcunMount/iam/pull/174)

IAM 中断与回滚原件、两个源码分支 bundle 和集中采集范围查询共 21 份，归档 19,031 字节，SHA256 `a37eb0e4eae2359bffa1276711883999704eaac5411aed2ab7cff101e116f526`，两地逐成员读回并 fsync。

IAM #175 在 #174 上继续验证阶段 33 的内部中断点。隔离 MySQL 在业务提交后、继承归档插入前注入失败，原角色应用回执和一条待发送通知已经持久化。补丁在策略版本行锁内读取原回执，续跑交由现有归档验证。授权状态漂移时拒绝；恢复到回执对应状态后，仅补原归档。两次重试均保持策略版本、原事件 ID 和正文 SHA，SQL34 正常继续。阶段 35 的既有重复调用同场通过，最终 clean 35，两条待发送通知和两份阶段事实均保留。三个定向 Go 包和文档事实门禁通过。接下来仍需将这些钩子接入有持久身份和阶段记录的冷启动续跑，并验证实际通知投递。[IAM #175](https://github.com/FangcunMount/iam/pull/175)

阶段 33 修复前后、定向测试、文档事实及源码 bundle 共 10 份，归档 9,547 字节，SHA256 `563526ecfb9fa4027bb17fdf4ca9c92773f7bfc5fd9b805d32b5328eeb7af79b`，两地逐成员读回并 fsync。

IAM #174 的 9 项检查通过，#175 精确源码 CI 的 7 项通过。隔离夹具 `8f739640` 将空库身份和阶段进度持久化，阶段 31 的回执和进度同事务提交。真实 MySQL 的六个原钩子前后中断点均以新连接恢复到 clean 45，原两条旧通知完整。组合夹具 `362f3a23b30db5fa5eb25a73901de2befb4152f5` 改由原业务事务暂存完整 SDK 消息，再覆盖同一六个中断点。每次恢复后两张旧发布表均为零行，阶段 33 和 35 各一条规范消息，已提交的 ID、原始输入字节、指纹和对应策略版本一致。并发第二启动、错误身份、非空未认领库和 dirty ledger 均拒绝。阶段 31 的夹具使用 GORM 回调接入原 SQL 事务。正式入口仍需将进度提交接入原事务，验证迁移入口互斥及锁会话中断，并完成实际 Broker 投递与授权通知效果。[IAM #175 源码 CI](https://github.com/FangcunMount/iam/actions/runs/42639252215)

冷启动续跑、规范消息组合验证、源码 bundle 和 W00 分层探测共 21 份原件，归档 16,183 字节，SHA256 `59e52ec073417f369a5c4d49f2ed9ee736c37b7d8914609a6663d6acef1c8866`，两地逐成员读回并 fsync。

隔离夹具 `bc86686e7c2ee1b78eeb645e52b10fbff935c718` 复用既有 `schema_migrations` MySQL advisory lock，把持锁、迁移驱动、GORM 钩子和阶段记录绑定到同一个物理连接。持锁期间，另一会话的原 `RunTo` 在原锁处拒绝。六个钩子前后真实 `KILL CONNECTION` 用例中，旧会话均未跨过当前 schema 阶段，新会话由原阶段记录恢复至 clean 45，原已提交的消息字节保持一致。六个受控报错用例及身份、非空未认领库和 dirty ledger 的拒绝用例同时复验通过。正式迁移入口尚未接入。正式实现需保留未认领已有库的升级路径，并明确首个身份记录创建中断时的只读判定和重试边界。Broker 投递与通知效果仍需独立实跑。

同会话验证的报告、日志、源码增量 bundle 等 5 份原件归档为 8,553 字节，SHA256 `57ccf20d4e36b3aec424b31f3d1e78e4bbfcd95c03afb2ee9814cd614f2cc7e8`，两地逐成员读回并 fsync。

IAM #176 精确候选 `315524293d16500a31536dd9325923700db45ead` 将同会话方案接入启动迁移入口。新空库在原锁下用一条 InnoDB `CREATE TABLE ... SELECT` 写入首个认领记录，保存实际库名与服务器 UUID。普通 `Run` 和 `RunTo` 拒绝越过未完成的认领，未认领已有版本沿原升级。阶段 31 与原事务共同记录进度，33 和 35 复用原回执。RocketMQ 事务启动的禁用 DDL 策略和已发布 SQL 字节保留。当前候选仍使用原通知写入路径。[IAM #176](https://github.com/FangcunMount/iam/pull/176) · [MySQL 原子 DDL 说明](https://dev.mysql.com/doc/refman/8.0/en/atomic-ddl.html)

MySQL 8.4.13 与 8.0.36 各通过九个进程迁移入口用例。覆盖首次认领后和 31、33、35 钩子前后的七个中断点，拒绝错位服务器身份和普通迁移跳过，另实测阶段 35 提交后真断连及未认领已有库升级。续跑至 clean 45 后原通知 ID 和正文摘要保持一致。五个定向 Go 包和文档事实检查通过。原件含源码 bundle，共 16 份，归档 22,246 字节，SHA256 `e44213e830e147d127db5c5a82943ecfe4cfe6c8fdc5a8eaee963b4701536dce`，两地逐成员读回并 fsync。完整 Broker 投递与授权通知验收继续独立推进。

F07 原工作流处于禁用状态。隔离分支以 `a5cc2c9` 为固定历史夹具，首轮 checkout 缺少比较所需 Git 对象，在夹具启动前失败。补齐后原生复现为 **22 通过、1 失败、0 跳过**，两种原存储已实际完成恢复，原生清理检查通过。末项失败位于历史 QS `9301bf8` 的 `owner_runtime_native_integration_test.go:735`。夹具以暂停准入启动替换 owner，断言却要求 `Stats.Ready=true`，而固定源码把该字段与写入准入取交集。历史报告和日志已两地保全，归档 SHA256 `b2f09de5c38a6fc8d2d056d192436267e8e11ff8bd61dac92101495b6bfe2385`。[F07 失败复现](https://github.com/FangcunMount/infra/actions/runs/42628757978)

历史 QS 夹具 `aa6d2f0` 只修改该断言。第二轮宿主子测试正常退出，7 项通过，0 失败、0 跳过、0 race 报告。两种原存储均记录具名解除和一次实际 SDK 提交确认，业务、请求、执行和见证各保留 1 条。暂停替换 owner 正常排空。整轮仍为 **22 通过、1 失败、0 跳过**，未签发独立清理复核结果。报告、运行元数据、日志 ZIP 和保全脚本在两地逐成员读回并 fsync，归档 56,834 字节，SHA256 `93e52c00471c652dbfcc4e79bdf91f86e5343e2beeb7129747c35d064cbaf59b`。[F07 第二轮原生报告](https://github.com/FangcunMount/infra/actions/runs/42631372602)

第二轮末段的 Mongo 清理复核表达式多一个右括号，原表达式通过 `node --check` 复现语法错误。隔离派发 `7f281b9d8e935620f8e80a5a71edfdbaf80675d1` 移除该括号并加语法预检，原 9 项夹具测试通过。第三轮 **23 通过、0 失败、0 跳过**，两种原存储各完成一次具名解除及 SDK 提交确认，业务、请求、执行和见证各保留 1 条。观察器退出、暂停替换 owner 排空、两库删除、源码洁净、Broker 参数恢复和隔离容器／网络／目录清理均通过。报告、元数据、日志 ZIP 和保全脚本两地读回并 fsync，归档 59,761 字节，SHA256 `b46f459c15f5de1aeadf6aceb3d16378f2054806dfa580cced101a0d7638bdb8`。证据范围为固定历史 QS 夹具，当前稳定 SDK、AI 原根和生产执行待独立验证。[F07 第三轮原生重验](https://github.com/FangcunMount/infra/actions/runs/42633443737)

并行源代码和隔离原件另有 10 份、11,334 字节，SHA256 `4871bf543d95a965f730d4994dc4a640045c67138fff9bbaf4edc67a83285410`。MacBook／ServerA 两地逐成员回读和 fsync 通过。

F07 的 AI 原生测试入口已经核对。历史 `native_limit` 配置固定 Python SDK `0.4.0a4`，AI `c635` 使用 `0.5.0`。AI 现有隔离用例验证 SQLAlchemy 原库原生拒绝及重开保护，具名解除和业务根读回还需同一原根的实跑。R03 用独立 Go 模块文件将恢复工具临时指向稳定 SDK `v0.6.1`，13 个 Go 包编译通过，279 项普通测试全部通过。测试报告 SHA256 `5d19a82e6e8b8192f409f738fcbba87a34926296e508b4f83edc8caa00ddcd4e`。后续还需验证执行器版本绑定、R01/R02 原生故障矩阵和正式制品。

## F05 冷启动通知投递复验

IAM #176 精确提交 `315524293d16500a31536dd9325923700db45ead` 的 7 个 CI 任务全部成功，PR 仍为草稿。[精确源码 CI](https://github.com/FangcunMount/iam/actions/runs/42642989106)

独立测试提交 `38dfdb5aff914f4a0535b1b46da54d83c7524d4e` 在隔离 MySQL 8.4.13 和 RocketMQ 5.5.1 实跑。夹具复用 #176 的迁移入口，在原 33 和 35 业务事务内保存完整通知。新库到达 clean 45，两张旧表保持零行。夹具随后通过稳定 SDK `v0.6.1` 发送，独立投递事务锁读原暂存字节，并一起提交投递状态和事务见证。两条通知均获 Broker 提交确认和消费 ACK，消费者核对了原消息 ID、正文和完整冻结报文。阶段 33 的版本 3 通知幂等确认，阶段 35 的版本 4 通知将真实 MySQL 支撑的接收端授权快照从 3 更新至 4。两份原请求、执行及见证均保留。

阶段 33 在 Sender 重启后重试同一请求，读回原冻结计划且未取得第二份发送能力。同键不同输入被拒绝。稳定 SDK 将该冲突计为存储错误并暂时关闭准入，随后由既有健康检查重新开放，夹具显式等待恢复。阶段 35 在 SQL 实际提交后由测试回调报告结果未知，SDK 从持久见证读回已提交事实并完成 Broker 确认与消费 ACK。模拟范围为宿主回调丢失提交结果。首轮保留了 Proxy 宣告端口与宿主映射不一致造成的路由超时，后续各轮已对齐端口。固定路由、两套隔离权限与 TLS 身份回读通过，各轮自有夹具已清理，既有容器、网络和卷清单未变。

四轮原件和源码增量 bundle 共 19 份，归档 22,070 字节，SHA256 `31456808e5260ae437ad26a793708419b44324aeef14f8164e4da35b150c96a0`。MacBook 和 ServerA 两地逐成员回读并 fsync。上述投递事务和暂存接线属于测试夹具。正式接线仍需在现有 `TransactionEventing` 生命周期内验证启动、重复启动、排空和重启，并保留 `checkTransactionHandoff` 对旧表未交接待办的拒绝语义。未认领已有库升级、旧表 readiness／责任审计替代和各对象退役继续独立验收。

IAM #177 草稿 `73df599562baaad09c0e3fe9c7b5070952b60dbb` 在新库认领中固定通知路径。事务路径在原迁移锁下准备 `iam_bootstrap_policy_notification`，阶段 33 和 35 各把完整 SDK 输入和指纹写入原授权事务。进度签收前读回原行，续跑复核已签收的阶段。迁移开始后缺表拒绝重建，现有库继续走原升级，默认启动仍使用原路径。MySQL 8.4.13 和 8.0.36 各通过 12 个隔离子用例，含两个阶段提交后中断的续跑、路径不匹配、原字节漂移、缺表和未认领已有库拒绝。定向 Go 测试与文档事实门禁通过。[IAM #177](https://github.com/FangcunMount/iam/pull/177) · [精确源码 CI](https://github.com/FangcunMount/iam/actions/runs/42646737085)

隔离测试提交 `e7ae654c3f27f4febb2d7fac1921d7afab060be2` 直接使用 #177 的迁移入口及原始通知表，复验 RocketMQ 5.5.1 投递。两条原通知均获 Broker 提交确认和消费 ACK，阶段 35 再次将授权快照从 3 更新至 4。阶段 33 的 Sender 重启后重复保留、阶段 35 的回调结果未知同场通过。投递仍由测试夹具驱动。15 份原件及源码增量 bundle 归档 25,633 字节，SHA256 `9aa7da26b7d09c30e7c5fcf1e3dab2fa72f0d4e83d6f301d4a4294bbe991f951`，两地逐成员回读并 fsync。

后续正式接线需区分三类旧执行。SDK 对同键重复保留只读回原执行。未决执行须保留给原 Checker 判定，不能从暂存行的未投递标记推断可以重发。确认为 Aborted 且原暂存事实未提交时，才可由宿主依据原冻结计划显式批准 SDK `Retry`，原 fence 和凭证保留。已有本地提交见证时继续确认 Broker 收口，业务 ACK 仍独立取证。需实测预留后进程中断、半消息未决、提交后重启和排空，再开放事务暂存入口。

IAM #177 的精确源码 CI 已完成，7 个任务全通过，原始日志 ZIP CRC 通过。基于 #177 的 #178 草稿接入正式事务 owner。旧表待办仍在启动前阻断。具名新库认领和两条原通知在启动前只读校验，交接沿用现有 Sender、Checker 和原主库。只有精确执行已由持久见证确认回滚，才可沿原计划重试，最多自动增加两个 fence。交接标记、主库协议选择的共享锁和 SDK 提交见证处于同一个 SQL 根。就绪等待两条本地交接证明，Broker 提交和消费 ACK 独立记录。[IAM #178](https://github.com/FangcunMount/iam/pull/178) · [精确源码 CI](https://github.com/FangcunMount/iam/actions/runs/42648960894)

隔离 MySQL 8.4.13 和 RocketMQ 5.5.1 实跑了 #178 的正式 owner，精确提交 `259643ccdec9be0f2177eed1cf72a42f88c5f5ce`。旧表有待办时启动拒绝。夹具模拟预留后进程中断，未决期间无新发送，替换 owner 保留 Checker。原 fence 1 确认回滚后，阶段 33 用原计划在 fence 2 投递，阶段 35 在 fence 1 投递。阶段 35 的本地 SQL 根等待原通知行锁时，150 毫秒停机返回未排空。释放隔离锁后同一根正常提交，再次停机通过。两条消息均取得 Broker 提交和消费 ACK，原 ID、正文及报文字节一致，授权快照升至 4。完成后重启只验证原见证，两个请求、三个执行及三个见证均保留，两个提交凭证为 `commit_confirmed`。

两轮原生、#177 CI 原件和源码增量 bundle 共 15 份，归档 563,580 字节，SHA256 `f8c275c31e032b24ada4b2e854b36cc9f8a6d2856402cea52a43fb7ca3ed3c41`，两地逐成员回读并 fsync。实际新库离线入口、部署权限和运行制品仍待接入及隔离验收。半消息到达后物理进程中断、Broker 最终结果未知的实测仍单独留项。IAM 和 AI 生产本轮未停写或改库。

### 2026-11-10 IAM 离线新库入口

IAM #178 精确源码 CI 已完成，7 个任务全部通过，原始日志 ZIP CRC 通过。#179 草稿新增 `iam-maintenance fresh-transaction-bootstrap`。库名与 MySQL 服务器 UUID 在同一个原迁移锁会话内复核，入口要求 VERIFY_IDENTITY，并在认领和迁移元数据写入前检查直接权限及库内已有对象。新库运行配置可要求具名原认领。安装事务绑定及协议选择继续走独立受核步骤。[IAM #179](https://github.com/FangcunMount/iam/pull/179) · [精确源码 CI](https://github.com/FangcunMount/iam/actions/runs/42650665569)

第一组隔离权限试验在历史迁移 19 因缺 `CREATE TEMPORARY TABLES` 被 MySQL 拒绝，原库位点为 dirty 19，失败原件保留。补齐认领前权限检查后，精确源码 `dccb397811b1737c2472ff41a805ee449dbad089` 的同一离线命令在 MySQL 8.4.13 和 8.0.36 各通过 10 项。隔离账号的权限限于具名库且无 GRANT OPTION，服务端要求 TLS。错库、错 UUID、缺确认、禁用 TLS、只有例程的非空库、元数据不可见、缺临时表权限和无库权限均拒绝。两个成功路径到达 clean 45，重复调用保持两个原通知的 ID、原字节和指纹。旧表、事务绑定及请求保持零行，相邻库保留原行。

同一源码的正式 owner 隔离 Broker 复验通过。要求新库认领时，两张认领材料缺席会在启动前拒绝。两条原通知的实际投递、消费 ACK、预留后重启和行锁排空复验仍成立。命令与 owner 分别实跑，使用受核运行镜像、实际账号和部署封装的全链路验收仍待完成。34 份原件及源码增量 bundle 归档 569,297 字节，SHA256 `472c14d0e9e63a8f37663d3d0c3446fa2846685a8fb276fb35469b60e60b0294`，MacBook 和 ServerA 逐成员回读并 fsync。本批归档还包含 W00 只读集中采集复验。

### 2026-11-10 IAM 离线命令与实际进程串联

IAM #179 精确提交 `dccb397811b1737c2472ff41a805ee449dbad089` 的 7 个 CI 任务通过，原始日志 ZIP CRC 通过。两轮隔离串联从相同提交构建本机维护命令与完整 `iam-apiserver`。二进制 SHA256 分别为 `6fce447dabdff756ff2d44411fff3608d7190e98e59e39f4f81a9098127c5497` 和 `11bd5ef626c0f3b6253941619b8a19445f2a0e3548400bc90e0e5e937c4ec254`。[IAM #179](https://github.com/FangcunMount/iam/pull/179) · [精确源码 CI](https://github.com/FangcunMount/iam/actions/runs/42650665569)

同一个空 MySQL 8.4.13 库经实际离线命令和 VERIFY_IDENTITY 到达 clean 45，两个原通知为待交接，原两张旧表、绑定和请求均无行。独立隔离步骤提交并回读原生绑定和协议选择。运行进程使用同库 DML 权限账号、显式认领检查、关闭自动迁移、独立 Redis 和 RocketMQ 5.5.1。两轮的第一次正常启动和重启均取得真实 HTTP `/readyz=200`，9 项就绪检查通过，SIGTERM 退出码均为 0。阶段 33 和 35 原 ID、输入字节及指纹保持一致，两份见证记录 `commit_confirmed`，实际 IAM 消费组发送和消费位点均为 2，积压为 0。正常轮重启保持两个执行，故障轮保持三个执行。

故障轮在阶段 33 持有通知行锁，实读 Broker 半消息已确认后对自有进程发出 SIGKILL。原 fence 1 见证仍为 prepared，交接标记为 0。释放隔离锁后，替换进程由 SDK 见证确认原执行本地回滚，沿原冻结请求进入 fence 2。原半消息回执与本地回滚见证保留，最终两条业务通知的消费位点为 2。该轮没有采集原半消息的 Broker 最终回滚确认。提交后 Broker 最终结果未知的真实故障，以及部署镜像、实际运行账号与生产授权，分别待独立复验。

初次构建命令参数顺序错误，修正后两轮源码及二进制摘要一致。夹具只使用本地回环，资源清理与原容器、卷和网络清单复验通过。25 份 CI、脚本及运行证据归档 598,028 字节，SHA256 `e1e9021b9c70572bd35fec7893746cfeecb40ab6ee63ed7c5f302172e6f6a169`。MacBook 和 ServerA 逐成员回读并 fsync。双地运行日志移除了配置和凭据相关行，本机私有原件及原字节摘要保留。

### 2026-11-10 F06 MySQL 第一批兼容读取

QS #482 的源码 `e4eeb8146081c616036619a98df5ae233c6a4847` 接入固定 `qs_rm_outbox_history` 视图。测评正向原证据、反向审计的上界及分页、原请求只读检查与原效果捕获可从视图读原消息。视图尚未安装时仍读取原表。视图损坏、查询错误或同名实体表拒绝。原请求写入授权继续在它已锁定的原 `rm_outbox` 上重复验证，未接入视图。文档提交 `53c5fe9d96129325825b36884838b8ed2acbf4e5` 固定源码基线，未改变签收状态。[QS #482](https://github.com/FangcunMount/qs-server/pull/482) · [精确提交 CI](https://github.com/FangcunMount/qs-server/actions/runs/42654169630)

MySQL 8.4.13 和 8.0.36 各通过两个原生用例。在自有库复制原行并改名保留原表，逐列回读存档行，正向分类、反向分页上界、孤儿冲突及原重试权威摘要一致。损坏视图在原表可用时也拒绝，同名实体表拒绝。篡改存档报文后原效果捕获拒绝，原表字节保持原样。三组定向 Go 测试和文档门禁通过。12 份原件及源码增量 bundle 归档 14,313 字节，SHA256 `fba57a6cfb213cb9fcd40d1008173fa5ea362edab7fa058889cda5201fb3fffd`，两地逐成员回读并 fsync。

实际存档仍需具名数据库与账号、写者排除、同窗逐列及成员核对、原始发布确认和两地保护。兼容视图定义和账号读取权限须单独签收。缺口列表、治理状态、replay、提醒恢复与调度交接仍有原表依赖，MySQL 物理对象及 Mongo 对象均待独立退役审查。

### 2026-11-10 F06 MySQL 治理与调度存档

QS #482 的治理状态、恢复摘要与候选列表优先读取现库物理表。原表退役后，历史视图只有在无待发送状态、已发布行具备确认、held 行具备匹配的原调度身份与计划摘要时才能支撑运行状态。原表缺失时，现库交接盘点继续拒绝。显式 `--inventory --history` 核对存档和目标冻结计划，使用独立回执与状态，`cutover_authorized=false`。未选择的 held 仍计为未核验。原 replay、恢复及调度交接的写入留在原物理路径。[QS #482](https://github.com/FangcunMount/qs-server/pull/482) · [当前 PR CI](https://github.com/FangcunMount/qs-server/actions/runs/42656173725)

隔离 MySQL 8.4.13 和 8.0.36 各通过三项原生用例，含精确源码编译的真实交接 CLI、原表在场优先、存档 held 配对、缺物理原表拒绝、未结存档和伪造持有标记拒绝。最终文档绑定提交 `26f288d9f114a6ba188d4281418d76f963b3d91b` 的 Go 实现与原生验证提交 `bcc0dbdbc15be006d5855fa48d5443c01b167503` 一致。定向测试、文档门禁和本地 PR 范围 lint 通过。较早手动 CI 的 lint 报告保留，本批 GORM 选择器已修正，另五项报告位于与 main 一致的文件。[较早 CI](https://github.com/FangcunMount/qs-server/actions/runs/42654169630)

本批 W00 与 F06 原件及源码增量 bundle 共 43 份，归档 58,033 字节，SHA256 `7e622581ed58ba9b14d35f95fe5828dc5806d639a7e80994fb69ec7402c55aa9`，两地逐成员回读并 fsync。W00 仍需窗口前复验，账户接受、具名窗口授权和当次 W06 批准仍待签收。生产存档实读和写路径切换继续单列，现有业务、历史、ACK、调度和 Broker 待办保留。

### 2026-11-10 F06 Mongo 历史兼容读取

QS #483 草稿精确提交 `5b1d720b546c6dce16976426afc1d7cbef2c604e`。v1 答卷缺口及原效果、混合日热榜、标准历史审计共用同一规则。物理 `rm_outbox` 在场时继续读取原集合，单行缺失按原路径报告；仅原集合缺席时读取固定 `qs_rm_outbox_history`。读前后向主节点查询集合 UUID，身份变化拒绝。本规则在 Mongo 事务外读集合元数据，业务及报文查询保留原快照边界。v2 事务见证继续走原查询。[QS #483](https://github.com/FangcunMount/qs-server/pull/483) · [精确提交 CI](https://github.com/FangcunMount/qs-server/actions/runs/42657861327)

相同最终提交在自有 MongoDB 7.0.37 副本集和 MySQL 8.4.13 通过 22 个定向用例。隔离复制后以改名保留原集合，验证 v1 原报文和冻结证据、混合日完整摘要、反向 BSON 分页和孤儿冲突均一致。原集合在场时缺行不补读，存档缺行、报文篡改、集合同名 UUID 变化和原集合重新出现时拒绝。定向 lint 与文档门禁通过。两轮原件和增量 bundle 共 11 份，归档 28,670 字节，SHA256 `39683162a52fb7f67ec44a3ba41394a4c5b67328bbe0e79a4ef020d0d9292618`，MacBook 和 ServerA 逐成员读回并完成持久化校验。

Mongo 生产存档仍需独立核对原 BSON 身份、报文字节、发布确认和现库两地保护。实际账号需复验数据库级 `listCollections` 及集合读权限。写者排除、治理重放、调度交接及物理集合退役另审。AI 发布冻结和 W00/W06 签收门槛继续生效。

### 2026-11-10 F06 Mongo 调度存档盘点与 MySQL CI

QS #483 的 `66c7f9d40c2bd5fda546f96aad5b5fc9778b1278` 新增 Mongo `--inventory --history`。使用固定存档、独立回执和 `cutover_authorized=false`。主节点在快照前后校验存档 UUID，同一快照核对原复合 BSON 身份、消息和目标冻结计划。未选择的 held 仍计为未核验。原物理集合缺席时普通盘点拒绝，存档存在时也不会借用；存档缺席时历史盘点同样拒绝。原写入、重放和调度交接保持原入口。[QS #483](https://github.com/FangcunMount/qs-server/pull/483) · [新提交 CI](https://github.com/FangcunMount/qs-server/actions/runs/42658884432)

隔离 MongoDB 7.0.37 副本集及 MySQL 8.4.13 的 23 个定向用例通过。实际编译的维护 CLI SHA256 为 `1827ce3e0aec4408e4a3ee1603ea66cdccb6f0a16ac1284db9ddc672379f9525`。原集合在场和暂时改名两种情况下，真实命令均能按显式存档核对已审核的 held 计划，保留原 BSON 字节；伪造 held 标记或替换复合 BSON 身份时拒绝。文档门禁、定向 lint 及普通 Go 测试通过。现库实读、实际账号权限、生产存档和治理／重放仍待验。#482 与 #483 的共享 CLI 在合并预演中存在冲突，联合源码还需同时验证两种存档模式和原命令。

QS MySQL #482 精确提交 `26f288d9f114a6ba188d4281418d76f963b3d91b` 的四个 PR 工作流均成功，检查共 29 项通过、1 项按条件跳过。主 CI 日志 ZIP 完整性通过。[QS #482](https://github.com/FangcunMount/qs-server/pull/482) · [主 CI](https://github.com/FangcunMount/qs-server/actions/runs/42656173725)

本批 25 份 Mongo 调度、MySQL CI 及 W00 原件含增量 bundle，归档 1,717,496 字节，SHA256 `95721248100cb70b7a5dbd22c918050d84cfe262ed772dd74a332fc1fc056958`，MacBook 和 ServerA 逐成员读回并完成持久化校验。

### 2026-11-10 F06 两种存档盘点联合验证

联合草稿 QS #484 精确提交 `934b02472f0d445f184a95eb54a6050e0f580f9c` 处理了 #482 与 #483 在共享命令上的合并冲突。仍按原 owner 选择 MySQL 固定视图或 Mongo 固定集合，保持各自回执 schema。普通现库盘点要求对应物理对象。存档回执保持 `cutover_authorized=false`。分对象草稿和签收边界保留。[联合草稿 #484](https://github.com/FangcunMount/qs-server/pull/484)

同一个 CLI 制品 SHA256 为 `83806e1061f54a99ab7be9855ac929cc5b17767498c4652e65eac0c473556f52`。MySQL 8.0.36、8.4.13 各通过 3 项，MongoDB 7.0.37 副本集通过 23 项，含原现库盘点、原交接与重试、两种显式存档读取和原物理对象缺席时拒绝。文档门禁与定向 lint 通过。生产账号、实际存档和物理退役仍按对象分别审查。Mongo 治理与重放仍待收口。

同批 W00 集中采集和两轮直读均通过，六个 QS 实例及原 AI 容器身份与前次一致。34 份原件和源码增量 bundle 共 29,939 字节，归档 SHA256 `28878993beb42139b1e4d2fc222cbb8f3afdb34e0d2e11400ca6a2665caf3aee`，MacBook 与 ServerA 逐成员回读并完成持久化校验。实际窗口、账户权限接受和独立执行批准仍待签收。

### 2026-11-10 F06 解释重试历史审计与原效果读取

QS #484 精确提交 `8a58d096409e5a6a74591d58bc5e67d0b5bb39a4` 接入解释重试的审计和恢复 inspect。原集合在场时仍读取原集合，缺一行仍作为缺证据。只在原集合缺席时使用固定存档，并前后核对 UUID。审计要求存档具有以 `message_id` 开头的索引。恢复 inspect 在同一快照核对 Run、Generation、后继缺席、原 BSON 身份、报文、指纹及发布确认。历史 NSQ apply 始终要求物理原集合，只有存档时在写入恢复日志前拒绝。[QS #484](https://github.com/FangcunMount/qs-server/pull/484) · [精确提交 CI](https://github.com/FangcunMount/qs-server/actions/runs/42660636437)

MongoDB 7.0.37 副本集 3 个原生用例通过，验证存档前后分类、原报文和恢复指纹一致，以及原集合缺行、无存档索引、存档篡改和两源缺失的拒绝。普通 Go 测试、文档事实门禁、定向 lint 和三个生产入口依赖图通过。8 份原件及增量 bundle 共 24,292 字节，SHA256 `c62d0662f0ee018ad38fbbc59c29f23f84823d85728554ca3bec5a5ce7c64412`，MacBook 与 ServerA 逐成员读回并完成持久化校验。

实际生产三个命令的依赖图不含旧 Mongo `standardoutbox` 治理与重放包，生产子系统的 `Outboxes()` 返回空。生产解释事务仍含历史 v1 future intent 的 Outbox append 分支。当前失败构造器生成 v2；成功构造器无 future intent；执行分支仍要求取得 reservation，且冻结 artifact 与当前输入逐字节一致。剩余门槛是按实际 owner 状态核对旧冻结计划，覆盖已提交、未决、回滚及重启的真实根验证，再审查该历史写分支退役。原冻结计划、SDK 凭证、历史报文、ACK、调度和 Broker 待办继续保留。

### 2026-11-10 F06 旧解释事务写入退役验证

QS #484 精确提交 `48573927664c5866e62fb87d7c51880b672f7dc2` 移除解释事务提交器对旧 Mongo Outbox 的 append。当前自动重试继续保存 v2 冻结调度。历史 v1 artifact、稳定业务输入、wire 和原凭证保留解析及只读恢复。即使向提交器传入已获得执行资格的 v1 future artifact，也会在进入业务事务和准备半消息前拒绝。[QS #484](https://github.com/FangcunMount/qs-server/pull/484)

MongoDB 7.0.37 隔离副本集使用真实 SDK 存储和原事务 guard。分别准备 v1 计划、在写业务与见证后回滚、提交 v1 原业务与 Outbox。后续相同业务输入保留原计划，未获取执行权。改名保留旧集合后用新客户端和实际 owner 恢复，已提交沿原业务 retry 授权继续，prepared 和已回滚状态阻断。原请求、执行凭证及存档报文字节保持，旧集合没有重建。四个定向用例、定向 lint、文档门禁通过。此轮不判定实际 Broker 最终结果或生产旧计划数量。首轮夹具遗漏终态对原 lease 字段的清除，修复为复用真实终态 CAS 后通过，首轮原件保留。

北京时间 00:36:45–01:06:45 集中采集 121 点连续通过，四个 owner 指标、具名目标数量及 35 秒新鲜度满足原口径。15 份 Mongo 实跑、集中采集原件及源码 bundle 共 15,279 字节，SHA256 `18519b21cb3176fcc94f0ec325c1f87c7dccffea1c774fad7d43bbb4811721fa`，两地逐成员读回并完成持久化校验。生产旧计划盘点、存档／账户资格和 Mongo 退役窗口仍待签收。
