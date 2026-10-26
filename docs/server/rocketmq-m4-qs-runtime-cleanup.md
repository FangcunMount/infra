# M4 QS API/worker 生产消息装配清理

本文记录C02-02范围及替代证明；进度仅由[M4总表](rocketmq-m4-execution.md)维护。验收源码为[QS PR450](https://github.com/FangcunMount/qs-server/pull/450)的`9850d15f0fdc385ca8c5a6dd30e394145ee7a89c`；[infra PR322](https://github.com/FangcunMount/infra/pull/322)提供真实依赖验收。实现、门禁与源码合并已完成；最终镜像/生产部署分别记账。

## 当前唯一装配

API实际组合根在资源初始化前校验显式RocketMQ、完整`qs.mysql`/`qs.mongo` owner和关闭的旧发布Outbox。只构造原双owner事务子系统及catalog筛出的NORMAL通知发布器；原owner构造器继续校验精确绑定、冻结文件及预算，不执行DDL。旧NSQ channel准备和wire publisher工厂从组合根退出。

Worker在资源准备及运行装配入口均拒绝NSQ、发布模式与任何事务owner；保持consume-only RocketMQ、当前deferred consumer、hold证据与原共享消费预算。旧NSQ channel准备、发布客户端及hold replayer不再由生产组合根创建。`NSQMessageTimeout`名称仍用于当前9分钟配置/8分30秒处理时限，本批保留其真实用途。

| 退出对象 | 继续保护的性质 | 替代证明 |
| --- | --- | --- |
| API旧NSQ与标准Outbox选择/自动channel准备 | 配置错误在资源打开前拒绝；当前双owner/NORMAL及启动失败清理 | 新拒绝矩阵、原resource/lifecycle单测；当前双owner真实Broker/MySQL/Mongo原生入口 |
| Worker发布与hold replayer装配 | 当前消费幂等、业务重试/hold授权、真实在途排空 | 新consume-only拒绝矩阵和48共享并发/处理时限单测；真实worker/Broker原生入口 |
| `standard_event_subsystem_m4_integration_test.go` | 当前事务与witness原子提交、冻结身份、部分失败/关闭 | 当前双owner宿主原生测试13项；当前owner和事务领域测试继续执行 |
| `standard_event_fair_scan_m4_integration_test.go` | 当前未来调度不提前、不重做业务、保留原授权/attempt及首wire | 当前evaluation/report实际到期dispatcher原生测试；不宣称继续支持已退出的Outbox fair-scan |
| `m4-standard-process-proof.sh` | 退役入口不可启动旧环境/产生副作用 | 正常/额外参数均先exit 2，stub断言Docker/Go/Git/mktemp零调用 |

原native报告明确区分当前宿主组件、真实Broker退出与生产者全进程退出，不以完整API或system验收命名；worker原生夹具使用有界测试并发，生产48预算由独立单测及C06/C08验收保护。

## 保留与后续归属

- 当前答卷、评分、报告、Task、QS↔AI业务事务及witness、Checker、冻结输入和NORMAL逻辑订阅均保留。
- 到期dispatcher、RetryDecision、attempt、原授权、消费幂等、hold技术重试及治理记录保留；不把发布扫描与业务恢复混为一体。
- 旧私有`buildM4StandardEventSubsystem`只供孤立旧测试/历史catalog规格读取，当前生产入口不再调用。残余helper、旧工具与中间夹具由C04清理，不将本批描述成旧代码全部删除。
- catalog的`outbox_profile`暂仍为逻辑职责分类，Store列为历史实现映射，不能据其名称认定Relay仍启用。C04/C05后续收敛。
- 历史表、迁移、首wire/ACK、Inbox、receipt、未决证据、备份与NSQ卷均不删除；C03/C05/C07分别处理读取、职责和资产。
- `run-retired-outbox-contracts.sh`固定不可变历史源码，继续隔离验证旧存储契约，不属于生产启动入口。

本地264项相关race通过且零失败/跳过；integration tags仅编译，不替代真实依赖。infra工具374项单测通过；actionlint和docs-check通过。真实三档门禁结果与合并信息在完成后补入receipt。本批无SSH、生产部署、生产DDL、凭据轮换、业务/模型调用或资产处置；生产CD保持暂停。

## 验证进度与失败保留

报告夹具漏装现行Mongo43治理schema，原保护正确封闭准入；现只在隔离夹具显式安装并核对原生读取，专项14项通过。第二轮两档各65项通过，8.4的worker第二输入在60秒等待处超时；恢复实例尚未经过与暂停实例相同的接收就绪屏障，原诊断还在恢复清理后读取暂停实例。现补齐相同屏障并在清理前读取活跃实例，保留全部五个物理输入、共享1与原60秒断言；三档worker专项各11项通过。此结论不扩展为生产延迟/SLA或SDK吞吐保证。

以下为合并前记录；最终结果见下一节。[receipt](evidence/rocketmq-m4-c02-qs-runtime-20261026.json)保留失败、源码、SDK、原始报告摘要和清理结果。中间FD源码的29项CI与当前9850候选CI分别记录，不能混称。当时尚未合并或部署，完成数维持17/38；此历史记录不覆盖最终状态。

## 完成证据

[QS PR450](https://github.com/FangcunMount/qs-server/pull/450)29项CI通过后合并`ca1158ca472d42e7c58e067e170b116364b1d8ea`；[infra PR322](https://github.com/FangcunMount/infra/pull/322)15项CI全通过后合并`18ad52057dbf3859198b9a9e274da333330df443`。最终[矩阵40314640918](https://github.com/FangcunMount/infra/actions/runs/40314640918)三档各65项通过：双owner13、worker11、原到期dispatch41，零失败/跳过，九报告和三汇总身份/摘要及完整清理已核对。所有宿主实际使用固定稳定Go SDK v0.5.0及原内容摘要，没有本地replace。源码CI只有生成文档条件job未触发，非用例跳过。

[完整receipt](evidence/rocketmq-m4-c02-qs-runtime-20261026.json)分开记录FF本地、FD中间源码和9850最终源码、两轮失败、专项复验、全矩阵及合并。C02-02进度记录合并后为18/38、C02 2/4；C02父任务尚未完成。没有生产部署或业务验收，最终镜像与部署归C08。
