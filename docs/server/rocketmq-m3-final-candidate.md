# M3 最终候选准备与验收边界

唯一任务进度见[M3总表](rocketmq-m3-execution.md)。本页细化原T29，不增加任务数。T28正式制品宿主门禁已完成；以下为最终候选准备，不表示T29完成或生产授权。

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

## 通用SDK门禁默认版本同步

首次PR238旧源码dedbd391的旧SDK bfaae2b在共享消费预算测试等待received超时，29通过/1失败/0跳过，原声明清理通过。根因尚未确认，[原失败证据](evidence/rocketmq-m3-image-ci-first-failure-20261024.json)保留。已正式发布的1345266在T28两档同类完整故障各48项通过。通用Docker/public/fault/limits/resource CI默认引用同步1345266；所有用例、90秒等待、队列/并发和错误门禁保持原值，独立原生index生成fixture仍绑定其原版本。旧SDK可显式传SHA复现，不把新版本通过称为旧版本bug修复。新head全部门禁未通过前不合并辅助实现、不勾选T29。

镜像inventory另记录实际构建工具的完整infra SHA，并要求等于workflow事件SHA；同时记录原Dockerfile摘要。构建、配置资源冻结、恢复/启动演练分别保留证据。

## IAM实际镜像组件演练（开发中）

`rocketmq-final-images.yml`保留默认build路径，新增显式iam-start阶段：只从指定Actions运行下载已核验IAM归档，在托管runner隔离内部网络启动依赖。使用固定IAM原迁移/Bootstrap准备完整schema41，先沿真实NSQ SDK排空夹具bootstrap消息，再停止旧进程。候选镜像自带原iam-maintenance执行有限范围保护、42–45安装、恢复至41、原事实摘要复核、再次安装及绑定；最后用修复后的标准JSON配置封新写启动原apiserver，核验Checker/采样/预算指标并真实关闭。

这只是T29的IAM组件，不能替代完整五镜像组合、原协调目录首次启动屏障、QS双库/AI原范围恢复、最终执行包或30分钟窗口。只有组件真实报告通过后才更新状态。该路径不SSH、不接生产、不使用外部凭据，不执行模型或system登录；CI原始日志/配置/保护文件不上传。完整schema41准备程序仅是隔离夹具，不进入生产镜像或执行包。
