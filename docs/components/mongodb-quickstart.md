# MongoDB 快速入门

> 当前生产目标：`serverC (4C4G)` 单独承载 MongoDB，宿主机仅本地暴露 `127.0.0.1:27017`，跨机器容器通过 overlay 网络访问 `mongo:27017`。

## 快速开始

```bash
# 1. 在 serverC 初始化本地卷
make init-serverC

# 2. 启动 MongoDB
make serverC-up

# 3. 检查状态
make serverC-status
make mongo-rs-status

# 4. 测试连接
make test-mongo
```

## 关键文件

| 文件 | 作用 |
|------|------|
| `deploy/serverC/docker-compose.yml` | serverC Mongo stack |
| `compose/env/prod/serverC.env` | MongoDB 环境变量 |
| `components/mongo/mongod.conf` | MongoDB 主配置 |
| `components/mongo/init-mongo.js` | 初始化用户脚本 |

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
```

## 连接方式

### 1. 同机管理

```bash
mongosh "mongodb://root:密码已URL编码@127.0.0.1:27017/admin?authSource=admin&replicaSet=rs0&directConnection=true"
```

### 2. 远程运维（SSH 隧道）

```bash
ssh -L 27017:127.0.0.1:27017 user@serverC
mongosh "mongodb://root:密码已URL编码@127.0.0.1:27017/admin?authSource=admin&replicaSet=rs0&directConnection=true"
```

### 3. 业务容器访问

```text
mongodb://用户名:密码@mongo:27017/数据库名?authSource=数据库名&replicaSet=rs0&directConnection=true
```

说明：

- `mongo` 是 `infra-network` 里的容器名。
- `serverD` 上的 `qs-worker` 等业务容器应优先使用这个地址。

## 环境变量

`compose/env/prod/serverC.env` 至少需要填写：

```bash
INFRA_HOST_LABEL=serverC
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

## 当前资源口径

| 项目 | 值 |
|------|----|
| 宿主机 | `serverC 4C4G` |
| 容器内存上限 | `3072M` |
| CPU 上限 | `3.00` |
| 对宿主机暴露 | `127.0.0.1:27017` |
| overlay 访问 | `mongo:27017` |

## 运维建议

- 不要把 MongoDB 公网暴露到 `0.0.0.0:27017`
- 修改密码后同步更新业务仓库里的 Mongo 连接串
- 定期执行 `make mongo-backup`
- 业务容器跨机访问优先用 overlay 容器名，不要写死 IP

## 相关文档

- [组件总览](./README.md)
- [Mongo 迁移到 serverC 指导手册](../server/mongo-migration-to-serverC.md)
- [网络架构](../network/architecture.md)
- [服务器架构设计](../server/architecture.md)
