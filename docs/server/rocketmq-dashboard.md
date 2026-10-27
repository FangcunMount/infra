# serverD RocketMQ Dashboard（私网原型记录）

> 原方案已完成隔离 19/19、生产 15/15；用户随后选择移除 serverD Nginx。当前实施与验收以 [serverA HTTPS / serverD 原生 RPC 执行表](rocketmq-dashboard-servera.md) 为准。下面保留原方案的已验证事实，不作为新拓扑部署命令。

目标：在 serverD 增加 Tailscale 私网管理界面，由 infra 管理，不重建或重启现有 Broker、NameServer 和 worker。

| 状态 | 任务 | 验收 |
|---|---|---|
| ✅ | 生产只读基线与版本核对 | 固定官方镜像及实际 JAR；原检查时 18082/10911 空闲 |
| ✅ | 隔离原生验证 | Broker 5.5.1、TLS enforcing、ACL2；默认/错误/匿名登录拒绝，独立登录后管理查询成功 |
| ✅ | 部署与权限 | 独立 Compose、独立 UI/Broker 身份、私网入口、RPC 仅 Broker bridge；原容器不重启 |
| ✅ | 运行验收及记录 | Topic/消费组/集群只读查询、退出会话失效、余量至少 512 MiB、原业务监控正常 |

## 固定构成与入口

- 官方 Dashboard 镜像标签 2.1.0：`apacherocketmq/rocketmq-dashboard:2.1.0@sha256:81fbd0f5d82c79a50899b48bf18449ee1c52e1deb0246999a90291c786fbeabb`；JRE 17。**实际内置 Maven 版本为 2.1.1-SNAPSHOT**，不能将标签源码等同于镜像内容。已直接核对固定镜像 JAR SHA256 `98125ee1496edbab776e1374f3566f81a2dfb5e0fba0a12c468acbc21b468a73` 及实际 SecurityConfig/登录接口；验收绑定实际镜像与 JAR。
- NGINX 1.30.6-alpine：`sha256:84ed8c0dd296c188bfc24ed506f46589e9285fb0b11cf3a04d91d524d3067e11`。
- 入口 `http://100.118.164.39:18082`，仅 Tailscale；不新增公网入口或 DNS。
- 独立项目 `rocketmq-dashboard`，复用外部 `rocketmq_rocketmq` 网络，512 MiB/0.5 CPU + 48 MiB/0.1 CPU，非 root、只读根目录、日志轮转。
- Broker 对外仍宣告 `100.118.164.39:10911`。网关透明转发原 TLS 到 `broker:10911`；DOCKER-USER 与 INPUT 新增两个端口的独立目标规则，覆盖 DNAT 和 Docker userland proxy 路径。管理 RPC 只允许 Broker bridge，网页只允许 Tailscale；同时允许宿主经自身 Tailscale 地址做本机检查。原 8081/5557 防火墙链保持。
- UI 使用上游 file 登录模式，独立用户名/随机密码；Broker 连接使用另一个专用 Super 身份，因界面承担 MQ 管理职责。原 infra 管理员与应用账号不复用、不轮换。UI 登录身份与 Broker 身份分离；所有管理动作具备该专用 Broker 身份的权限。
- 保留镜像实际包含的 Spring Security CSRF：经 `/rocketmq-dashboard/csrf-token` 取得 token/cookie，再提交 **JSON** 及 X-XSRF-TOKEN；实际 LoginController 参数带有 `@RequestBody`，不同于标签源码中的表单接口。缺 token 的写请求必须 403。Spring Security 的组件内部身份使用同一 UI 账号，避免生成临时密码进入日志。验收请求携带真实入口 Origin，不关闭 CORS/CSRF。
- 不采用上游 ACL 登录模式：2.1.0 的按用户池没有完整沿用 TLS 配置；采用全局 TLS 管理池及独立 UI 认证，并通过实际 Broker 验证。
- Dashboard 管理客户端强制 TLS，保持原 ACL2 与业务 gRPC TLS 配置。只读核验发现现网 remoting 与业务 gRPC 使用不同证书；管理信任包固定 SSH 核对后的 NameServer/Broker 实际公开证书指纹，变化即拒绝安装。不把服务器私钥交给 Dashboard，不关闭证书验证，也不为本次安装修改原进程的 TLS 配置。
- 关闭 Dashboard 定期统计采集，保留 Prometheus/Grafana 在 Mac mini。验收不发送消息、重放、重置位点、删除 Topic 或触发模型。

## 运维及恢复

私密配置位于 `/data/infra/rocketmq-dashboard/private`，目录 0700/文件 0600，属容器 UID 10001；凭据交付文件由 root 0600 保存，禁止进入 Git、日志或会话正文。渲染/启动不执行数据库 DDL。

先安装 `scripts/dashboard/firewall.py` 的两个目标规则，再启动独立项目；使用原部署锁 `/var/lib/fangcun-image-retention/deploy.lock`，不改锁 inode 或权限。启动后用 `scripts/dashboard/acceptance.py` 验证登录、集群、Topic、消费组及登出。

停止/回退仅执行该项目 `docker compose down`（不带 `-v`），保留私密配置及专用身份供诊断。不得执行原 RocketMQ 项目的 down/up、删除原网络/存储、变更业务 owner 或 worker 资源。独立 `rocketmq-dashboard-firewall.service` 随 Docker 重启重新安装本项目规则；Compose 始终保持私网地址绑定。原安装源码保留于 #348；当前使用 `scripts/dashboard/native_transition.py` 与 `scripts/dashboard/ingress.py`，版本化源码安装在本项目目录中，不覆盖原 Broker 源码或配置。

源码与版本依据：[Dashboard 2.1.0](https://github.com/apache/rocketmq-dashboard/releases/tag/rocketmq-dashboard-2.1.0)、[固定源码](https://github.com/apache/rocketmq-dashboard/tree/a013c8fad163122713b0bd2db3d73b3bf0db373e)、[NGINX](https://nginx.org/)。部署与 CI 证据将在验收后附加。
