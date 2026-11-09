# 2026-11-09 AI #246 入窗复验

**当前决定为 No-Go。** 账户、制品、材料比较、Worker 就绪与四 owner 的服务端观测均已复验。Prometheus 集中采集仍异常，直读方案待独立审查签收。真实窗口尚待授权和现场签收。AI 自动发布关闭，QS 生产发布工作流仍手动禁用。各项现场签收留空。[窗口签收清单](rocketmq-host-retirement-ai-246-window-signoff.md)

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

M1 复验发现 `make check-infra` 仍经历史 `all` 检查访问 NSQ，导致无 NSQ 的 `make run-all` 和 `make quick-start` 在进程启动前失败。QS 草稿 `2ecee7169` 将标准入口指向 MySQL、Redis、MongoDB 数据预检，保留显式历史探测。定向回归覆盖缺 NSQ、三种数据依赖拒绝和历史入口，文档门禁已通过。完整开发启动还需在隔离环境验证 Proxy、TLS、路由、owner、真实进程和业务链路。[QS #481](https://github.com/FangcunMount/qs-server/pull/481)

F02 已补两份源码草稿。QS 在同一个有界只读查询中单独报告观测到的事务锚点缺失或冲突数量，原业务回执阻断语义保留。MySQL 8.4.13 隔离用例实际覆盖完整锚点、缺档案、见证冲突及后续查询失败。对应面板以独立时序展示计数，缺样保持为空。QS 草稿精确提交 `f4706861ccf56d9b53c68559ce052586f1e11b0d` 共 29 项检查成功、1 项按条件跳过，含当前运行时 E2E。上线需分别签收和受控发布，51 条私有历史分类继续待数据责任人签收。[QS #480](https://github.com/FangcunMount/qs-server/pull/480) · [infra #426](https://github.com/FangcunMount/infra/pull/426)

F05 在 IAM `7cd2b02` 的空 MySQL 8.4.13 隔离库实际通过完整迁移与 bootstrap 测试。最终 clean 45，`domain_event_outbox` 有两条 `iam.authz.version_changed.v2` pending，`rm_outbox` 为 0。下一批先为全新库的两个授权版本通知补持久替代路径及可验证通知效果，再替换当前 handoff 和 readiness 的旧表读取。升级、历史审计与其他对象的依赖仍分别验证。F06 热榜、答卷缺口、原效果、MySQL 和 Mongo 调度交接五个包的定向测试通过，作为替代路径的改动基线。

IAM 测试夹具 `a416f59dae78c8b3b28350d1690a5a10e7c395df` 在空 MySQL 8.4.13 上复用 33 和 35 的原业务事务，将完整 SDK 消息写入隔离暂存表。迁移至 clean 45 后，两张旧表均为零行，暂存表在两个阶段各有一条，消息 ID、生产者、类型、作用域、指纹和策略版本均校验通过。故意在暂存后中止时，策略版本和暂存记录一起回滚。五份原件含增量 bundle，在 MacBook 与 ServerA 逐成员读回并 fsync。归档 8,065 字节，SHA256 `2c496638f36cefea88d6e2913895b3438420527a9c349f95d75ed801499c1185`。

夹具预先建好暂存表，当前 IAM 运行时未接入替代路径。正式方案需要在阶段 33 前建立并验证暂存结构，在原事务中固定消息身份，并记录阶段完成状态。阶段 34 依赖阶段 33 的角色模型迁移回执，启动恢复还要覆盖已越过版本 0、阶段尚未完成的情况。待原生事务 owner 可用后，验证同一消息身份的交接、重试和实际授权通知效果，再审查 handoff 与 readiness 的切换。

F07 原工作流处于禁用状态。隔离分支以 `a5cc2c9` 为固定历史夹具，首轮 checkout 缺少比较所需 Git 对象，在夹具启动前失败。补齐后原生复现为 **22 通过、1 失败、0 跳过**，两种原存储已实际完成恢复，原生清理检查通过。末项失败位于历史 QS `9301bf8` 的 `owner_runtime_native_integration_test.go:735`。夹具以暂停准入启动替换 owner，断言却要求 `Stats.Ready=true`，而固定源码把该字段与写入准入取交集。历史报告和日志已两地保全，归档 SHA256 `b2f09de5c38a6fc8d2d056d192436267e8e11ff8bd61dac92101495b6bfe2385`。[F07 失败复现](https://github.com/FangcunMount/infra/actions/runs/42628757978)

历史 QS 夹具 `aa6d2f0` 只修改该断言。第二轮宿主子测试正常退出，7 项通过，0 失败、0 跳过、0 race 报告。两种原存储均记录具名解除和一次实际 SDK 提交确认，业务、请求、执行和见证各保留 1 条。暂停替换 owner 正常排空。整轮仍为 **22 通过、1 失败、0 跳过**，未签发独立清理复核结果。报告、运行元数据、日志 ZIP 和保全脚本在两地逐成员读回并 fsync，归档 56,834 字节，SHA256 `93e52c00471c652dbfcc4e79bdf91f86e5343e2beeb7129747c35d064cbaf59b`。[F07 第二轮原生报告](https://github.com/FangcunMount/infra/actions/runs/42631372602)

第二轮末段的 Mongo 清理复核表达式多一个右括号，原表达式通过 `node --check` 复现语法错误。隔离派发 `7f281b9d8e935620f8e80a5a71edfdbaf80675d1` 移除该括号并加语法预检，原 9 项夹具测试通过。仍要求 23 项原生通过、零失败零跳过，以及观察器退出、两库删除、源码洁净和隔离资源清理全部通过。第三轮已派发，待结果签收。[F07 第三轮原生重验](https://github.com/FangcunMount/infra/actions/runs/42633443737)

并行源代码和隔离原件另有 10 份、11,334 字节，SHA256 `4871bf543d95a965f730d4994dc4a640045c67138fff9bbaf4edc67a83285410`。MacBook／ServerA 两地逐成员回读和 fsync 通过。

F07 的 AI 原生测试入口已经核对。历史 `native_limit` 配置固定 Python SDK `0.4.0a4`，AI `c635` 使用 `0.5.0`。AI 现有隔离用例验证 SQLAlchemy 原库原生拒绝及重开保护，具名解除和业务根读回还需同一原根的实跑。R03 用独立 Go 模块文件将恢复工具临时指向稳定 SDK `v0.6.1`，13 个 Go 包编译通过，279 项普通测试全部通过。测试报告 SHA256 `5d19a82e6e8b8192f409f738fcbba87a34926296e508b4f83edc8caa00ddcd4e`。后续还需验证执行器版本绑定、R01/R02 原生故障矩阵和正式制品。
