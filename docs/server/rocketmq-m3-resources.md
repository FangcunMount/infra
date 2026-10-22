# M3 最终 RocketMQ 资源候选

[M3 唯一进度总表](rocketmq-m3-execution.md)维护 T21 验证及合并状态。本文件说明最终资源契约；生产安装、实际私网可达性和启用状态由 T30–T33 单独核验。T21 只操作隔离 Compose，不安装 serverD 资源、不修改现有 NSQ 或 worker 配额。

## 路由与角色

候选为 [serverd-routes-m3-v2.json](../../components/rocketmq/serverd-routes-m3-v2.json)：revision `m3-1`，四个事务 owner、12 个路由绑定、10 个物理 Topic、9 个 Group。所有 Topic 采用显式 1 读/写队列、perm 6，Group 重试队列 8；T29 固定摘要，T30 核对容量和实际清单后才能安装。既有 `serverd-routes.json` 仍保留原 v1 责任，不在原 Topic 上转换消息类型。

| 角色 | 发布 owner | 订阅责任 |
| --- | --- | --- |
| `m3-iam` | `iam.mysql`：授权事务、SMS NORMAL | IAM 自身授权广播 |
| `m3-qs-apiserver` | `qs.mysql`：评分、Task 事务、command/ACK、survey/Task NORMAL | QS 授权广播、模型目录 NORMAL、AI event |
| `m3-qs-worker` | 无发布权限；不持有事务 owner | `qs-worker` 的 survey、Task NORMAL/事务、evaluation MySQL/Mongo 事务 |
| `m3-qs-mongo` | `qs.mongo`：答卷、报告及其到期 dispatch | 无消费授权；宿主显式借用此身份创建该 owner Sender/Checker |
| `m3-ai` | `ai.mysql`：receipt/state event | QS command、业务 ACK |

每个角色的 Pub/Get 只覆盖本 owner 精确 Topic；Sub/Get 只覆盖其 Topic 和 Group，不授权管理或通配符。RocketMQ ACL 分别授权 Topic、Group 资源；验收按有效权限交集计算，不假称支持 Topic/Group 对的关联策略。apiserver 与 worker 分别使用角色凭据；仅 apiserver 持有两个事务 owner，Mongo owner 使用显式 `transactions.qs.mongo.credentials_file`，MySQL owner 也显式设置 `credentials_file`。双 owner 不能共用 Broker username，不能仅用两个相同内容的文件绕过检查。

`assessment_model.changed` 实际位于 `qs.survey.lifecycle`；独立 modelcatalog 订阅跟随这个 NORMAL 输入。`qs.evaluation.lifecycle` 有 `qs.mysql` 与 `qs.mongo` 两个事务物理输入，它们共用原逻辑 `qs-worker` Group 和宿主在途预算。拆 Topic 不增加 worker 或执行额度。

授权广播使用稳定工作负载标识：IAM `instance_id=iam-primary-1`，QS `instance_id=qs-apiserver-1`。它们不绑定当前云、主机名或 PID。增加新活跃实例需先增加精确广播 Group/ACL，不得复用 Group 导致广播变负载均衡。T30 必须将实际实例清单与此候选对齐；未经核验不推断生产实例数。

SMS 只声明 IAM 当前目录中的尽力发布责任，manifest 不虚构尚未登记的外部 SMS 消费者。生产清单须核验实际短信 provider；任何有效外部 MQ 消费责任都必须具名补齐，不能静默丢弃。

## TLS 与显式安装边界

沿用 infra 的 Docker Broker/Proxy：只绑定受控私网 IP，管理端口不对宿主发布；应用以私网 endpoint 和明确 CA 文件校验证书链、SAN，TLS 最低 1.2，不设置 insecure skip。保持现有 Docker 内存/CPU 及 serverD 三个 worker 配置，Prometheus/Grafana 继续在 Mac mini。

T21 在回环隔离 Broker 必须验证相同模板的可信 CA/SAN 正例、错误 CA、错误 SAN、明文拒绝，随后再次验证可信连接。首轮在明文拒绝失败，当前修正候选仍待真实复验，不把已具备TLS握手等同于强制TLS。它不能证明生产私网、防火墙或当前证书已正确配置，这些由 T30/T31 实际回读。

资源安装必须显式传入新 manifest 和私有凭据文件，经 Compose 项目身份校验后调用 `scripts/rocketmq/provision.py`。v2 工具先完整读取 Topic/Group、用户及 ACL；类型、队列、凭据或既有超额 ACL 冲突时全部拒绝，不旋转密码、不改写旧资源、不删除或转换 Topic。构造和宿主启动不执行安装。

## 可重复隔离验证

`make rocketmq-m3-resources-test SDK_DIR=/path/to/fixed-sdk ROCKETMQ_TEST_IMAGE=owned-image` 复用 infra 隔离 Compose 生命周期及清理。显式 SDK 源码固定 `8de893b367cc797580799abd8325f41dd62356db`，原生权限探针固定 Python 客户端 5.1.2，Broker 5.5.1。探针不是 SDK/宿主业务验收。

必需证据包括 130 个实际传输操作结果（含每角色前后各一次的10个签名授权对照、84 个越权拒绝、10 个实际 Broker 错误类型拒绝和 TLS 正反例），以及类型、队列、凭据和 ACL 四类完整冲突拒绝。为证明服务端类型检查，隔离 raw-client 子类仅在本进程实例中关闭发送前类型校验；不修改 SDK、全局 factory 或生产配置。半消息成功后立即回滚，不产生业务提交。所需依赖缺失、缺项、跳过、未知错误码或不完整清理全部失败。

报告记录源码、manifest/探针/锁摘要、实际 Broker 参数和镜像、结果及清理。只上传安全 JSON，不输出凭据、原正文或原生日志。原始客户端日志限制在临时私有目录，随所属 Compose、进程组和目录清理；首次失败仍保留安全计数及退出状态。T22 再验收全宿主装配、共享 owner 生命周期及预算，T23 验收宿主真实故障。

固定5.5.1的 [gRPC negotiator](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/proxy/src/main/java/org/apache/rocketmq/proxy/grpc/ProxyAndTlsProtocolNegotiator.java) 使用 [TlsSystemConfig](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/remoting/src/main/java/org/apache/rocketmq/remoting/netty/TlsSystemConfig.java) 的全局 `tls.server.mode`，默认permissive。新候选以JVM固定参数强制enforcing，并为同进程Broker、NameServer及MQAdmin的内部remoting同步启用TLS与证书信任，避免仅强制gRPC后破坏内部链路。NameServer只读挂载tls目录，不增加常驻进程或预算。T30/T31需按冻结新镜像核对证书链及外部/内部SAN、挂载与实际明文拒绝，不能只替换proxy.json或沿用旧验收receipt。

实际worker入口只通过gRPC调用API业务根；唯一旧发布器用于retry-hold replay。最终worker为consume-only，不配置事务owner、Sender或Checker，不因迁移新增worker goroutine/配额。最终配置关闭发布准入并停止旧hold replay；旧hold/未来责任须在T25/T32具名交接或处置，不以越权失败代替退出活动扫描。旧126操作开发草案对应worker曾有发布授权；修正后保留全部现存Topic正反例，worker发布正例改成明确拒绝，移除其6个不适用的错误类型发布正例，最终120操作，不增加完成数。

开发调试可以显式选择workflow_dispatch的bootstrap档，只安装首个IAM角色的两个Topic/一个Group，执行12个原生结果，不跑完整冲突矩阵，报告固定full_gate=false。PR与默认dispatch始终为full档，必须130个结果及4类冲突；bootstrap报告不能用于T21勾选或合并门禁。开发阶段暂时关闭PR154，仅手动运行定向原生workflow；冻结后重新打开同一PR并执行全部必需矩阵，不删除已有失败。

固定5.5.1的ResponseBuilder将认证和授权异常统一映射为40100（UNAUTHORIZED）。越权测试只接受该确切状态；每个角色在拒绝批次前后以同一凭据读取其获准Topic，两个成功对照都必须存在，避免错误凭据伪装为权限拒绝。类型错误仍要求40014。当前矩阵从120增加10个对照为130；保留旧失败和开发档来源，不修改任务总数。
