# serverD 说明

`serverD` 承载：

- `qs-worker`
- `operating` 后台
- `miniblog`
- `qlume`
- `nsqlookupd`
- `nsqd`
- `nsqadmin`
- `prometheus`
- `grafana`

其中 `qs-worker`、`operating`、`miniblog`、`qlume` 由各自业务仓库部署，`NSQ` 与 `Prometheus/Grafana` 由 `infra` 仓库维护。

当前 `infra` 仓库为 `serverD` 提供：

- `infra-network` 跨云 overlay 网络
- [docker-compose.yml](./docker-compose.yml) NSQ + Prometheus + Grafana 基础设施栈
- [compose/env/prod/serverD.env](../../compose/env/prod/serverD.env) 参考环境变量
- 与 `mongo`、`nsqlookupd`、`nsqd` 的服务发现约定
- Prometheus 规则与 Grafana provisioning / dashboards 初始化同步

推荐约定：

- MongoDB 主机名：`mongo`
- NSQ Lookupd 主机名：`nsqlookupd`
- NSQD 主机名：`nsqd`
- Prometheus 主机名：`prometheus`
- Grafana 主机名：`grafana`
- MySQL / Redis：继续使用云托管地址

常用命令：

```bash
make serverD-monitoring-up
make serverD-monitoring-status
make serverD-monitoring-logs
```
