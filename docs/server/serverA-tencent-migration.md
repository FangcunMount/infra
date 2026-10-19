# P. 代码分析报告：serverA 从阿里云迁移到腾讯云

## 分析目标

将旧 serverA 的运行服务迁到腾讯云北京 7 区的 `154.8.167.1`（4C8G）。
MySQL、Redis 继续留在阿里云；MongoDB 留在 serverC，不做数据库迁移。
本文件区分已验证事实、目标配置与尚未执行的切换，不能作为迁移完成证明。

## 分析范围

2026-10-19 通过 SSH 只读核对旧 A、B、D，并初始化新 A。变更位于独立
`codex/servera-tencent-migration` worktree，不改 qs-server 工作目录的未提交业务代码。

| 对象 | 实际状态 / 目标 |
| --- | --- |
| 旧 A | `47.94.204.124`，Tailscale `100.85.122.124`，Ubuntu 24.04，Swarm manager |
| 新 A | `ubuntu@154.8.167.1`，Ubuntu 24.04，4 CPU，MemTotal 7685MiB，根盘可用约 165GiB（初始化前快照） |
| B | 阿里云，当前能连接 RDS 私网；新增 64MiB / 0.1 CPU 的代理，不迁移其业务 |
| C | 腾讯云北京 6 区，MongoDB，保持原服务与数据 |
| D | 腾讯云北京 3 区，worker / NSQ 等，保持原落点 |

## 入口与调用路径

目标路径：

```text
Clients -> 新 A / nginx -> API、collection、AI（新 A）
                       -> IAM、Qlume、MiniBlog、operating（既有 overlay 目标）
新 A API / AI、D worker -> infra-network -> mysql-rds-proxy(B) -> 阿里云 RDS 私网
新 A API / collection -> 原阿里云 Redis 公网地址:16380
新 A -> mongo(C)、nsqd(D)、IAM(B)，保留 Tailscale + Swarm overlay
```

本次不重建 `infra-network`，不将跨云 Swarm 改造成腾讯云 VPC 原生网络。
仅迁移服务器不会自动改变既有 underlay。原网络的 MTU=1280，端点 MTU 需实测。

## 当前职责与依赖

旧 A 实际运行：nginx、qs-apiserver、collection 两副本、qs-ai、mysql-rds-proxy、prometheus-route。
公网入口还代理 IAM、operating、Qlume、MiniBlog、Grafana 和私网监控采集，不能仅迁 QS 域名。

冻结镜像（2026-10-19 只读快照，切换前再次核对）：

| 服务 | 源码 revision | Docker image ID |
| --- | --- | --- |
| API | `84d65b5b58d9037257f5da2660a6a58b2e625378` | `sha256:8b23c9574366c9671d63282caf63455730b90018357c71ca02a3073f56aa7979` |
| collection ×2 | `84d65b5b58d9037257f5da2660a6a58b2e625378` | `sha256:b0f51841f84e4dd798286fd1c8629303fd0b619ca351af26b26db76896f00932` |
| AI | `7c71d1e95500aa20c3d82f57a7304578c8a794dd` | `sha256:e511347af54ea85d6b360f8b6cc89f02eb81f474977871739129a7cf702c2fa8` |
| nginx / route | `nginx:1.27` | `sha256:6784fb0834aa7dbbe12e3d7471e69c290df3e6ba810dc38b34ae33d3c1c05f7d` |

迁移镜像由旧 A 导出、经 SSH 传输后导入，不重新编译、不使用 latest。
旧 A 的 API / collection 原 Compose 目录位于临时发布目录，不能假定目录仍然存在。
因此从实际 `docker inspect` 导出六个服务的私有 Compose，并核对原环境变量和镜像。

## 行为 / 契约 / 不变量边界

- Redis 实例、数据、DB 编号、密码和现有客户端保持原业务语义；仅追加新机访问授权。
- RDS 不迁移、不做 DDL；API / AI 仅将数据库主机改为 `mysql-rds-proxy`，账户、数据库和 URL 参数保持一致。
- 证书、mTLS、消息签名/加密密钥通过 SSH 传输，保持文件内容和数字 UID/GID；不打印、不提交。
- `source-containers.json` 和生成的 `compose.json` 包含凭据，仅保存在新机 root 的 0700 目录，文件 0600。
- 新旧业务容器不能未经控制同时注册相同生产 alias；AI 等消费进程采用先停旧、再启新的顺序。
- 原 qs-server `PRODUCTION_DEPLOY_PAUSED=true` 保持；迁移不顺便发布 main 上的新业务版本。
- 不删除旧主机、旧容器、旧数据卷、回退镜像、源证书或历史日志，不执行 prune。

## 测试与可观测性现状

已核对旧 A 七个运行容器（六个服务类型）的状态与挂载；旧 A 的 nginx、API、collection、AI、RDS 代理健康。
旧 A RDS 解析到私网地址，TCP 连接和 MySQL greeting 成功；B 到 RDS 私网 TCP 成功。
已在 B 启动不带生产 alias、不发布宿主机端口的候选代理，并从旧 A 的 AI 容器通过
该代理完成数据库认证和 `SELECT 1`。B 的六个既有业务容器 ID 保持不变。
候选代理验证后已停止并保留，避免等待用户操作期间持续占用 B 的资源；生产代理仍在旧 A。
旧 A、D 到原 Redis 公网端口 TCP 成功。

导出工具的测试覆盖：数据库 URL 凭据/查询参数保留、Compose 美元符号转义、固定镜像、
只读 bind 挂载与缺失路径拒绝、未审查服务/volume 拒绝，以及 tmpfs 格式。
新机已通过 Compose 配置校验，并逐项比对六个服务的环境变量：仅 API/AI 的 MySQL 路由发生预期改变。
另在新机以 `network_mode=none` 创建六个不启动的临时校验容器，实际核对镜像、环境变量、
bind mounts、内存/CPU、只读根文件系统、cap_drop、security_opt 和 tmpfs 全部符合预期；
临时容器已移除，没有启动应用或注册生产 alias。Compose 美元符号转义也经过真实合成容器验证。
这些检查不等于新机数据库认证、跨机 mTLS 或真实业务验收。

## 分析指标与判定

| 指标 | 判定 | 证据与触发标准 |
| --- | --- | --- |
| 入口清晰度 | 绿 | 已从实际容器、挂载、nginx 路由追到入口、应用和跨机依赖 |
| 行为边界 | 绿 | 固定线上镜像和配置，单独列出 MySQL 主机路由变化，无数据库迁移 |
| 依赖方向 | 黄 | A 迁移后仍依赖阿里云 B/RDS/Redis，不属于完全单云架构 |
| 测试保护 | 黄 | 导出/Compose 检查通过；新机端到端依赖与业务尚未验证 |
| 可观测性 | 黄 | 已发现 mini 监控固定旧 A 地址，切换时需更新来源、gateway、known_hosts 和 extra_hosts |

## 主要风险点

1. 新机必须先登录现有 Tailscale tailnet，才能加入当前 Swarm。设备名 `serverA-tencent`，不能复制旧节点的 Tailscale 或 Docker Swarm 状态目录。
2. 新 A 到原 Redis:16380 当前 TCP 超时。新机 UFW inactive、OUTPUT ACCEPT；现有云凭据无 Redis 管理权限，已请用户核对白名单并追加新 IP。尚不能断言超时原因已定位或已修复。
3. RDS 代理生产 alias 必须单主切换；新旧代理同时提供同名 alias 会造成随机路由。
4. Swarm 管理节点替换必须保持多数派。当前 A/B/D 三 manager；新机先加入现有集群，验证后升为 manager，再降级旧 A。操作使用节点 ID，不能靠重名 hostname 猜测对象。
5. DNS 指向旧 A 的记录不全对应当前有效站点；只更新核实的迁移入口，保存 RecordId/原值/TTL，不批量改全部匹配 IP 的历史记录。
6. 证书续期、CI/CD 目标、监控采集地址都属于迁移闭环，不能只看新容器 healthy。

## 初步发现或假设

B 已可访问 RDS 私网，既有代理的瞬时内存约 9MiB、配置上限 64MiB，因此可优先验证代理迁 B，避免新增 RDS 公网入口。
B 自身内存不宽裕，此瞬时值不能作为峰值容量证明，切换需观察内存和连接情况。
Redis 继续使用同一个实例可避免数据复制和锁状态分裂；新出口授权仍需单独验证。

## 下一步建议与执行顺序

1. 完成 Tailscale 设备登录和 Redis 访问授权，读取新机 Tailscale IP；验证 tailnet 与现有集群网络。
2. 导入镜像并核对完整 image ID；校验证书、密钥、配置、二维码目录的内容和权限。新机保留 ubuntu 登录，deploy 使用受限 sudo；检查 UID/GID 冲突，不能覆盖云镜像现有账户。
3. 在 B 启动唯一候选名的临时 RDS 代理，验证 greeting 和真实数据库只读查询。候选不能注册 `mysql-rds-proxy` 生产 alias。新 A 以隔离探针验证 Mongo、NSQ、IAM mTLS、Redis AUTH/PING 和 MySQL 认证。
4. 通过既有 manager 将新 A 加入同一 Swarm，不运行 `swarm init` 或重建 overlay。用新机 nginx 对现有上游验证所有迁移域名，使用 `curl --resolve`、正确 SNI 和真实证书。
5. 保存 DNS 和部署变量回退快照。验证新入口后按阶段切换：先 RDS 代理，再 API、collection、AI；每步检查依赖、唯一 alias 和健康。失败先停止新实例，再恢复旧实例，避免双消费者。
6. 更新核实过的公网 DNS 入口、qs-server / qs-ai 的 serverA 地址与主机密钥配置；修正新机 hostname 以符合部署前置校验。保持原部署暂停状态，不触发新版本发布。
7. 更新 mini 监控发现来源、gateway、known_hosts、Prometheus extra_hosts；验证新机证书续期并部署续期 hook/timer。
8. 验证完整业务链路并分开记录：镜像/容器状态、依赖认证、域名/TLS、监控、真实业务结果。保留旧 A 回退资产；旧机退订另行执行。

生产凭据不能放进这份文档。执行记录应只保留时间、服务名、固定 SHA、探针结果和回退资产路径。

## 执行进度（2026-10-19）

| 阶段 | 状态 | 证据 / 剩余事项 |
| --- | --- | --- |
| 新机系统与 Docker | 已准备 | Ubuntu 24.04、Docker 29.1.3；保留 ubuntu 免密 sudo；deploy 受限 sudo 校验通过 |
| 镜像与运行配置 | 已准备 | 四个固定镜像导入成功，六个运行规格通过不启动容器的实际比对 |
| 证书与续期 | 已准备 | 两套证书和私钥匹配；两域名 `certbot renew --dry-run` 成功，部署 hook 验证和续期 timer 已安装 |
| RDS 代理迁 B | 候选验证通过，未切流 | 候选连接完成认证和 SELECT 1；旧 A 仍提供生产 proxy alias |
| Tailscale / Swarm | 等待设备授权 | 新机 NeedsLogin；未加入集群、未改变管理节点角色 |
| Redis 新出口连接 | 未通过 | TCP 超时；已请用户核对白名单，尚未完成认证/PING 验证 |
| DNS | 仅完成备份 | 两个域名共 30 条记录保存在新机 root 的私有快照中，没有修改 A 记录 |
| 生产应用 / CI / 监控切换 | 未执行 | 旧 A 继续服务；部署目标、MySQL 的后续 CD 配置和 mini 监控仍须同步 |

新机镜像导入和证书演练完成不代表迁移完成。以上两项外部前置条件解决后，继续从跨机依赖验证推进。

参考：[Docker manager 安全退出](https://docs.docker.com/reference/cli/docker/swarm/leave/)、
[Redis 白名单说明](https://www.alibabacloud.com/help/en/redis/user-guide/configure-whitelists)。
