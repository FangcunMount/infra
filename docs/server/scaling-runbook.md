# 服务器升降配操作手册

## 目的

这份文档只回答三件事：

1. 当前四机拓扑里，哪些文件决定服务落点。
2. 调整机器规格或迁移服务时，需要改哪些仓库。
3. 发布顺序怎么排，才能避免基础设施与业务配置脱节。

## 当前拓扑

- `serverA 2C2G`：`nginx + qs-apiserver`
- `serverB 2C2G`：`qs-collection-server + IAM`
- `serverC 4C4G`：`mongodb`
- `serverD 2C4G`：`qs-worker + operating + nsq`
- 云托管：`MySQL`、`Redis`

## 配置来源

### infra

用途：

- 维护 `serverA/serverC/serverD` 的基础设施 compose
- 维护四台机器的环境变量基线
- 维护 Swarm / overlay 网络

重点文件：

- `deploy/serverA/docker-compose.yml`
- `deploy/serverB/docker-compose.yml`
- `deploy/serverC/docker-compose.yml`
- `deploy/serverD/docker-compose.yml`
- `compose/env/prod/serverA.env`
- `compose/env/prod/serverB.env`
- `compose/env/prod/serverC.env`
- `compose/env/prod/serverD.env`

### qs-server

用途：

- 维护 `qs-apiserver`
- 维护 `qs-collection-server`
- 维护 `qs-worker`

说明：

- `serverA` 的 `qs-apiserver` 资源和应用并发在 `qs-server` 仓库调整。
- `serverB` 的 `qs-collection-server` 在 `qs-server` 仓库调整。
- `serverD` 的 `qs-worker` 在 `qs-server` 仓库调整。

### IAM / operating 仓库

用途：

- 分别维护 `IAM`、`operating` 的容器和应用配置。

说明：

- `serverB` 上的 `IAM`
- `serverD` 上的 `operating`

都不在 `infra` 仓库里直接改 compose。

## 什么时候改什么

### 只改基础设施服务落点

例如：

- `MongoDB` 从一台机器迁到另一台机器
- `NSQ` 从 `serverD` 迁出

需要改：

- `infra/deploy/server*.yml`
- `infra/compose/env/prod/server*.env`
- `infra/docs/server/architecture.md`

### 只改业务服务资源

例如：

- `qs-worker` 需要更多内存
- `IAM` 连接池需要缩减

需要改：

- 对应业务仓库的 compose 与应用配置
- 如果依赖地址变化，再同步修改 `infra/compose/env/prod/server*.env`

### 调整整机规格

例如：

- `serverA 2C2G -> 4C4G`
- `serverC 4C4G -> 4C8G`

先改：

- 本仓库文档和环境变量中的目标规格说明

再改：

- 对应业务仓库的容器资源限制
- 如果基础组件也需要放宽，改 `components/nginx/docker-compose.yml`、`components/nsq/docker-compose.yml`、`components/mongo/docker-compose.yml`

## 推荐发布顺序

### A. 涉及基础设施迁移

例如：

- Mongo 落点变化
- NSQ 配置变化
- 四节点网络变化

顺序：

1. 先改并发布 `infra`
2. 验证 `serverA/serverB/serverC` 基础组件已正常运行
3. 再发布依赖这些组件的业务仓库

### B. 只调整业务服务资源

顺序建议：

1. `IAM`
2. `qs-apiserver`
3. `qs-collection-server`
4. `qs-worker`
5. `operating`

### C. Mongo 相关配置变更

顺序：

1. 更新 `infra/compose/env/prod/serverC.env`
2. 重启 `serverC` Mongo stack
3. 验证 `mongo-rs-status`
4. 再发布依赖 Mongo 的业务服务

## 发布后检查

### serverA

- `make serverA-status`
- `curl -sf http://127.0.0.1/healthz`
- 检查 `qs-apiserver` 是否能访问云 MySQL / Redis

### serverB

- `make serverB-status`
- `make nsq-stats`
- 检查 `qs-collection-server` 与 `IAM` 是否能解析 `nsqlookupd` / `nsqd`

### serverC

- `make serverC-status`
- `make mongo-rs-status`
- `make test-mongo`

### serverD

- 检查 `qs-worker` 是否能访问 `mongo:27017`
- 检查 `operating` 是否仍能访问云 MySQL / Redis

## 当前口径（2026-04）

- `serverA`：`2C2G`
- `serverB`：`2C2G`
- `serverC`：`4C4G`
- `serverD`：`2C4G`
- `infra` 仓库直接管理：`nginx`、`NSQ`、`MongoDB`

## 变更原则

- 服务落点变化，先改 `infra`
- 容器资源变化，优先改对应业务仓库
- 依赖地址变化，要同步更新 `compose/env/prod/server*.env`
- 文档口径必须和部署清单同步提交
