# MongoDB 组件说明

> 当前生产目标：`MongoDB` 独占部署在 `serverC (4C4G)`，对宿主机只本地暴露 `127.0.0.1:27017`，跨机器业务容器统一通过 `infra-network` 访问 `mongo:27017`。

## 当前部署定位

| 项目 | 说明 |
|------|------|
| 部署节点 | `serverC (4C4G)` |
| 组件定义 | `components/mongo/docker-compose.yml` |
| 部署清单 | `deploy/serverC/docker-compose.yml` |
| 生产环境变量 | `compose/env/prod/serverC.env` |
| 对宿主机暴露 | `127.0.0.1:27017` |
| 跨机器容器访问 | `mongo:27017` |
| 运行模式 | 单节点副本集 `rs0` |

这套设计解决两件事：

- 让 `serverA/serverB/serverD` 上的业务容器继续用统一的 overlay 服务发现访问 Mongo。
- 把 Mongo 从旧的混部节点中剥离出来，单独享用 `serverC` 的 CPU、内存和磁盘。

## 当前资源口径

### 宿主机

- `serverC`: `4C4G`
- 仅承载 `MongoDB`

### 容器

| 资源 | 当前值 | 说明 |
|------|--------|------|
| `mem_limit` | `3072M` | 约占宿主机 4G 的 75%，已经把大部分内存给 Mongo |
| `cpus` | `3.00` | 给 Mongo 预留 3 个核心，宿主机仍保留 1 核余量 |
| `WiredTiger cache` | `2.0GB` | 对齐 3GB 容器内存，兼顾缓存能力和连接/journal 空间 |
| `maxIncomingConnections` | `300` | 比旧 `serverA` 的 100 连接明显更宽松 |
| `oplogSizeMB` | `1536` | 单节点副本集下更从容的事务 / 回滚窗口 |

说明：

- 这版已经把 `serverC` 的大部分资源给了 Mongo，但没有直接给满 4G/4C。
- 预留的 1G 内存和 1 个核心，用来承接宿主机、Docker、日志与突发抖动，避免把节点压到没有缓冲。
- 如果后续业务峰值继续上升，再基于监控决定是否进一步上提，而不是一开始就把机器跑满。

## 网络与访问约定

### 1. 同机运维

```bash
mongosh "mongodb://root:密码已URL编码@127.0.0.1:27017/admin?authSource=admin&replicaSet=rs0&directConnection=true"
```

### 2. 远程运维

```bash
ssh -L 27017:127.0.0.1:27017 user@serverC
mongosh "mongodb://root:密码已URL编码@127.0.0.1:27017/admin?authSource=admin&replicaSet=rs0&directConnection=true"
```

### 3. 业务容器访问

```text
mongodb://用户名:密码@mongo:27017/数据库名?authSource=数据库名&replicaSet=rs0&directConnection=true
```

约定：

- `mongo` 是 `infra-network` 内的容器名。
- `serverA/serverB/serverD` 上的业务容器不要写死 `serverC` IP。
- 不要把 Mongo 改成公网监听 `0.0.0.0:27017`。

## 启动顺序

```bash
# 1. 初始化 serverC 本地卷
make init-serverC

# 2. 准备单节点副本集 keyFile
make mongo-keyfile

# 3. 启动 MongoDB
make serverC-up

# 4. 初始化/修复 rs0
make mongo-rs-init

# 5. 检查状态
make serverC-status
make mongo-rs-status
```

## 常用命令

```bash
make serverC-up
make serverC-down
make serverC-logs
make serverC-status

make mongo-shell
make mongo-rs-status
make mongo-backup
make mongo-monitor
make mongo-stats
make mongo-init-users
```

## 环境变量

生产环境至少要填写 [serverC.env](../../compose/env/prod/serverC.env) 里的这些项：

```bash
INFRA_HOST_LABEL=serverC
INFRA_DATA_ROOT=/data/infra

MONGO_PORT=27017
MONGO_INITDB_ROOT_USERNAME=root
MONGO_INITDB_ROOT_PASSWORD=change_me_mongo_root_password
MONGO_DATABASE=infrastructure_prod
MONGO_APP_USER=infra_app
MONGO_APP_PASSWORD=change_me_mongo_app_password
MONGO_READONLY_USER=infra_readonly
MONGO_READONLY_PASSWORD=change_me_mongo_readonly_password
MONGO_MEMORY_LIMIT=3072M
MONGO_CPUS=3.00
```

## 运维建议

- 先执行一次完整备份，再做迁移或重大调参。
- 单节点副本集的目的主要是启用事务能力，不要把它误解成高可用。
- 如果后续要上多节点副本集，先解决跨云延迟和选主问题，再谈扩容。
- 修改 Mongo 用户密码后，要同步更新所有业务仓库里的连接串。

## 相关文档

- [MongoDB 快速入门](../../docs/components/mongodb-quickstart.md)
- [Mongo 迁移到 serverC 指导手册](../../docs/server/mongo-migration-to-serverC.md)
- [服务器架构设计](../../docs/server/architecture.md)
