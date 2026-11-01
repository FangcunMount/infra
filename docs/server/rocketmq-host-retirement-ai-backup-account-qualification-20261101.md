# AI246 实际全备恢复、执行账户与PITR范围

本轮已补齐**当前AI完整逻辑备份的实际恢复资格**及**准备镜像的实际执行账户技术审查**。DB04采用完整备份路线，云PITR没有验收，不列入已通过项。发布继续冻结；真实停写排空、同窗口新冻结保护/全备及独立执行批准仍为No-Go。本说明不批准生产恢复、生产DDL或首次业务启动。数据及恢复责任人均为shujie。

入口：[执行总包](rocketmq-host-retirement-ai-246-execution-package-20261101.md)、[真实全备回执](../evidence/2026-11-01-ai246-real-backup-restore-qualification.json)、[账户回执](../evidence/2026-11-01-ai246-execution-account-review.json)、[PITR范围](../evidence/2026-11-01-ai246-cloud-pitr-review.json)。备份体、实际账户原文及私有诊断不进入GitHub/CI，只提交代码和脱敏资格摘要。

## 实际数据恢复结果

| 项目 | 已取得事实 |
| --- | --- |
| 源库 | 固定AI身份`04f11940…`；MySQL8.0.36、完整43、空`messaging_outbox`；51个InnoDB基表，404列元数据；无view/trigger/routine/event |
| 完整内容 | 8,503行、91,768,335原字段字节，含原ledger的一行29字节；49保留表8,502行/91,768,306字节，原事务凭证、模型/业务历史、ACK、Inbox、archive及调度均在内 |
| 导出 | 单连接REPEATABLE READ + WITH CONSISTENT SNAPSHOT, READ ONLY；19.361秒完成，事务及池释放，无FLUSH/LOCK/写者停机或源库DDL/DML |
| 归档 | 私有gzip JSONL完整逻辑备份，26,704,524字节；SHA256 `58a8625f5a56ff5607388766851ce2a546fdb4f21b410abda4d46680ebe9eae4`；原件与索引可用于重建全部定义和数据，非仅指纹 |
| 恢复目标 | 新建自有MySQL8.0.36容器，network=none、无发布端口、无生产连接配置；UUID身份不同于源库。专用本地凭据仅可访问该实例，未启动AI/SDK/模型业务 |
| 版本 | 官方MySQL不可变引用`mysql@sha256:65ce0889751900d2dd5fc5aa5a5fb59073d401fc43df2eae6bd6afb18e7626dd`，原始config `sha256:f5f171…cce9d4`。ServerA直拉超时后，复用既有CI40168876623的固定纯镜像导出，校验后离线加载；没有通过CI传输真实备份 |
| 实际恢复 | 权威第4次资格42.001秒完成；完整表定义、404列原始元数据和全部原字段指纹逐字相同，完整43/原目标0行；新连接24.272秒再次核验通过 |
| 字节绑定 | 恢复前后都校验同一归档SHA；恢复验证代码SHA `022f0863412fdafefa362930c8344ea4a40daeb2948cc3de15dde5c8aa39e73d`；捕获版本及代码见原回执，10个捕获路径函数AST与当前版本一致 |
| 隔离收口 | 所有既有容器ID与原AI启动身份不变；只停止/移除本轮标签匹配的自有恢复/验证容器，物理datadir、原件和失败诊断在root私有目录保留。未prune、未删除既有数据库/卷/历史备份 |

这些秒数是在限额的隔离实例上完成的实测，不是生产RTO承诺。当前捕获`frozen=false`，不能变更为已经停写或作为未来窗口的冻结备份。

### 数据与结构的保护方式

[备份/恢复代码](../../scripts/mysql/ai_backup_material.py)逐字段保存MySQL原始HEX/NULL，包含完整DDL、原始列元数据、全部行和逐表多重集摘要。恢复显式固定UTC，二进制使用HEX literal，文本/JSON使用原列字符集转换，数字用文本转换避免把`0x31`误作数字49。生成列不作为可写列重插，但其实际计算值仍参加全部行指纹比较；`DEFAULT_GENERATED`普通列照常恢复。空值、空字节、重复行及字段边界不折叠。

捕获预算固定20,000行、128MiB原字段、90秒；未知对象、非InnoDB、源身份/43布局变化、非空目标、超限或连接未释放均不出具成功资格。恢复只接受全归档完成标记、固定SHA、私有0600文件及当前进程所有权；目标必须是自有hostname、仅loopback的隔离网络、不同UUID、空AI库，先拒绝再执行CREATE/INSERT。没有通向生产的restore选项。

前两次实际恢复在`evaluation_completions`建表处失败，原备份与原诊断保留。原因是`INFORMATION_SCHEMA.GENERATION_EXPRESSION`的引号转义形式不能直接作为SQL执行；另有已知SHOW CREATE字符集introducer表示差异。当前代码仅解码受审AI表达式的元数据引号，要求除字符集introducer外与原DDL表达式结构完全相同，未知转义/表达式变化拒绝；用原元数据重建表达式后，仍逐字比较完整原DDL、全部原列元数据及内容，不归一化结果以掩盖差异。第3次完整恢复通过；第4次加入恢复前后归档SHA强绑定后再次通过，并用新连接复核。

## 实际执行账户审查

[固定只读探针](../../scripts/mysql/ai_account_observe.py)在准备镜像`sha256:e6afea10…d9470e`中，以实际UID10001、只读根和仅公共CA挂载运行，没有SDK/业务生命周期或模型凭据。使用原独立数据库网络ID连接，**不依赖运行中的f9网络命名空间**，与未来停机后的维护连接方式一致。数据库URL只经私有stdin传入，不出现在CLI参数、Git或公开回执。

| 绑定 | 本轮实读 |
| --- | --- |
| 实际principal指纹 | `eca7fff1f06f2f57d814a6f7ef4a964480fe97efeefd8447ff8c4a3a9bbe880a`，由server UUID、AI库名、CURRENT_USER绑定；与运行容器和准备配置一致 |
| 完整GRANTS摘要 | `0f2be53777c287113419b682e6029cc2f21b0d708dc757f6b4794b6d2a851249`；无活动角色、partial_revokes=0，无GRANT OPTION |
| 必要能力 | 全AI读取、目标表DROP、原ledger UPDATE的直接权限齐备。没有在生产执行DROP/UPDATE来测试权限 |
| 服务器与诊断会话 | read_only=0、super_read_only=0；诊断会话transaction_read_only=1，连接/池均释放 |
| TLS | VERIFY_IDENTITY与实际加密握手通过；只读挂载原公共CA，无私钥或业务配置挂载 |
| 账户边界 | 既有共享管理账户拥有AI整库ALL，另外涉及iam/qs/statistic_db整库权限、若干mysql表SELECT及PROCESS/复制读取/XA_RECOVER_ADMIN；**不是最小权限账户** |

[权限分类器](../../scripts/mysql/ai_execution_account.py)要求直接授权、无活动角色和部分撤销；相似库名、仅单表SELECT、未知GRANT结构均不能当作全AI权限。回执区分“具备操作所需能力”和“权限仅限目标”；后者并未成立，本轮没有GRANT/REVOKE、改密或创建生产账户。

正式独立执行审查必须逐字绑定：源库身份、principal、GRANTS摘要、准备镜像、独立网络ID、TLS/CA、真实执行UID和已审核工具。W04重新只读采集后与上述绑定比较；任何变化取消本次资格。账户审查原件摘要纳入writer库存的`inventory_sha256`，再由当前writer回执和保护/执行review引用；现有工具不会自动发现全部旁路或代替责任人签收。最终审查须明确接受现有较宽账户的受限使用，或另行指定/复审专用账户；不自动缩权，也不把管理员观察入口的全局可见性转移给此账户。

## 云PITR范围与本批选择

当前SQL可以读取MASTER STATUS和两份活动binlog清单，log_bin=true、配置保留2,592,000秒。这不等于已取得云端成功全备、连续归档日志或实际可恢复时间范围。本机与ServerA没有已配置的云CLI访问配置，本轮没有创建收费RDS实例、修改云备份策略或启动云恢复。

[RDS恢复说明](https://www.alibabacloud.com/help/en/rds/apsaradb-rds-for-mysql/restore-full-data-of-an-apsaradb-rds-for-mysql-instance)及[日志备份说明](https://www.alibabacloud.com/help/en/rds/support/use-the-log-backup-feature)将云日志备份/恢复过程与SQL端本地日志配置区分。本批明确采用**已实测的完整逻辑备份路线**；云PITR未验收且未纳入已通过项。若以后选用云PITR，仍须取得实例级成功备份集、连续日志/最早最晚恢复时间，并实际恢复到隔离目标、验证所选恢复点及完整数据。当前记录不借配置值替代这些证据。

一致快照使用InnoDB的[一致性非锁定读](https://dev.mysql.com/doc/refman/8.0/en/innodb-consistent-read.html)；[事务说明](https://dev.mysql.com/doc/refman/8.0/en/commit.html)要求正确隔离级别。当前代码显式REPEATABLE READ与READ ONLY，并比较捕获前后结构，不借此声称已经排除写者。

## 正式窗口如何使用，不预填窗口事实

1. W00/W01签收本轮方法、实际恢复资格及账户审查；发布继续冻结。本轮live备份永久保留其原始`frozen=false`和时点，不改名为未来窗口材料。
2. W03在另行授权的真实窗口排除全部写者，210秒正常排空，保留Broker持久待办、原调用/事务和所有历史；不取消未知调用或补发模型。
3. W04重采AI管理员锁/依赖观察，并用实际维护网络/镜像只读核对当前账户、权限、TLS及库身份；责任人签收包括本轮账户审查原件的新库存摘要。
4. W05在实际排除仍有效期间，重新运行受核只读全备捕获，输出到宿主持久私有文件，源URL和凭据只从受核配置经私有stdin提供；不输出到终端/CI。另运行原`publisher_window capture`生成带真实writer attestation的frozen保护。两份独立一致快照在全程真实排除写者的前提下须逐表匹配定义/字节、ledger和目标，时间均处于writer有效期内。
5. 对当次新备份和保护做两地回读/SHA/fsync。新窗口备份的源身份、代码SHA、原DDL、头、principal及全部指纹必须匹配该窗口；数据/结构变化、预算超限或新状态不被旧资格覆盖时保持No-Go，重新恢复核验。
6. W06独立签发原有review/v2及SHA，之后才允许既定单目标DDL/正常ledger前向。当前备份和本说明都不能作可消费批准，也不改变原持久consumed和首次重开屏障规则。

恢复资格只批准方法和介质的可审查性：恢复目标为新隔离实例，不能直接变成第二业务主库；生产恢复/路由切换须另审权威副本、绑定代际和全部新增事实。首次业务重开已发出或有新44事实后，仍只允许44兼容前向修复，不准把旧43/全备覆盖回现库、回放旧ledger、重建旧表或删除新事实。

## 本轮验证与原件

20项定向纯测试覆盖HEX/NULL/字符集/JSON、生成列与DEFAULT_GENERATED、未知转义/表达式拒绝、SHA与私有文件/网络边界、直接权限/角色拒绝和既有切库边界；实际恢复与新连接完整复核另有真实数据原件。原始备份仅在MacBook/ServerA0700目录、0600文件保留，至少30天且未结延期；SQL诊断、前两次失败、两次完整成功以及代码/镜像来源原件不删除。自有datadir在root私有父目录下保留原MySQL文件权限，未触碰既有卷、旧备份或其他四候选对象。

15:30:14UTC最终现库只读仍完整43、目标0行、全部49保留表指纹与备份相同；原f9容器healthy/restart0/原启动时间，AI自动发布false、QS工作流disabled_manually。未停生产业务、未执行生产DDL/DML、未签发/消费生产批准，M5尚未生产发布。

审查收口：精确提交`e6ff4a553b3a30173fafc90d7fc7267acf7ce5ca`的[CI41322507227](https://github.com/FangcunMount/infra/actions/runs/41322507227)成功，20项测试和编译通过，原始日志ZIP CRC通过。66份新审查原件及索引归档259,408字节，SHA256 `7a2b8111c9e512357032955e5bfe96346534c7a050af6f93281953a6b1cde54b`，MacBook/ServerA两地逐成员回读/SHA/fsync通过；真实备份与官方MySQL镜像单独保留。归档复制回执外置并同样两地保存，不声称收录于自身归档。15:46:07UTC再次实读AI自动发布false、QS disabled_manually、原f9 healthy/restart0/原启动时间。DB05仅剩真实窗口材料和批准持久消费；本轮未发出生产执行批准。
