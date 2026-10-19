# MySQL RDS 私网代理

目标架构中 `serverA/serverD` 位于腾讯云，无法直接路由到阿里云 RDS 的私网地址。
serverA 迁入腾讯云后，该组件在与 RDS 同网的 `serverB` 上运行独立 Nginx Stream 代理，并仅通过
`infra-network` 提供 `mysql-rds-proxy:3306`。

链路如下：

```text
qs-worker(serverD) / qs-apiserver(serverA) / qs-ai(serverA)
  -> infra-network / Tailscale underlay
  -> mysql-rds-proxy(serverB)
  -> RDS private endpoint:3306
```

约束：

- 不发布任何宿主机端口。
- 使用 `nginx:1.27` 镜像，不修改公网 Nginx 容器。
- 后端地址由 `serverB.env` 的 `MYSQL_HOST`、`MYSQL_PORT` 注入；代理不需要数据库密码。
- worker 保持 `mysql-rds-proxy:3306`；新 serverA 上 API/AI 也使用该地址。
- 发布 worker 前必须读取 MySQL greeting，不能只检查代理监听端口。

此文件描述迁移目标，实际执行状态见 [serverA 腾讯云迁移记录](../../docs/server/serverA-tencent-migration.md)。
旧 serverA 的定义保留在 `aliyun-rds-proxy` profile 中，仅供回退。
不能同时启动两台机器的生产 `mysql-rds-proxy` alias。

```bash
# 在 serverB 执行；只操作 RDS 代理，不重启 IAM 或其他业务容器。
make mysql-rds-proxy-verify
make mysql-rds-proxy-recreate

# 回退到旧阿里云 serverA 时，先停止 B 上的代理，再在旧 A 执行：
make mysql-rds-proxy-recreate MYSQL_RDS_PROXY_NODE=serverA
```
