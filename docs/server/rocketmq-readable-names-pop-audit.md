# 可读资源切换：POP 只读审计准备

**本页不证明排空、不授权维护或删除。** 当前9个Group/15客户端均登记为`CONSUME_ACTIVELY`；固定Proxy的SimpleConsumer登记方式与Broker普通lag指标的POP分支不一致。因此，普通lag/in-flight/ready的0不能单独作为切换门禁。

已只读核对serverD：POP offset/checkpoint buffer当前0；8个revive队列各保留1条原生记录。revive lag的Prometheus名称虽带milliseconds后缀，固定实现实际返回记录数，不能据此按时间单位解读或直接忽略。当前只完成其中一个队列尾部记录的精确核对：确为ACK，Broker未重启或变更，尚未检查所有队列及全部责任。

`inspect_record` 是纯函数，只接受固定5.5.1格式、当前集群的唯一revive系统Topic和8个固定队列。它校验CQ提供的位置、消息版本、总长度、原始body CRC、topic及metadata种类；拒绝业务Topic、压缩、截断、缺失计数和未知格式。只输出种类、计数及摘要，不输出正文、用户、租户、group或wire；**始终`drain_proven=false`，不会根据ACK或CK位图确认业务或触发恢复。** 无I/O、线程、MQ依赖或构造副作用。

原生核验在Broker原容器内使用只读CQ查询和`dd if=...`读取该系统记录的精确有界字节，不启动新容器，不写Broker文件，不确认/重投/更改offset，不修改Broker配置。输出保存在本机0600文件，仅[脱敏证据](evidence/rocketmq-readable-names-pop-record-20261028.json)进入仓库。此前通过Dashboard只读view查询未成功，未将失败算成成功，也未为此修改Dashboard、网络或权限。

后续仍需所有队列的精确尾部区间、原生重试资源、四owner确认和业务receipt、消费真实在途及隔离持有消息/恢复控制。只读ACK记录不等于所有在途清零；缺数据或不确定时维持未通过，不自动修复、删除、补发或重做模型。

固定上游：[MessageDecoder](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/common/src/main/java/org/apache/rocketmq/common/message/MessageDecoder.java)、[MessageSysFlag](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/common/src/main/java/org/apache/rocketmq/common/sysflag/MessageSysFlag.java)、[PopCheckPoint](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/store/src/main/java/org/apache/rocketmq/store/pop/PopCheckPoint.java)、[AckMsg](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/store/src/main/java/org/apache/rocketmq/store/pop/AckMsg.java)。具体blob见证据文件。唯一任务进度见[总表](rocketmq-readable-names-execution.md)。
