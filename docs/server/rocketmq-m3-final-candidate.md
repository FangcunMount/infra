# M3 最终候选准备与验收边界

唯一任务进度见[M3总表](rocketmq-m3-execution.md)。本页细化原T29，不增加任务数。T28正式制品宿主门禁尚在执行；以下为独立准备，不表示T29完成或生产授权。

| 子项 | 当前状态 | 完成证据 |
| --- | --- | --- |
| 镜像及维护二进制 | 准备中 | 五个原Dockerfile实际构建、源码SHA/模块/wheel身份、image config ID/归档摘要、UID及恢复工具排除清单 |
| 配置、资源与执行包 | 待开始 | 实际所需M3 events/routes/owner绑定、禁自动DDL、封新写配置、ACL/TLS/资源摘要和原维护命令逐项绑定 |
| 原范围恢复、启动与窗口 | 待开始 | 最终候选实际恢复/启动和切换演练，具名步骤及耗时证明30分钟目标；不能用进程sentinel代替实际runtime |

## 仅构建路径

`rocketmq-final-images.yml`只在GitHub托管隔离runner构建原IAM、QS API/collection/worker及AI Dockerfile，保存独立归档与小型inventory报告；不登录registry、不推latest、不SSH、不连接生产、不修改CD暂停、不启动业务入口。PR仅运行离线证明解析测试，实际构建须显式dispatch。

输入是三个已审源码完整SHA和显式Go镜像UID/GID（源码默认2000）；AI原Dockerfile固定10001。必须在T30对照实际主机身份，不把默认值当生产事实。候选归档只使用固定SHA命名，报告记录image config ID、归档SHA256、真实runtime二进制模块Sum或安装包版本。源码/已安装版本不能代替运行健康、业务接受或系统登录。

QS当前runtime镜像没有`qs-migrate-offline`。候选构建从同一固定源码构建原Linux/amd64工具，并注入真实40字节GitCommit，作为独立附件；不写替代DDL工具、不另开数据库事务。原IAM镜像已经带iam-maintenance，AI镜像含原迁移源码。执行包只放明确受审步骤及所需附件，不能全量复制infra工具目录。

实际rootfs只读枚举，不解包到宿主；拒绝路径逃逸及未验收`host-observer`、native_recovery.py、native-resume helper、JavaNativeHalfManaged。原业务恢复代码与SDK Checker继续保留，不能因文件含recovery字样误删。排除镜像内工具不代替执行包审查，二者必须分别通过。

## 仍须完成

镜像inventory不是恢复/启动演练；本路径明确输出`runtime_ready=false`和`cutover_rehearsal_complete=false`。最终配置必须另行挂载M3事件清单与route revision，保持原三个worker资源/并发；不得依赖镜像默认NSQ配置启动。最终镜像、配置、保护范围与执行清单齐全后才提交具名生产确认。

105独立生产前置、T30实际版本/对象身份、合法system登录以及上线后48小时观察继续保留。首次新runtime命令之前按原批准范围恢复；发出后保留不可逆启动屏障，只做兼容前向修复。未决事务/notice/witness和历史保护资产不清理。
