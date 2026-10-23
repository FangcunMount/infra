# T25：原生回查恢复与持久保护处置（验证中）

本批属于[M3总表](rocketmq-m3-execution.md)的T25-C，尚未完成，不授权生产。启动屏障/目标CLI的14项隔离验证已经通过；此处继续处理原生超限与不再收到回查的确认审计缺口。先完成真实依赖可行性验证，再冻结处置文件和宿主接口。SDK仍固定tx.4/a4，业务写入、schema、Topic/ACL及worker预算均不变。

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

持久notice的解除需要精确处置证明，并保留原始notice与首次导出摘要。优先验证在不改动M2 codec/schema、业务witness和旧notice的条件下，以显式冻结的宿主处置文件建立已核验的终态视图：当前配置owner/store/epoch/route精确匹配，原分支终态与真实正向RPC审计重新读取，新notice不得被旧文件覆盖。缺审计、未知/矛盾证据以及错误绑定仍封闭。该文件格式和跨语言适配尚未冻结，不能提前据此部署或解除保护。

全部旧写者/自主任务冻结、保留责任清单、原链路排空及启动前维护/恢复仍须组合验证；T25-D收口源码/隔离门禁，T29再绑定最终镜像和具体生产清单，T30–T33负责实际运行核验、具名批准和system验收。

可重复开发入口：`rocketmq-native-recheck.yml`固定SDK源码04757bd3、Go1.25.12、Java17、MySQL8.0.36与Broker5.5.1；`ci-native-recheck.py`只允许GitHub-hosted Linux和本地daemon，不接受外部服务。当前为可行性开发，尚未有真实通过报告；不据此勾选C3。

首轮开发40015398289（530f43e）为4通过/1失败/0跳过，停在编译/纯Java探针组合阶段，尚未准备SDK half；Go与Java编译摘要已经记录，但原报告没有更细启动阶段，不推断原生恢复失败。自有Compose/进程/文件与既有资源集合清理通过；Broker参数恢复正向文案判定失败单独保留。固定源码已确认UpdateBrokerConfig使用逗号而非句点；后续按其实际文案及参数回读。Java class受umask077影响的权限明确安装到自有容器UID3000，新增分阶段与固定错误分类诊断，待真实复验，不改写旧报告。

第三轮40016777071（b6d7163）已通过8项：纯Java7边界、真实Prepared超限、原MySQL提交后exit23、新暂停实例无自动回查；停在精确原生记录读取，尚未调用恢复管理操作，所有参数和所属资源清理通过。源码核对发现`QueryMsgByKey`经clientDecode返回MessageClientExt，其getMsgId可能是UNIQ_KEY而不是物理offset ID；不能把审计字段名broker_message_id当作地址。后续从同一固定Broker实际配置和原索引commitlog_offset构造物理ID，并重新验证source Topic、队列位置、Reference/wire/UNIQ摘要；不放宽身份检查。增加IPv4/IPv6及非法offset/port纯向量，失败诊断只输出阶段和布尔验证项，不输出正文/原属性。
