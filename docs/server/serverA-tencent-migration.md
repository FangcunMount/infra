# P. 代码分析报告与执行记录：serverA 迁入腾讯云

2026-10-19 已完成生产入口和应用切换：腾讯云 `154.8.167.1` 承载 Nginx、
qs-apiserver、collection 两副本、qs-ai 和 prometheus-route。
MySQL、Redis 实例及数据保持原样；MySQL 私网代理迁至阿里云 serverB，MongoDB 保持在 serverC。
本次使用原线上镜像，没有发布新的业务版本或执行数据库 DDL。

运行证据：[迁移核验快照](evidence/servera-tencent-20261019.json)。
这份快照记录服务器、依赖和入口核验。切换后，用户已确认小程序登录、打开问卷和查看已有报告均正常；
新增答卷提交、生成新 AI 报告等链路未纳入本次验收。

## 分析目标与范围

通过 SSH 核对旧 A、B、C、D、Mac mini 和新 A 的实际容器、挂载、调用路径和发布脚本，
再实施服务器替换。代码变更位于独立 `codex/servera-tencent-migration` worktree；
没有修改 qs-server 工作目录的未提交业务代码。

| 对象 | 切换后状态 |
| --- | --- |
| 新 A | 腾讯云北京 7 区，4C8G，Ubuntu 24.04，公网 `154.8.167.1`，Tailscale `100.74.123.45`，Swarm manager |
| 旧 A | 阿里云 `47.94.204.124` / `100.85.122.124`，已降为 worker；只保留 Nginx 处理旧 DNS 缓存，原应用和代理已停止并保留 |
| B | 阿里云，新增 64MiB / 0.1 CPU 的 mysql-rds-proxy；六个既有业务容器 ID 未变 |
| C | 腾讯云北京 6 区，4C4G，MongoDB 服务与数据未迁移 |
| D | 腾讯云北京 3 区，worker、NSQ、RocketMQ 保持原落点 |
| Mac mini | 原 Prometheus/Grafana 数据卷保留，发现来源和采集入口改为新 A |

新机 Tailscale 设备名为 `serverA-tencent`，操作系统 hostname 保持 `serverA`，满足原 CD 主机校验。
新旧节点暂时同名，Swarm 变更必须使用节点 ID：
新 A `jgna7l1gjknfv1g8gjgw0huau`，旧 A `n7rqopks61wjms3dl37gzv16r`。
目前 manager 为新 A、B、D，均 Ready；原 overlay ID `m3tfd5h9sp5d1xmzht0ey0oql` 未变。

## 入口与调用路径

```text
Clients -> 新 A / nginx -> API、collection、AI（新 A）
                       -> IAM、Qlume、MiniBlog、operating（既有 overlay 目标）
新 A API / AI、D worker -> mysql-rds-proxy(B) -> 阿里云 RDS 私网
新 A API / collection -> 原阿里云 Redis 公网地址:16380
新 A -> mongo(C)、nsqd(D)、IAM(B)，使用现有 Tailscale + Swarm overlay
Mac mini -> 新 A monitoring 私网入口 -> 各应用 metrics
```

迁移没有将现有 Swarm 改成腾讯云 VPC 原生网络；B、RDS、Redis 仍然跨云。
`infra-network` 的 MTU=1280，保持原子网和网络标识，没有执行 `swarm init` 或重建网络。

## 当前职责、行为契约与边界

旧 A 实际运行七个容器：Nginx、API、collection ×2、AI、RDS 代理、prometheus-route。
入口还覆盖 IAM、operating、Qlume、MiniBlog、Grafana、NSQ、worker 和私网监控。
冻结镜像均从旧 A 导出，经 SSH 导入新 A；没有重新编译或替换为 latest：

| 服务 | revision | Docker image ID |
| --- | --- | --- |
| API | `84d65b5b58d9037257f5da2660a6a58b2e625378` | `sha256:8b23c9574366c9671d63282caf63455730b90018357c71ca02a3073f56aa7979` |
| collection ×2 | 同 API | `sha256:b0f51841f84e4dd798286fd1c8629303fd0b619ca351af26b26db76896f00932` |
| AI | `7c71d1e95500aa20c3d82f57a7304578c8a794dd` | `sha256:e511347af54ea85d6b360f8b6cc89f02eb81f474977871739129a7cf702c2fa8` |
| Nginx / route | `nginx:1.27` | `sha256:6784fb0834aa7dbbe12e3d7471e69c290df3e6ba810dc38b34ae33d3c1c05f7d` |

- Redis 的实例、密码、DB 编号和业务语义不变，用户追加了新机出口白名单；API/collection 完成 AUTH/SELECT/PING。
- RDS 保持私网 endpoint。API/AI 的 MySQL 主机改为 `mysql-rds-proxy`，账户、数据库、密码和 URL 参数保持一致。
- RDS 代理先停旧 A 再启动 B，生产 alias 始终单主；临时候选代理已停止并保留。
- 应用先停旧再启新；collection 逐副本切换，没有创建第二套 AI 消费进程。
- 证书、mTLS、消息密钥和二维码通过 SSH 复制；不打印或提交生产凭据。
- 不删除旧主机、容器、卷、源证书和历史日志，不执行 prune。
- qs-server `PRODUCTION_DEPLOY_PAUSED=true`、qs-ai `AUTO_DEPLOY_ENABLED=false` 均保持原值。

## 测试、可观测性与指标判定

| 指标 | 判定与证据 |
| --- | --- |
| 入口与依赖方向 | 已核实各 vhost、上游和跨机依赖；阿里云依赖仍存在 |
| 运行规格保护 | 六个服务完成固定 image ID、环境、挂载、CPU/内存和安全选项比对；首次启动前执行隔离容器检查 |
| 依赖认证 | 新机 Redis 认证/PING、MySQL 认证/SELECT 1、IAM mTLS 与 NSQ/Mongo 连通检查通过 |
| 应用就绪 | API、collection 两副本、AI 就绪；D 三个 worker 就绪；AI 数据库 current/expected 均为 `0040_module_table_names` |
| 域名/TLS | 12 个 vhost 预期状态通过，证书验证为 0；11 条有效 A 记录已切换，apex CNAME 继续指向 www |
| 可观测性 | 7 个应用副本加 Prometheus/RocketMQ，共 9 个 scrape target 为 up；Grafana 容器 ID 与两个原数据卷未变 |
| 真实业务验收 | 用户确认登录、打开问卷和查看已有报告正常；新增答卷提交、新 AI 报告生成和支付未验证 |

导出工具六项测试覆盖 URL 凭据/参数保留、Compose 美元符号转义、固定镜像和只读 bind、
未审查服务/volume 拒绝、tmpfs 格式。CI 同时验证代理仅内网开放，且 A 默认不会启动代理。
外部 80/443 起初被腾讯云安全组阻挡，用户放行后，从 serverD 和 Mac mini 的实际 HTTPS 请求验证通过。

## 实施中的问题与修复

1. 新机云镜像已有 GID 冲突，deploy 使用 UID1002/GID2001，www 使用 UID/GID2000。
   ubuntu 的免密 sudo 保留，deploy 使用原受限 sudo。重复 sudoers include 已备份、修复并通过 visudo。
2. 初始化项目会调整目录权限；迁入的 API 配置曾因 owner 变化无法读取，已立即回退旧 API，
   恢复源文件权限，并以实际容器用户验证后重新切换。证书内容与权限单独核对恢复。
   `serverA-up` 现在仅检查初始化前置条件，不会每次启动都递归执行初始化。
   首次部署应先初始化空主机，再复制生产配置；不要在生产配置迁入后重复初始化。
3. Mac mini 来源 IP 曾被新机 Tailscale SNAT 改写为 Docker 网关地址，监控返回 403。
   新 A 不承担 subnet router/exit node，已持久设置 `tailscale set --snat-subnet-routes=false`；
   临时诊断规则已移除。Mac mini 私网采集返回 200，公网同路径仍返回 403，未放宽 Nginx allowlist。
   参见 [Tailscale SNAT 配置](https://tailscale.com/docs/reference/troubleshooting/network-configuration/disable-subnet-route-masquerading)。
4. 原证书定时脚本路径失效。新机使用固定版本 Certbot venv、deploy hook 和 systemd timer；
   两套域名的 `renew --dry-run` 均成功。hook 校验证书/私钥匹配，Nginx 校验失败时恢复旧文件。

## 项目初始化与运行管理

新 A `/opt/infra` 是真实 Git checkout，通过专用 GitHub **只读** deploy key 拉取；
排除大体积 `/static/` 二进制的 sparse checkout 不影响初始化组件。已实际运行 `make init-serverA ENV=prod`。
私有配置、证书和账号密钥均保留在 Git 以外。

| 服务 | 切换后的管理入口 |
| --- | --- |
| Nginx | `/opt/infra/deploy/serverA/docker-compose.yml`，project `servera`；后续可用 `make serverA-up ENV=prod` |
| MySQL 代理 | B 的 `/opt/infra/deploy/serverB/docker-compose.yml`，project `serverb` |
| collection ×2 | `/root/servera-migration-20261019/collection.native.json`，project `qs-collection`，service `server`，scale=2；保留原 CD 的项目与副本命名 |
| AI | `/opt/qs-ai/releases/<current>/compose.yaml` + `runtime.json` + `image.env`，project `qs-ai` |
| API | 私有快照 `compose.json` 的 `qs-apiserver` service，project `servera-migrated`；原 CD 会按固定容器名替换 |
| prometheus-route | `/opt/infra/deploy/serverA/monitoring-route.yml`，project `monitoring-route` |

`/root/servera-migration-20261019/compose.json` 是迁移快照，含凭据，不能整栈重新 up，
否则会与已恢复的原生 Compose 项目冲突；仅在明确的单服务恢复步骤使用。
迁移中替换的中间容器已停止并以 `*-migration-retained` 名称保留。

AI 的 current/previous 两套 release 均已复制，runtime 数据库路由同步改为 B 代理；
previous image `sha256:bf224ecc0cf5404900fa9e07de3bdd1f54543d976ec63c6669c402e585af450c` 已导入。
保留 `state.json` 的成功版本顺序，没有伪造新业务发布记录。

## DNS、CI 与运维闭环

- 两域名原 30 条 DNS 记录和 11 条变更计划保存在新机 root 私有目录；TTL=600。
  仅切换 Fangcunmount 的 qs/collect/iam/operating/www/grafana/nsqd/worker 和 Yangshujie 的 www/admin/api。
  sonar 和历史 Yangshujie QS 等记录未批量修改，退订旧机前须单独处理遗留记录。
- qs-server、qs-ai 使用仓库级 SVRA 公网/Tailscale 地址、deploy 用户、端口、主机公钥和指纹覆盖，
  仓库级 MYSQL_HOST 改为 `mysql-rds-proxy`，没有修改组织级数据库配置。
  MiniBlog 的可选 Nginx reload 目标改为新 A/deploy；没有触发发布。
- 从实际 Mac mini runner 使用已有 deploy key 登录新 A、校验 hostname 和免密 sudo 成功。
  仓库变量/secret 名称原始快照保存在本机 `/tmp/servera-cd-before-20261019/`，不含可读取的 secret 明文。
- mini 发现来源改为新 A，Prometheus extra_hosts 改用 `MONITORING_GATEWAY_IP`；
  两个既有 volume 不变，Grafana 没有重建，备份位于 mini 的 `~/infra-monitoring/servera-migration-20261019/`。
- D 的 RocketMQ 精确来源 allowlist 追加新 A Tailscale IP，保留旧 A 和其他规则；未切换消息 provider。
- 新 A 保留仅监听 `127.0.0.1:27017` 的 MongoDB 运维隧道，经过 MongoDB hello 验证。
  新建独立转发 key，仅允许新 A 来源和 C 的 `127.0.0.1:27017`，不复制旧 SSH 私钥。
- 本机 SSH 别名 `servera` 已指向新机 ubuntu，`servera-aliyun` 保留旧机 yangshujie；原 SSH 配置已备份。
- 旧机 mihomo/云代理等主机附属工具保留在旧机；本次没有复制个人代理配置或声称所有 OS 服务均已克隆。

## 回退与退役边界

旧 A 原应用/代理容器全部保留且停止，Nginx 继续运行；旧机没有退订。
回退应用时先停新机对应服务，再启动旧机对应容器，禁止同时恢复两套 AI 消费者。
如果回退 RDS 代理，先停 B 代理，再启动旧 A 的原代理，保持 alias 单主。
重载两台 Nginx 以刷新上游地址；DNS 按 root 私有快照中的 RecordId/原值恢复。

若需要整机回退，同时恢复 mini 监控来源/gateway、仓库目标和主机密钥覆盖，
并按节点 ID 调整管理角色，确保 manager 多数派；不要在旧 A 已降级后从旧 A 执行 manager 命令。
A 的 RDS Compose 仅作为显式 `aliyun-rds-proxy` profile 保留，默认启动不会意外恢复第二个代理。
旧机退订、历史 DNS 清理、旧监控 key 回收，以及未覆盖业务链路的验收须另行完成。
