# M3 单次切换的首次启动边界

进度以 [M3总表](rocketmq-m3-execution.md) 为准。本工具是 T25-C 的离线实现候选，尚不构成该子项完成、生产执行批准或 T29 最终候选演练。它不修改业务、SDK、schema、Topic、ACL 或 worker 配额。

## 唯一协调位置

整次多主机切换只使用一处已审核、固定绝对路径的协调目录。所有新 runtime 的启动命令和旧数据恢复命令都必须由同一协调入口发出；远端启动也必须先在协调端持久化屏障，再发出 SSH 命令。不能在 IAM、QS、AI 各自的主机上创建独立目录，然后凭某台没有本地标记判断整次切换尚未启动。目录丢失、移动、损坏、创建新目录或绕过协调入口执行过命令，都不能重新取得恢复资格。

`start_boundary.py` 在任何首个启动 callback 前，以独占新建、文件及目录 fsync 写入不可逆标记。启动失败、进程退出、尚未 ready、回查未完成，都不撤销标记。目录锁串行化启动与恢复；破损或不完整证据按不可用处理。启动前恢复即使失败也封闭正常启动，避免带着部分恢复的数据继续上线。

`cutover_step.py` 默认只核对离线清单。显式执行时核对当前 Linux 协调主机，持有唯一协调目录锁，再执行独立摘要已审核的脚本快照。目标主机启动助手另持有该目标的原部署锁，避免用协调主机的锁假代远端互斥，或同机执行时重复取得同一锁而自锁。脚本以 Bash errexit/nounset/pipefail 运行；不再次打开可能已被替换的脚本路径，不继承 shell 配置、Docker context 或用户环境。命令输出仅写协调目录0600文件，不写会话或公开 CI 报告。超时等待并终止本次自有进程组，不能把取消或遗留后台工作记作成功。

清单的 `host` 指协调主机。远端目标、固定镜像/config/env 摘要、显式 Docker socket、远端部署锁及原服务集合必须写进 T29 审核的具体脚本/附件，不能由消息属性或环境猜测。工具只执行审核过的字节，不能从摘要自行判断脚本是否真的安全。受限目标启动入口已实现；当前还没有具体生产脚本，也没有证明实际远端传输或IAM/QS/AI最终镜像启动，仍须完成相关门禁，不提前勾选T25-C/T29。

## 和现有部署入口分开

| 原源码入口 | 已核对行为 | 协调切换要求 |
| --- | --- | --- |
| IAM `scripts/cd/remote-deploy.sh` | Compose force-recreate/remove-orphans；共用部署锁 | 固定新 runtime 启动步骤必须在协调屏障之后，先验证原服务集合 |
| QS `scripts/cd/remote-deploy.sh` | API/collection/worker 启动；collection 失败可能重启旧容器 | 切换不调用旧容器自动恢复路径；保留三个 worker 的原配置 |
| AI `deploy/serverA/deploy.py` | `apply` 自动 Alembic；`verify` 启动；部分失败尝试旧 release | DDL 在批准的离线步骤执行；新 runtime 只走固定启动步骤，失败走具名兼容修复 |

原共享锁为 `/var/lib/fangcun-image-retention/deploy.lock`；AI 另有 `/opt/qs-ai/deploy.lock`，锁顺序保持共享锁在前。工具不创建、替换 inode 或 chmod 原锁。协调端只持有整次操作的目录锁；目标启动助手在实际目标主机持有原部署锁。批准的恢复脚本也须持有其实际目标的原锁；普通部署函数不得在已持有同一锁的子进程中再次取锁。普通生产 CD 继续暂停，不能用一个新锁文件替代原入口互斥。

## 受限输入和执行方式

绑定对象使用 `m3-start-boundary/v1`，精确包含 `schema`、`operation_id`、`directory`、`scope_sha256`、`protection_sha256`、`restore_receipt_sha256`、`source_bundle_sha256`、`data_owner`、`recovery_owner`。后三类摘要绑定的实际保护、恢复演练和最终候选附件由 T29/T30 冻结，不能填测试摘要作为生产证据。目录0700、输入0600、同用户、单硬链接、非最终 symlink；对象须规范编码且无重复/未知字段。

单步对象使用 `m3-cutover-step/v1`，精确包含：

| 字段 | 用途 |
| --- | --- |
| `directory` / `binding_sha256` | 原固定协调目录与原绑定独立摘要 |
| `host` | 精确协调主机；不能用目标主机身份代替 |
| `step` / `kind` | 固定步骤；`runtime-start`、`pre-start-restore` 或 `forward-repair` |
| `script` / `script_sha256` | 固定绝对路径的0600原始脚本，最多1MiB |
| `cwd` / `timeout_seconds` | 已审核工作目录；1–1200秒命令预算 |

整个单步对象另取独立 SHA256；正文、凭据和环境值不放入公开清单。默认核对不接触部署锁、DB、SSH、Docker 或 MQ。以下是未来执行形式，**不是当前生产清单**：

```sh
python3 scripts/rocketmq/cutover_step.py --plan /受限目录/step.json --reviewed-sha256 已审核摘要
python3 scripts/rocketmq/cutover_step.py --initialize --plan /受限目录/binding.json --reviewed-sha256 已审核绑定摘要
python3 scripts/rocketmq/cutover_step.py --execute --plan /受限目录/step.json --reviewed-sha256 已审核摘要
```

`--initialize` 只允许新建一次；不提供 reset、删除标记、换目录恢复资格的命令。前向修复使用独立审核的单步摘要，保留不可变审批引用；不把普通镜像重启或原发布批准冒充修复批准。命令返回仅为 `reviewed_command_returned`，始终 `cutover_authorized=false`，不等于服务健康、数据恢复成功、system 验收或允许开准入。

## 故障与未决责任

首次启动前才允许执行批准范围内的旧数据恢复。首次启动命令一旦发出，所有目标库都按整次切换可能已开始处理，不能覆盖旧全量备份，也不切回 NSQ/Outbox。启动执行失败或结果未知时封闭后续正常启动，等待具名兼容前向修复。SIGKILL/主机故障可能留下远端执行；标记仍有效，操作人须按原具名进程/容器和锁核对真实在途，不能因本地进程消失认定远端已经停止。

无回查的 audit 缺口、原生超限、DLQ、业务 receipt 未收敛都保留原身份与 Unknown。不得伪造正向 Broker 确认、忽略原治理行、重发旧 half、更换事件 ID 或重做模型调用。当前持久保护没有生产解除接口；发现此类未结责任时继续关闭新准入，阻断上线，记录精确证据及具名处置。兼容修复能力未证明前，不通过删除保护或改计数来放行。

独立 CI 只验证受控文件/进程的首次屏障、真实退出、并发锁、失败、超时、私有输出和修复引用；报告明确不属于实际 runtime/数据库验收。T25-D 仍须组合旧责任盘点、排空/未来计划交接和恢复门禁；T29 再使用最终镜像验证启动/恢复及30分钟目标，T30 才核验实际生产状态与具名批准。


## 目标主机的固定启动入口

`runtime_start.py` 只负责已批准首次屏障之后的目标主机启动。默认验证 `m3-runtime-start/v1` 原始规范清单：`schema`、`coordinator_binding_sha256`、`host`、`project`、`directory`、`compose_file`、`compose_sha256`、`environment_file`、`environment_sha256`、`services`、`images`、`instances`、`ai_host`。配置与env必须是同一冻结发行目录中的0600文件；服务最多16个、总实例最多16，每个镜像必须是不可变`@sha256`引用。预算只是拒绝超限，不授予扩大原worker配置的权限。

执行要求独立清单摘要和显式`--execute --coordinated-start-already-issued`。后一个参数仅是操作者声明，不是远端自动证明或生产批准；生产必须从唯一协调目录的受审脚本调用，不能直接手工运行目标助手或据此绕过屏障。目标入口重新核对实际Linux主机、原部署锁和锁内文件摘要，再运行固定本机Unix socket的Compose config，拒绝构建配置、镜像或实例数量冲突，然后执行：

```text
compose up --detach --no-deps --no-build --pull never --wait --wait-timeout 120 <冻结服务集合>
```

入口不发出pull/build/DDL/stop/down/remove-orphans/旧镜像恢复命令。它读取精确服务容器集合，核对项目/服务label、Config.Image、running/health及原定实例数；缺失或矛盾保持失败，不自动重试或回退。成功只表示本次目标runtime回读完成，`cutover_authorized=false`，不等于业务、消费者、Checker或system验收。镜像内部启动行为和实际资源/worker预算仍由T28/T29最终镜像门禁验证。

隔离GitHub验收使用唯一临时NSQ1.3.0容器仅作为Compose启动夹具，记录实际digest；它不是业务普通消息中间上线，也不代表RocketMQ事务验收。测试先真实启动失败，证明协调屏障阻止恢复；再以独立修复引用启动同项目固定镜像并回读，验证未选中依赖不启动、原目标锁互斥、镜像/实例冲突在up前拒绝，以及所有临时容器/网络/私有目录清理。实际跨主机命令、生产保护恢复附件和最终候选30分钟演练仍单独记账。
