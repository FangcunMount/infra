# M4 最终生产发布索引与恢复边界

**M4清理后的最终八实例已上线，system及新答卷/新AI业务回归通过，公共入口于2026-10-27 09:22:52恢复。** 维护从09:05:31开始，约17分21秒，无延期。M4任务38/38、父任务8/8；最终文档PR合并后全部闭环。唯一进度见[M4总表](rocketmq-m4-execution.md)，精确身份和摘要见[最终release receipt](evidence/rocketmq-m4-final-release-20261027.json)。自动生产CD保持暂停。

## 源码、制品、部署与业务

| 层次 | 已验证结果 | 权威证据 |
| --- | --- | --- |
| 应用源码/依赖 | IAM `4609d4542d9303130ab94ed67593d0a69d0d010d`；QS `1f38f583d43c9faf4601a5df9f3f82b764e6547d`；AI `b00cf3a2f30deffa99e9bf71aa1b6177c651c23c`；各库已合并，最终源码/原生矩阵通过 | [最终审计](evidence/rocketmq-m4-c08-final-audit-20261027.json) |
| 稳定SDK | Go v0.5.0 / Python0.4.0；源码`1345266aa0e864c46de5d1e3e3c939dd8002a890`，wheel摘要与正式依赖保持；M4未改tag或制品 | [依赖/摘要](evidence/rocketmq-m4-final-release-20261027.json) |
| 镜像发布 | 五类固定ACR镜像；run40371739428为5/0/0。云端离线engine ID、原始config/rootfs与ACR manifest分别记录，未复制CI凭据 | [发布receipt](evidence/rocketmq-m4-c08-acr-publication-20261027.json)/[冻结receipt](evidence/rocketmq-m4-c08-final-freeze-20261027.json) |
| 运维源码 | PR340—343已合并；固定启动/原锁/维护边界Linux及macOS各27项通过，run40429156660。最后索引PR只修改文档/receipt，不重建应用 | [执行包](evidence/rocketmq-m4-c08-window-ready-20261027.json) |
| 真实部署 | serverA五实例、serverD三worker按原预算/UID/GID运行；健康/HTTP ready、0重启、无OOM；四owner就绪、10监控目标up，D可用1218MiB | [实际部署](evidence/rocketmq-m4-c08-production-deployment-20261027.json) |
| 真实业务 | 合法system空角色与IAM/QS双订阅；用户本轮新答卷→评分→规则报告；一次新解读、一次模型调用、4个AI事件/首次ACK及13条业务witness全部对齐；旧模型任务未变化 | [业务汇总与私有证据摘要](evidence/rocketmq-m4-c08-production-deployment-20261027.json) |
| 公共入口/数据 | 原三站点字节/inode/权限恢复，临时验收例外移除；公网4项TLS200。未执行DDL、凭据/Topic/ACL/Redis变更或Broker重启 | [恢复回读](evidence/rocketmq-m4-c08-production-deployment-20261027.json) |

## 保留责任和独立后续项

- NSQ三容器保持停止、restart=no、无监听/活动连接；1519个文件及原配置/备份完整摘要一致。历史表、卷、镜像及备份按[C07台账](rocketmq-m4-retained-assets.md)保留，最早2026-11-25复核；没有物理删除或自动GC，未决事实不自动过期。
- 当前Inbox/receipt、首次wire/ACK、模型response/checkpoint、消费幂等、业务重试/未来调度与witness/Checker继续承担责任。保留旧名称的当前业务记录不等于旧Relay仍运行。
- IAM、QS的`PRODUCTION_DEPLOY_PAUSED=true`；AI的`AUTO_DEPLOY_ENABLED=false`。本批没有恢复自动生产CD。
- 既存IAM角色授权详情读取出现服务端错误，单独登记为未解决；本轮空角色创建、零grant/member、策略原子提交和双订阅有独立证据，未假称详情接口通过。
- R01—R03高级原生超限恢复见[独立台账](rocketmq-native-recovery-followups.md)，PL-R007/008保留原移交；均不冒充已完成。M3 T34沿用用户豁免，未进行或声称48小时观察通过。
- 首启动屏障继续有效；不得使用旧全量备份覆盖当前事实，不切回NSQ/Outbox、不补发旧消息或重做模型。后续修复使用精确候选及原证据前向处理。

## 已执行冻结清单（历史快照）

以下内容保留执行前的具名清单与恢复约束，其中“尚未”“未来”指执行前快照；当前结果以上方发布索引及2026-10-27实际receipt为准。旧v3窗口已经完成，不得复用原T0/例外或直接重跑部署；后续变更需重新冻结执行清单。

## 当前准备和待冻结项

- IAM候选4609d4542d9303130ab94ed67593d0a69d0d010d、QS候选1f38f583d43c9faf4601a5df9f3f82b764e6547d均已合并且运行输入冻结；后续仅文档/workflow提交不冒充镜像代码变化。
- C08审计发现AI还安装SDK的NSQ extra及无调用的CI NSQ服务；[AI PR231](https://github.com/FangcunMount/qs-ai/pull/231)移除它们。候选b00cf3a2f30deffa99e9bf71aa1b6177c651c23c已通过14项完整CI、两档各5668用例、真实依赖及重新构建/八实例验证。此前f83472c7的AI镜像仅为阶段证据，不作为最终发布。
- [归档发布器](rocketmq-m4-final-candidate.md#固定归档发布)仅传输固定归档、预检全部目标tag不存在并回读不可变manifest/config摘要。最终v2发布计划和18项报告已绑定AI依赖修正；旧计划禁止进入最终生产发布。[正式发布40371739428](https://github.com/FangcunMount/iam/actions/runs/40371739428)已通过5/0/0；IAM工作流d2291007、infra传输dd65adab已固定并合并。原始[发布receipt](evidence/rocketmq-m4-c08-acr-publication-20261027.json)不包含部署。
- [主机准备回执](evidence/rocketmq-m4-c08-host-preflight-20261027.json)记录固定只读材料工具安装、四角色普通部署用户正向校验及8项错误绑定拒绝。该回执是当时快照；随后[API原生冻结工具](evidence/rocketmq-m4-c08-api-tool-install-20261027.json)已固定安装，尚未调用、激活材料或部署应用。
- [最终候选冻结receipt](evidence/rocketmq-m4-c08-final-freeze-20261027.json)已固定五类ACR引用、归档/config/云端engine ID、五项目Compose/环境/21材料及API正式离线预检。[v3包](evidence/rocketmq-m4-c08-window-ready-20261027.json)已冻结维护/停止/启动/前向恢复与最小system用例；实际T0仅在门禁复核后创建。

## 具名目标和保持项

| 主机 | 容器 | 固定预算 |
| --- | --- | --- |
| serverA | iam-apiserver | UID/GID2000；1GiB/1CPU；iam.mysql 8发送/4回查/32队列/100维护 |
| serverA | qs-apiserver | UID/GID2000；1GiB/2CPU；qs.mysql与qs.mongo各4/2/16/50 |
| serverA | qs-collection-server-1、qs-collection-server-2 | 各UID/GID2000；320MiB/1CPU；不新增事务owner |
| serverA | qs-ai | UID/GID10001；768MiB/0.75CPU；ai.mysql 4/1/16/100 |
| serverD | qs-worker-runtime-1、2、3 | 各UID/GID2000；768MiB/1CPU；各48并发；publish=false且无事务owner |

本批不执行DDL或数据迁移；实际目标仍IAM45、QS MySQL110/Mongo44、AI0043_native_transaction_limit。原store、writer epoch、m3-1路由、Topic/ACL、TLS、数据库凭据、Redis位置、Broker参数、监控位置、端口和网络不变。MQ/JOSE仅改为已核验版本文件的只读挂载，不重新生成密钥。保护全部当前/前序/pin/容器引用镜像、原指针及部署锁inode；不调用任何镜像清理或保留策略的apply。

## 已冻结的应用参数（尚未执行）

固定目录`/opt/fangcun-m4/releases/m4-c08-20261027-v1`。下表各Compose、同目录`runtime.env`、主配置/事件文件及镜像完整摘要均由[receipt](evidence/rocketmq-m4-c08-final-freeze-20261027.json)逐项绑定；API最终主配置由正式原生工具生成，不能拿`base-compose.json`运行。

| 主机 / 目录 | 原project | service / 副本 | 最终Compose |
| --- | --- | --- | --- |
| A / `iam` | `docker` | `iam-apiserver` / 1 | `iam/compose.json` |
| A / `ai` | `qs-ai` | `qs-ai` / 1 | `ai/compose.json` |
| A / `qs-api` | `servera-migrated` | `qs-apiserver` / 1 | `qs-api/compose.json` |
| D / `qs-worker` | `qs-worker` | `runtime` / 3 | `qs-worker/compose.json` |
| A / `qs-collection` | `qs-collection` | `server` / 2 | `qs-collection/compose.json` |

未来启动只能在协调器核对维护/排空和精确文件摘要、持有原锁后，使用原project、上述Compose与env文件，以及`up -d --no-build --no-deps --pull never --wait --wait-timeout 60`和固定service/副本。A还须保持原AI部署锁；D三个worker另查真实HTTP ready，不能用没有Docker healthcheck推断失败或通过。精确协调包及来源见下节；必须由同一入口填写真实T0/期限，不能直接绕过门禁执行参数表。

新包保留原四owner的publish=true，worker始终false且无owner，由外部维护入口阻止新业务；本次不先冻结closed API后再改同SHA配置。未来API binding指针已准备，原活动`/data/infra`指针不变；原生冻结按QS源码SHA不可改写。普通deploy实际调用、重复冻结和三组错误参数拒绝均已通过，原sudo规则保持。

## 维护入口和C08-03门禁已验证

serverA原`nginx`镜像sha256:6784fb0834aa7dbbe12e3d7471e69c290df3e6ba810dc38b34ae33d3c1c05f7d已实际验证原始/closed两种三站点组合，两个`nginx -t`均退出0。[非活动入口receipt](evidence/rocketmq-m4-c08-inactive-ingress-20261027.json)固定`/data/apps/nginx-configs`下`iam.fangcunmount.cn.conf`、`qs.fangcunmount.cn.conf`、`collect.conf`的原/closed摘要、inode及权限；副本在固定release目录的`ingress/original`和`ingress/closed`。测试容器无发布端口、原主机挂载只读，缓存/日志写入临时tmpfs，完成即清理；未reload或更改原Nginx/站点。

本次真实关闭时须再次核对这三个原文件及Nginx身份，保持原inode/owner/mode写入已冻结closed字节，先全量syntax检查再reload并核对实际503。首次应用启动前若需撤销本次维护，只恢复本次原始三文件并验证/reload，不触及数据库或旧M3运行状态。首次M4启动后业务恢复采用前向修复，不能把恢复HTTP入口当成允许回退旧业务/数据。system来源、实际T0/期限和有界验收例外只能在合法会话就绪后记录；没有用测试地址/时间冒充生产事实。实际在途/停止与启动协调已由下节v3包冻结；仍须复核真实门禁。

## 窗口前门禁

1. 最终源码/依赖CI、当前实际宿主故障和五归档验证通过；稳定SDK Go0.5.0/Python0.4.0及wheel摘要保持。最终八实例实际启动/关闭、零DDL、原预算、全部清理通过。
2. 从实际主库只读回读四owner的原字节binding及clean heads，不用SDK binding schema_version代替宿主迁移head；核对八实例身份/资源/重启和worker HTTP ready。serverD可用内存至少512MiB；不足或出现OOM/非预期重启则停止。
3. 固定新镜像已通过原归档在主机离线预置：两主机ACR读取鉴权拒绝，未复制CI凭据；必须核对真实保存config SHA、rootfs及关键配置，再使用冻结的实际engine ID，不能把该ID误当作ACR manifest。保留原镜像。调用固定root材料验证器，核对已安装的精确审核API原生冻结工具；仅授权固定源码/镜像、基路径和UID/GID。普通部署用户实际原生预检成功、重复冻结一致且错误输入在替换前拒绝后，才能准备启动。
4. 原私有配置、环境、挂载、网络与服务身份在原主机内冻结，不将凭据或原wire导出。新包以真实Compose解码回读，并逐字段比对原owner/预算、只读材料、服务证书、监听及下游地址。root工具、sudo规则、计划和源码均绑定精确摘要；保留原版本。
5. system合法会话与门店A最小验收入口就绪。用户已正常登录，页面核对actor10001，且已准备新答卷等待一次提交。不能用管理员令牌、替代身份或数据库探针代签system验收；入口未准备好不进入维护。
6. 核对AI真实在途、已有模型调用/checkpoint和未来调度责任。需要额外等待时留在窗口前；不为清理强杀模型、重置attempt、重做unknown或重新投递旧消息。

## 唯一v3执行入口

[receipt](evidence/rocketmq-m4-c08-window-ready-20261027.json)冻结唯一操作`20261027-c08-v3`及全部摘要。实际目标[源码副本](evidence/rocketmq-m4-c08-window-operator-20261027.py.txt)与本地协调器`/Users/yangshujie/.local/state/fangcun-m4/20261027-c08-runtime/window_execute_v3.py`的摘要必须与binding相同。目标状态目录`/var/lib/fangcun-m4/windows/20261027-c08-v3`；v1/v2仅保留失败证据、禁止执行。

| 顺序 | 同一协调入口参数 | 实际门禁 |
| --- | --- | --- |
| 1 | `close --host serverA` | 原Nginx/三文件/原锁匹配，写入已验closed字节；实际503后保存T0/期限 |
| 2 | 原quiescence只读入口 | Prepared/queued/leased/活动模型为0，旧blocked及模型身份保持 |
| 3 | `stop --host serverD --role qs-worker`；A依次`ai`、`qs-collection`、`qs-api`、`iam` | 只停止原ID/配置，原锁覆盖，真实Exit0；不假称ShutdownIncomplete已结束 |
| 4 | A `start --role iam`、`ai`、`qs-api`；D `start --role qs-worker`；A `start --role qs-collection` | `--host`明确A/D；持久首启动标记先于命令，固定image/参数，无build/pull/deps；保留9分钟验收余量 |
| 5 | `status --host serverA`、`status --host serverD` | 八实例kernel UID/GID/资源/image/health，D三HTTP ready；四owner保护另读 |
| 6 | `acceptance --host serverA` | 同T0期限内仅实际TCP来源通过维护503；正常TLS/应用登录保持 |
| 7 | system业务用例及精确只读关联 | 一个新空角色无grant/member并验证双订阅；一次新答卷→评分/报告；一次新解读业务操作→receipt/state/ACK；旧任务不重试 |
| 8 | `open --host serverA --business-proof <本次实际私有证据>` | 三项真实证据通过后恢复本次原始三站点字节并test/reload，不伪造proof |

五项目CLI默认预览与十次普通镜像id探针已在实机通过；原锁owner/inode/mode、www/app别名及原预算保持。源CI两系统各27项覆盖漂移/锁互斥/失败不回退；真实八实例关闭、零DDL及进程/Broker恢复沿最终native报告，不在生产注入故障。用户已授权按M4自动处理同类操作；本次不增加数据库、凭据或路由变更。

## 受控执行顺序

窗口目标不超过30分钟。v3包创建真实T0和1800秒期限；启动前至少剩540秒验收预算。未知结果保留标记并前向修复，不重置T0。

1. 通过既有维护入口封闭新业务写入，IAM登录一并维护；允许已接受工作沿当前事务协议收敛。保留读证据和Checker，不把开关、取消或lease当作回滚证明。
2. 记录未决责任、当前准入revision及实际在途；等待真实任务排空。关闭失败或ShutdownIncomplete不得假称已停止，也不提前关闭DB/loop。
3. 原共享部署锁覆盖具名配置替换和启动；不删除/重建锁。原eight-runtime镜像和配置继续保留。仅使用冻结的最终配置和材料版本，不运行旧M3 credential/schema/cutover步骤。
4. 按冻结依赖启动IAM、AI、QS API、三个worker和两个collection实例；注册四owner Checker、验证全部worker消费者。新外部写保持维护，核对实际image ID/source/config/material、UID/预算、健康和原生保护状态。
5. 在合法system会话内执行具名最小业务回归；逐项核对数据库事实、精确witness、消费效果和业务receipt，再解除本次维护。恢复失败按原revision查询，不盲目重复开门。

## 恢复边界

- M3首个新runtime屏障持续有效，任何阶段均不能用旧全量备份覆盖当前业务事实；不得运行旧离线迁移、NSQ/Outbox provider切换、消息补发或模型重做。
- 新候选尚未启动时，准备失败只保留新材料/镜像供核对；当前运行实例和原配置保持。解除本次新加维护须核对原准入责任，不能恢复早已关闭的业务开关。
- 发出本次首次启动命令后保留全部事实，按精确镜像、配置和已冻结原事务证据前向修复；允许相同候选受控重启，不承诺未经验证的旧应用版本回退。不得更换事件ID、writer epoch或重置未知状态。
- 故障注入仅在隔离CI。实际进程/Broker退出与新实例回查、模型调用不增加分别有证据；生产不注入故障。原生超限高级恢复R01—R03继续独立，不加入本批，也不授予自动解除保护权限。

## 最小业务验收及发布记账

IAM使用具名空角色操作验证实际witness及IAM/QS双订阅；答卷→评分→规则报告与QS→AI command→receipt/state→ACK分别验收。若需要新答卷或新模型调用，先冻结唯一新测试对象/请求及次数，不复用原已完成答卷或七个blocked请求。Task外部提醒及额外模型评测不在本批，不发送测试通知。

当前尚未完成这些真实用例。任何既往M3验收、容器健康、源码/CI或探针均不能填成本轮system通过。48小时观察仍是用户对M3 T34的豁免，不新增观察门禁，不伪称已通过。收尾分别记录源码合并、稳定SDK保持、五镜像发布、主机工具/材料启用、八实例实际部署、业务验收、政策保留及自动CD暂停，再更新C08和最终发布索引。
