# M2 完整实施规划：事务 SDK、双存储证明与固定预发布

本文维护该规划的实施、验证及里程碑/任务进度；SDK公开契约由其接入文档负责，M2-0历史证据保留在下文。

## M2 SDK 批次进度（2026-10-19）

本节为本批次唯一进度总表。批准范围为 Go/Python 独立事务 SDK、原事务 witness、Checker、有界生命周期、双存储证明及固定预发布；不包含三宿主改造或生产变更。沿用下文 M2-0 证据，新增任务独立计数。

基线：SDK `fd9c51691d785ced6e27d1ad3509fc4ac99a7b1f`；infra `44c379bedf5d37194aff1c87eccc8c8080cb3b2c`。隔离分支：SDK 协议 `codex/rocketmq-m2-sdk`、存储续批 `codex/rocketmq-m2-storage`；infra `codex/rocketmq-m2-sdk-tracking`。

进度：**21/24**。任务完成表示实现及所列验证通过；PR 合并、发布、部署独立记账。里程碑全部任务及合并门禁满足后才完成。每项任务完成立即更新本表、证据与会话；失败/阻塞保留，不删除或静默减少分母。

### 最新核验快照（2026-10-19 15:00 +08:00）

| 核验项 | 当前结果 / 证据 |
| --- | --- |
| 已完成任务 | T01–T21，21/24；M2-P至M2-5均满足任务、验证及实现PR合并门禁；T22–T24仍待完成 |
| 固定 SDK 候选 | `c02bc984f42a66da6852da2315ba7aab9e5c8610`；[PR43](https://github.com/FangcunMount/reliable-messaging/pull/43)已合并；树与已验8841fdf完全一致，两个预发布tag必须绑定此SHA |
| infra 合并 | `b90817cd347045f8738811c6693f7401be9fc8f8`；[PR27](https://github.com/FangcunMount/infra/pull/27)已合并；同时保留main中其他任务的serverA迁移及对应防火墙变更，未覆盖或回滚 |
| 真实 SDK / 故障门禁 | infra85a2a61固定SDK8841fdf：[基础31项/档](https://github.com/FangcunMount/infra/actions/runs/39210736101)、[故障46项/档](https://github.com/FangcunMount/infra/actions/runs/39210736172)、[完整48项/档](https://github.com/FangcunMount/infra/actions/runs/39210736275)双档均通过，0失败/跳过；[T19证据](evidence/rocketmq-m2-sdk-packet-faults-20261019.json)、[T20证据](evidence/rocketmq-m2-sdk-limits-20261019.json) |
| 普通消息及旧协议回归 | [完整Docker回归](https://github.com/FangcunMount/infra/actions/runs/39210736103)通过；普通消息、raw20项、公开Go19项，全部fixture资源排空 |
| T21 契约冻结 | [API评审及冻结记录](evidence/rocketmq-m2-sdk-api-review-20261019.json)；12个接口/适配/示例/正文文件摘要复核一致；schema/codec=1、路由v2、原摘要domain及63位fence冻结于本次预发布 |
| T22 精确合并SHA源码CI | [Go/race/lint](https://github.com/FangcunMount/reliable-messaging/actions/runs/39213028892)、[Python源码/wheel](https://github.com/FangcunMount/reliable-messaging/actions/runs/39213028897)、[存储证明](https://github.com/FangcunMount/reliable-messaging/actions/runs/39213028971)、[既有集成](https://github.com/FangcunMount/reliable-messaging/actions/runs/39213029020)运行中；不以合并前的通过代替 |
| T22 精确合并SHA BrokerCI | [双档48项完整验收](https://github.com/FangcunMount/infra/actions/runs/39213056193)、[完整Docker回归](https://github.com/FangcunMount/infra/actions/runs/39213060928)已显式指定c02bc98运行；自动使用旧默认8841fdf的Docker运行由该正确SHA运行替代，不计为通过证据 |
| T23–T24 / 生产 | 两tag和GitHub预发布尚未创建；下载重装待发布后单独验证；本批未改三宿主依赖或生产链路 |

下一步：完成T22的精确合并SHA全部CI和独立wheel/sdist安装，生成receipt/摘要后，执行T23固定发布及T24正式tag/下载制品重新安装验收。旧失败证据继续保留在下文和evidence中，不删除或计为通过。

补充候选核验：已下载 SDK `3bf3dc8` 的双 Python profile 制品；源码与独立 wheel 各120项通过、0失败/跳过，wheel/sdist 摘要在两档一致且绑定同一源 SHA/树。见[候选预检证据](evidence/rocketmq-m2-sdk-candidate-20261019.json)。这不是最终合并候选或已发布制品的验证，不据此完成 T22/T24。另修复 T20 审计 CLI 的变量引用及 critical 告警退出码2，并保留发布安装 JSON 附件；11项本地脚本测试通过，真实 native-limit 门禁继续待通过。

| 里程碑 | 任务 | 本批完成数 | 状态 | 完成门禁 |
| --- | --- | --- | --- | --- |
| M2-0 | 既有批次 | 不计入24项 | ✅ 已完成 | 20 项真实验证，0 跳过 |
| M2-P | T01 | 1/1 | ✅ 已完成；infra PR21 合并 6fdefde | 基线、任务及证据格式建立 |
| M2-1 | T02–T04 | 3/3 | ✅ 已完成 | 双语言契约及失败状态通过、PR 合并 |
| M2-2 | T05–T09 | 5/5 | ✅ 已完成；SDK 合并 d7d1415 | 四种原事务适配及并发证明、PR 合并 |
| M2-3 | T10–T13 | 4/4 | ✅ 已完成；SDK PR38、infra PR23 已合并 | Go 真 RPC、回查及关闭有界、PR 合并 |
| M2-4 | T14–T16 | 3/3 | ✅ 已完成；SDK PR39、infra PR23 已合并 | Python 线程/loop/取消证明、PR 合并 |
| M2-5 | T17–T20 | 4/4 | ✅ 已完成；SDK PR43、infra PR27已合并 | 正式 SDK 故障集成 required CI 非空且 0 跳过、PR 合并 |
| M2-6 | T21–T24 | 1/4 | T21契约已冻结；T22精确合并SHA验证中，T23/T24待发布及下载重装 | 固定 tag/制品及下载重装通过 |

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
| ✅ | T17 | SDK/infra v2 路由、类型、owner ACL、共享消费预算 | 2026-10-19 +08:00；SDK 3bf3dc8 / infra 910b614；[31项/档双profile门禁](https://github.com/FangcunMount/infra/actions/runs/39201819179) 通过、0跳过；[证据](evidence/rocketmq-m2-sdk-routing-e2e-20261019.json)；SDK PR43(c02bc98) / infra PR27(b90817c)已合并 |
| ✅ | T18 | 正式 SDK 跨语言/MySQL、Go/Mongo 真端到端 | 2026-10-19 +08:00；SDK 3bf3dc8 / infra 910b614；[31项/档双profile门禁](https://github.com/FangcunMount/infra/actions/runs/39201819179) 通过，原ID/首次wire、跨实例/语言及真实数据库断连恢复通过；[证据](evidence/rocketmq-m2-sdk-routing-e2e-20261019.json)；SDK PR43(c02bc98) / infra PR27(b90817c)已合并 |
| ✅ | T19 | 退出、断网、DB提交丢回复、Broker重启故障矩阵 | 2026-10-19 14:55 +08:00；SDK8841fdf / infra85a2a61；[46项/档、15项故障双档门禁](https://github.com/FangcunMount/infra/actions/runs/39210736172)通过、0跳过；[证据](evidence/rocketmq-m2-sdk-packet-faults-20261019.json)；实际精确回查、SIGKILL后完整中止、真实提交边界及进程组清理全部通过；SDK PR43(c02bc98) / infra PR27(b90817c)已合并 |
| ✅ | T20 | 资源上界、指标、超限告警与只读审计 | 2026-10-19 14:57 +08:00；SDK8841fdf / infra85a2a61；[48项/档完整门禁](https://github.com/FangcunMount/infra/actions/runs/39210736275)双档通过、0跳过；[证据](evidence/rocketmq-m2-sdk-limits-20261019.json)；真实原生超限索引、0600审计、Unknown/Prepared保留、停止新准入及进程组排空均通过；SDK PR43(c02bc98) / infra PR27(b90817c)已合并 |
| ✅ | T21 | 原事务示例、接入/恢复/关闭文档及API评审；冻结协议 | 2026-10-19 15:00 +08:00；固定SDK c02bc98；[API评审/12文件摘要/协议冻结证据](evidence/rocketmq-m2-sdk-api-review-20261019.json)；SDK PR43与infra PR27已合并，公开入口/双存储/原事务示例/有限恢复及关闭正文核对通过；发布仍待T22–T24 |
| ☐ | T22 | 固定候选 SHA、完整 CI、wheel/sdist/摘要/receipt | 分支候选 SDK 8841fdf；Go/Python 预定版本及确定性构建准备；显式 prepare_release.py 校验合并源码、CI状态、双档制品及故障报告并生成receipt；22项本地脚本测试通过；最终合并候选/完整CI/receipt待完成 |
| ☐ | T23 | 两语言 tag 同一 SHA，GitHub 固定预发布 | — |
| ☐ | T24 | 下载发布 tag/制品重新安装验收、索引与总表关闭 | infra prepare_published.py + workflow 已准备，固定 Go module、wheel/sdist 独立安装与完整验收；尚未发布或运行此门禁 |


本次 T11–T16 的公开 SDK 验收为 23/23、0 跳过；之后仅追加单次半消息 RPC 及回调诊断修复，已通过对应实际 TLS/编排测试和最新源码 CI。SDK Go/Python PR38/39 均已合并。infra 完整工作流曾因旧 SDK 固定引用与新增三分支探针不匹配失败；已统一固定到 SDK main `65eae5b`，精确 SHA 重跑 [公开 SDK 23 项](https://github.com/FangcunMount/infra/actions/runs/39194664066) 与[完整 Docker/普通消息/M2-0 回归](https://github.com/FangcunMount/infra/actions/runs/39194664076) 均通过，infra PR23 已合并 4b7ed57，M2-3/M2-4 里程碑关闭。原失败运行 [39193222448](https://github.com/FangcunMount/infra/actions/runs/39193222448) 保留，不作通过证据。

剩余实现统一汇总到 SDK PR43 / infra PR27；旧 SDK PR40–42、infra PR24–26 关闭为被汇总，源码与失败运行保留，任务总数仍为24。当前分支候选 SDK `8841fdfcdd9ec25b49f845a3ed3eb825385d0c32`；T17/T18已验证源码为 `3bf3dc8`。后续候选调整Mongo故障宿主提交预算，补充部分准备后真实SIGKILL及启动/进程排空证据；当前48项门禁、合并及固定发布尚未完成，不视为最终发布SHA。

T17 失败记录：[39197245044](https://github.com/FangcunMount/infra/actions/runs/39197245044) 暴露整体 provision 等待预算不足；[39198164925](https://github.com/FangcunMount/infra/actions/runs/39198164925) 创建后配置回读拒绝，定位为固定5.5.1 `updateSubGroup -q` 才是 retry queue 数，`-r` 为 retryMaxTimes。仅修正新 v2 入口，不改变生产 v1。后续汇总候选重跑保留类型/配置冲突拒绝及幂等回读。

最低 Go race 的旧运行 [39198554820](https://github.com/FangcunMount/reliable-messaging/actions/runs/39198554820) 发现 observer=nil 时上游1秒休眠不响应关闭；已修正、10次真实 TLS/race 回归通过、私有补丁及38文件摘要复现通过，SDK `342c94b` 全部源码/存储/Python门禁通过。该修正包含于汇总候选，旧失败不计通过。

[39199909523](https://github.com/FangcunMount/infra/actions/runs/39199909523) 通过 v2 资源/幂等回读及23项公开SDK正向场景，共27项后，在错误owner负向诊断处失败；报告确认 Compose 容器与私有fixture目录均已清理。根因为 Go 上游 startup 格式化丢失 error cause，及 Python 上游 route callback 吞掉原始状态；新候选保留结构化 RocketMQ/gRPC 拒绝错误，未将普通超时/Unavailable计作拒绝。实际TLS受控状态保留及Python真实manager实例隔离测试通过，完整Broker门禁重跑并以 SDK 3bf3dc8 双档31项通过。拒绝错误门禁提前到正向长测试之前；原失败保留，完成数以最新总表为准。

T19 失败记录：[包级故障39201819131](https://github.com/FangcunMount/infra/actions/runs/39201819131) 及[完整矩阵39201819090](https://github.com/FangcunMount/infra/actions/runs/39201819090) 在33项通过后，Mongo提交前TCP断连等待120秒超时；实际代理已截获原事务提交包，业务结果尚不能从超时判定。失败profile清理容器和私有目录成功。核对固定Mongo Go1.17.6源码，其WithTransaction未知提交循环使用background commit context及120秒重试窗口；仅给外层ctx加deadline不能约束该循环。新探针在故障场景由宿主显式StartTransaction/同session业务+witness/带10秒预算CommitTransaction，继续按精确持久化证据判定结果，常规callback重入验证保留。编译及49篇文档检查通过；真实重验前T19/T20继续未完成。

补充故障门禁（本次任务总数仍24项）：原[46项完整矩阵](https://github.com/FangcunMount/infra/actions/runs/39203750293)双档0失败/跳过，包含真实Mongo提交前后网络故障及Go/Python各原生超限索引。另一个[44项运行](https://github.com/FangcunMount/infra/actions/runs/39203750280)在一档完成44项，另一档42项后新Go/Mongo实例Start返回结构化TOPIC_NOT_FOUND(40402)；TCP健康不代表全部Topic真实路由就绪。新增仅重建已完全排空的空闲Checker、最多6次/100秒准入窗口的40402启动等待，40300等鉴权错误不重试，不Reserve或重做业务，保留各次真实回查计数。另补Go/Python部分半消息后SIGKILL共2项，故障从13增15项，完整验收从46增48项。实测uv启动器PID与生产者子PID不同；fixture改为独立session/process group，SIGKILL与失败清理均覆盖整组，并以stdout EOF证明子进程排空。两项真实父子进程测试及严格启动/发布门禁等共22项本地脚本测试通过；SDK ACK屏障真实TLS/race重复10次及lint通过；这些不替代48项真实依赖验收。

精确回查门禁修正：[39206054502](https://github.com/FangcunMount/infra/actions/runs/39206054502) 的新增部分准备/SIGKILL场景在39项通过后失败：全局Rollback计数可能来自旧消息，不能证明当前execution已中止。旧进程组已真实退出，失败报告确认容器、私有目录及全部fixture进程组均排空。SDK 8841fdf仅在恢复探针中通过公共PreparedStore/Evidence接口透明观察真实读取，原样返回原证据/错误，不额外查库、不确认Broker；验收按当前原消息ID匹配Reference及其决定，并分别核对execution/全部witness和真实消费可见性。包括基础跨语言恢复、DB不可用、部分ACK丢失、SIGKILL、重启及原生Unknown的全部公开SDK回查场景统一采用该判据，旧全局指标仅作诊断。22项本地脚本（含排除旧Reference/全局计数误判）及探针编译、lint/格式/49篇文档检查通过；48项真实门禁待重验，T19/T20不打勾。

同一48项旧运行的另一档在45项通过后，Python/MySQL重启恢复的6次1秒间隔启动均返回40402而失败，资源清理通过；未将其计通过。保留最多6次/100秒准入窗口，将空闲启动尝试间隔扩至最多15秒，覆盖重启后的注册/路由恢复；仍只接受明确40402且前一实例已经完全排空，其他错误立即失败，业务不重做。

半消息丢ACK判据修正：[39208349317](https://github.com/FangcunMount/infra/actions/runs/39208349317)及[39208349372](https://github.com/FangcunMount/infra/actions/runs/39208349372)均在双档各37项通过后失败；原判据等待b0/b1同时真实回查，但结果证明b0已收到真实Rollback ACK、仅b1仍需新实例精确回查，b2从未发送。本地业务0次、三个阶段均保留、全部fixture资源清理完成。已改为严格校验三分支阶段，排除已有RollbackConfirmed的分支，仅等待实际未决半消息的精确回查，并额外核对execution及全部3个witness为Aborted；SIGKILL场景仍要求两个已准备分支全部回查。25项本地脚本通过，真实48项新门禁待重验，进度仍18/24。见[失败与修正证据](evidence/rocketmq-m2-sdk-half-rollback-oracle-20261019.json)。

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

## M2-0 历史交付状态（2026-10-19）

本节记录 M2-0/早期协议交付当时的状态，供追溯；其中“尚未实现/未发布”不是后续SDK批次的当前判断。当前任务与合并/发布状态以本文开头的进度总表为准。

M2-0 [完整CI](https://github.com/FangcunMount/infra/actions/runs/39184548857)通过：20项真实验证成功、0失败、0跳过。签名构建、普通消息回归、事务验证及镜像导出均成功。[结构化证据](evidence/rocketmq-m2-20261019.json)记录固定版本、有效参数和逐探针事件。测试中的RPC运行时/探针文件与SDK PR33最新head逐文件SHA256一致；后者只比验收引用多出源码复现检查。

- [infra PR20](https://github.com/FangcunMount/infra/pull/20)：隔离Docker验收与记录。
- [SDK PR33](https://github.com/FangcunMount/reliable-messaging/pull/33)：TLS/RPC配置、取消资源和启动失败清理修复；SDK自身CI通过。
- [SDK PR34](https://github.com/FangcunMount/reliable-messaging/pull/34)：M2-1纯协议初版；Go检查/race/lint、Python源码与隔离wheel各21项测试、本地完整mypy通过，PR完整CI已通过（Python3.11/MySQL8.0.36、Python3.13/MySQL8.4，源码与安装wheel均通过0跳过门禁）。

协议区分请求、冻结计划代次与执行fence；旧终态不改写，Checker不以根请求最新版本替代旧证据。数据库原子性、claim/CAS、取消编排、事务发送器、有界回查生命周期及业务接入尚未实现。M2/M3整体未完成，SDK接口保持provisional；没有发布SDK或切换生产provider。下一批为原MySQL/GORM/Mongo/SQLAlchemy事务绑定及真实存储证明。

最终只读核对：serverD现有RocketMQ、NSQ及3个worker均running=true、OOM=false、restartCount=0。测试不作为生产业务验收。SDK协议PR34验证head为`d89584b51ecdcb23aba8a2b4e20dc361e94683f4`；源码、wheel、完整CI均通过，仍未发布正式接口。
