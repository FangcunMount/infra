# T25：原生回查恢复与持久保护处置（验证中）

本批属于[M3总表](rocketmq-m3-execution.md)的T25-C，尚未完成，不授权生产。启动屏障/目标CLI已扩展至17项隔离验证通过；此处继续处理原生超限与不再收到回查的确认审计缺口。先完成真实依赖可行性验证，再冻结处置文件和宿主接口。SDK仍固定tx.4/a4，业务写入、schema、Topic/ACL及worker预算均不变。

## 已核对的源码边界

- IAM/QS `native_limit_mysql.go`、QS `native_limit_mongo.go`及AI `mysql/native_limit.py`当前保存只封新写的原始notice，没有生产解除入口。重启与换配置不能被当作旧责任已处理。
- 固定SDK04757bd3的`RecoveryReceiptRecorder`只记录实际EndTransaction RPC成功之后的观察；不得直接调用该方法来填写缺失确认。确认审计与消费回执分别记账。
- 5.5.1 Proxy在无法取得transaction data时返回`TRANSACTION_DATA_NOT_FOUND`。不能假定旧transaction ID在任何新实例/任何时间都能直接重新确认。[Proxy源码](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/proxy/src/main/java/org/apache/rocketmq/proxy/processor/TransactionProcessor.java)
- 5.5.1提供`DefaultMQAdminExt.resumeCheckHalfMessage`，Broker将指定物理记录的检查次数归零，并复制到内部半消息队列，保留正文与属性。它不是业务重试、事务提交证明或无限恢复窗口。[管理API](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/tools/src/main/java/org/apache/rocketmq/tools/admin/DefaultMQAdminExtImpl.java)、[Broker实现](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/broker/src/main/java/org/apache/rocketmq/broker/processor/AdminBrokerProcessor.java)
- Broker仍按原born timestamp与实际fileReservedTime判断跳过；物理数据过期、证据不足或绑定矛盾时继续Unknown并封闭准入。[有限窗口源码](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/broker/src/main/java/org/apache/rocketmq/broker/transaction/queue/TransactionalMessageServiceImpl.java)

## C3-0：先验证Broker原生机制

仅在隔离GitHub项目中验证，不在本机运行Docker、MQ、数据库或SSH：

1. 复用固定SDK的原有sdkprobe，lease显式设为一小时；原实例准备半消息后停在本地事务之前，Checker真实读取Prepared并返回Unknown。隔离Broker将checkMax临时设为2，取得真实原生超限索引后恢复原参数，再允许原业务事务提交事实与witness；在callback返回前进程exit23，不冒称SIGKILL或数据库断网。
2. 取得真实原生超限索引，启动使用相同主库/owner/store/epoch的新实例。新实例不Reserve/Execute，保留Checker，证明缺口仍在而没有自动重新发业务消息。
3. 私下读取选定物理记录，核对原Reference、route、首次wire hash、原Broker client ID与有限保留窗口，显式恢复一次原生回查。
4. 等待真实Checker RPC和正向审计；核对原请求/执行/witness/测试事实数量不变，首次业务身份与wire不变。单独记录原生内部复制/可能重投，不承诺物理消息只出现一次。
5. 拒绝错误owner、Reference/wire、物理来源或过期窗口；读取失败不能填零。记录实际版本、参数、摘要和清理。

原生操作结果分为NotAttempted、RecheckEnqueued、Unknown。RPC超时/进程退出不授权自动重放同一管理操作；不会把RecheckEnqueued写成CommitConfirmed。原SDK继续负责精确权威回查和实际RPC审计。

## 后续门禁（尚未实现/验证）

可行性通过后，再实现受审核的一次管理入口：固定Broker身份/消息、原主库绑定、单次批准消费、独立证据和有界观察。管理入口不调用宿主executor或模型，不生成新业务ID、wire、授权或fence。原生内部复制必须单独记录；消费者继续使用原业务身份幂等。

持久notice处置由infra中的短生命周期Go CLI实现，复用固定SDK跨实例/跨语言读取MySQL与Mongo见证的能力，不新增常驻服务。宿主保留正常池/事务/Checker与准入，只补受审resolved治理记录的读取/校验；临时工具只持有原具名owner/主库/路由配置，不根据消息属性选数据库。

固定SDK的RecordRecoveryFinal保留首次正向审计时间，同一终态再次确认时不会刷新final_recorded_at；不能用“时间戳比恢复前更新”证明本次RPC。工具包装现有RecoveryReceiptRecorder，只在SDK完成真实RPC及原审计后，为本次匹配Reference写独占0600私有观察。SDK源码、首次时间、codec/schema均不改，CLI不能手工调用该接口补证据。

临时实例封新发送、登记完整owner事务Topic并保持有界Checker；不调用Reserve/Execute/业务回调，不授权模型、调度或业务重试。本实例中止维护明确禁用，原宿主继续负责维护；文件I/O仍占真实回查容量，超时不能谎报排空。启动任何可回查/确认的SDK连接前都经过infra不可逆首次运行屏障，不能将它标成允许旧备份覆盖的纯DDL维护。

顺序为：原主库只读snapshot/私有计划、独立审核、原Broker物理位置/REAL_TOPIC/Reference/wire与有限窗口核验、必要的native recheck（仅RecheckEnqueued）、新实例真实RPC及本次私有观察、fresh原库精确终态/SDK正向审计、独立审核的治理CAS。本地提交、RPC结果与消费完成分别记账。

治理只用现有status/resolved_at/resolution_receipt_sha256；首次evidence_sha256及原索引不变。同一已处置索引重导出不重开，新的物理索引仍blocked。缺记录、Prepared、错误owner/epoch/fence/route/wire、矛盾终态、DB/审计失败、缺失/过期正文均封闭；truncated_possible不能当完整范围来解除。文件契约、四种存储CAS、具名入口与真实拒绝矩阵仍待完成，不授权生产或勾选C3。

全部旧写者/自主任务冻结、保留责任清单、原链路排空及启动前维护/恢复仍须组合验证；T25-D收口源码/隔离门禁，T29再绑定最终镜像和具体生产清单，T30–T33负责实际运行核验、具名批准和system验收。

可重复开发入口：`rocketmq-native-recheck.yml`固定SDK源码04757bd3、Go1.25.12、Java17、MySQL8.0.36与Broker5.5.1；`ci-native-recheck.py`只允许GitHub-hosted Linux和本地daemon，不接受外部服务。固定源码815f4656已在40020383336通过17/0/0并由PR200合并；仅勾选可行性组件C3-a，持久notice和完整故障矩阵未完成，C3不勾选。

首轮开发40015398289（530f43e）为4通过/1失败/0跳过，停在编译/纯Java探针组合阶段，尚未准备SDK half；Go与Java编译摘要已经记录，但原报告没有更细启动阶段，不推断原生恢复失败。自有Compose/进程/文件与既有资源集合清理通过；Broker参数恢复正向文案判定失败单独保留。固定源码已确认UpdateBrokerConfig使用逗号而非句点；后续按其实际文案及参数回读。Java class受umask077影响的权限明确安装到自有容器UID3000，新增分阶段与固定错误分类诊断，待真实复验，不改写旧报告。

第三轮40016777071（b6d7163）已通过8项：纯Java7边界、真实Prepared超限、原MySQL提交后exit23、新暂停实例无自动回查；停在精确原生记录读取，尚未调用恢复管理操作，所有参数和所属资源清理通过。源码核对发现`QueryMsgByKey`经clientDecode返回MessageClientExt，其getMsgId可能是UNIQ_KEY而不是物理offset ID；不能把审计字段名broker_message_id当作地址。后续从同一固定Broker实际配置和原索引commitlog_offset构造物理ID，并重新验证source Topic、队列位置、Reference/wire/UNIQ摘要；不放宽身份检查。增加IPv4/IPv6及非法offset/port纯向量，失败诊断只输出阶段和布尔验证项，不输出正文/原属性。

第四轮40018504724（ef47725）仍8/1/0，物理读取阶段返回MQClientException，未发出恢复操作，全部实际参数和资源清理通过。进一步核对5.5.1 `QueryMessageProcessor.matchesRequestTopic`：HALF与CHECK_MAX存储的VIEW_BY_ID必须使用REAL_TOPIC做请求Topic，不能传内部存储Topic；`DefaultMQAdminExt.viewMessage`又会吞掉物理读错误改做UNIQ搜索。后续固定本机Broker直接按原offset/REAL_TOPIC读取，继续核对返回的内部Topic与所有队列/身份字段；resume使用同一REAL_TOPIC。新增仅数值response code诊断，无原始errmsg/正文/凭据，不修改ACL或绕过Topic授权。


## 可行性通过：40020383336

PR200合并1fc072b，原生报告摘要`f4e50b2a156470e3a2badbcfa7a42e2eb1676ab7f6a299434e42cec32d8022b6`。实际17/0/0；包含11个有限窗口/物理地址纯向量、真实CHECK_MAX、原事务commit后exit23、新实例封新发送、原生resume和真实Checker Commit RPC/audit。恢复指标CommitConfirmed=1、AuditRecorded=1、CheckCommit=1；新half、普通发送、本地业务回调计数均0，所有在途/排队为0且Stopped=true。原请求/执行/witness/业务事实各1，原始索引摘要不变；八项清理全部通过。原始参数6000ms/5000ms/checkMax24/fileReserved48h已回读恢复，不能把该配置乘积作为SLA。

管理响应只记`RecheckEnqueued`，成功提交由新Checker读取原证据并实际调用RPC、写正向审计证明。原程序真实exit23不是SIGKILL或网络故障；这是固定SDK源码探针，不是正式制品/四宿主或system入口，也尚无持久notice处置证明。失败40015398289、40016571315、40016777071和40018504724保留；后两轮均未发出resume，不将其读取失败冒称回查失败。完整源码/CI、报告摘要及限制回链总表的结构化证据文件。


### 客户端ID复用的源码修正（已合并，完整恢复仍待验证）

5.5.1原生复制保留UNIQ_KEY，getMsgId可能返回客户端ID。IAM/QS Go及AI Python先复现“两位置同客户端ID”被拒绝，再改为按完整v1指纹拒绝重复；摘要字节保持。两语言固定向量c17eef089ffe8dcd195b09d54c8d7af26283362fc173a6226b964a4a4c0968d3和61922da276bd4e4b9eced322f30aac9224929b6614dce2205f5fed99df91a878一致，大小写等价的同一完整索引仍拒绝。当前Go纯race/Python28纯通过，仅源码准备，不是实际两副本Broker证明或C3闭环。


### 当前恢复工具原语（尚非完整 CLI）

`tools/rocketmq-native-recovery`固定下载 tx.4，拒绝本地replace。check-only Store不暴露Bind，拒绝Lookup/Reserve/Prepare/Abort/普通记账，本实例不执行中止维护。私有Runtime不提供Sender，只登记完整owner路由、有限Checker并在Start返回后立即StopAdmission；固定SDK在StopAdmission之后拒绝Start，不能使用错误顺序。执行能力从构造时即被Store封住，启动仍必须经过首次runtime屏障。

本次观察只由SDK真实RPC→原正向audit→包装sink路径产生，首次DB时间不变。独占0700目录/0600文件绑定受审请求摘要、本次nonce、源码、Reference摘要及终态；最多16份，同步I/O不脱离真实回查容量，取消/碰撞/限额/写入或同步失败保留文件并拒绝成功证明。关闭必须实际排空，不能以调用方超时宣告完成。当前本地race、文件隐私/不可覆盖及生命周期契约使用明确fake，不是实际RPC或治理CAS验证；完整CLI/四种宿主矩阵继续。


### 已合并的读取/存储组件与余项

IAM145、QS436、AI221已分别合并；合法resolved历史导入保留首次证据，周期仅读取活动责任，新物理索引仍封闭。infra207/209/210已合并check-only/私有观察、三SQL owner与qs.mongo snapshot；最新64纯、MySQL三档各17、Mongo7.0.37的10项通过，自有DB/容器清理均回读。均使用固定发布Go tag tx.4，无replace或SDK协议改写。旧正向audit为明确的受控reader fixture，不是本次真实RPC。

当前没有生产解除CLI或治理CAS；源绑定、真实物理核验、受审请求/receipt、实际SDK RPC和治理提交仍须组合验证。组件表、完整源码/CI/报告摘要及失败历史回到[M3总表](rocketmq-m3-execution.md)。首次SQL资源遗漏setup失败以及QS文档空白门禁失败均保留，未改写为通过；稳定SDK、实际生产、system与48小时观察未执行。
