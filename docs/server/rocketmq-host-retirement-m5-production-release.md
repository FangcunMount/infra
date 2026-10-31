# M5 首批生产发布回执

2026-11-01 03:58:04 CST，M5 首批受控发布完成：QS main `4620d11e2cffbc4b67b43965812cff3340f0be43`，MySQL/Mongo 为 clean **111/44**；API 1、Worker 3、Collection 2 均实际就绪、零重启、无 OOM。原两站点入口恢复，公网 HTTPS `/health` 均返回 200，Collection Prometheus 就绪副本数为 2。QS 自动发布仍为 `disabled_manually`。

[结构化生产回执](../evidence/2026-11-01-host-retirement-m5-production-release.json)记录精确源码、镜像、容器 ID、窗口事实、资格验证与私有原件哈希。[执行包](rocketmq-host-retirement-m5-execution-package.md)和[交接历史](rocketmq-host-retirement-m4-m5.md)继续保留准备阶段与失败记录；其中较早的“未执行”只描述当时状态，不作为当前操作授权或可重放步骤。

## 实际窗口

操作号 `20261101033500-1`；T0 为 03:33:03 CST，验收记录在 T0+1501.12 秒形成，未延长 1800 秒正常窗口。A 全局/AI 与 D 全局部署锁原 inode 连续持有，证据双份读取校验后释放；未改锁权限。原六实例只收 SIGTERM，实际 exit0、无 OOM，原容器/镜像/配置保留。

维护 owner 在原 API 仍就绪时注册双真实 Checker，关闭新发送。Collection/Worker 已接受工作结束后，原 API 最后正常退出；维护 SDK 活动/运行/排队为零且真实成功退出后才取得静态保护。管理员路径在执行前实读七项线程/事务/修改/元数据锁/EVENT 计数均零（[41235628434](https://github.com/FangcunMount/qs-server/actions/runs/41235628434)）；这些是独立时点观察，未伪称跨库原子冻结。

W06 两次完整静态基线相同，覆盖 88 对象、408279 行/文档；保全原目标 DDL、真正 EOF 空流及完整 110/false 账本。同窗口十文件在 Mac 与 A 各自读取、哈希和 fsync 后，才生成并消费绑定源码/身份/材料的一次性批准。SQL111 返回 verified=true、unknown=false，Mongo 未变；未执行 force、down、dirty 清除或全库回放。

启动前和启动后两次独立完整比较都确认：差异仅为空 `qs.mysql.ai_messaging_outbox` 缺失、完整 MySQL 账本变为 111/false；其余对象定义、数量及完整内容摘要相同。`system.profile` 从设计起仅保护诊断定义，允许既有 profiler 自然增长；未扩大其他对象例外。其余五候选、execution/guard/witness、原 wire/archive、Inbox、业务 ACK/历史及 retry/hold/调度全部保留。

## 真实启动及前向修复

首业务启动前先持久化不可逆标记，此后 R1 旧账本/旧材料回放永久禁止。API 先就绪，其后启动 Worker 与 Collection。Worker 并行首次接网时，第 2 个容器停在 Created/PID0/exit128，Docker 报 infra-network 不存在；其他副本已连接原 overlay。保留原失败，独立核对准确容器/网络 ID 和持续锁，按 R2 仅对这个未启动容器执行一次 `docker start`。未重建网络、修改数据库或停止健康实例。随后三副本实际 `/readyz` 与反向治理均通过，Collection 两副本实际健康/指标及 Prometheus 就绪数均通过。

当前运行仍全部为 4620；准备好的 1073 同 111 兼容三镜像作为前向恢复备用，本次未启用。故障后只能沿兼容 111 的前向修复路线保留新事实；不得因旧实例仍在就重放 110 账本。

两站点恢复的是原始字节、owner 和 0644 模式，`nginx -t` 与 reload 成功。源站 HTTP 301 和公网 HTTPS 200 均实读。Mac 的公网 HTTP 路径另见 DNSPod 302 webblock，原样记录，未改 DNS、未把它写成公网 301。

## 资格与证据归属

- [QS #477](https://github.com/FangcunMount/qs-server/pull/477)、[infra #419](https://github.com/FangcunMount/infra/pull/419) 已合并；精确 QS main [41229846372](https://github.com/FangcunMount/qs-server/actions/runs/41229846372) 33 成功、1 原条件跳过，infra main contracts [41229762223](https://github.com/FangcunMount/infra/actions/runs/41229762223) 成功。
- 固定 main 双 owner 原生 [41229864790](https://github.com/FangcunMount/infra/actions/runs/41229864790) 原 13 项加 CLI 9 项通过，零失败零跳过；[14 项恢复及三个真实进程启动/排空 job](https://github.com/FangcunMount/infra/actions/runs/41229868407/job/124621663311) 成功。该工作流另三个历史 SDK 控制作业拒绝不匹配版本，整体失败保留，不写成全部通过。
- main CLI 原生 job 124621597511 成功；隔离恢复总耗时 21.49 秒，批准填实际取整 22 秒，未用 3600 秒预算假充测量值。生产 R1 未执行。
- 额外隔离 COMMIT 回包丢失资格运行 [job 124629067389](https://github.com/FangcunMount/qs-server/actions/runs/41232378028/job/124629067389) 成功：服务器已 COMMIT OK、代理真实丢回包，unknown 保留，独立重读完整 110/44 与原材料相同，重复消费被拒。调用的是冻结 main 的同字节 CLI `40969dff…`，资格测试分支不改变生产源码。整体工作流因五项原有未使用代码 lint 失败，单列保留。
- 仅构建 [41231219935](https://github.com/FangcunMount/qs-server/actions/runs/41231219935) 来源、双仓 manifest/config、全压缩层与解压 DiffID 均核验；Docker29 本地 engine ID 与 OCI config ID 分开绑定。初始不完整 save 包和显式 platform 保存失败保留，未当作合格制品。

较早窗口因原文件模式保全在 T0 前取消；本次两次只读 freshness 因 Mac 比服务器慢约一秒被拒，保留失败并以同服务器时钟的真实新鲜 SDK 回执继续，未改时钟或业务事实。业务账号 metadata_lock 查询 1142 保留，改走已有管理员路径，未 GRANT。

## 保全与剩余边界

完成窗口原件归档 SHA256 为 `ae42573b25cfdd15d5b2f76ef0496cea07332dce0a195d261c33c8791367d794`；Mac 私有目录与 A `/var/lib/fangcun-m5-protection/20261101033500-1/completed-window-evidence.tar.gz` 两份完整读取校验一致。原始批准/消费、首次启动、失败/R2、双基线、实际启动和入口回执均保留，至少 30 天且未结责任延期；不自动清理。

原有 51 条缺失原发布事务锚点未关闭，QS 历史 AI MQ 聚合观测仍不可用；当前 57 条回执决策均终态、held=0、Inbox stored=2780、quarantine=0。提醒 confirmed 在实际业务源码中为终态，通用诊断第三列的非业务谓词不作为在途判定。未补造 witness、清空 ACK、批量 retired 或重做历史。该发布关闭首批空表和兼容运行交付，不批准另五对象删除，也不宣称历史责任全部关闭。

本次未制造新的认证业务写入、模型/provider 调用或生产压测；这些不冒充已完成的端到端业务验收。自动 CD 保持冻结，后续部署须固定当前 111 兼容源码/镜像并沿已有审查路线。
