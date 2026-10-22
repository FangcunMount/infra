# T18：已持久化响应的终态恢复

本批只恢复已经接受的业务，不授予新的模型调用或业务 retry。唯一进度总表为 [M3执行表](rocketmq-m3-execution.md)。A 的表征报告不表示恢复已经实现。2026-10-22按用户决策收敛为单一首发宿主协议，不开发历史兼容；遗留实现的删除由 [M4](rocketmq-m4-execution.md)负责。

## 已复现的边界

源码 `0b7f838578c6191ac02748254a718a33113618f2`，infra `b2ef8a3eb1bdc606179117a76ec303d98b9d96d3`，CI [39738320198](https://github.com/FangcunMount/infra/actions/runs/39738320198)：实际 MySQL 8.0.36、SDK 0.4.0a2、客户端 5.1.2，两项通过、零失败/跳过，九类记录清理为零。

1. 已保存 response_received、终态准备失败并有精确 Aborted 后，普通 finish 仍返回 Pending。
2. 原 scanner 重新领取会增加 session version、job attempt 和 lease fence；重新计算 finish 输入时，同一个幂等键发生输入冲突。模型响应被复用，没有第二次模型调用。

以上只使用受控发送失败，不声明 Broker 网络故障或进程重启证明。

## 冻结的恢复规则

- 业务身份（Run、冻结请求/响应、业务版本、首次事件、首次 wire）与执行租约 fence 分开。新 fence 只能替换执行权限，不能产生新的业务 attempt。
- response_received 且响应非空的过期运行任务走专用终态接管：按原 Session → Job → Lease 顺序锁定；要求当前 Run、RUNNING、leased、两份租约过期及有效原响应。只推进 lease/job fence 和到期时间，不调用 Session.running、不增加业务版本或 attempt，不重新占用 participant/model 配额。
- 当前租约或原根提交尚在运行时，竞争者不能接管；取消、终态、Run 改变、缺失响应均拒绝这条接管路径。缺失或矛盾配额证据不得默许新增配额。
- 直接修正尚未投产的宿主finish协议：稳定输入仍包含完整业务 Session、Job/Run、答案、WorkflowResult，仅排除执行租约 fence；原事务必须用当前 Claim 验证真实有效 fence。不新增v1/v2在线兼容，不改写SDK已发布制品或通用schema；最终宿主codec/输入向量随候选冻结。
- 重复恢复先查询原请求：Committed 必须校验精确 witness 和原 archive；Prepared/Unknown 保持 Pending；只有精确 Aborted 才由宿主显式授权 SDK retry。retry 复用同一冻结计划、事件 ID、时间和 wire，不重新 Seal。
- 不查询旧请求表来猜测中间协议的input hash，不创建跨版本执行迁移器。最终协议范围内的Prepared/Unknown/身份冲突仍不得通过换键绕过。生产前核验旧责任；若发现已有中间事务责任，先阻断切换并具名处置，不自动覆盖或清空。
- 当前权限/业务输入已变化时，保持具名 Pending/拒绝并保留证据；不发布原 Artifact、不调用模型、不偷偷改写原操作。取消及权限撤销仍使用原宿主治理入口，不能由 Checker 授权。
- dispatched/unknown 不进入 response_received 接管；继续 provider_result_unknown 处理，不能推断请求没有发出。
- 原终态根提交仍原子包含业务、档案与 witness。LocalCommitted + FinalUnknown 仍是已提交业务，不得重做。

## 必需验收 manifest

五条路径：interpretation_report、serial_generation、serial_semantic、candidate_generation、candidate_semantic。每条都执行 normal、response_committed_terminal_mq_unavailable、terminal_committed_confirmation_lost、response_committed_process_sigkill，共 20 组。

附加门禁：同租约恢复、重复恢复、精确前次 Aborted、新旧 fence 并发、当前协议 Prepared 不可绕过、业务输入冲突、权限撤销、取消、缺失/未知响应、participant 配额不增加、model capacity 不重占、业务 attempt/版本不增加、首次 wire/Artifact/序号稳定、旧模型调用者迟到写入被拒绝。不新增宿主中间协议兼容测试。

按原 invocation 统计独立 HTTP 服务的持久计数；恢复前后请求数相同。worker 必须是独立进程。真实网络丢回复、客户端主动丢弃回复、SIGKILL 分别记录。允许重复 delivery，但原事件身份与业务效果必须幂等。所有 required 测试非空、零失败/跳过，记录精确源码、依赖、镜像、测试 ID 和清理。

实现顺序：先同租约精确 Aborted 恢复，再专用租约接管与最终协议稳定身份，随后独立 HTTP/进程/真实 Broker 故障。开发跑定向门禁，最终候选冻结后集中完整验收。只有全部门禁及合并通过才关闭 T18；M4清理不阻塞本批。
