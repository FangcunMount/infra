# 腾讯云 Redis 切换准备与执行手册

状态：2026-10-20，**生产已切换到腾讯云，30 分钟技术观察通过；用户确认业务验收全部正常**。容量按用户决定保留 256MiB，新实例保留 `noeviction`。用户已授权正式推送上线和切换。自动发布继续暂停，阿里云旧 Redis 保留，不包含退订授权。

## 策略比较与选择

| 行为 | 旧库 allkeys-lru | 新库 noeviction |
| --- | --- | --- |
| 达到内存上限 | 近似 LRU，从所有键中淘汰，含无 TTL 的键 | 不因内存压力淘汰键；需要分配内存的命令可能报 OOM |
| 已有数据 | 会话、吊销/消费标记、锁、去重可能被静默删掉 | 保留到正常过期或显式删除；正常 TTL 仍生效 |
| 可见故障 | 缓存未命中；业务状态丢失可能不易察觉 | 登录/刷新、锁/幂等写入、缓存填充可能失败，必须监测写错误 |
| 读与健康检查 | 通常继续响应 | GET/PING 可正常；DEL 等释放内存的命令仍可能成功，PING 不能证明可写 |
| 多逻辑 DB | 共享实例内存，不能隔离缓存与认证状态 | 同样共享内存；DB2 缓存增长可使 DB0 认证写入失败 |

本实例同时承载 IAM 状态、分布式锁和 DB8 长期去重（默认 400 天），因此推荐 `noeviction`，不能把它作为全部可丢弃的缓存。正常 TTL 过期与内存淘汰不同。`noeviction` 也不替代备份、持久化或故障恢复。

旧库采样约 38MiB，历史峰值约 212.88MiB（时间与成因未知），尚无淘汰计数。准备时源库快照 44 个键、DUMP 数据 44,490 字节；这不是峰值工作集。新库空库与探测连接开销约 8MiB，不能用空库占用保证 256MiB 长期足够。

设 70% 内存警戒、80% 或新增 OOM 为停止推进条件；不自动删除业务键，不自动换成 LRU 或扩容。切换后执行有限 30 分钟观察，后续接入长期云监控仍需单独闭环。

官方行为依据：[Redis Key eviction](https://redis.io/docs/latest/develop/reference/eviction/)。隔离实测已覆盖跨 DB 淘汰无过期认证键、满额写拒绝、旧值保留、读取和 DEL。

## 范围与配置不变量

- 源：`r-2zegjo7i4al4sh8q83pd.redis.rds.aliyuncs.com:16380`，Redis 7.0.15，迁移前生产明文连接；现已无业务连接和新增写入。
- 目标：`crs-3dli07u2`，`bj-crs-3dli07u2.sql.tencentcdb.com:23136`，Redis 7.1.10，公网 TLS，完整 CA 和主机名校验，最低 TLS 1.2。
- A：IAM ×1（DB0）、API ×1、collection ×2；D：worker ×3。QS 默认 DB1，profiles 保留 DB0、2—8；不统一 DB 号。
- 不改镜像、MySQL、MongoDB、消息配置、资源限制、健康检查或业务代码；不发布当前 main 的其他功能。AI 没有直接 Redis 连接，但验收覆盖上下游。
- 腾讯云 APP 的已验证认证方式是单参数 `AUTH 账号名@密码`。Go 的 Username 留空，Password 用复合值。密码来自本机私有文件，手册不保存值。
- CA：`components/redis-client/ca-chain.pem`，SHA256 `620fec36c5647475f0be9c51afe21d05d88ccf61cfadc578ceb069d8def97132`。
- 宿主 CA `/data/infra/ssl/redis/ca-chain.pem`；容器只读挂载 `/etc/qlume/redis/ca-chain.pem`，设置 `SSL_CERT_DIR=/etc/ssl/certs:/etc/pki/tls/certs:/etc/qlume/redis`，保留系统根证书。禁止 skip verify。

四类当前镜像均已用原 Go Redis 客户端验证证书、主机名失败场景和重连。无需制作业务镜像：

| 类型 | 固定 image ID |
| --- | --- |
| API | `sha256:72c13c69cfa4ed68c9eeeba81c72bff678f02b803a7ddc3d5aac2205ae7cfbdd` |
| IAM | `sha256:57a47a713f336d84f6ba48fac7c0f229c38318ed16115071b20b7e7bcabdfbf5` |
| collection ×2 | `sha256:b0f51841f84e4dd798286fd1c8629303fd0b619ca351af26b26db76896f00932` |
| worker ×3 | `sha256:6a495795a99668c08fa579c7647001414e5a912809a72414ecc9024004548fd1` |

## 已准备的材料与工具边界

A/D 的 `/root/redis-tencent-cutover-20261019` 为 root 私有目录：

- `target.json`：新库凭据；A 的 `old-connection.json` 保存旧库回退凭据。
- `plans/<容器名>/plan.json`：原 inspect、固定镜像、配置文件哈希、仅 Redis/TLS 变化的 Docker create payload。**包含生产凭据，不得进入 Git 或普通日志。**
- A 的 `source-live-baseline.json`：实际源库备份，`consistent=false`，仅保全与预演，不可作为最终恢复输入。
- `common-env-plan.json`：`/opt/infra/compose/env/prod/serverA.env` 或 serverD.env 的前后版本及原哈希；执行时已比对并应用到活动文件。
- `toolkit/`：固定 CA 与工具；A 已更新审核后的 infra 来源，D 仅安装本轮 Redis 文件，保留宿主原有未提交修改。

工具：`runtime.py plan/verify` 仅生成/验证计划，不停止、重建或启动容器。`data.py export/inventory/verify/clocks`、`restore` 默认 dry-run；恢复必须显式 `--apply`。`reconcile` 是写入新库后的受控反向镜像，同样默认 dry-run。`cli.py` 只允许盘点读命令并验证 TLS。`monitor.py` 仅运行指定观察窗口。

这里没有通用一键生产切换器。执行时需按下述事务边界记录实际 Docker API 调用与回执，不能把 plan 成功当成部署成功。

## 正式切换顺序

1. **窗口前关口**：保留自动发布暂停，确认没有部署、维护、统计/热度重建或其他 Redis 写入。核实旧库额外 `100.104.168.8` 两条连接归属；不能直接当作监控或盲目 kill。确认所有业务写方清单完整。重新运行控制预检：等待 command/result/audit fallback 完成，锁自然释放，不手动 DEL 活锁。
2. **代码与配置先审后用**：infra、QS、IAM 本次补丁通过检查并合并后，固定 infra SHA，仅安装审核过的 Redis 文件，避免发布其他 main 改动。A/D `python3 /opt/infra/scripts/redis/ca.py verify` 必须成功。维护 Actions 使用 host 只读客户端，不能依赖 `redis-cli --sni` 代表完整主机名校验。
3. **冻结写入**：关闭相关入口与定时/维护触发，排空请求/消费者；在 A/D 持有 `/var/lib/fangcun-image-retention/deploy.lock`，禁止竞争部署。先再次验证七个原计划的容器 ID、配置哈希及网络。禁用原容器自动重启，按原有 StopTimeout 优雅停止七个容器，检查退出状态。API 已配置约 8 分 30 秒排空上限，停写窗口不能只按传输时间估算。
4. **冻结回执**：root 私有 JSON 必须记录全部写方已隔离的人工确认、source_host、有效期不超过十分钟的 expires_ms，以及 A 四个、D 三个容器的 name/running=false/restart_policy=no。工具验证这份回执的完整性；操作者必须从两台宿主的真实 inspect 生成证据，不能手填“成功”代替验证。若窗口超时，重新核验并生成回执。
5. **时间与最终快照**：使用旧、新连接运行 `data.py clocks --connection old-connection.json --peer-connection target.json`，时钟差关口 ≤2 秒。随后 `export --connection old-connection.json --frozen-receipt fence.json --output final-source.json`；只用冻结快照。保存 checksum，复核目标 DB0—8 全空。
6. **恢复并核验**：`restore --connection target.json --snapshot final-source.json` dry-run；审核后加 `--apply --frozen-receipt fence.json`。使用 DUMP/RESTORE ABSTTL，跳过已过期键，不恢复原 TTL、不复活过期令牌。目标非空即拒绝，不用 FLUSH 或 REPLACE。`verify` 要求 DUMP、绝对期限一致且无额外键。恢复中途失败则保持冻结、保留两边证据；不得直接重试或清空目标。
7. **容器网络交接**：七个原容器实际使用静态 IPAM。原容器停止后，逐项保存名称/网络连接回执，重命名原容器并断开其端点以释放静态 IP，再按审核 payload 创建同名替代容器，保留 IP、alias 和所有其他设置。不得重建全局 Docker 网络。第一台启动前仍可删除本轮新建的未启动容器、恢复旧名称并按原 IPAM 重连原端点。
8. **写入提交点**：第一台新容器启动即视为新库已接受写入，即使公网入口尚未放开。顺序 IAM→API→worker 三副本→collection 两副本；原 IAM 保持停止，禁止双实例。逐项核对镜像、CA 挂载、环境、就绪、Redis 连接和错误。不要跨两个独立 Redis 滚动运行 worker。
9. **收敛默认入口**：在保持发布暂停的情况下，审核并原子应用 common-env 私有计划（先比对原哈希）；更新组织共享 Redis Secrets，保留各仓库 REDIS_DB。确认维护盘点/控制预检通过。没有通过以上关口就不放开业务入口。
10. **验收与观察**：恢复入口，验收登录/刷新、问卷读取提交、已有报告、AI 请求、worker 消费、后台权限；观察内存、OOM、应用错误、锁/幂等和授权新鲜度至少 30 分钟。在腾讯云对迁入数据完成真实备份，并只在隔离实例验证恢复。空库旧备份不能替代。保留阿里云实例，后续另行决定退订。

工具路径可取 root 暂存 `toolkit/scripts/redis`；快照、fence 和连接文件均要求 0600，父目录 0700。执行操作须记录 SHA、主机、时间、计划哈希与实际结果，不记录密码、键名或值。冻结结束前任何异常均停止推进。

## 组织设置清单（已应用）

| 共享 Secret | 切换值 |
| --- | --- |
| REDIS_HOST | `bj-crs-3dli07u2.sql.tencentcdb.com` |
| REDIS_PORT | `23136` |
| REDIS_USERNAME | 删除旧共享值，使其为空；先核实无仓库/环境覆盖 |
| REDIS_PASSWORD | 由私有凭据生成 APP 账号名与密码的复合认证值，不写入文档 |
| REDIS_USE_SSL | `true` |
| REDIS_SSL_INSECURE_SKIP_VERIFY | `false` |

保留原有组织可见范围，保留 QS DB1、IAM DB0，检查仓库和 environment 无旧 endpoint 覆盖。组织管理 API 返回 403；通过已授权的组织管理页面完成更新，并由管理员完成 GitHub 再次身份验证。真实只读维护 Actions 已使用新配置通过。自动发布暂停继续保留。

## 回退分界

- **第一台新容器启动前**：目标恢复失败也保持原源库，恢复原容器名称、静态端点和原 restart policy 后启动旧容器，恢复旧入口。新库的残留迁移数据私有保全，单独处理，不能用全库删除掩盖失败。
- **新库开始写入后**：严禁仅把地址改回旧库。先冻结所有新写方，生成新源 fence 与快照，再备份旧目的库。`reconcile --connection old-connection.json --snapshot latest-new.json --before-snapshot reviewed-old.json` 先 dry-run，审核 stale 删除和更新数后才 `--apply --frozen-receipt new-fence.json`。它按绝对期限同步新值、明确删除已不存在的旧键，目的库漂移即拒绝。核验完全通过后再恢复原容器/入口以及组织、common-env 旧值。
- 已真实验证 7.0→7.1 和 7.1→7.0 的测试 DUMP/RESTORE、二进制内容与 ABSTTL，反向格式兼容目前成立；仍须以正式数据逐键核验为准。
- IAM 消费/吊销标记、锁、去重不得当普通缓存丢弃；回退过程中保持全局冻结，失败时保留现场，不自动降级 TLS。

## 生产执行与验收记录

代码已通过检查并合并：[infra #40](https://github.com/FangcunMount/infra/pull/40)、[IAM #133](https://github.com/FangcunMount/iam/pull/133)、[QS #408](https://github.com/FangcunMount/qs-server/pull/408)。本次只替换 Redis/TLS 运行配置，七个实例沿用上表的业务镜像，不发布 main 的其他业务改动。

- 全局停止七个写方，控制作业与 DB6 锁为零，时钟差保守上界 5ms。旧库额外两条连接 age=idle、cmd=NULL，长期未发命令；未将其认定为业务连接，也未 kill。
- 最终冻结快照 40 键、DUMP 50,282 字节，checksum `7a4141ea2f5aea100f5462f1d77665df04ab85d50ddfd79259a43d7609d45995`。迁入后 DUMP 与绝对过期时间一致，missing/mismatch/extra 均为 0。
- 从腾讯云冻结目标实际导出同 checksum 的逻辑备份；在隔离 Redis 7.0.15（仅 Unix socket、TCP port 0）恢复全部 40 键并验证内容和绝对过期时间。此恢复测试不表示恢复过云 RDB。
- 腾讯云另行完成迁入后的手动云备份，2026-10-19 23:13:26，状态正常，控制台大小 591.27KB，格式 RDB-Redis 7.0。
- 七个新实例逐项就绪，实际 TCP 连接均指向公网目标；严格 CA/主机名验证、只读 CA 挂载、原镜像、资源和非 Redis 环境一致。旧容器保留、停止、restart=no。默认 env、冻结 Compose 与组织 Secrets 已同步。
- 首次真实维护 Actions 发现宿主公开 CA 目录受 umask 077 影响为 0700，deploy 无法读取；运行容器未受影响。只将专用公开 CA 目录修正为 0755、PEM 为 0644，并增加安装器回归覆盖。未知内容和私有祖先目录保持原权限。19 项隔离测试通过。
- 修复后 [真实 Redis status Actions](https://github.com/FangcunMount/qs-server/actions/runs/39277559475) 成功；组织配置、宿主部署账号和 CA 验证均已实际执行。db-ops 工作流恢复 active，QS/IAM 自动生产发布仍暂停。
- 2026-10-20 只读复核：三个 worker 均 ready，每个原 NSQ 通道均有三个新 worker 客户端，finish/requeue/inflight 计数均为 0。业务验收已由用户确认；当前计数仍不能独立证明新消息实际消费。
- 合并后 [主分支 CI](https://github.com/FangcunMount/infra/actions/runs/39280052929) 和 [专项分支 CI](https://github.com/FangcunMount/infra/actions/runs/39280030869) 均已成功。

30 分钟观察共 61 个样本，峰值内存 12.18MiB（4.76%），OOM 与淘汰计数均为 0，旧库业务连接和新增写入为 0。观察结果以 [执行回执](evidence/redis-tencent-cutover-20261019.json) 为准。2026-10-20，用户确认小程序重新登录、问卷读取与提交、已有报告、一次 AI 请求及后台登录和权限页面全部正常。未配置持续云监控告警，也未退订旧 Redis；这两项不包含在本次技术切换完成声明中。后续新写入发生后回退必须使用上文冻结与反向核验流程，不能直接改回旧地址。
