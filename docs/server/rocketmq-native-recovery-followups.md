# 原生超限恢复能力：后续验收台账

2026-10-24 用户批准[尽快上线范围调整](rocketmq-m3-fast-cutover-proposal.md)。本表承接原 T25-C3-b/c 未完成的高级手工恢复能力，**独立于 M3 36 项及 M4 清理 8 项，不算已验证通过**。生产首发不包含未验收的恢复 CLI，也不承诺原生超限后自动恢复可用性。

| 状态 | ID | 后移工作 | 当前证据和未完成边界 |
| --- | --- | --- | --- |
| ☐ 待审 | R01 | 四宿主/存储原生超限恢复的原根和具名解除验收 | IAM PR146/infra PR221 已通过并合并。[QS #485](https://github.com/FangcunMount/qs-server/pull/485) 补齐当前 QS 双存储隔离原根，[infra #429](https://github.com/FangcunMount/infra/pull/429) 补齐 AI 原 SQLAlchemy 根、原报文消费和具名解除。QS PR437/infra PR228 的 40059571496 失败原件继续保留。 |
| ☐ 待审 | R02 | 完整恢复/拒绝/治理故障矩阵 | 原 C3-c 边界继续保留。infra PR225 的组件矩阵已合并，[infra #427](https://github.com/FangcunMount/infra/pull/427) 用稳定 SDK 重跑了受管提交、回滚、治理故障、IAM 实际原根及原库矩阵。逐宿主的通过范围须按各自报告签收。公开 SDK POP 排空有独立失败记录，仍在复验。 |
| ☐ 未完成 | R03 | 恢复工具正式发布、固定稳定 SDK 和生产受审封装 | [infra #430](https://github.com/FangcunMount/infra/pull/430) 固定 Go SDK v0.6.1、Java helper 与执行镜像。隔离正向恢复已用同一次实际运行镜像完成并封存。仍待固定 Linux 生产协调器、执行账户、具名网络与凭据、容器退出确认及独立审查。 |

每项保留源码 SHA、报告摘要、CI、失败、合并和发布事实；后续批准执行时再冻结批次，不为了 M3 计数删除失败或重命名为已完成。已有源码可保留在仓库，生产镜像/执行包必须排除未验收恢复入口。

M3 首发遇到原生超限：原库持久封对应 owner 新写、保留 Checker、读取与审计；具名排障，未查清前不解除。已提交业务可能等待投递。禁止重做业务/模型、改消息ID、自动切 NSQ、伪造确认和旧备份覆盖。独立修复必须审核当前事实及具体执行清单。

## R03 封装验收

现有正向恢复夹具的编排复用测试 Broker 的网络命名空间，并共享测试宿主 UTS。生产候选要在精确 Linux 宿主上使用同一个实际协调目录和活动锁，匹配协调器及容器的 UID、受审主机身份、镜像和唯一当前步骤。现有 MacBook SSH 操作器的屏障保留在 macOS，须先选定并独立审查 Linux 侧的单一协调权威，才能满足 Go CLI 的本机锁和主机校验。审查人逐项签收下表后，先在隔离环境用同样的封装完成正向和拒绝演练。

| 检查点 | 封装必须提供的原件 |
| --- | --- |
| 运行身份 | 精确 Linux 主机、UID/GID、操作目录、活动协调锁和已批准步骤；只读渲染与实际执行分开。核对精确镜像 ID、OCI manifest、源码、CLI、Java helper 摘要和镜像内版本。 |
| 隔离 | 已核验的专用网络及原库、Broker 和管理端点白名单；实际容器的只读根、零 capabilities、no-new-privileges、384 MiB、1 CPU、64 进程、无 Docker socket。证明其他网络与宿主挂载不可用。 |
| 材料 | 固定原库、Broker ACL 与 TLS 材料、配置和导出路径。将审批与输入只读挂载，仅对同一协调目录开放工具回执写入。验证符号链接、权限或摘要漂移时拒绝。 |
| 中止 | 持久绑定唯一容器身份。Docker CLI 返回、超时、断连或协调器退出后，必须实读容器终态、SDK 排空与实际 RPC 回执。未确认时保留屏障、转独立前向核对并阻断再次启动。 |
| 双阶段 | 恢复和具名解除分别要求当前独立批准。用原报文、审计、未选通知、进程退场和两地回执签收。新通知及未知结果继续保持原准入状态。 |

公开 SDK 复验 [42689506222](https://github.com/FangcunMount/infra/actions/runs/42689506222) 曾在 Go 订阅关闭后读到 POP 责任重新出现。补存第二次确认的 offset buffer、checkpoint buffer、定时责任和样本摘要，保留原失败条件。此用例独立于受管恢复正向结果。

Linux 协调器的受审脚本调用容器入口，提交独立摘要绑定的私有计划。计划固定操作目录、宿主、镜像 ID、镜像源码、专用网络 ID 和名称、协调绑定、步骤、唯一命令和逐件输入摘要。只接受 `recover`、`resolve-notice` 和 `verify-resolution`。默认仅核对计划和文件，实际发出容器还要求 `--execute`、UID/GID 3000、同机活动锁和原受审步骤。CLI 继续核验独立批准与原库和 Broker 身份。[容器入口](../../scripts/rocketmq/native_recovery_container.py)

选址审查使用 `m3-native-recovery-container/v2` 作为专用网桥候选。该计划沿用 v1 字段，在创建前与启动前各从实际 Docker 读取同一网络 ID，要求本机 `bridge` 为内部网络，IPv4 网关模式为 `isolated`，并关闭 IPv6。启动前不符时保留已发出与已创建的身份回执，供后续独立核对。v1 继续用于现有隔离夹具。专用转发器、具名端点、实际 ACL/TLS 和生产执行账户须由独立证据签收。[Docker 网关模式](https://docs.docker.com/engine/network/port-publishing/#gateway-modes)

具名网络成员审查使用 `m3-native-recovery-container/v3`。独立计划的 `network_members` 按完整容器 ID 列出允许接入专用桥的现有成员，每项固定 Docker 端点 ID 和带前缀长度的 IPv4 地址。容器创建前及启动前分别核对实际成员集合与地址。额外成员、成员缺失或同一容器重新连接导致的端点变化都会阻断。Docker 在实际启动前尚未将待执行容器计入活动成员。两次读取之间及运行期间的网络变更权限须在具名宿主单独控制。

固定输入目录为操作目录的同级 `inputs`，内含五份私有 JSON 文件及 `java/tools.yml`、`java/tls/server.crt` 和 `java/native-admin.sh`。执行账户持有 0600 的管理员脚本，配置必须指向容器内只读挂载的 `/run/native-recovery/native-admin.sh`，且配置、计划和文件三个摘要一致。协调目录保留原 inode 和回执写入，协调权威文件与既有恢复回执单独只读挂载。容器内时限为 195 秒，随后最多给出 12 秒退出宽限。启动前记录步骤和容器 ID，只有 Docker 实读退出状态才记录终态。

等待或创建结果未知时，先用 `--observe-prior <原步骤计划 SHA256>` 在原 Linux 宿主和绑定目录生成只读观察。保存其标准输出原字节及摘要，核对完整容器 ID、镜像、步骤标签、网络、实际起止与退出状态，再独立核对 SDK、原库与 Broker 事实。容器仍在运行、查不到或身份不符时继续阻断。新的具名前向步骤可在计划中加入 `prior_terminal`，绑定 `step_plan_sha256` 和 `observation_sha256`。入口在活动锁内重新读取终态并比对摘要，将交接记入 `-reconciled.json`，保留原已发出记录。任何新 `recover` 都要使用未发出过的请求，具名解除仍绑定原恢复回执。实际生产宿主的未知结果核对与具名网络出口须另行签收。

原根工作流仅在手动启用 `coordinated_image` 时运行 v3 隔离场景。Broker 固定通告地址，断开两条夹具网络后按相同地址重接，保留原物理消息 ID 的地址语义。重接后固定 Broker、NameServer 和 MySQL 三个夹具成员的端点。恢复、具名解除和复核三步均绑定同一成员摘要。宿主探针使用一次性 runner 上的单端口回环转发，执行容器通过隔离桥直连 Broker。作业分别核对回环映射和夹具网络回收。

Infra `e5ba8fa8190fe15f1dbe70f4113dc4b25cd94d5d` 与 AI `c6359b441de48fde5b295529fe9c10f50e4c53f5` 已通过 Python 3.11、3.13 与 MySQL 8.0.36、8.0.44、8.4.11 的六组完整隔离矩阵，共 66 项通过。每组用同一隔离桥内的 UID 3000 容器完成恢复、解除和复核，保留原首次审计和原报文 ACK，拒绝重复请求，具名重开无新 half。开发作业实际执行的 Linux amd64 镜像原件已逐层读回。生产专用出口、执行账户、原库与 Broker 端点仍须独立复验。[完整隔离矩阵](https://github.com/FangcunMount/infra/actions/runs/42787455864) · [开发作业与镜像原件](https://github.com/FangcunMount/infra/actions/runs/42786265415)
