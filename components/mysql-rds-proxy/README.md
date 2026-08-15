# Worker MySQL RDS 私网代理

`serverD` 位于云服务商 B，无法直接路由到云服务商 A RDS 的私网地址。
该组件在与 RDS 同网的 `serverA` 上运行独立 Nginx Stream 代理，并仅通过
`infra-network` 提供 `mysql-rds-proxy:3306`。

链路如下：

```text
qs-worker(serverD)
  -> infra-network / Tailscale underlay
  -> mysql-rds-proxy(serverA)
  -> RDS private endpoint:3306
```

约束：

- 不发布任何宿主机端口。
- 使用 serverA 已部署的 `nginx:1.27` 镜像，不修改公网 Nginx 容器。
- 后端地址由 `serverA.env` 的 `MYSQL_HOST`、`MYSQL_PORT` 注入。
- worker 使用 `mysql-rds-proxy:3306`；serverA 上的 apiserver 继续直连 RDS。
- 发布 worker 前必须读取 MySQL greeting，不能只检查代理监听端口。
