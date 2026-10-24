# M3 旧写者停写与离线维护契约（C2工具门禁完成）

唯一进度见[M3总表](rocketmq-m3-execution.md)。本契约用于T25-C2/D组合验证和T29冻结实际步骤，不授权生产；源码清单不能替代T30实际进程、数据库、入口和具名执行核验。C2源码/隔离门禁已由PR222闭环，实际生产证据仍待T29–T33。

## 先区分停写和关闭发布

最终RocketMQ实例设置`publish_enabled=false`后，仍需登记本owner完整事务Topic、运行Checker和有界协议维护，不能直接关闭SDK。IAM/QS/AI均已有该装配及隔离验收。这个开关不自动冻结旧NSQ业务、HTTP根事务、外部CLI、未来调度或模型调用，不能据此声明旧写者已退出。

整次切换使用原唯一协调目录及[首次启动屏障](rocketmq-m3-start-boundary.md)。只读盘点/保护先完成，真正DDL、绑定选择和旧未来计划交接均作为独立受审`pre-start-maintenance`步骤。维护失败/中断后保持封闭；独立`pre-start-repair`不是业务重试。首次新runtime命令发出后，禁止所有库旧备份覆盖，只有受审兼容前向修复。

## 原责任交接顺序

| 阶段/对象 | 必须保留并完成的责任 | 进入下一阶段所需证据 |
| --- | --- | --- |
| 窗口前QS/AI长任务 | 提前关闭新长任务；原已接受模型调用自然收敛，保留response/checkpoint/provider unknown | 原operation、租约、provider状态和业务receipt；未知模型不能重做或换ID |
| IAM授权写者 | 冻结Role/Resource/Grant/Assignment及受管替换的REST、全部有权gRPC caller；暂停scopemigrate apply/rollback、conditionretire、operationscatalog、rolemodel、accountprovision/reviewer-scope及bootstrap/bypass工具 | 实际入口禁写、原在途授权事务结束、版本不再增加；保留登录、鉴权、读取和sessionrevocation。发布暂停不替代禁写 |
| QS外部入口 | 封闭答卷/评分/报告/Task及AI command的新业务写，包含collection/API和直接维护入口 | 禁写与必要读取实测；原已返回202答卷仍由旧链路处理，不把MQ半消息ACK当业务202 |
| 旧消费者/Relay | 原NSQ、旧Outbox、AI事件/ACK及receipt仍沿旧链路收敛 | 完整原订阅快照、到期Outbox、in-flight/deferred、业务回执及已接受工作逐项核对；不能先停Relay再宣称队列为空 |
| 未来计划 | 保留原授权、due、attempt、first wire与未知责任；使用已合并QS PR433实际CLI/冻结清单交接 | 原未来调度先失去执行资格；新dispatcher尚未运行；旧Relay/Replay不再拥有已交接行。行交接不代替旧进程停止 |
| 最后旧写者/自主任务 | 停止QS三个旧worker、旧API/collection写路径、AI worker/scanner/Relay/自主恢复、相关维护和所有自动部署/重启入口 | 精确原进程/容器退出、所属DB事务与外部调用核对、业务版本/计划不再变化。失败退出不记作成功排空；资源/并发保持原配置 |
| 原备份与离线维护 | 对冻结保护范围生成可核对备份/恢复附件，再执行显式DDL和绑定选择 | 主库身份、schema、source/image/config/resource摘要、保护文件摘要及恢复演练；任何不符仍关闭准入 |
| 新runtime | 先持久首个启动记录，再运行目标助手，发布关闭但Checker/消费者可验证 | 原绑定回查、消费者及所有fanout效果/receipt；合法system验收后再开准入。无system会话不能用探针代替 |

原NSQ的排空工具只提供两次稳定原生快照，未来交接工具只交接冻结行；二者都不输出生产授权。原NSQ服务及数据卷的退出另按T33–T35记录，不能为制造零积压而删Channel、清空队列、ACK未知消息或删除卷。

## IAM：保留登录时的保护范围

IAM既有`/opt/iam/maintenance/authz-write-freeze`只负责跨普通部署保留已审核gRPC ACL，不自动改写运行ACL、冻结REST或暂停QS侧授权写。M3固定启动入口不会调用普通部署同步脚本，因此最终Compose/config必须明确包含冻结ACL及摘要，不能以该目录存在代替运行禁写实测。所有维护/bypass写者仍需独立排除。

已核对的M3迁移42–45只新增七张表：`rm_tx_binding/request/execution/witness`、`iam_authz_message_protocol`、`iam_authz_operations`、`messaging_native_limit_notices`。保护候选范围因此是这七个原先不存在的对象及原真实`schema_migrations`的DDL/行。已有AuthN/login/sessionrevocation、授权事实、版本、Redis会话/JWKS等不在该旧数据恢复范围内；不是冻结全库后允许全库覆盖。

IAM [PR141](https://github.com/FangcunMount/iam/pull/141)提供实际`iam-maintenance m3-messaging`：默认只读导出新0600计划；独立审核后，先显式迁至45，再重新预查并独立选择`iam.mysql`原store/epoch及`transaction/m3-1`。绑定和协议CAS共同提交，不启动业务/SDK/MQ/Redis；脏版本、主库/DDL漂移、旧双Outbox未排空、新事务责任或已有绑定拒绝。`writers-excluded`只是声明。计划/连接预算有界，提交不明不自动重试。

安装入口本身不是保护/恢复工具。另已合并IAM PR142的`m3-messaging-recovery`限定保护/恢复，三档实际CLI各14项通过：真实版本表保护、原迁移锁、版本表漂移/新责任拒绝、受控部分DDL及范围外事实保留分别证明；不是实际生产AuthN验收或任意DROP/恢复授权。C2仍须完成三库组合。生产初始版本必须T30重新读取，未证实41或已有新增对象时阻断，不能force、伪造版本行或覆盖旧证据。

## QS与AI显式维护边界

QS使用原`qs-migrate-offline`，维护所持MySQL/Mongo连接及双库保护/批准，不启动API/worker/SDK。105独立上线仍阻塞T30及之后，不能并入M3切换或恢复到未兼容105的旧镜像。最终资源目标由冻结候选读取，不照抄规划初始106/41；恢复沿用原双库身份、保护、未知结果和不可逆启动边界。

AI的Alembic入口只构造显式MySQL engine和宿主迁移metadata；当前M3新增41事务表、42事件证据、43原生超限表，源码head为`0043_native_transaction_limit`。最终候选必须显式核对该head及迁移文件摘要，复用已验证TLS；不调用普通deploy apply的自动DDL/旧镜像fallback。旧`schema-maintenance`数据重构和历史MySQL迁云工具有各自的source/head/freeze契约，不能换个target参数就当作本轮M3授权。原模型checkpoint、Inbox/receipt和当前业务事实继续保留。

## 尚未完成的组合证据

本轮源码/隔离门禁不证明实际Nginx/gRPC入口、容器自动重启、全体工具、DB会话和未来计划已冻结。PR222已完成QS/AI显式维护/绑定的原三库步骤组合及源写者/保留责任复核；最终实际保护恢复附件由T29冻结。C3另处理原生有限回查恢复和持久notice的具名处置；缺少真实正向RPC审计仍封闭。T25-D收口工具组合，T29绑定最终镜像和30分钟演练，T30–T33才执行具名生产步骤。不会为关闭一个开发任务宣称生产已停写。

## 后续组件记录：禁DDL启动与初始绑定

IAM PR144、QS PR434已合并事务runtime禁自动DDL：最终配置须显式migration.enabled=false；仍只读核验原journal/双库完整head，不能以关闭DDL跳过schema/绑定检查。AI原启动仅执行只读schema-check，显式Alembic安装继续独立；普通deploy apply的自动迁移/旧镜像fallback不进入本次受审首次启动步骤。

AI PR220、QS PR435为初始绑定候选，未关闭C2。AI双档实际CLI已通过，但完整CI仍有旧草稿回放失败待复验；QS正在整合PR434并等待实际原双库CLI。两者只在显式安装后的原库内INSERT新owner绑定，私有计划/独立摘要/有效期、空新责任、原身份和schema均重查；不覆盖旧绑定，不将绑定当消息迁移或排空，不自动启动业务。QS两个owner分属两个原根，必须分别读取结果；任一失败/未知都继续停机，不删另一个已提交根来补偿。

最终三库组合仍需验证：IAM限定范围保护/安装/选择，QS原双库保护/显式完整DDL及两owner绑定，AI原保护/显式Alembic及单owner绑定；都经同一infra协调目录的独立受审步骤和单次摘要，不以声明替代真实全写者排除。最终生产命令、原对象/数据保护与恢复材料、实际版本/主机和具体镜像由T29冻结；T30之后才具名生产操作。


## 2026-10-24 全写者源码复核补充

固定IAM36456cdf、QS83147d8e、AI05d2db71的17份入口/装配/工作流原字节摘要见总表结构化证据。源码清单不证明实际旧镜像、外部caller、DB会话及自动重启已冻结，T29–T33继续回读。

| 入口 | 窗口内责任 | 必须保留的边界 |
| --- | --- | --- |
| IAM REST authz及gRPC scoped/managed replacement | 冻结授权写，核对原版本不再增加 | 保留AuthN登录、读取和session撤销；不能连带封闭全部HTTP POST |
| IAM maintenance dispatcher | scope/role-model/condition/statistics-operations/account-provision/reviewer-scope及authorization-migrate分别排除；DDL只走冻结C1步骤 | reliable-messaging当前仅只读preflight；tenant-retirement在连接DB前拒绝，不当作活动写者排空 |
| QS worker/runtime | 旧hold replayer、NSQ消费者与未来计划先交接；新consume-only deferred consumer承接原业务责任 | 关闭publish不证明未来计划无执行者；拆Topic不放大并发 |
| QS维护工具 | qs-operator prepare/recover apply、selected/orphan retire，以及qs-ai-messaging admission open单列权限 | 审计或close记录不授权其他工具apply/open |
| AI supervisor及维护 | generation/evaluation、旧mq_relay和显式semantic-contract恢复分开排除；保留checkpoint/provider unknown及receipt | 新事务模式不装配旧Relay，不证明旧容器/scanner已停 |
| 自动及手工部署 | IAM/QS原CD暂停继续保留；AI排除AUTO_DEPLOY_ENABLED及手工workflow_dispatch，schema-maintenance同样列入 | AI自动开关只门控workflow_run，不阻止手工触发 |

三库维护组合草稿PR222在同一C1目录执行真实宿主维护契约，再用明确标注的进程sentinel验证首个启动后的拒绝。它不代替实际业务runtime、原生产备份/恢复或全写者停写；门禁通过前不勾选C2。


## C2收口记录

PR222已合并a94c831，43项原生组合、17文件责任复核及10检查/11报告494项通过，C2为4/4。上述早期候选和失败描述按当时记录保留，最终合并/门禁以总表本条为准。源工具维护边界已完成，不表示生产入口、全部外部写者、自动重启或数据库会话已冻结；实际执行须T29固定附件、T30复核和具名批准，C3/D、system和48小时观察继续。


## 2026-10-24 已批准的首发恢复边界

用户采用[尽快上线方案](rocketmq-m3-fast-cutover-proposal.md)。T25-C3改为原库持久封新写、保留Checker/读取/审计、无自动解除和具名排障；高级手工resume/resolve工具完整四宿主验收移至[独立台账](rocketmq-native-recovery-followups.md)，未完成不算通过。

首发执行包排除尚未验收的`native-recovery recover/resolve-notice`及原生resume helper，CI专用`host-observer`也不部署。T29必须回读最终镜像与执行包验证排除，不以源码检查冒充镜像事实。原数据/notice/witness不删；超限后可用性受限，消息可能等待投递。具名修复不得执行新业务/模型、替换ID、伪造确认或旧备份覆盖。首次启动前原范围恢复及启动后前向修复边界不变。
