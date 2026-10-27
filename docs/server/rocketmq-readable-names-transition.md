# 可读资源的权限过渡与部署边界

本文件说明 T10 准备工具；生产资源尚未应用，完整验收状态见[执行总表](rocketmq-readable-names-execution.md)。正式制品、最终镜像和演练未通过前，不进入维护窗口。

`provision_v2.provision(container, new_manifest, accounts, previous=old_manifest)` 只准备新资源与精确的旧新权限并集。原 v2/v3 独立 provision 默认保持；不能用只含新权限的 manifest 覆盖现有账号。

## 准备及拒绝条件

- 旧 v2 与新 v3 的逻辑身份、route revision、账号职责、Topic/Group预算完全相同。新 manifest 的被动历史必须精确等于旧路由。
- 原 Topic、Group、账号、凭据及旧权限须完整存在且一致。缺失或漂移直接拒绝，不能借准备动作重新创建旧资源、修复旧权限或轮换凭据。
- 新资源只能从完整预检返回的缺失项创建。现有账号权限只能是完整旧权限加零个或多个精确新权限；通配符、额外动作及其他权限漂移拒绝。
- 中断后的精确部分并集可以继续；完成后回读新资源和全部并集权限。报告明确只表示资源/ACL准备，不能代表退役、部署或业务验收。

## 配置与 CD

保持现有配置生成器、挂载目标、原store/epoch、TLS、JOSE及预算。候选 `routes.json` 使用 infra 的 v3 manifest，先写入新的不可变材料版本目录，保留原凭据/CA/密钥字节。T14停旧实例后才切换活动材料版本；不得提前改写旧运行版本中的文件。

当前三个自动CD控制量由T13重新读取并冻结：IAM/qs-server的`PRODUCTION_DEPLOY_PAUSED`，qs-ai的`AUTO_DEPLOY_ENABLED`。暂停后确认无已获执行资格的部署在途；继续使用各库既有部署锁和镜像保留。T16恢复记录的原值，不盲目统一启用。新资源的生产预置不发送探针消息；ACL发送/订阅正反验证在隔离环境完成，实际生产发布由system验收验证。

## 具名退役注意事项

只在逐个对象完成总表所列责任清零、导出配置/ACL/进度并保存审核证据后执行。历史数据库证据保持；未结对象保留并登记。

已核对5.5.1上游实现：`deleteSubGroup`使用具体Broker的`-b`分支，不能使用会连带删除重试/DLQ Topic的`-c`分支；offset清理须在导出后明确指定。`deleteTopic`使用具名cluster并同时清理Broker/NameServer路由，执行前必须重新核对cluster成员仍为冻结的目标。`deleteAcl`始终指定单个具名resource，不能省略资源而删除整个ACL。实际退役工具和真实隔离验收尚未完成，不能据此文档执行删除。

来源：[DeleteSubscriptionGroupCommand](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/tools/src/main/java/org/apache/rocketmq/tools/command/consumer/DeleteSubscriptionGroupCommand.java)、[DeleteTopicSubCommand](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/tools/src/main/java/org/apache/rocketmq/tools/command/topic/DeleteTopicSubCommand.java)、[DeleteAclSubCommand](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/tools/src/main/java/org/apache/rocketmq/tools/command/auth/DeleteAclSubCommand.java)。上游blob分别为`44113e32de68dde45c8f5c1e6991806a941b9963`、`bdee33c52f5153160a9b4b34b73784362ae1c998`、`a3553e0cb39b9a23b8c9c58563fd97042319f1d9`；不以CLI名称推断删除范围。

### 只读退役清单生成

`scripts/rocketmq/readable_retirement.py` 仅离线生成具名命令供审核，不调用Docker、SSH或MQ，不授权执行。输入为冻结的旧/新manifest、五个既有账号的用户名映射、逐个选定的旧对象，以及15秒内取得的完整责任观察。它拒绝通配符、重复/新/未知对象、缺失计数、非整数或非零责任、缺少导出摘要、集群成员漂移及未通过业务验收。

选定对象必须同时证明活动写者、消费者、积压、in-flight、不可见重试、未决事务、Broker绑定计划、待回执、未处置死信和原生超限责任均为零。未选中的旧资源在报告中明确保留。命令始终只撤销单个旧resource权限、在具体Broker上删除Group并显式清理已导出的offset、逐Topic清理Broker及NameServer；不生成retry/DLQ或历史数据库删除命令。

报告通过独占创建写入0600文件。`execution_authorized=false`始终保持：输入观察的真实性、现有部署锁下的实时复核、执行后的Broker/NameServer/Dashboard回读和隔离删除演练仍是后续执行器门禁，不能用该离线报告替代。

### 隔离删除语义专项

`ROCKETMQ_READABLE_RETIREMENT=1` 仅在完整 owned readable transition 档启用。先要求130项真实ACL/TLS门禁及精确旧新并集通过，再校验隔离Compose项目、单Broker成员和实际空Topic offset；逐个撤销所选旧权限、删除一个旧Group和一个旧Topic。专门创建的空retry/DLQ sentinel必须保留；其他旧/新资源及权限逐项比较，NameServer Topic列表回读确认删除。

这只验证新建空测试资源上的CLI语义，不证明生产责任已清零，也不授权生产删除。专项CI预算45分钟，独立于生产维护上限30分钟。生产观察需在旧POP消费者仍在线时取得，不能把指标缺失或普通consumer offset差值单独当作POP不可见责任为零；之后停旧运行时前还须核对宿主协议、业务回执及调度责任。

### 既有 CD 材料链路兼容

既有 `m4_material_stage` 继续负责不可变材料，不生成或解释 Topic/Group 名称。新增真实 v3 清单的四角色回归：活动和历史映射逐字节进入原只读版本文件，原 credentials/JOSE 来源字节保留，重复 stage 不改写，verify 只读且不激活 current 指针。该工具24项本地测试通过；宿主 CD 配置仍使用原路径、身份、epoch 和部署锁。最终镜像下的实际解码及原配置打包器启动由独立 T11 入口验证，不把纯材料测试等同于生产部署。


### POP 重试伴随删除保护

追加核对5.5.1 `AdminBrokerProcessor.deleteTopic`：当 `clearRetryTopicWhenDeleteTopic` 启用时，Broker可能连带清理与该Topic关联的POP v1/v2重试Topic。仅确认CLI使用具名Topic仍不足以证明删除范围。

离线审核现在要求完整新鲜Broker Topic名称快照；发现所选Topic存在任意`%RETRY%<group>_<topic>`或`%RETRY%<group>+<topic>`伴随资源，即拒绝生成删除清单，不修改Broker开关，也不把伴随对象隐含纳入删除范围。原138项隔离报告只验证classic retry/DLQ sentinel；增强专项增加未选Topic上的POP v1/v2 sentinel并核验全部保留，尚待真实CI。旧报告继续保留，不将它表述为已覆盖所有POP伴随删除。

上游：[AdminBrokerProcessor](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/broker/src/main/java/org/apache/rocketmq/broker/processor/AdminBrokerProcessor.java)，核对blob `876a72fa29cce1f92addd94b332168ebcacd0b77`。
