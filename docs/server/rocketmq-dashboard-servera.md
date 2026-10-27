# RocketMQ Dashboard：serverA HTTPS 与 serverD 原生 RPC

**状态：已上线，执行与验收 6/6。** [完整发布证据](evidence/rocketmq-dashboard-servera-release-20261027.json)。

用户已选择并已完成：serverA 现有 Nginx 提供 `https://mq.fangcunmount.cn`；Dashboard 保留 serverD，管理 RPC 直达 serverD 原生私网端口；移除 serverD Nginx。

原私网方案已完成：源码 [infra #348](https://github.com/FangcunMount/infra/pull/348) 已合并；隔离 19/19、实际部署 15/15；原 Broker/NameServer 未重启，三个 worker 与四 owner 就绪、10 个监控目标 up。[原方案部署证据](evidence/rocketmq-dashboard-private-prototype-20261027.json) 不代表本次新拓扑已经完成。

| 完成 | 任务 | 验收标准及进度 |
|---|---|---|
| ✅ | S01 冻结实际运行基线 | Broker 原容器 `ce02d3e209b1…`，镜像 `638793767186…`；原 Compose `73384d115bc1…`，只叠加原生端口；serverA 现有通配符证书覆盖 mq |
| ✅ | S02 原生端口与入口实现 | 原镜像/命令/环境/资源/挂载/账号不变；Broker 直映射10911、Dashboard直映射18082；A HTTPS/Secure cookie生效，D Nginx已移除 |
| ✅ | S03 隔离重建与恢复验证 | 首批26/26；最终候选31/31、0失败0跳过：真实重建/恢复、账号与普通ACL、冷备、HTTPS/CSRF/错误CA、前端资源、503关闭恢复与跨bridge拒绝 |
| ✅ | S04 受控生产转换 | 生产后端13/13；持锁、1.79GB冷备fsync、首次启动标记；Broker停止至健康48.298秒。仅Broker/Dashboard重建，NameServer与worker不重启 |
| ✅ | S05 域名与真实验收 | 用户DNS已核对；实际HTTPS15/15、生产跨bridge拒绝2/2；浏览器登录页正常、JS MIME正确；原4个HTTPS站点200、3worker/4owner/10目标正常 |
| ✅ | S06 收尾 | 源码#350已合并；本收尾提交记录活动配置/恢复命令及证据；UI凭据以本机0600文件交付，不含Broker凭据 |

## 已核对的边界

- serverA：公网 `154.8.167.1`，Tailscale `100.74.123.45`，现有 Nginx 容器 `8d9f2f4d1a9c…`；镜像 `nginx@sha256:6784fb0834aa7dbbe12e3d7471e69c290df3e6ba810dc38b34ae33d3c1c05f7d`。只增加 mq vhost，其他配置原字节保留，不重启 Nginx 容器。
- serverD：Tailscale `100.118.164.39`；Broker 1280 MiB/1.5 CPU，三个 worker 各 768 MiB/1 CPU、原并发 48 保持。NameServer 容器 `fdfa8e5d6067…` 保持。
- Broker 原 Compose：`/opt/infra-rocketmq/releases/73384d115bc1734e6589fb18064777e0f3dfcf0c/components/rocketmq/docker-compose.yml`，SHA256 `d294f7310a2d499ca17d8a78e2ac42e5b291734b8f6792411863f8f8d871c4f8`；原环境文件 `/etc/infra/rocketmq/runtime.env`。不使用最新 main 的整份 Broker Compose 替换旧运行配置。
- 10911 仅在 D 的 Tailscale 地址映射，允许本机及 MQ bridge；18082 仅允许 serverA 的 Tailscale 来源及本机检查。INPUT 和 DOCKER-USER 两条路径都保护。
- 保持原 Broker 镜像、TLS/ACL、配置文件、store/auth 挂载、用户/Topic/Group、业务 DB 与协议 owner/epoch；不重放消息、不改消费位点、不重做模型。
- Dashboard 使用已验证的固定官方镜像 digest（标签 2.1.0，实际 JAR 2.1.1-SNAPSHOT）；JSON + CSRF 与独立账号保持。新 Broker 管理证书经 SSH 和容器身份核对后更新信任包。
- 用户已添加 mq A 记录；独立公共 DNS 查询确认其指向 `154.8.167.1`。本次不调用 DNS 写接口，不使用阿里云密钥。

## 执行与恢复顺序

先完成并合并隔离验证。持有原部署锁，记录旧 Broker/NameServer/应用身份、原 Compose/环境与挂载摘要；停止本项目旧 gateway，停 Broker 并制作完整冷备份，验证 tar 清单与摘要，fsync 后才发出原生 Broker 的启动命令。原环境及原 Compose 叠加仅含 hostname/10911 的 override，`--no-deps` 只重建 Broker。

确认原存储及账号加载、gRPC/指标和 worker/owner 重连后，使用新管理证书启动直接映射的 Dashboard；serverA 安装单独 vhost，`nginx -t` 后 reload；经实际 HTTPS 验证后配置 DNS。记录短暂 MQ 重连区间，不把未知结果认定为回滚，不补发消息。

首次新 Broker 启动标记之前可以使用经验证的冷备份；发出启动命令后，恢复必须继续使用**当前 store**与同一镜像，禁止旧冷备覆盖新消息。若 Broker 启动失败，按原 Compose、原环境、当前 store 恢复 gRPC 服务；若仅 Dashboard/域名失败，保留健康 Broker，前向修复管理入口，不回滚业务数据。备份及证据作为本次恢复资产保留。

## 隔离验证记录

首批候选 `5f87e319ffd90f3f22ba153f9f28bc3fb16b792d` 已通过 [26/0/0 原生验证](https://github.com/FangcunMount/infra/actions/runs/40453913111)，包含 Broker 真实重建、原映射恢复、当前存储复用、HTTPS/Secure cookie/CSRF、严格 TLS 和跨 bridge 拒绝。最终源码候选 `b49afa3cf1e6d309728b219320aee370446f3a2d` 已完成 [31/0/0 完整验证](https://github.com/FangcunMount/infra/actions/runs/40454910407)，并合并为 `df69d53b7b1cd480acf04c8969668e9b53678062`（[PR #350](https://github.com/FangcunMount/infra/pull/350)）。相关测试包括前端静态资源、正常账号ACL、503关闭与恢复；测试环境清理全部通过。

## 当前活动配置

| 对象 | 活动位置 / 身份 |
|---|---|
| 公开入口 | `https://mq.fangcunmount.cn` → serverA `154.8.167.1` |
| serverA vhost | `/data/apps/nginx-configs/mq.fangcunmount.cn.conf`；SHA256 `d513fd57c0e03f7a94199e4f691cd062dbc3ad8aa2c919596668962042a7477d` |
| serverA HTTPS 回执 | `/data/infra/rocketmq-dashboard/ingress/20261027T054003.json`；实际文件 SHA256 `da4a249cc19444e445bd0a38bd04c59d76b2b3c3fefea6baf51b1c73fb8ba86d` |
| 版本化源码（A、D） | `/data/infra/rocketmq-dashboard/source/df69d53b7b1cd480acf04c8969668e9b53678062` |
| serverD 活动索引 | `/data/infra/rocketmq-dashboard/active-native.json`，含组合命令、Dashboard 环境、公开入口和收尾回执 |
| serverD 操作目录 | `/data/infra/rocketmq-dashboard/native-transition/20261027T052951`；`state.json` 已 complete，`receipt.json` 保留后端阶段原始13项验证，`closure.json` 链接后续HTTPS验证 |
| Broker 新容器 | `9ed29110036730ee1a87033b8e184f85f128454f2f0a75893822ef3caf821fbb`；原镜像 `638793767186…`、1280 MiB / 1.5 CPU |
| Dashboard 新容器 | `01752a09dd57b855dcb0273d66367a58a39422f7464e9264e64ed8766ebd4855`；512 MiB / 0.5 CPU，UID10001、只读根目录 |
| Dashboard 私密配置 | 操作目录中的 `dashboard-private`，0700 / 文件0600，UID10001；HTTPS Secure cookie 与严格管理证书验证 |
| 独立账号 | UI 用户 `dashboard-admin`；serverD `/data/infra/rocketmq-dashboard/credentials.json` 仅root可读。交付只导出UI账号，不导出Broker管理凭据 |
| 防火墙 | `rocketmq-dashboard-firewall.service` 使用本次版本源码；D 18082仅A的 `100.74.123.45`，10911仅MQ bridge及本机；保留原8081/5557链 |
| 当前恢复资产 | 操作目录中的 `broker-before-native.tar`，1787688960字节、82文件；SHA256 `6c6bebd23b81a9d8cdbaf220a444e581ffe68bf3a13306dc9abc06449b7184ca`；未恢复过store |

末次回读：serverD 可用内存1129 MiB；Broker、NameServer、Dashboard及三个worker均无OOM/非预期重启。NameServer与worker身份保持；四owner准入开启、保护未触发，10个原监控目标均up。Broker重连期曾出现一次未就绪的监控读取，随后完整重读通过，失败材料保留。原四个HTTPS站点均200；serverA原vhost字节及Nginx容器身份保持。

## 日常维护与受限恢复

Broker 的活动定义是**原始Compose加本次override**。只运行原始Compose会移除10911映射；请使用活动索引中的组合命令。下述示例在serverD运行，需持原部署锁：

```sh
sudo docker compose \
  --env-file /etc/infra/rocketmq/runtime.env -p rocketmq \
  -f /opt/infra-rocketmq/releases/73384d115bc1734e6589fb18064777e0f3dfcf0c/components/rocketmq/docker-compose.yml \
  -f /data/infra/rocketmq-dashboard/native-transition/20261027T052951/native-rpc.override.json \
  up -d --no-deps --pull never broker
```

受限恢复组合保存在操作目录的 `commands.private.json`：原Compose加 `recovery.override.json`，继续使用**当前store**恢复原端口和gRPC服务。当前冷备不用于日常回退覆盖，不删除事务证据，不重发历史业务，不修改业务数据库或消费位点。仅管理入口失败时关闭mq vhost为503并前向修复，不重启健康Broker。

本次沿用原进程的remoting TLS配置，其管理证书由进程生成；**以后重启或重建Broker/NameServer，需要重新核对管理证书并更新Dashboard信任包**。业务gRPC的固定证书不因此更换。以serverD的可信Docker控制面为准，核对原项目、镜像和容器身份；通过版本化源码中的 `native_transition.trust_bundle` 取得新证书，原子更新活动配置的 `ca.crt`（UID10001、0600），再只重启Dashboard。不得打开TLS测试信任或关闭证书校验来恢复界面。更新后的信任指纹另写维护回执，保留本次原始证据。

所有Topic、Group、ACL及位点变更继续纳入infra管理并核对消息类型/owner；本次实际验收只查询管理信息，没有发布业务消息、重放、重置位点或调用模型。Prometheus/Grafana继续位于Mac mini，serverD未新增采集代理。
