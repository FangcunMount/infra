# M4 八角色配置重建边界

本文细化既有 C06-D 的输入与验证对象，不新增任务或门禁。进度只在 [M4总表](rocketmq-m4-execution.md)维护。2026-10-26 已完成生产输入的只读采集与配置身份预览；**尚未完成最终候选重建、文件安装或部署**。

## 固定角色与资源

| 角色 | 数量 | 事务 owner | 原资源/执行预算 | 最终文件边界 |
| --- | --- | --- | --- | --- |
| IAM | 1 | `iam.mysql` | 1024 MiB / 1 CPU；发送8、Checker 4/32、每轮维护100 | 3个 `/etc/iam/rocketmq/` 只读文件 |
| QS API | 1 | `qs.mysql`、`qs.mongo` | 1024 MiB / 2 CPU；各发送4、Checker 2/16、各维护50 | SQL/Mongo独立凭据，CA/routes；另保留原4个JOSE文件 |
| QS AI | 1 | `ai.mysql` | 768 MiB / 0.75 CPU；发送4、Checker 1/16、维护100；原MQ max_in_flight=1 | 3个 `/run/qs-ai-rocketmq/` 文件及4个原JOSE文件，同一revision |
| Collection 1 | 1 | 无 | 320 MiB / 1 CPU | 不增加MQ配置或凭据 |
| Collection 2 | 1 | 无 | 320 MiB / 1 CPU | 不增加MQ配置或凭据 |
| Worker 1 | 1 | 无 | 768 MiB / 1 CPU；原业务并发48 | 3个 `/etc/qs-worker/rocketmq/` 只读文件，发布关闭 |
| Worker 2 | 1 | 无 | 768 MiB / 1 CPU；原业务并发48 | 同上，不增加owner |
| Worker 3 | 1 | 无 | 768 MiB / 1 CPU；原业务并发48 | 同上，不增加owner |

所有事务owner保持m3-1、16分支、DB回查2秒、RPC5秒、lease60秒、维护间隔5秒。Go时长JSON使用纳秒，YAML可以使用等价时长字符串；只换算时长单位核对预算，store/epoch按原字节比较。

## 原绑定与账户责任

- 已从当前运行配置读取 IAM、QS双owner、AI 的原store/epoch及完整预算。私有记录只采集协议字段，不输出数据库URL、密码、密钥或业务正文。当前数据库绑定仍须沿既有权威校验核对，配置读取不替代这一证明。
- IAM和QS打包器的只读预览保持原身份及等价预算，默认关闭预览准入；AI原绑定通过最终完整预算校验。预览没有修改生产环境、生成新writer epoch或安装文件。
- QS API固定 `qs-apiserver-1`；IAM授权订阅保持 `qs-authz-sync` 前缀与已部署逻辑订阅身份。它使用原SQL账号，不取得事务owner，不增设第六个Broker账号。
- QS领域MySQL与AI command/ACK共用同一原 `qs.mysql` 身份；Mongo使用独立账号。文件名不同不足以证明账号不同，最终预检仍须核对实际传输文件与账号约束。
- 三个worker消费专用；Collection没有MQ责任。事件catalog中现行 `durable_outbox` 分类仍被事务订阅使用，不因名称删除或改写协议。

## 文件与入口验证

IAM新源路径为 `/data/infra/iam-messaging/versions/<revision>/rocketmq/`；worker为 `/data/infra/qs-worker-messaging/versions/<revision>/rocketmq/`。这些路径是受验源码的目标，**不能推断生产已安装**。QS/AI继续使用各自既有受限版本目录，保持原JOSE文件；API的Mongo凭据挂载与AI桥接一致性预检已在QS PR447实现，并通过真实标准镜像的十项离线验证；生产新工具与版本材料尚未安装。

重建沿现有C06-D门禁执行：逐个绑定确切源码/镜像、原身份、实际文件摘要与Unix身份/权限，再由真实宿主decoder、离线镜像预检和Compose核对有效配置。缺失、符号链接、权限变化、混合revision、错误owner/路由或预算必须在配置同步、停止或替换运行服务之前拒绝；生产固定root工具只能由已安装的审核摘要选择，不能执行上传目录中的任意root Python。

保持现有部署锁inode、镜像保留清单、MySQL/Redis及mTLS CA、QS API/worker原8分钟30秒、AI原210秒及IAM原关闭预算。不得为了让预检通过重建共享锁、放宽秘密文件权限或打开生产CD。

## 证据范围与剩余工作

本轮只读复核确认8个应用、4个owner、10个监控目标和4个公网健康入口正常，serverD可用内存约1236 MiB。这是采集时刻的健康快照，不能冒充最终候选部署、业务验收或已被用户豁免的48小时观察。

输入元数据覆盖8角色的实际挂载、配置摘要、只读属性及文件身份。首版采集器只读取Go嵌套事务字段，随后补齐Python外层 `messaging.transactions` 并重新只读采集；旧报告保留，不把扫描器缺字段解释为运行owner缺失。初次预算直接比较遇到Go纳秒与YAML时长表示差异，规范单位后相同；失败历史和修正均保留。

API完整主机预检已有源码与真实离线镜像证据，完整CI/合并单独见总表。剩余C06-D依次为：权威数据库绑定与原配置身份核对、实际私有材料版本及权限准备、五种服务八实例隔离重建、材料故障于替换前拒绝、冻结配置契约与全部PR合并。API单镜像预检不冒充八实例启动、四owner真实回查或生产验收。详细报告只发布摘要，原始证据保存在0700目录、0600文件中，索引见 [C06证据receipt](evidence/rocketmq-m4-c06-source-progress-20261025.json)。本批没有业务写入、模型调用、DDL、凭据轮换、服务重启或历史资产删除。
