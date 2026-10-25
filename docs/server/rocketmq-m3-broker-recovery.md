# serverD Broker 恢复与管理员凭据更换：具名执行清单

状态：**待独立生产批准，尚未执行**。M3仍28/36；本清单只恢复现有RocketMQ，不批准业务切换。目标、原CID/镜像/资源/私网端口、三个配置文件摘要及实际认证元数据位置见[固定计划](evidence/rocketmq-m3-broker-recovery-plan-20261025.json)。执行前冻结该文件精确SHA-256；任一目标、状态或摘要变化即停止重新审阅。

## 范围与依据

通过Mac mini固定个人SSH入口操作serverD。只对原`rocketmq-broker-1`执行一次启动及更换后一次重启；保留原5.5.1镜像、1280MiB/1.5CPU、`100.118.164.39:8081/5557`、数据卷和48小时保留设置。NameServer、NSQ、三个worker、数据库及应用容器不重建、不重启；不创建Topic、账号、ACL或执行schema/provider切换，不修改Tailscale或防火墙。

只更换原管理员密码，保留username、Super/Enable、内部账号和原权限。更换`broker.conf`、`proxy.json`、`tools.yml`中的同一管理员密码；不把初始化JSON变更当作持久用户更新。新密码由目标机安全随机生成256bit，保存在本次root私有目录0600文件，禁止聊天、命令日志或公开报告输出。

[固定5.5.1 BrokerStartup](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/broker/src/main/java/org/apache/rocketmq/broker/BrokerStartup.java)将实际AuthConfig路径设为`storePathRootDir/config`。本次只读实际找到`/data/infra/rocketmq/store/config/users`和`acls`，各8个文件；`/data/infra/rocketmq/auth`为空，不能将其误记为完整用户备份。[元数据实现](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/auth/src/main/java/org/apache/rocketmq/auth/authentication/provider/LocalAuthenticationMetadataProvider.java)写RocksDB并flushWAL。原用户必须通过真实`updateUser -u … -p …`更换，`-p`不能与互斥的`-t/-s`同时使用。

变更原语/隔离测试由infra PR268维护。CLI输出用户类型/状态为枚举，按精确语义忽略大小写比较；旧凭据拒绝必须为新Java进程读到真实NO_PERMISSION（CODE16），不能用网络超时冒充。判定依据见[AuthenticationPipeline](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/broker/src/main/java/org/apache/rocketmq/broker/auth/pipeline/AuthenticationPipeline.java)、[ResponseCode](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/remoting/src/main/java/org/apache/rocketmq/remoting/protocol/ResponseCode.java)。[实际隔离复验40153370577](evidence/rocketmq-m3-admin-rotation-validation-20261025.json)为8/0/0，五项纯契约通过；首轮枚举校验失败在密码写入前停止，原失败另存。PR268精确76906037的10项源码CI全部通过，已正常合并63b5cc0b；代码与验证门禁已具备，生产执行仍等待本清单的独立具名批准。

## 执行顺序与停止点

1. 再读hostname、原CID/image、停止/143/无OOM、NameServer健康、三个worker和原部署锁；核对原配置摘要/模式/UID3000及私网绑定。沿用原部署互斥锁，冲突即停止。读取磁盘余量和数据规模，完整冷备份所需空间不足则停止；不得清理旧卷或镜像腾空间。
2. Broker保持停止。在新建且不可覆盖的root0700私有目录中冷备份原`store`（含真实users/acls）、`auth`及三个原配置，归档0600，保存逐文件指纹、归档摘要和原inode/属主/模式。将备份经原个人SSH路径复制到Mac mini私有备份目录并核对摘要，再允许启动；保留至少30天，有未结责任延长，不自动删除。
3. 原始三个配置先用`admin_rotation.prepare`验证同一管理员及无冲突；生成新凭据和替换文件的私有副本。保存旧/新tools的独立短生命周期客户端目录，Java用`-Drocketmq.home.dir`指定，不修改全局工具factory。
4. 执行`docker --host unix:///var/run/docker.sock start rocketmq-broker-1`。单次有界等待健康，最长180秒；不循环启动、不重建容器。新鲜原凭据客户端验证精确原用户、密码、Super/Enable。任何不一致或超时进入失败路径。
5. 经原管理员执行真实`updateUser`，在调用前记阶段，收到明确成功后才继续；回复未知时不继续写配置或重启，不盲目重发。原账户更新后对三个现有配置inode原位写入并fsync，保持0640、UID/GID3000；保留原文件inode是为了覆盖独立`tools.yml`文件bind mount。非管理员字段逐项保持。
6. 对同一个原Broker执行一次`docker --host unix:///var/run/docker.sock restart --time 90 rocketmq-broker-1`，有界等待180秒。用相互独立的全新Java客户端依次验证新凭据成功、旧凭据明确CODE16、新凭据再次成功；验证默认tools也使用新凭据、持久用户类型状态未变、三个配置读取一致、原CID/image/资源/端口不变。
7. 只读回读有效`transactionTimeOut`、`transactionCheckInterval`、`transactionCheckMax`和`fileReservedTime`，白名单解析后输出，不输出完整getBrokerConfig/listUser/getAcl。读取现有Topic/ACL只为后续冻结，不创建或修改。核对Broker健康、Mac mini原Broker监控target恢复、系统可用内存≥512MiB、无OOM/非预期重启及三个worker状态保持。
8. 脱敏回执分别记录启动、真实密码更新、三份配置持久化、重启、三段认证结果、有效参数、内存/监控及worker前后对比。移除本次容器内短期旧/新工具认证目录；新运维凭据及冷备份留在私有保管范围。明确生产Topic/ACL/schema/provider及业务准入仍未切换。

## 失败处理

只停止原Broker（`docker stop --time 90 rocketmq-broker-1`），不停止NSQ或worker。保留阶段、新凭据、私有错误捕获及原冷备份；不因RPC回复丢失恢复旧密码，不自动覆盖RocksDB或store。后续按精确阶段读取持久事实、使用新凭据具名修复。Broker无法停止、发现实际资源/绑定变化或影响其它服务时停止自动操作并报告。

启动前失败保留原停止状态。启动后验证失败不能宣称恢复成功；不通过关闭认证、放宽TLS/ACL、换新容器/数据卷或临时改公网入口绕过。30分钟M3业务维护窗口尚未开始，本步骤的生产批准只涵盖本清单，后续M3具名业务切换仍单独确认。
