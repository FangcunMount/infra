# M3 统一维护窗口执行清单

当前状态：**公网已于2026-10-25 20:58:39恢复；M3为32/36，T33继续独立AI生产验收。** 用户明确批准核心/IAM验收后先开放、AI开放后继续，并追加最多60分钟；本轮实际维护82分46秒，原30分钟目标未达到。三库升级、四owner绑定、凭据/Secrets和固定八实例已落地；规则报告不替代AI验收，48小时观察未开始。[实际开放回执](evidence/rocketmq-m3-public-reopened-20261025.json)。

## 固定目标与变更

| 主机 / 项目 / 服务 | 实例与资源 | 固定候选 |
| --- | --- | --- |
| serverA / docker / iam-apiserver | 1；1GiB、1CPU，UID2000 | IAM `ca59dec47fe4e544cd06bf52f9e3c64fbbdad211` |
| serverA / servera-migrated / qs-apiserver | 1；1GiB、2CPU，UID2000 | QS `b75d4a52ec261275a0ffb588eeb31fd6496966d0` |
| serverA / qs-collection / server | 2；各320MiB、1CPU，UID2000 | 同QS源码 |
| serverA / qs-ai / qs-ai | 1；768MiB、0.75CPU，UID10001，关闭预算210秒 | AI `ddff86cad27d03c95dad28490d6cccbc1ce5b15f` |
| serverD / qs-worker / runtime | 3；各768MiB、1CPU，并发48，UID2000 | 同QS源码 |
| serverC / mongo | 原7.0.31、rs0和容器不替换 | 仅保护/迁移所选`qs`库 |
| serverD / RocketMQ | 原5.5.1 Docker Broker/Proxy、网络/端口/资源保持 | 显式安装M3 v2资源与最小账号权限 |
| macmini-001 / Prometheus | 保留现有发现、抓取与Grafana | 安装8条M3事务告警并回读 |

五镜像使用[已发布不可变digest](evidence/rocketmq-m3-acr-publication-20261025.json)，目标[已预置](evidence/rocketmq-m3-target-image-cache-20261025.json)。配置为`m3-20261025-v2`，目标根`/opt/fangcun-m3/releases/m3-20261025-v2`；各项目`sealed/acceptance/open`目录中的Compose、环境和assets均逐文件冻结。18项真实读取、15项Compose、15项原UID挂载读取已经通过，生产尚未启用。

DDL仅由原宿主维护入口执行：[17份增量资源](evidence/rocketmq-m3-incremental-migration-inputs-20261025.json)，IAM40→45，QS105/40→110/44，AI0040→0043_native_transaction_limit。不执行down、force、journal修正、自动seed或全目录脚本。SDK Go v0.5.0 / Python0.4.0、owner/store/epoch/revision与[配置回执](evidence/rocketmq-m3-v2-production-candidate-configs-20261025.json)一致。

此次还包含一次共享MySQL应用账号自身密码轮换：新凭据已在未启用候选内冻结；[受审工具](rocketmq-m3-mysql-credential-rotation.md)真实TLS验证通过，用户确认仅上述服务使用该账号。不会在文档、命令参数、CI日志或公开制品中填写凭据。三库部署`MYSQL_PASSWORD` Secret通过stdin同步，生产CD继续暂停。

## 窗口前完成，不占停机时间

1. 再次只读核对镜像/原容器、三个数据库UUID及账号、Mongo rs0、clean版本、原锁inode、CD暂停、serverD可用内存≥512MiB、Broker及worker监控。配置或身份漂移时重新冻结，不带着不明差异进入窗口。
2. `route_revision=m3-1`的12项路由、5个最小权限账号显式provision并读回；资源冲突立即拒绝。安装Mac mini告警并校验配置、reload/readback；此时业务仍NSQ、候选准入仍关。T31单独记账，不能提前打勾。
3. 使用唯一MacBook协调入口，经原Mac mini SSH跳板到A/C/D；两跳关闭agent forwarding。保留原A/D部署锁和A的AI锁，不复制SSH私钥、不建立第二协调目录。实际SSH_AUTH_SOCK发生变化须重新冻结本地受审脚本。
4. system后台正常登录已核对。用户另已在合法小程序会话准备一份SNAP-IV18答卷，尚未提交；实际测试对象和变更scope仅保存在0600私有回执中。新runtime就绪前保留该表单，不重载、不提前提交；登录及准备不算新链路验收。
5. 静态包只包括受审源文件、原维护二进制、精确配置、Nginx候选和命令配方。实际T0、停写证据、保护摘要、期限和维护批准文件在真实事实发生后生成。最终生产批准须明确授权在本清单范围内填写这些事实字段，模板或空摘要不能直接运行。

预窗口三MySQL活跃只读快照为518,498,844B、压缩75,067,274B，读取40.29秒、含压缩45.31秒，Mac mini副本摘要一致。它只用于体量和传输准备，**不替代同窗口停写保护，也不授予恢复权**。完整当前档位隔离C1为19/0/0；51.02秒是受控数据耗时，不是生产恢复SLA。

## 具名步骤与停止条件

| 顺序 / 任务 | 执行动作与真实证据 | 不满足时 |
| --- | --- | --- |
| W01 / T32 | 记录入口关闭T0；在A只替换`iam.fangcunmount.cn.conf`、`qs.fangcunmount.cn.conf`、`collect.conf`为已验证closed字节，先`nginx -t`再reload，实际登录/写入口503。其他域名和内部gRPC保持 | 还未停业务时恢复这三个原文件；保留失败材料 |
| W02 / T32 | 不接收新业务；旧八进程继续沿NSQ收敛在途和回执，查询有效订阅depth/backend/in-flight/deferred及Outbox、未来计划；不重放业务、不调用模型补发 | 不能证明排空/责任交接则不做DDL；关闭窗口或具名延长，不能以修改状态伪装排空 |
| W03 / T32 | 依次有界停止原AI、两个Collection、API、三个Worker及IAM；保留容器、卷、配置、镜像。核对实际进程退出和MySQL在途事务/连接、Mongo业务活动。三库EVENT为空；唯一TTL集合`interpretation_catalog_repair_plans`必须重新证明为空 | 有未知后台写者或非空TTL集合即停止；不临时关闭全局TTL或宣称容器stop等于数据库无在途 |
| W04 / T32 | 用固定8.0.36客户端对iam/qs/ai作同一冻结边界内完整逻辑备份，含routines/events/triggers/原列元数据；serverC对整个qs库mongodump含索引/UUID。完成旧NSQ卷冷保护，相关服务停机后取一致副本。三类保护均0700/0600、保留≥30天、Mac mini副本逐摘要核验 | 没有完整、可核验保护或窗口余量不足，不进入迁移 |
| W05 / T32 | 记录真实freeze/protection/responsibility摘要，绑定已通过的当前档位完整恢复与启动receipt；初始化唯一持久Boundary。原批准摘要、执行包摘要、数据/恢复负责人绑定该操作 | 禁止虚构恢复耗时、复制CI数据库身份、将预窗口活跃快照填为停写保护 |
| W06 / T32 | 原IAM maintenance导出schema计划→核对→apply；再导出select计划→核对→apply。原QS工具消费一次性批准，105/40→110/44，再分别preview/apply/verify两个owner。原AI Alembic upgrade head，再原binding preview/apply/verify。各步经同一Boundary维护步骤并持原宿主锁 | 失败/未知保持全停；只读核对实际DDL与服务器活动，禁止删consumed marker重试或自动接管dirty |
| W07 / T33 | 生成且fsync第一启动标记，**在任何新业务启动及密码SET语句之前**。在serverA以原AI固定镜像的Python/asyncmy0.2.14执行受审工具，借用原TLS CA和infra-network，轮换一次共享MySQL密码；新连接成功、旧连接明确1045，核对plugin/grants不变；同步三库部署Secrets | 结果未知只verify；不再次apply、不改回已暴露密码；启动标记后进入前向恢复边界 |
| W08 / T33 | 经原`runtime_start.py`固定digest、`--pull never --no-build --no-deps --wait`启动五项目共八实例sealed；核对四owner Checker、资源、实际Topic/DB绑定、健康和指标，消费者已就绪，新事务准入仍关闭 | 不把容器健康充当业务验收；保持入口503，以当前事实修复 |
| W09 / T33 | 经同一协调器逐项目使用acceptance配置启用事务发布，三个入口对其他连接继续503；等待全部八实例稳定、Checker/消费者连接。按下节有界来源规则，仅本次操作者的已核验实际TCP来源在有效窗口内可沿原TLS与应用鉴权执行验收 | 任一owner/队列/资源不满足即封该owner新写，保留Checker；不自动回NSQ/Outbox |
| W10 / T33 | system合法会话沿原应用接口执行有界用例；逐项核对业务事实、witness、消息消费和receipt，以及IAM自身/QS双订阅。使用明确测试组织与用例，不重做历史7个blocked AI请求 | 无会话/组织、用例失败、证据不足即保持维护；不以探针或替代身份打勾 |
| W11 / T33 | 所有验收通过，恢复三个原Nginx文件、语法验证/reload和公网读取，恢复准入。**保留已验证的acceptance配置及容器**，不为目录名称再重启一轮；open目录仅是受验同语义备选，不自动启用 | 最终生产配置索引明确记录acceptance路径，禁止记录成未启用open路径 |
| W12 / T34–36 | 开始连续48小时观察；旧生产发布/消费/Relay责任已退出。按T35退出NSQ服务/自动重启及部署责任，保留旧卷、表、wire、历史工具与保护资产 | 观察不足48h不能完成M3；清理由M4负责 |

时间预算：W01–03最多6分钟；W04–05最多5分钟；W06最多5分钟；W07–09最多5分钟；W10–11预留9分钟。分项是计划截止点，不是新的恢复SLA。进入不可逆第一启动前须有至少9分钟实际验收余量，并检查原迁移工具要求的恢复/启动预留；达不到即不启动。到30分钟仍未满足，记录超时、保持安全状态并明确告知，不能为了时间开入口或覆盖新事实。维护前提早封长耗时业务，无法在窗口前收敛时改期。

## 原维护命令配方

以下仅是原入口的固定参数顺序，凭据从受限文件传给子进程环境。运行时私有计划的摘要由实际导出文件计算，不允许占位摘要或脚本自签授权。原维护工具自己记录schema/身份/单次消费，不用自写SQL绕过。

| 原入口 | 固定参数与执行归属 |
| --- | --- |
| IAM镜像 `/app/iam-maintenance` | `m3-messaging --action schema --store-id production-iam-mysql-primary --writer-epoch m3-1 --export-plan <私有新文件> --timeout 30s`；apply用`m3-messaging --apply --writers-excluded --plan <原文件> --reviewed-sha256 <实际摘要>`；schema完成后单独导出`--action select`再apply |
| QS附件 `qs-migrate-offline` | 原二进制SHA `c654ab9d2b84a7c23d7d25e4389ae1371391b4c13592922fe06fe795c5e50e98`；`--mysql-database qs --mongo-database qs --timeout 10m --apply --approval-file <原批准> --approval-sha256 <实际摘要>`，原API镜像、infra-network、原MySQL TLS/CA与Mongo URI。维护附件不进入业务镜像 |
| QS两个binding | 公共`--mysql-database qs --mongo-database qs --timeout 30s`；preview另加`--binding-action preview --binding-plan <新文件> --binding-operation-id <本次ID> --binding-owner qs.mysql或qs.mongo --binding-store-id production-qs-mysql-primary或production-qs-mongo-primary --binding-writer-epoch m3-1`；apply/verify用原文件与`--binding-reviewed-sha256`，仅apply加`--binding-writers-excluded` |
| AI原镜像Python | `-m alembic upgrade head`；`-m qs_ai.maintenance.transaction_binding --action preview --plan <新文件> --operation-id <本次ID> --store-id production-ai-mysql-primary --writer-epoch m3-1`；apply/verify带`--reviewed-sha256`，仅apply加`--writers-excluded`。`QS_AI_RELEASE_SHA`精确ddff86ca完整SHA |
| Broker | 原`provision.py --container <已冻结原Broker名> --project rocketmq --manifest <12路由原字节> --credentials <0600账号文件>`；完整preflight冲突即拒绝，不修改既有Topic类型/既有账号凭据 |
| 启动与恢复 | 操作端`m3_operator_step.py --plan <精确步骤> --reviewed-sha256 <独立摘要> --execute`；目标端`runtime_start.py --plan <目标步骤> --reviewed-sha256 <独立摘要> --execute --coordinated-start-already-issued`。首启动后恢复入口必须拒绝；不以原CI fixture替代生产助手 |

## 原范围恢复和责任处置

第一启动标记不存在时，且完成实际服务器活动核验，可按本清单批准范围恢复**iam、qs、ai三完整MySQL库与Mongo整个qs库**；恢复前删除所选库再载入，避免新增M3对象残留。MySQL原备份保留，派生文件仅对已核验AI0040两个生成列表达式做受限字面量修正；每次必须匹配该次备份与完整列元数据摘要，所有业务INSERT和其余DDL字节保持。以utf8mb4恢复，规范化比较只限已知MySQL显示差异，核对原DDL/列/数据与Mongo文档/索引/UUID。恢复失败保持全停，不重启旧程序试运气。已通过的完整C1证明原方法，不把本次备份声称为已经实地恢复过。

第一启动标记存在后，即使新容器没ready、密码轮换失败或步骤进程退出，也不允许旧全量备份覆盖当前事实。保留配置与实际数据库，封新写、保持Checker、具名排障并使用兼容修复镜像。禁止直接翻provider、换事件ID、重做模型调用或自动删除未决证据。此界限保守包含密码轮换，避免新连接/Secret责任与旧恢复混淆。

444个无客户端授权channel含4364份fanout副本，只有`iam.authz.version`/`.v2`缓存失效消息；并非4364个独立业务事件。最终批准须明确：保留全部消息/卷，不清空/ACK/删除，以新IAM与QS从权威版本加载并分别验证实时fanout后退出这些旧缓存订阅的在线责任。其它业务队列、Outbox、未来计划和回执不能据此豁免排空；新发现未结责任则阻断。QS现有7个blocked AI请求、历史result_outbox/first wire/receipt保持原样，不授权重试或模型调用。

自动生产CD保持IAM/QS暂停、AI自动部署关闭，待生产事实与新配置部署通路另行审核后恢复。M3任务勾选不表示自动恢复CD；NSQ历史资产保留也不表示仍有活动业务责任。

## 最终批准范围

T30将本清单、已冻结静态包摘要、原基线和全部差异提交一次具名确认。确认涵盖T31资源/告警、W01–11、限定原范围恢复、一次MySQL轮换及Secrets同步、旧授权缓存订阅责任交接；实际T0与同窗口摘要仅按真实事实填入私有执行计划。身份/版本/资源不符、额外DDL、额外数据删除、越界恢复或未知责任均超出本清单。测试批准、预置和“类似基础设施操作”授权不代替这次业务生产批准。

## 2026-10-25 执行补充：原合法客户端的有界验收入口

用户已指定实际小程序测试身份并回复“已准备提交”。实际填写页使用生产IAM/Collection/QS域名；原私网REST探针无法代替这条合法客户端链路。W01仍先完全关闭三个入口，W09才安装同窗口临时例外，W11恢复原配置。

纯渲染器`m3_nginx_acceptance_gate.py`仅接受1–4个精确单播IP、真实开始时间及最多1800秒的到期时间。使用原始TCP对端`$realip_remote_addr`，不信任可伪造的X-Forwarded-For。后台与小程序已通过独有只读请求、原访问日志及实际Nginx网络命名空间ESTABLISHED连接交叉核对为同一来源；精确地址只保存在私有回执，不发布到infra。

例外只控制维护503，保持原TLS、代理、应用登录/权限及数据库规则；未匹配或到期一律503，不自动恢复公众访问。三个实际配置的非活动副本`nginx -t`及六个原生HTTP行为共7/0/0通过，原站点和业务容器保持，未reload活动Nginx。首次数字比较语法验证失败材料保留，修正为有界时间正则map后通过；不将失败改写成成功。另有5项纯测试与双OS源码CI分别记账。

本补充是已批准合法业务验收的入口收敛，不改固定应用镜像、v2配置、数据库迁移或140成员原包。补充源文件、CI及[验证回执](evidence/rocketmq-m3-bounded-acceptance-ingress-20261025.json)独立绑定；真正W09配置使用当次已记录T0和期限，不能将非活动测试时间作为生产输入。

## 2026-10-25 首次窗口结果与待验证修正

18:38:17关闭入口，旧责任盘点通过并停止原八实例；发现qs profiler=1后，于18:45:41恢复原实例和入口，总计444秒。原MySQL/Mongo版本与业务provider未切换，M3 DDL/密码/Secrets/新候选均未执行。T32不勾选，原T0和所有失败材料保留。详见[窗口回执](evidence/rocketmq-m3-window-cancelled-profiler-20261025.json)。

[Mongo官方说明](https://www.mongodb.com/docs/manual/tutorial/backup-and-restore-tools/)及[工具实现](https://github.com/mongodb/mongo-tools/blob/master/mongorestore/filepath.go)明确：标准恢复不导入`system.profile`文档。原整库DROP恢复配方暂停使用。修正方向是在业务写者冻结后保留整库逻辑归档，恢复时只重建已审核的全部业务集合；诊断集合、UUID/配置/既有记录原位保留，不更改profiler级别、阈值或采样率。只允许这一精确诊断例外，其他未知系统集合/新增集合仍拒绝。业务BSON、索引、options及UUID必须逐项相同，诊断日志按现有capped政策继续记录，不承诺倒回T0。

新增模块只生成计划，不能连接数据库或授权恢复；完整有持续profiling写入的7.0.31/Tools100.16.0隔离证明、源CI、清理和新操作冻结通过前，该方法不进入生产步骤。固定业务镜像、17份迁移和SDK制品保持。下一窗口必须重读实际CID/StartedAt/队列/库身份及版本，使用新的操作ID；旧窗口不重置、不复用首启动目录。


专项实现已通过[固定镜像真实CI](https://github.com/FangcunMount/infra/actions/runs/40187719008)：6/6真实、Ubuntu/macOS各7/7纯契约，源码由[PR289](https://github.com/FangcunMount/infra/pull/289)合并。[验收记录](evidence/rocketmq-m3-profile-preserved-proof-20261025.json)明确诊断文档保留原位并继续自然增长，不执行`dropDatabase`，不更改profiler设置。生产恢复仅在原首次启动屏障之前，按原业务集合清单与审核迁移新增对象精确选择；未知集合/诊断身份漂移在任何删除之前拒绝。整库逻辑归档作为保护资产保留，`mongorestore --drop --preserveUUID --nsInclude=qs.* --nsExclude=qs.system.profile`仅恢复全部业务集合。首次维护失败记录继续保留，下一窗口使用独立操作ID、最新基线和当次停写保护。
