# ServerB 部署 Prometheus + Grafana 指南（历史/可选）

> 注意：这份文档不属于当前目标拓扑的默认方案。当前目标架构中，`serverB` 承载的是 `qs-collection-server + IAM`，NSQ 已迁移到 `serverD`，不默认部署 `Prometheus` 与 `Grafana`。保留本文件仅作为历史参考或临时监控方案。

## 目的

这份指南只解决一件事：把 `Prometheus` 和 `Grafana` 部署到 `serverB`，并说明它们如何抓取业务容器指标。

当前约定：

- 监控栈运行在 `serverB`
- 监控栈与业务容器通过 `infra-network` 通信
- 默认不对宿主机直接暴露 `9090` / `3000`
- `serverB.env` 是实际生效配置，`.env.example` 只保存默认口径

## 相关文件

- 编排入口：`deploy/serverB/docker-compose.yml`
- Prometheus 组件：`components/prometheus/docker-compose.yml`
- Prometheus 抓取模板：`components/prometheus/prometheus.yml.tmpl`
- Grafana 组件：`components/grafana/docker-compose.yml`
- Grafana datasource provisioning：`components/grafana/provisioning/datasources/prometheus.yml`
- Grafana dashboard provisioning：`components/grafana/provisioning/dashboards/dashboards.yml`
- 生产环境模板：`compose/env/prod/.env.example`
- 生产环境实际文件：`compose/env/prod/serverB.env`

## 前置条件

部署前先确认：

1. `serverB` 已安装 Docker 和 Docker Compose
2. `infra-network` 已存在
3. `compose/env/prod/serverB.env` 已在目标机器准备好
4. `serverB` 上已有足够空间用于 `infra_prometheus_data` 和 `infra_grafana_data`

建议先执行：

```bash
docker network ls | grep infra-network
docker volume ls | grep 'infra_'
free -h
df -h
```

## 第一步：准备 `serverB.env`

`serverB.env` 不在 Git 管理中，通常从模板复制一份：

```bash
cp compose/env/prod/.env.example compose/env/prod/serverB.env
```

至少确认这些变量：

```env
INFRA_HOST_LABEL=serverB

PROMETHEUS_RETENTION_TIME=7d
PROMETHEUS_SCRAPE_INTERVAL=30s
PROMETHEUS_QS_APISERVER_TARGET=qs-apiserver:8080
PROMETHEUS_QS_COLLECTION_TARGET=qs-collection-server:8080
PROMETHEUS_QS_WORKER_TARGET=qs-worker:9092
PROMETHEUS_MEMORY_LIMIT=256M
PROMETHEUS_CPUS=0.10

GRAFANA_DOMAIN=grafana.example.com
GRAFANA_ROOT_URL=https://grafana.example.com
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=change_me_grafana_admin_password_here
GRAFANA_MEMORY_LIMIT=128M
GRAFANA_CPUS=0.05
```

说明：

- `INFRA_HOST_LABEL=serverB` 用于给容器打宿主机标签，后续排查更直观
- `PROMETHEUS_RETENTION_TIME` 决定历史指标保留时长
- `PROMETHEUS_SCRAPE_INTERVAL` 同时影响 `scrape_interval` 和 `evaluation_interval`
- `PROMETHEUS_QS_APISERVER_TARGET` / `PROMETHEUS_QS_COLLECTION_TARGET` / `PROMETHEUS_QS_WORKER_TARGET` 指向 `serverA` 上通过 overlay 网络可达的 QS metrics 地址
- `GRAFANA_ROOT_URL` 要和你最终访问 Grafana 的 URL 保持一致

## 第二步：确认编排文件

`deploy/serverB/docker-compose.yml` 已经把监控栈挂到 `serverB`：

- `prometheus`
- `grafana`

并复用了两个持久化卷：

- `infra_prometheus_data`
- `infra_grafana_data`

如果只是部署监控，不需要把整个 `serverB` 栈全部重启，可以只操作这两个服务。

## 第三步：部署

在 `infra` 仓库根目录执行：

```bash
docker compose -f deploy/serverB/docker-compose.yml pull prometheus grafana
docker compose -f deploy/serverB/docker-compose.yml up -d prometheus grafana
```

如果是首次部署，也可以顺手把 `nsq` 三件套一起拉起：

```bash
docker compose -f deploy/serverD/docker-compose.yml up -d nsqlookupd nsqd nsqadmin
```

## 第四步：验收

### 1. 看容器状态

```bash
docker ps --filter name=prometheus --filter name=grafana --format 'table {{.Names}}\t{{.Status}}'
```

### 2. 看健康检查

```bash
docker inspect --format '{{.Name}} {{.State.Health.Status}}' prometheus grafana
```

### 3. 看日志

```bash
docker logs --tail 100 prometheus

```

### 4. 容器内自检

```bash
docker exec prometheus wget -qO- http://127.0.0.1:9090/-/healthy
docker exec grafana wget -qO- http://127.0.0.1:3000/api/health
```

预期：

- Prometheus 返回包含 `Prometheus is Healthy`
- Grafana 返回 JSON，且 `database` 为 `ok`

## 第五步：确认 Grafana 已接上 Prometheus

本项目已通过 provisioning 预置 datasource：

- 名称：`Prometheus`
- URL：`http://prometheus:9090`

对应文件：

- `components/grafana/provisioning/datasources/prometheus.yml`

预置 dashboard 目录：

- `components/grafana/dashboards/`

如果 Grafana 已正常启动，首次登录后应该能直接看到已导入的 dashboard。

## Prometheus 会抓哪些目标

Prometheus 当前采用两类抓取方式：

1. 静态抓取 `serverA` 上的核心 QS 服务
2. 通过 Docker Service Discovery 自动发现 `serverB` 本机容器

### 1. 静态抓取的 QS 服务

默认固定抓：

- `qs-apiserver:8080/metrics`
- `qs-collection-server:8080/metrics`
- `qs-worker:9092/metrics`

这两个地址通过 `serverB` 上的 Prometheus 容器经 `infra-network` 访问 `serverA` 上的业务容器。

### 2. Docker 自动发现的本机容器

对本机自动发现，抓取条件有两个：

1. 容器要在 `infra-network`
2. 容器要带这些 label

最少需要：

```yaml
labels:
  - "prometheus.scrape=true"
  - "prometheus.metrics_port=8080"
```

建议补齐：

```yaml
labels:
  - "prometheus.scrape=true"
  - "prometheus.job=your-service"
  - "prometheus.component=your-service"
  - "prometheus.metrics_port=8080"
  - "prometheus.metrics_path=/metrics"
```

如果某个 `serverB` 本机业务服务“明明跑着，但 Prometheus 看不到”，通常就是：

- 没加 `prometheus.scrape=true`
- 没接入 `infra-network`
- `metrics_port` 写错
- 服务本身没有监听 `/metrics`

如果 `qs-apiserver` / `qs-collection-server` / `qs-worker` 看不到，优先检查：

- `infra-network` overlay 是否在当前 Swarm 节点间正常互通
- `serverB.env` 里的 `PROMETHEUS_QS_APISERVER_TARGET` / `PROMETHEUS_QS_COLLECTION_TARGET` / `PROMETHEUS_QS_WORKER_TARGET` 是否正确
- `serverA` 上的目标容器是否真的监听了 `/metrics`

## 访问方式

当前配置默认是“仅容器网络内可达”：

- `Prometheus` 没有对宿主机发布 `9090`
- `Grafana` 没有对宿主机发布 `3000`

这意味着部署完成后，监控栈已经可用，但浏览器不能直接通过 `serverB:3000` 访问。

推荐做法：

1. 通过 `serverA` 的 Nginx 做反向代理
2. 域名指向 `serverA`
3. Nginx 反代到 `infra-network` 里的 `grafana:3000`

如果只是临时排查，也可以直接用容器内自检命令，先确认服务本身健康。

## 常见问题

### 1. Prometheus 启动了，但没有业务 target

先检查：

```bash
docker inspect <container_name> --format '{{json .Config.Labels}}'
docker inspect <container_name> --format '{{json .NetworkSettings.Networks}}'
```

重点看：

- 是否有 `prometheus.scrape=true`
- 是否接入 `infra-network`

### 2. Grafana 启动失败

常见原因：

- `GRAFANA_ADMIN_PASSWORD` 为空
- `grafana_data` 目录已有旧状态，和当前 provisioning 冲突
- 宿主机磁盘不足

先看：

```bash
docker logs --tail 200 grafana
```

### 3. Prometheus 占用空间增长过快

优先调小：

- `PROMETHEUS_RETENTION_TIME`
- `PROMETHEUS_SCRAPE_INTERVAL`

如果只是 `2C2G` 的轻量节点，不建议把保留时间拉太长。

### 4. 改了 `.env.example` 但没生效

因为真正生效的是：

- `compose/env/prod/serverB.env`

`.env.example` 只是模板，不会自动覆盖目标机器上的实际配置。

## 变更后建议记录

每次改监控栈，建议在提交说明或发布记录里写清：

- 改了哪些变量
- 为什么要改 retention / scrape interval
- 是否同步修改了 `serverB.env`
- 是否已经验证 Prometheus targets 和 Grafana dashboard 正常
