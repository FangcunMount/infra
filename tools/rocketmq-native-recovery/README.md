# RocketMQ 具名恢复维护工具（实现中）

这是infra维护的短生命周期SDK宿主，尚无可用于生产的CLI。共享Go SDK可在相同原主库读取Go/Python MySQL见证及Go Mongo见证，不新增常驻服务；业务宿主继续拥有业务池、原业务事务、正常Checker及维护。

当前包含`internal/checkonly`和`internal/observation`原语：构造纯验证；拒绝Lookup/Reserve/Prepare/Abort和常规半消息/最终确认记账；本实例Reconcile明确不处理，不能把零解释为没有Prepared。权威Evidence及真实RPC后的RecoveryReceiptRecorder仍借用原Store，DB预算2秒。本次目标的终态漂移返回Unknown，不据旧成功时间伪造本次回查。

固定SDK会保留首次正向审计时间。包装器只在SDK实际RPC后调用原审计成功，再发出当前Reference摘要/终态观察；重复回查不改首次时间，仍可有本次观察。观察不证明消费完成或操作授权，原始wire、ID、能力token及凭据不输出。私有I/O尚在运行时不提前返回取消，保留真实回查容量。

目前纯测试使用明确命名的fake authority/callback，不是实际RPC或双存储验收。构建使用固定发布Go tag tx.4，不用本地replace；没有更改SDK源码/codec/schema。已构造私有 SDK runtime（不暴露 Sender）、有界排空证明及每次真实 RPC 后置回调的独占0600文件：每实例最多16个观察，摘要绑定请求/本次nonce/源码/Reference，文件和目录同步失败或取消均不能形成成功证明。

固定 SDK 在 StopAdmission 后拒绝 Start。工具的 Store 从构造起拒绝所有执行，私有 runtime 先 Start，再立即 StopAdmission；不提供外部发送接口，不将此顺序写成先停 SDK 再启动。Close/Wait 不吞 ShutdownIncomplete；Stopped、零真实在途/队列、无发送/本地回调/中止维护、正向 RPC 和 audit 完整后，才能封存私有观察。仍待原库 snapshot、审批图、物理检查、治理 CAS 与真实矩阵，不能据纯测试冻结生产 CLI。

任何可确认消息的SDK启动都必须由infra不可逆首次运行屏障包裹，不能当作允许旧备份覆盖的DDL维护。完整进度以[唯一总表](../../docs/server/rocketmq-m3-execution.md)为准；不授权生产，M3/T25/C3均未据此关闭。


## 原主库只读 snapshot（候选）

`internal/authority`目前覆盖iam.mysql/qs.mysql/ai.mysql的MySQL读取。显式配置选择原pool，操作输入只含operation/branch/fence和原物理索引摘要，不从消息属性选择连接。每次新建2秒上界的只读RepeatableRead根事务，检查实际server UUID/database/primary flags、原绑定、精确执行+witness、v2事务物理Topic及原治理notice；Prepared/矛盾/缺行/错误owner或epoch/无效receipt均拒绝，错误不返回部分snapshot。

不SELECT execution token、冻结plan/wire或业务正文；不更改任何SDK、业务、Outbox或治理行，不执行DDL。首次正向audit只作为before状态，旧时间不能证明本次RPC。固定IAM45治理模板仅用于隔离测试，摘要0d0df3ac8dcc10ebbe9e735ee0a8da600f0eefb3cdc6f33da276c975500e0e5a，不是操作器安装资源。原生测试在GitHub-hosted回环MySQL服务中显式安装自有数据库，真实原事务提交/SDK中止、读回、拒绝和删除回读分别记账；“旧audit”是命名的受控fixture，不冒称真实RPC。Mongo、批准文件图、物理检查、治理CAS及完整CLI仍待实现。

首次存储CI 40039265183 在编译前发现根忽略规则排除了 SQL 测试模板，三档均0通过/1 setup失败/0跳过，尚未连接自有测试数据库。报告保留；仅对这一个公开固定模板增加跟踪例外，并把embed与摘要检查放入普通纯测试，使缺失资源在基础编译门禁就失败。不放宽数据库dump忽略规则。


## qs.mongo 原主库 snapshot（候选）

Mongo适配显式绑定qs.mongo，固定原client/database的Primary/Majority；构造不连接。2秒总预算覆盖已安装simple schema、replica set primary、原binding collection UUID/库身份和新snapshot session。拒绝借用任何业务session；原session不重试数据库callback，也不写SDK/业务/治理。投影排除plan、token、wire和Broker handles，限制16分支及Reference大小，检查int64 fence、精确原引用和重复分支；scope/epoch/fence/owner或终态不符均拒绝，错误不交付部分snapshot。

固定QS43模板仅用于自有隔离数据库，摘要d6904ab7c3ab3c4a310314dc7f532eb321679a0e7a31c0b867c11a9280bfc4fa。required GitHub验证固定digest的7.0.37 replica set、真实原业务+witness根、未知/错误读取和删除回读，实际RPC及治理CAS仍未实现。私有观察、native管理动作和消费完成继续分别记账，不能用这些存储fixture关闭C3。


## MySQL治理CAS存储原语（候选，非授权入口）

`ResolveNotice`只接受已由上层独立核验的受审snapshot、请求/完整receipt摘要和当前SDK观察元数据；这些DTO或hash本身不构成授权/真实RPC证明。目前没有调用它的生产CLI。上层仍须完成具名批准、首次runtime屏障、私有文件图/nonce/source、原物理记录和真实RPC校验，完整门禁不能跳过。

原主库2秒上界的RC根持有binding共享锁及目标notice行锁，重新读取精确Ref/原库身份/本地终态/正向SDK审计/首次索引证据后，仅UPDATE status/resolved_at/resolution_receipt_sha256。同receipt重复只回读、不刷新首次时间；不同receipt拒绝覆盖。受影响行数不等于提交，Commit报错返回governance Unknown，独立VerifyResolution用新读取边界确认；不补写SDK审计、不修改业务或Outbox、不自动开准入。旧确认时间不要求更新。

三档真实SQL存储fixture使用明确命名的synthetic受审输入，验证锁等待、竞争CAS、幂等/不同receipt、未具正向审计拒绝、原SDK时间与未选索引保留；它不证明批准、实际RPC或提交回复丢失。真正网络故障及完整CLI/治理图仍待C3后续。


## Mongo治理CAS存储原语（候选）

Mongo使用独立Primary/Snapshot/Majority根，借用session直接拒绝。先按相同原库UUID/绑定、精确终态/正向SDK审计和目标原notice核验，再条件写同一治理document的三个解除字段；新物理索引仍独立blocked。根内不写binding/执行/witness/业务；caller必须持有具名独占操作锁、排除binding/schema写者，DTO/hash不构成授权。没有WithTransaction callback或手动重试；实际写冲突直接返回，提交错误保留governance Unknown，独立新读Verify判断同receipt结果。

新增固定replica set的受控存储fixture检查真实写冲突、两根竞争、不同/重复receipt、首次SDK与治理时间及未选索引保留。RPC/批准元数据为明确synthetic输入，完整CLI/真实RPC/真实提交回复丢失未据此完成。原只读snapshot不改变，CI收尾改为成功的docker ps查询判定资源不存在，daemon/读取错误不能被记作清理成功。


## 受审文件与协调器门禁（候选）

`privatefile`限64KiB、0600同UID单硬链接常规文件，拒绝symlink/FIFO/目录/超限/不同独立SHA，不覆写旧对象；Root相对读取固定协调目录inode。协议JSON拒绝大小写别名/重复key、未知字段、多对象和过深嵌套，错误不回显原值。

`barrier.RequireIssued`读取既有C1的binding、state、first-runtime-start和精确reviewed-step：要求0700同UID目录、被实际协调器持有的锁、同绑定/本机/当前step、runtime_start_issued或forward_repair_issued，修复另核对消费的repair approval。不会新建、重置或删除屏障，结束/维护状态和单独旧marker不允许新操作；记录完整与hash匹配仍不替代请求/receipt审核、物理核验或真实RPC。

纯门禁用现有Python协调器实际发布runtime/forward步骤并持锁，验证Go读取及故障拒绝，没有DB/MQ/SSH。本地首轮负例收尾误用t.Context：Go在t.Cleanup之前取消它，导致自有Python子进程被提前杀死；已改为10秒独立资源预算、先关输入并Wait再cancel，未放宽协调器规则。完整CLI/单次native管理授权和真实MQ矩阵仍待，不能据此发布生产解除入口。
