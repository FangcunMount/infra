# 服务器升降配操作手册

## 目的

这份文档约定一个简单原则：

- 不做额外的“档位切换”脚本或 profile 注入。
- 资源配额、连接池、后台并发都直接维护在各仓库的配置文件里。
- 需要升配或降配时，直接改配置文件，然后按固定顺序发布。

这样可以避免“代码里改了配置，但运行时又被另一层覆盖”的问题。

## 配置来源

### 1. `infra`

用途：决定服务部署在哪台机器、监控栈在哪台机器、基础设施组件的资源限制。

重点文件：

- `deploy/serverA/docker-compose.yml`
- `deploy/serverB/docker-compose.yml`
- `components/prometheus/docker-compose.yml`
- `components/grafana/docker-compose.yml`
- `compose/env/prod/.env.example`
- `compose/env/prod/serverA.env`
- `compose/env/prod/serverB.env`

说明：

- `serverA.env` / `serverB.env` 是本地环境文件，不在 Git 管理中。
- 仓库里用 `.env.example` 保存默认口径，实际部署时要把变更同步到目标机器上的 `serverA.env` / `serverB.env`。

### 2. `qs-server`

用途：控制 `qs-apiserver`、`qs-collection-server`、`qs-worker` 的容器资源和应用内部并发。

重点文件：

- `build/docker/docker-compose.prod.yml`
- `configs/apiserver.prod.yaml`
- `configs/collection-server.prod.yaml`
- `configs/worker.prod.yaml`

说明：

- 容器 `cpu` / `memory` / `GOMEMLIMIT` 直接改 `build/docker/docker-compose.prod.yml`。
- 应用层连接池、任务并发、限流、定时任务频率直接改各自 `*.prod.yaml`。
- `qs-worker` 副本数不再硬编码在 workflow 里：
  - 长期默认值：GitHub Actions 仓库变量 `QS_WORKER_REPLICAS`
  - 临时发布覆盖：手动触发 `cicd.yml` 时填写 `worker_replicas`

### 3. `iam-contracts`

用途：控制 `iam-apiserver` 的容器资源和应用内部并发。

重点文件：

- `build/docker/docker-compose.prod.yml`
- `configs/apiserver.prod.yaml`

说明：

- 容器 `cpu` / `memory` / `GOMEMLIMIT` / `GOGC` 直接改 `build/docker/docker-compose.prod.yml`。
- MySQL / Redis 连接池、`suggest` 同步频率等直接改 `configs/apiserver.prod.yaml`。

## 什么时候改什么

### 只调容器资源

适用场景：

- ECS 升配或降配
- 业务逻辑不变，只想给服务更多或更少 CPU / 内存

需要改：

- `qs-server/build/docker/docker-compose.prod.yml`
- `iam-contracts/build/docker/docker-compose.prod.yml`
- 如监控栈也要收缩或放宽，再改 `infra/components/prometheus/docker-compose.yml`、`infra/components/grafana/docker-compose.yml`

### 容器资源下降，同时需要收紧应用内部负载

适用场景：

- ServerA 从 `4C8G` 降到 `2C4G`
- Worker 从多实例改为单实例
- 需要减少连接池、后台任务或队列并发

除了 compose 文件，还要改：

- `qs-server/configs/apiserver.prod.yaml`
- `qs-server/configs/collection-server.prod.yaml`
- `qs-server/configs/worker.prod.yaml`
- `iam-contracts/configs/apiserver.prod.yaml`
- GitHub 仓库变量 `QS_WORKER_REPLICAS`，或本次发布的 `worker_replicas`

### 调整服务落点

适用场景：

- 监控栈迁移到另一台机器
- 新增服务到 `serverB`
- 某个组件需要从 `serverA` 搬走

需要改：

- `infra/deploy/serverA/docker-compose.yml`
- `infra/deploy/serverB/docker-compose.yml`
- 组件自身 compose（例如 `components/prometheus/docker-compose.yml`）
- 对应机器的 `serverA.env` / `serverB.env`

## 推荐发布顺序

### A. 涉及基础设施落点变化

例如这次把 `Prometheus/Grafana` 从 `serverA` 移到 `serverB`。

顺序：

1. 先改并发布 `infra/serverB`
2. 确认新机器上的服务已起来
3. 再下线 `serverA` 上的旧实例
4. 最后再发布业务服务

### B. 只调整业务服务资源

顺序：

1. 发布 `iam-contracts`
2. 发布 `qs-server/apiserver`
3. 发布 `qs-server/collection`
4. 最后发布 `qs-server/worker`

原因：

- 先收紧 API 和 IAM，再收紧 worker，可以避免后台消费速度高于前台承载能力。

### C. 只调整 worker 副本数

顺序：

1. 修改 `QS_WORKER_REPLICAS`，或手动触发时填写 `worker_replicas`
2. 单独运行 `qs-server` 的 `worker` 部署
3. 验证副本数与消费情况

## 发布后检查

### ServerA

- `docker ps --format 'table {{.Names}}\t{{.Status}}'`
- `docker stats --no-stream`
- `free -h`
- `curl -sf http://127.0.0.1:8081/health`
- `curl -sf http://127.0.0.1:9080/healthz`（容器内或经 docker exec）

### ServerB

- `docker ps --format 'table {{.Names}}\t{{.Status}}'`
- `docker stats --no-stream`
- 检查 `prometheus` / `grafana` / `nsqd` 是否都在运行

### Worker

- `docker ps --filter 'label=com.docker.compose.project=qs-worker' --format 'table {{.Names}}\t{{.Status}}'`
- 检查实际运行副本数是否等于 `QS_WORKER_REPLICAS`
- 检查 worker 日志中是否能连通 `qs-apiserver:9090`
- 观察 NSQ backlog 是否持续增长

## 当前口径（2026-04）

- `serverA`：`2C4G`
- `serverB`：`2C2G`
- `Prometheus/Grafana`：部署在 `serverB`
- `qs-worker`：默认单实例，副本数由 `QS_WORKER_REPLICAS` 控制

## 变更原则

- 改资源配额时，优先提交 compose 变更。
- 改业务承载能力时，同时提交应用配置变更。
- 不再引入额外的运行时 profile 覆盖层。
- 所有“为什么这样调”的说明，写进 PR 或提交说明，避免只留下结果、不留下依据。
