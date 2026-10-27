# RocketMQ Dashboard：serverA HTTPS 与 serverD 原生 RPC

用户已选择：serverA 现有 Nginx 提供 `https://mq.fangcunmount.cn`；Dashboard 保留 serverD，管理 RPC 直达 serverD 原生私网端口；移除 serverD Nginx。

原私网方案已完成：源码 [infra #348](https://github.com/FangcunMount/infra/pull/348) 已合并；隔离 19/19、实际部署 15/15；原 Broker/NameServer 未重启，三个 worker 与四 owner 就绪、10 个监控目标 up。[原方案部署证据](evidence/rocketmq-dashboard-private-prototype-20261027.json) 不代表本次新拓扑已经完成。

| 完成 | 任务 | 验收标准及进度 |
|---|---|---|
| ✅ | S01 冻结实际运行基线 | Broker 原容器 `ce02d3e209b1…`，镜像 `638793767186…`；原 Compose `73384d115bc1…`，只叠加原生端口；serverA 现有通配符证书覆盖 mq |
| ☐ | S02 原生端口与入口实现 | 原镜像/命令/环境/资源/挂载/账号不变；仅 Broker 新增 Tailscale 10911，Dashboard 直映射 18082；A 代理 HTTPS，正确转发 Origin/协议及 Secure cookie；D 无 Nginx |
| ☐ | S03 隔离重建与恢复验证 | 真实 Broker 重建、存储与账号保留、冷备份校验、原配置恢复路径；HTTPS 登录/CSRF/TLS/错误 CA、其他 Docker 网络拒绝；非空、零跳过 |
| ☐ | S04 受控生产转换 | 具名原容器/源码摘要检查、原部署锁、冷备份 fsync、首次启动标记；仅重建 Broker 与 Dashboard；A Nginx 语法验证后 reload，原业务容器不重启 |
| ☐ | S05 域名与真实验收 | mq A 记录指向 serverA；实际证书/跳转/前端资源/登录/管理查询通过；原站点、worker、owner、监控恢复正常；D Nginx 容器退出 |
| ☐ | S06 收尾 | 源码/证据合并、活动配置与恢复命令索引、私密 UI 凭据文件交付；逐项打勾 |

## 已核对的边界

- serverA：公网 `154.8.167.1`，Tailscale `100.74.123.45`，现有 Nginx 容器 `8d9f2f4d1a9c…`；镜像 `nginx@sha256:6784fb0834aa7dbbe12e3d7471e69c290df3e6ba810dc38b34ae33d3c1c05f7d`。只增加 mq vhost，其他配置原字节保留，不重启 Nginx 容器。
- serverD：Tailscale `100.118.164.39`；Broker 1280 MiB/1.5 CPU，三个 worker 各 768 MiB/1 CPU、原并发 48 保持。NameServer 容器 `fdfa8e5d6067…` 保持。
- Broker 原 Compose：`/opt/infra-rocketmq/releases/73384d115bc1734e6589fb18064777e0f3dfcf0c/components/rocketmq/docker-compose.yml`，SHA256 `d294f7310a2d499ca17d8a78e2ac42e5b291734b8f6792411863f8f8d871c4f8`；原环境文件 `/etc/infra/rocketmq/runtime.env`。不使用最新 main 的整份 Broker Compose 替换旧运行配置。
- 10911 仅在 D 的 Tailscale 地址映射，允许本机及 MQ bridge；18082 仅允许 serverA 的 Tailscale 来源及本机检查。INPUT 和 DOCKER-USER 两条路径都保护。
- 保持原 Broker 镜像、TLS/ACL、配置文件、store/auth 挂载、用户/Topic/Group、业务 DB 与协议 owner/epoch；不重放消息、不改消费位点、不重做模型。
- Dashboard 使用已验证的固定官方镜像 digest（标签 2.1.0，实际 JAR 2.1.1-SNAPSHOT）；JSON + CSRF 与独立账号保持。新 Broker 管理证书经 SSH 和容器身份核对后更新信任包。
- mq 当前 DNS 为 NXDOMAIN；serverA 已有可用阿里云 DNS 凭据入口，凭据不进入 Git 或日志。DNS 写入前再次预查同名记录，冲突拒绝覆盖。

## 执行与恢复顺序

先完成并合并隔离验证。持有原部署锁，记录旧 Broker/NameServer/应用身份、原 Compose/环境与挂载摘要；停止本项目旧 gateway，停 Broker 并制作完整冷备份，验证 tar 清单与摘要，fsync 后才发出原生 Broker 的启动命令。原环境及原 Compose 叠加仅含 hostname/10911 的 override，`--no-deps` 只重建 Broker。

确认原存储及账号加载、gRPC/指标和 worker/owner 重连后，使用新管理证书启动直接映射的 Dashboard；serverA 安装单独 vhost，`nginx -t` 后 reload；经实际 HTTPS 验证后配置 DNS。记录短暂 MQ 重连区间，不把未知结果认定为回滚，不补发消息。

首次新 Broker 启动标记之前可以使用经验证的冷备份；发出启动命令后，恢复必须继续使用**当前 store**与同一镜像，禁止旧冷备覆盖新消息。若 Broker 启动失败，按原 Compose、原环境、当前 store 恢复 gRPC 服务；若仅 Dashboard/域名失败，保留健康 Broker，前向修复管理入口，不回滚业务数据。备份及证据作为本次恢复资产保留。
