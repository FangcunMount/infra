# M4 八角色配置重建边界

本文细化既有 C06-D 的输入与验证对象，不新增任务或门禁。进度只在 [M4总表](rocketmq-m4-execution.md)维护。2026-10-26 已完成生产输入、四owner权威数据库binding及原材料的只读核对；**已预置未激活版本材料，并完成本批八实例隔离配置重建；宿主部署保护接入正在收尾、配置契约候选已建立；最终生产安装与业务部署归C08**。

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

- 已从当前运行配置读取 IAM、QS双owner、AI 的原store/epoch及完整预算。私有记录只采集协议字段，不输出数据库URL、密码、密钥或业务正文。随后从三个MySQL的READ ONLY事务及Mongo primary/majority元数据核对四owner，原store/epoch按字节相同；不是仅凭配置或健康推断。
- IAM和QS打包器的只读预览保持原身份及等价预算，默认关闭预览准入；AI原绑定通过最终完整预算校验。预览没有修改生产环境、生成新writer epoch或安装文件。
- QS API固定 `qs-apiserver-1`；IAM授权订阅保持 `qs-authz-sync` 前缀与已部署逻辑订阅身份。它使用原SQL账号，不取得事务owner，不增设第六个Broker账号。
- QS领域MySQL与AI command/ACK共用同一原 `qs.mysql` 身份；Mongo使用独立账号。文件名不同不足以证明账号不同，最终预检仍须核对实际传输文件与账号约束。
- 三个worker消费专用；Collection没有MQ责任。事件catalog中现行 `durable_outbox` 分类仍被事务订阅使用，不因名称删除或改写协议。

## 文件与入口验证

早期打包源码以 `/data/infra/...` 为来源。D02实际预览后，最终新材料来源固定为 `/var/lib/fangcun-m4-materials/{iam-messaging,qs-server-messaging,qs-ai-messaging,qs-worker-messaging}/versions/<revision>/`，四角色已预置未激活版本；D03路径合同已由IAM PR152、QS PR448、AI PR226通过完整CI并合并。QS/AI保留原JOSE文件名与bytes；API的Mongo凭据挂载与AI桥接一致性预检已在QS PR447实现，并在PR448标准镜像重新通过十项离线验证。生产仅安装了D02固定材料工具、私有计划及未激活版本材料；三库新CD发布工具与运行配置尚未启用。

重建沿现有C06-D门禁执行：逐个绑定确切源码/镜像、原身份、实际文件摘要与Unix身份/权限，再由真实宿主decoder、离线镜像预检和Compose核对有效配置。缺失、符号链接、权限变化、混合revision、错误owner/路由或预算必须在配置同步、停止或替换运行服务之前拒绝；生产固定root工具只能由已安装的审核摘要选择，不能执行上传目录中的任意root Python。

保持现有部署锁inode、镜像保留清单、MySQL/Redis及mTLS CA、QS API/worker原8分钟30秒、AI原210秒及IAM原关闭预算。不得为了让预检通过重建共享锁、放宽秘密文件权限或打开生产CD。

## 证据范围与剩余工作

本轮只读复核确认8个应用、4个owner、10个监控目标和4个公网健康入口正常，serverD可用内存约1236 MiB。这是采集时刻的健康快照，不能冒充最终候选部署、业务验收或已被用户豁免的48小时观察。

输入元数据覆盖8角色的实际挂载、配置摘要、只读属性及文件身份。首版采集器只读取Go嵌套事务字段，随后补齐Python外层 `messaging.transactions` 并重新只读采集；旧报告保留，不把扫描器缺字段解释为运行owner缺失。初次预算直接比较遇到Go纳秒与YAML时长表示差异，规范单位后相同；失败历史和修正均保留。

API完整主机预检已有源码与真实离线镜像证据，完整CI/合并单独见总表。C06-D01已核对四owner权威绑定、八角色19处MQ/8处JOSE文件与五个Broker主体指纹、原UID/资源和worker48并发；[证据](evidence/rocketmq-m4-c06-original-bindings-20261026.json)不包含秘密正文。D02已完成版本材料预置并回读，D03已完成三库宿主路径联动及八实例隔离重建；当前剩余材料故障在全部宿主同步/停止前拒绝及D05配置契约冻结。独立启动报告不替代生产部署、真实业务回查故障矩阵或system验收。详细报告只发布摘要，原始证据保存在0700目录、0600文件中，索引见 [C06证据receipt](evidence/rocketmq-m4-c06-source-progress-20261025.json)。本批生产侧没有业务写入、模型调用、DDL、凭据轮换、服务重启或历史资产删除；隔离环境显式安装schema的证据另记D03。

## C06-D02：新增版本材料，保留活动配置

受限工具 `scripts/ops/m4_material_stage.py` 只把已冻结的原MQ/JOSE bytes复制到四个角色的
`/var/lib/fangcun-m4-materials/<role>-messaging/versions/m4-.../` 新目录。API共8份、AI共7份、IAM和worker
各3份，合计21份不同文件；三个worker共享一个材料版本，对应八实例的27处文件引用。
原source的摘要、长度、UID/GID及mode全部校验后才允许创建目录；复制完成前再次核对source。
新文件root所有、角色GID只读（0440），版本目录0750；现有父目录、原文件及current指针不修改。
版本已存在时必须摘要、收据、权限和文件集合完全相同，只读复核后返回，不覆盖原版本。

工具默认仅预览，显式 `--apply` 才写新版本；CLI固定目标根目录、角色、主机和GID，
没有目标目录覆盖参数。生产调用必须root、固定审核工具SHA、私有具名plan及其精确SHA；
复用原共享部署锁，锁缺失/符号链接/权限变化/占用均拒绝，不创建或替换锁inode。
工具不轮换凭据、不生成身份或密钥，不修改sudo规则、准入、运行配置，不调用Docker/数据库/Broker。
复制故障只清理本次私有暂存和仍为空的新父目录，已发布的版本及历史资产继续保留。

本批源码先运行本地14项故障保护和required Linux root/普通UID/共享锁的19项真实权限验证，
全部通过并合并后才预置生产新版本。生产root工具/私有plan/版本材料安装分别留receipt；
新材料预置不表示C06-D03八实例重建、D04部署入口保护或C08生产发布已完成。

D02首次目标机预览在任何材料复制前拒绝旧根目录：serverA/serverD的 `/data`、serverD的 `/data/infra` 由UID2000持有。新版本根改为 `/var/lib/fangcun-m4-materials`，保持原有严格root所有/不可被其他用户写入的检查，不更改旧目录权限。原 `/data/infra/...` 与M3 profile仅作为已冻结、摘要校验的只读source。新的receipt固定material_root；八角色重建与最终CD须同步该宿主来源路径，容器内约定不变，此路径联动仍纳入C06-D03/D04/D05。旧工具/计划与失败日志保留，未复制/激活材料。

2026-10-26 D02生产材料结果：[完整receipt](evidence/rocketmq-m4-c06-versioned-materials-20261026.json)。四角色21份原文件、27处挂载引用的 `m4-c06-20261026-v1` 已预置且再次只读验证；runtime fingerprint、current指针和原锁相同。新版本未激活，旧原材料及目录不变。新宿主来源路径尚须在三库CD/重建联动后冻结，不能恢复自动部署。

2026-10-26 D03来源路径合同已合并：[源码/完整CI/报告receipt](evidence/rocketmq-m4-c06-root-material-paths-20261026.json)。阶段构建固定IAM 48182c39424573060fda0e27ed6670d2b326f42d、QS d20436edb363c17f0b177126aebe43a44bc5e082、AI 61ef88ac95800dfd3c0c90fd56c102f7c0e77e8f；仅生成隔离候选制品。现有M3固定镜像的旧启动报告不作为本轮重建证明；新八实例必须使用本轮源码的实际打包/decoder、root来源文件及原角色预算完成启动与关闭。D03在真实重建通过前保持进行中。

## C06-D03：当前源码八实例重建已通过

[PR315](https://github.com/FangcunMount/infra/pull/315)以候选012d1ce4fa24d115a1ad01eb063407cb8c52ef99通过13项源码/原生CI后合并。沿用上述三个合并SHA生成的确切五镜像档案，复用原隔离fixture的数据库与mTLS准备；IAM/QS实际renderer、QS实际主机冻结工具及普通镜像原生预检、AI实际绑定打包器和Compose共同产生配置。与M3旧固定来源分开记录，不改写旧报告。

本轮在独立GitHub-hosted Docker环境生成21份合成文件，按原GID设置root所有、0440，并在八实例实际容器内验证27处MQ/JOSE只读挂载、真实UID/GID、原CPU/内存预算、四owner Checker及三个worker48并发。18项检查全部通过，八实例Exit0/无OOM，worker额外9次重启Exit0；MySQL/Mongo运行期DDL为0，旧有容器/网络不变，本轮文件、容器与网络完整清理。原生报告SHA、制品digest、metric及失败历史见[完整receipt](evidence/rocketmq-m4-c06-eight-instance-rebuild-20261026.json)。没有发送生产事件、调用模型或进行system验收。

首次worker服务键映射和第二次Go绑定JSON时长编码错误均在启动应用前失败，隔离清理通过。Go绑定JSON使用纳秒数，YAML/viper配置保留等价时长字符串；仅转换四个固定预算，不规范化原store/epoch。实际源码投影和Go Decode/ValidateFinalBinding/RenderFinal三项检查现已前移到依赖容器启动前，全部通过；不以mock代替原生预检。

## C06-D04：只读材料校验基础已合并，宿主接入进行中

PR316新增 `--verify-staged --expect-role ... --expect-revision ...`。该root入口以审核计划校验已安装目标的完整收据、角色、版本、文件集合、hash、UID/GID和权限；缺失版本直接拒绝。原始来源目录只用于首次预置，不作为普通部署的持续依赖，避免清理旧M3资产后破坏新配置。

验证不创建/复制文件、不激活指针、不再次获取部署锁，允许父CD流程持有原锁时调用；原预览/apply仍保留锁和不可变预置语义。18项源保护、7项旧入口回归及23项真实Linux UID/锁验证通过并合并。这个新入口尚未安装生产，也尚未接到IAM、QS、AI主机部署流程；D04的同步/停止前完整拒绝矩阵和D05冻结仍未完成，不能据此解除CD暂停。


## C06-D04/D05：固定宿主保护与配置契约候选

四角色共用 `--verify-installed` 入口：从已安装版本的root收据取得规范化plan摘要，在最多128份root所有、0600的私有原plan中查找，并分别核对原文件SHA和规范化SHA。D02原plan是格式化JSON，两个SHA不能混用；不新增环境变量或依赖旧M3来源。固定工具摘要为 `36f3046ed453dfbf8beae684269c94d1a6db0abaa23de51e09d41e462c6a3d5c`，父目录root所有且不可被组/其他用户写入，工具root所有、0555。普通部署用户先核对工具身份，再用隔离Python调用这个已安装的确切工具；不得执行上传目录中的root代码。

IAM在包同步前验证，QS worker在配置同步前验证，QS API在既有原生镜像/配置预检之后、配置同步前验证；AI的prepare/apply/restore均在密钥/数据库预检、迁移或停止前验证。Collection不增加MQ依赖。四角色的50项真实Linux权限/调用顺序故障用例已通过，完整三库CI与合并状态以总表及最终receipt为准。GitHub runner的原 `/opt` 为0777，测试在私有mount namespace中绑定本次拥有的root不可写祖先，不更改原 `/opt` 权限；所有合成材料、挂载和命名空间已清理，生产保护不放宽。

[机器可读契约候选](evidence/rocketmq-m4-c06-config-contract-20261026.json)绑定D01原数据库身份、D02四份材料收据、D03五阶段镜像/八实例运行证明，以及D04固定主机入口。阶段镜像仍只代表D03配置重建；后续删除运行实现后的最终镜像由C08重新构建与验收。C06-D05须等待三库完整CI及相关PR合并，不能把候选写成已完成。

生产当前只有D02旧摘要工具及未激活材料，新的只读工具和宿主保护尚未安装启用。C08部署前须按冻结清单安装新摘要工具，保留旧工具/计划/原锁/指针，使用真实部署用户在原锁下逐角色回读，再继续最终配置与应用部署。缺新工具时CD拒绝，不允许跳过校验。IAM/QS暂停、AI自动部署关闭继续保持；本次源码验证不解除暂停，也不表示生产或system业务验收。
