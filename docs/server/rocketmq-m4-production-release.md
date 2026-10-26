# M4 最终生产发布清单与恢复边界

**准备中，尚未执行应用部署，不能据本草稿开启维护。** C01—C07源码和政策保留闭环；最终候选、生产执行、system回归及发布索引归C08，唯一状态见[M4总表](rocketmq-m4-execution.md)。自动生产CD继续暂停。

## 当前准备和待冻结项

- IAM候选4609d4542d9303130ab94ed67593d0a69d0d010d、QS候选1f38f583d43c9faf4601a5df9f3f82b764e6547d均已合并且运行输入冻结；后续仅文档/workflow提交不冒充镜像代码变化。
- C08审计发现AI还安装SDK的NSQ extra及无调用的CI NSQ服务；[AI PR231](https://github.com/FangcunMount/qs-ai/pull/231)移除它们。候选b00cf3a2f30deffa99e9bf71aa1b6177c651c23c须通过完整CI、真实依赖及重新构建/八实例验证。此前f83472c7的AI镜像仅为阶段证据，不作为最终发布。
- [归档发布器](rocketmq-m4-final-candidate.md#固定归档发布)仅传输固定归档、预检全部目标tag不存在并回读不可变manifest/config摘要。当前发布计划/18项报告尚未绑定上述AI依赖修正，禁止调度旧计划进入最终生产发布；完成后更新固定IAM发布workflow的infra SHA和计划摘要。
- [主机准备回执](evidence/rocketmq-m4-c08-host-preflight-20261027.json)记录固定只读材料工具安装、四角色普通部署用户正向校验及8项错误绑定拒绝。它不表示API原生冻结工具已安装、材料已激活或应用已部署。
- 生产启动前还须冻结五类ACR不可变引用、全部归档/镜像config ID、最终配置/环境/21份材料摘要、API原生预检工具与唯一执行目录、实际准入和停止/恢复命令、system最小用例。缺任何一项不开始维护。

## 具名目标和保持项

| 主机 | 容器 | 固定预算 |
| --- | --- | --- |
| serverA | iam-apiserver | UID/GID2000；1GiB/1CPU；iam.mysql 8发送/4回查/32队列/100维护 |
| serverA | qs-apiserver | UID/GID2000；1GiB/2CPU；qs.mysql与qs.mongo各4/2/16/50 |
| serverA | qs-collection-server-1、qs-collection-server-2 | 各UID/GID2000；320MiB/1CPU；不新增事务owner |
| serverA | qs-ai | UID/GID10001；768MiB/0.75CPU；ai.mysql 4/1/16/100 |
| serverD | qs-worker-runtime-1、2、3 | 各UID/GID2000；768MiB/1CPU；各48并发；publish=false且无事务owner |

本批不执行DDL或数据迁移；实际目标仍IAM45、QS MySQL110/Mongo44、AI0043_native_transaction_limit。原store、writer epoch、m3-1路由、Topic/ACL、TLS、数据库凭据、Redis位置、Broker参数、监控位置、端口和网络不变。MQ/JOSE仅改为已核验版本文件的只读挂载，不重新生成密钥。保护全部当前/前序/pin/容器引用镜像、原指针及部署锁inode；不调用任何镜像清理或保留策略的apply。

## 窗口前门禁

1. 最终源码/依赖CI、当前实际宿主故障和五归档验证通过；稳定SDK Go0.5.0/Python0.4.0及wheel摘要保持。最终八实例实际启动/关闭、零DDL、原预算、全部清理通过。
2. 从实际主库只读回读四owner的原字节binding及clean heads，不用SDK binding schema_version代替宿主迁移head；核对八实例身份/资源/重启和worker HTTP ready。serverD可用内存至少512MiB；不足或出现OOM/非预期重启则停止。
3. 固定新镜像先拉取到主机并核对image config ID；保留原镜像。调用固定root材料验证器，安装精确审核的API原生冻结工具；仅授权固定源码/镜像、基路径和UID/GID。普通部署用户实际原生预检成功、重复冻结一致且错误输入在替换前拒绝后，才能准备启动。
4. 原私有配置、环境、挂载、网络与服务身份在原主机内冻结，不将凭据或原wire导出。新包以真实Compose解码回读，并逐字段比对原owner/预算、只读材料、服务证书、监听及下游地址。root工具、sudo规则、计划和源码均绑定精确摘要；保留原版本。
5. system合法会话与门店A最小验收入口就绪。当前Mac锁定且Chrome没有Qlume会话，已请求用户正常登录。不能用管理员令牌、替代身份或数据库探针代签system验收；入口未准备好不进入维护。
6. 核对AI真实在途、已有模型调用/checkpoint和未来调度责任。需要额外等待时留在窗口前；不为清理强杀模型、重置attempt、重做unknown或重新投递旧消息。

## 受控执行顺序

窗口目标不超过30分钟。精确命令、截止时间和恢复清单尚待最终候选绑定；未冻结前本节仅定义顺序。

1. 通过既有维护入口封闭新业务写入，IAM登录一并维护；允许已接受工作沿当前事务协议收敛。保留读证据和Checker，不把开关、取消或lease当作回滚证明。
2. 记录未决责任、当前准入revision及实际在途；等待真实任务排空。关闭失败或ShutdownIncomplete不得假称已停止，也不提前关闭DB/loop。
3. 原共享部署锁覆盖具名配置替换和启动；不删除/重建锁。原eight-runtime镜像和配置继续保留。仅使用冻结的最终配置和材料版本，不运行旧M3 credential/schema/cutover步骤。
4. 按冻结依赖启动IAM、AI、QS API、三个worker和两个collection实例；注册四owner Checker、验证全部worker消费者。新外部写保持维护，核对实际image ID/source/config/material、UID/预算、健康和原生保护状态。
5. 在合法system会话内执行具名最小业务回归；逐项核对数据库事实、精确witness、消费效果和业务receipt，再解除本次维护。恢复失败按原revision查询，不盲目重复开门。

## 恢复边界

- M3首个新runtime屏障持续有效，任何阶段均不能用旧全量备份覆盖当前业务事实；不得运行旧离线迁移、NSQ/Outbox provider切换、消息补发或模型重做。
- 新候选尚未启动时，准备失败只保留新材料/镜像供核对；当前运行实例和原配置保持。解除本次新加维护须核对原准入责任，不能恢复早已关闭的业务开关。
- 发出本次首次启动命令后保留全部事实，按精确镜像、配置和已冻结原事务证据前向修复；允许相同候选受控重启，不承诺未经验证的旧应用版本回退。不得更换事件ID、writer epoch或重置未知状态。
- 故障注入仅在隔离CI。实际进程/Broker退出与新实例回查、模型调用不增加分别有证据；生产不注入故障。原生超限高级恢复R01—R03继续独立，不加入本批，也不授予自动解除保护权限。

## 最小业务验收及发布记账

IAM使用具名空角色操作验证实际witness及IAM/QS双订阅；答卷→评分→规则报告与QS→AI command→receipt/state→ACK分别验收。若需要新答卷或新模型调用，先冻结唯一新测试对象/请求及次数，不复用原已完成答卷或七个blocked请求。Task外部提醒及额外模型评测不在本批，不发送测试通知。

当前尚未完成这些真实用例。任何既往M3验收、容器健康、源码/CI或探针均不能填成本轮system通过。48小时观察仍是用户对M3 T34的豁免，不新增观察门禁，不伪称已通过。收尾分别记录源码合并、稳定SDK保持、五镜像发布、主机工具/材料启用、八实例实际部署、业务验收、政策保留及自动CD暂停，再更新C08和最终发布索引。
