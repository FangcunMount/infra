# RocketMQ 具名恢复维护工具（实现中）

这是infra维护的短生命周期SDK宿主，尚无可用于生产的CLI。共享Go SDK可在相同原主库读取Go/Python MySQL见证及Go Mongo见证，不新增常驻服务；业务宿主继续拥有业务池、原业务事务、正常Checker及维护。

当前包含`internal/checkonly`和`internal/observation`原语：构造纯验证；拒绝Lookup/Reserve/Prepare/Abort和常规半消息/最终确认记账；本实例Reconcile明确不处理，不能把零解释为没有Prepared。权威Evidence及真实RPC后的RecoveryReceiptRecorder仍借用原Store，DB预算2秒。本次目标的终态漂移返回Unknown，不据旧成功时间伪造本次回查。

固定SDK会保留首次正向审计时间。包装器只在SDK实际RPC后调用原审计成功，再发出当前Reference摘要/终态观察；重复回查不改首次时间，仍可有本次观察。观察不证明消费完成或操作授权，原始wire、ID、能力token及凭据不输出。私有I/O尚在运行时不提前返回取消，保留真实回查容量。

目前纯测试使用明确命名的fake authority/callback，不是实际RPC或双存储验收。构建使用固定发布Go tag tx.4，不用本地replace；没有更改SDK源码/codec/schema。已构造私有 SDK runtime（不暴露 Sender）、有界排空证明及每次真实 RPC 后置回调的独占0600文件：每实例最多16个观察，摘要绑定请求/本次nonce/源码/Reference，文件和目录同步失败或取消均不能形成成功证明。

固定 SDK 在 StopAdmission 后拒绝 Start。工具的 Store 从构造起拒绝所有执行，私有 runtime 先 Start，再立即 StopAdmission；不提供外部发送接口，不将此顺序写成先停 SDK 再启动。Close/Wait 不吞 ShutdownIncomplete；Stopped、零真实在途/队列、无发送/本地回调/中止维护、正向 RPC 和 audit 完整后，才能封存私有观察。仍待原库 snapshot、审批图、物理检查、治理 CAS 与真实矩阵，不能据纯测试冻结生产 CLI。

任何可确认消息的SDK启动都必须由infra不可逆首次运行屏障包裹，不能当作允许旧备份覆盖的DDL维护。完整进度以[唯一总表](../../docs/server/rocketmq-m3-execution.md)为准；不授权生产，M3/T25/C3均未据此关闭。
