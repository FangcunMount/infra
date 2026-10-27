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
