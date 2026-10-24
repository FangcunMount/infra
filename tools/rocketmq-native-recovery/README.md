# RocketMQ 具名恢复维护工具（实现中）

这是infra维护的短生命周期SDK宿主，当前恢复执行为受审候选，四种宿主/完整故障门禁仍待完成，不授权生产。共享Go SDK可在相同原主库读取Go/Python MySQL见证及Go Mongo见证，不新增常驻服务；业务宿主继续拥有业务池、原业务事务、正常Checker及维护。

## 当前可执行的只读入口

`cmd/native-recovery`提供`version`、`preview`、`verify-review`、`recover`、`resolve-notice`与`verify-resolution`。只读命令不启动SDK或native admin，不把文件审核成功当作执行授权。恢复执行必须同时通过私有请求/批准、源码/二进制/配置/完整路由、真实协调器issued屏障及双方责任人核验；没有绕过这些条件的开关。完整宿主与真实故障门禁继续。

`recover`仅接受单独审核的`action=recover`批准。先消费独占、同步到盘的单次请求claim，再以新原库snapshot重验绑定/终态/首次证据；受审native脚本执行精确物理检查后，启动不暴露Sender的check-only SDK，显式请求一次原生recheck，并等待当前SDK RPC→原审计→私有观察。所有owner配置事务Topic进入Checker；普通发送、原业务执行和中止维护都不可用。原生管理只返回RecheckEnqueued/Unknown，不能写成Broker确认或业务成功。

本实例只有在SDK实际Stopped、全部在途/队列为零、无新half/业务/中止、正向RPC与审计完整，且原池确实关闭后才封存receipt。回执绑定请求/nonce/源码/二进制/原协调绑定与当前步骤、完整原始观察文件及摘要、SDK统计和实际物理报告。拒绝未列出的观察文件、缺文件、错误nonce/来源、JSON重建或未排空；旧SDK成功时间不构成本次RPC。启动/取消/超时/未知均保留claim和私有材料，不复用原请求重跑。

`resolve-notice`需要另一个`action=resolve`批准，绑定该完整receipt摘要，在新的受审forward步骤重新核验所有私有原字节、原物理报告和原库精确证据，之后仅调用治理CAS。Broker final与governance commit分别返回；治理提交错误保持Unknown，`verify-resolution`用原receipt和新的权威读取判断，不重启SDK或补造RPC。工具从不自动开放宿主准入，剩余notice和健康/freshness仍需具名宿主复核。

可选私有配置`native_admin_script/native_admin_script_sha256/native_admin_nameserver/native_admin_broker`为执行所必需。脚本构造时复制已审原字节，以受控进程组执行，不重开路径；仅生成的私有请求路径进入argv，输出有64KiB上界且只保存在0600日志。多响应、超限、取消、遗留进程组、admin未关闭或身份/正文/保留窗口不符不能产生成功receipt。脚本必须为本次固定镜像/网络/凭据配置审查；生产使用单独受限helper cgroup内的直接Java子进程，不使用Docker socket或常驻代理。隔离CI为复用自有Broker暂运行Docker exec，容器归CI统一排空，不当作生产资源演练。

协调器仅在已经审核并issued的脚本环境中传递`M3_COORDINATOR_DIRECTORY/BINDING_SHA256/STEP/STEP_PLAN_SHA256`（字段均带`M3_COORDINATOR_`前缀），避免脚本包含自身计划hash的循环。环境值本身不是批准，Go仍重读活动锁/原binding/state/marker/精确reviewed step。首个启动后旧备份恢复边界保持不变。

构建必须来自精确、干净的infra提交：

```sh
go build -trimpath -buildvcs=true \
  -ldflags "-X main.sourceSHA=$(git rev-parse HEAD)" \
  -o /absolute/private/native-recovery ./cmd/native-recovery
/absolute/private/native-recovery version
```

`version`核验编译VCS revision/clean标记与声明源码一致，依赖必须是固定已发布tx.4、原module sum、无replace，并计算当前二进制摘要。未冻结/脏源码构建不能形成可审核请求。固定源码与二进制摘要仍须独立审查，不能靠自报版本批准生产。

`preview`接收四份0600同UID单硬链接输入及各自独立原字节SHA：`--config/--config-sha`、`--manifest/--manifest-sha`、`--export/--export-sha`、`--selection/--selection-sha`，另指定新`--output`文件，其父目录必须为自有0700。所有输入和完整owner路由先验证，再连接原数据库；manifest保留原NORMAL/TRANSACTION及fanout结构，只为本owner登记去重后的全部事务Topic。公开manifest需在具名操作目录中复制为私有受审文件，不直接修改仓库文件权限。

配置schema为`m3-native-recovery-config/v1`，显式提供owner/store_id/writer_epoch、database_kind/database_uri/database_name、database_ca_pem、endpoint/access_key/secret_key/root_ca_pem。MQ字段仅验证并冻结，不创建客户端；MySQL仅借当前显式原库，连接池上限4/idle1，禁止multiStatements、interpolateParams、skip-verify及明文回退；Mongo拒绝无效URI和不安全TLS，固定Primary/Majority读取。凭据仅存在私有配置中，命令参数传文件路径，错误不回显原URI或未知参数。

selection schema为`m3-native-recovery-selection/v1`，包含operation_id、branch_id、fence、完整native_index_sha256、source_bundle_sha256、data_owner、recovery_owner。原索引export继续使用现有v1指纹，不用clientID去重；完整验证全部行，包括未选择的复制记录。64条截断集合允许精确选择目标，但不能证明owner责任已经清空。

只读snapshot通过后，输出`m3-native-recovery-request/v1`，冻结原主库身份、绑定、精确SDK canonical Reference、本地终态、原audit时间、首次notice证据、物理位置、配置/manifest/export/源码/二进制摘要、具名责任人与随机nonce，30分钟到期。重复preview不覆盖首次文件，不重新生成消息或修改业务事实。输出摘要只有在原池真正关闭成功后才返回；失败文件保留取证。

`verify-review`只检查`--request/--request-sha`、`--approval/--approval-sha`与`--binding-sha`，可显式指定`--action recover`。批准文件由具名负责人在工具外明确审核，schema为`m3-native-recovery-approval/v1`；绑定check/recover动作、原请求SHA、空receipt_sha256、原协调绑定/source bundle、双方姓名和不超过请求期限的expires_at。它不校验活动issued屏障、不连接数据库、不产生批准文件或消息，不可据`review_graph_valid`执行恢复。resolve/verify另行绑定同一个已审实际RPC receipt，未知治理提交不要求伪造新RPC。

本批纯测试的所有权威数据/批准均为明确fixture。required存储门禁额外运行**编译后的独立CLI进程**，分别读取三种MySQL owner与qs.mongo原库并核对私有文件、原Reference/主库身份/旧audit、重复拒绝和审核非授权；物理索引与姓名均为synthetic，不当作真实MQ或生产批准。原SDK执行/见证/业务、目标notice在只读前后保持不变，自有资源单独删除回读。

首轮完整manifest纯测试拒绝已有`accounts`对象：原清单使用`m3-iam`等带连字符的账号键。增加仅供该manifest使用的显式账号键名单解析，未知字段、重复键、大小写别名仍拒绝；批准/request解码器未放宽。失败及修复继续保留在进度记录。

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
