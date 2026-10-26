# M4 AI 最终事务运行装配清理

C02-03实现、验证与合并完成，进度由[M4总表](rocketmq-m4-execution.md)维护。[AI PR228](https://github.com/FangcunMount/qs-ai/pull/228)固定候选`9a48509e777b4b0a819308dd05b7db7fff9af42f`，合并`a2f192733312fef591bb9be24e5e3892e470420e`；[infra PR326](https://github.com/FangcunMount/infra/pull/326)增加固定版本原生验收，合并`8c798db7c5f71c968740e6f0bcb7e5179392e811`。本批没有部署生产。

## 当前唯一运行路径

`serve()`与`MessagingRuntime.create()`调用同一`require_final_messaging()`，在TLS、密钥、容器和数据库资源获取前拒绝禁用、NSQ、空owner、仅普通消息及错误owner选择。只接受显式RocketMQ和精确`ai.mysql`；具体数据库绑定、路由、材料及预算仍由原构造器校验。原AsyncSession根事务归属不变，启动只读检查仍先于运输构造，不执行DDL。

生产组合根仅保留原TransactionServices、TransactionMessagingStore、TransactionOnlyEvents、TransactionCommandReceiver、command/ACK订阅及ArchivePayloadReader。退出NSQ publisher/subscriber、普通发布器及MQRelay的生产选择与清理分支。构造函数没有新增后台任务。

| 退出对象 | 保护责任 | 当前替代证明 |
| --- | --- | --- |
| NSQ/普通发布/Relay组合根分支和后台组件 | 原业务事务/witness、首wire/receipt、Checker和消费幂等 | 资源获取前拒绝矩阵；正式SDK下QS↔AI真实依赖配对 |
| 原publisher start/stop、relay step专用夹具 | 真实在途、取消、有界关闭、失败启动清理及宿主pool归属 | 当前owner生命周期/单进程监听器测试；13个关键函数AST与基线完全相同 |
| 单项旧NSQ启动集成测试及旧`ai-messaging.yml`镜像workflow | 当前装配检查及旧存储/SDK隔离回归 | 主CI完整分片及现行镜像导入/配置拒绝；下层旧契约测试仍执行 |
| `smoke_single_process.py`旧NSQ环境启动 | 废弃入口不能创建外部资源 | 正常及额外参数均先exit 2，stub校验Docker/OpenSSL/Git零调用 |

主CI镜像检查保持network-none、read-only、nonroot；它只证明容器内导入、惰性容器构造和缺owner拒绝，不等于最终镜像完整启动。后者由C08重新固定镜像并验收。未删除SDK通用兼容包、Mac mini开发NSQ或仍承担业务责任的旧名存储。

## 验证及边界

[源码CI 40324335333](https://github.com/FangcunMount/qs-ai/actions/runs/40324335333)12项检查通过；两档MySQL各5724项、合计11448执行，0失败/错误/跳过。每档四分片互斥且并集覆盖全部收集用例；CI虚拟合并与候选源码树相同。本地82项当前装配/事务/生命周期/文档拒绝测试、Ruff、mypy 454文件、75份Markdown/1395链接检查通过。

[原生矩阵40325144474](https://github.com/FangcunMount/infra/actions/runs/40325144474)固定Python 3.11/3.13 × MySQL 8.0.36/8.0.44/8.4.11；每档实际五测试、25项事实、0失败/跳过，完整清理。使用稳定Python SDK 0.4.0下载wheel及Go v0.5.0，无editable/replace。验证实际AI默认接收器与空闲Checker、Go QS command/event组件、原业务/档案/witness根事务、首wire、重复receipt/ACK、正文鉴权与取消，不调用真实模型。

报告使用合成只读来源，不宣称完整公开HTTP、system登录、生产部署或吞吐验收。本批原生矩阵不含网络包故障；C02-04另行执行进程退出/Broker重启并单独记录。

## 历史及后续

新增拒绝测试先红后绿；旧publisher/relay夹具首轮22失败、37通过，更新为现行装配并保留原监听、pool、取消、启动清理断言。文档首轮92处陈旧hash/装配事实失败，改为追踪共享guard的AST检查，并新增破坏guard、owner与资源顺序的拒绝测试。两处重命名标题锚点随后修正；该中间stdout已覆盖，只记录观察，不声称保留原始失败文件。

四份混合旧语义的运行文档明确标为`needs_review`，C04尚未完成。旧Payload/Operation读取、临时协议工具、历史reader及混合存储职责分别由C03/C04/C05处理。`result_outbox`当前ACK/state历史、Inbox/receipt、首wire/签名密文、response/checkpoint/artifact、attempt与业务授权、witness和未决证据均保留；表、卷、备份没有处置。

[完整receipt](evidence/rocketmq-m4-c02-ai-runtime-20261026.json)记录源码、源码树、CI、报告摘要、镜像digest、版本、失败与保护映射。C02-03记录合并后为19/38、C02 3/4；生产CD继续暂停，C02-04、最终发布/部署及业务验收分别计数。
