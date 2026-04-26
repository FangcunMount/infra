# Mongo 迁移到 serverC 指导手册

## 目的

这份手册解决一件事：

把 `MongoDB` 从旧的混部节点迁移到 `serverC (4C4G)`，同时保持：

- `serverA` 只保留 `nginx + qs-apiserver`
- `serverB` 只保留 `qs-collection-server + IAM`
- `serverD` 上的 `qs-worker + operating + nsq` 继续通过 overlay 网络访问 Mongo
- 业务仓库统一改用 `mongo:27017`

## 当前目标拓扑

- `serverA 2C2G`：`nginx + qs-apiserver`
- `serverB 2C2G`：`qs-collection-server + IAM`
- `serverC 4C4G`：`mongodb`
- `serverD 2C4G`：`qs-worker + operating + nsq`
- 云托管：`MySQL`、`Redis`

四台机器共同加入 `infra-network`，Mongo 的目标落点只有 `serverC`。

## 核心结论

### 1. Mongo 迁移后，对宿主机仍只本地暴露 `127.0.0.1:27017`

原因：

- 业务容器统一通过 overlay 容器名访问 `mongo:27017`
- 宿主机端口只保留给本机运维和 SSH 隧道
- 不需要把 `27017` 直接暴露到公网

### 2. 业务连接口径要统一成 `mongo:27017`

迁移完成后，业务仓库里不要继续写：

- `localhost`
- `127.0.0.1`
- `serverA`
- `serverC` 的固定 IP

应该统一改成：

```text
mongodb://用户名:密码@mongo:27017/数据库名?authSource=数据库名&replicaSet=rs0&directConnection=true
```

### 3. 这次迁移和公网 HTTPS 证书无关

Mongo 迁移不会动 `serverA:/data/ssl`，也不会影响 `nginx` 的公网证书。

## 迁移边界

### infra 仓库负责

- `serverC` 上 Mongo 组件的 compose、配置、脚本
- `infra-network` 跨机器网络约定
- `serverC.env` 的 Mongo 变量基线
- Mongo 备份、单节点副本集、初始化用户脚本

### 业务仓库负责

- `qs-apiserver`
- `qs-collection-server`
- `IAM`
- `qs-worker`
- `operating`

这些业务仓库需要把 Mongo 依赖地址切到 `mongo:27017`。

## 迁移前检查

### A. 四节点 Swarm / overlay 网络

确认：

- `serverA/serverB/serverC/serverD` 都已加入 Swarm
- `infra-network` 已存在
- `serverC` 上的 Mongo 容器可以加入 `infra-network`

建议检查：

```bash
docker node ls
docker network inspect infra-network
```

### B. serverC 基础准备

确认：

- `serverC` 系统初始化已完成
- `compose/env/prod/serverC.env` 已填写真实密码
- `serverC` 的数据目录可写

建议检查：

```bash
cat compose/env/prod/serverC.env
make init-serverC
```

### C. 旧库备份窗口

必须先确认：

- 当前旧 Mongo 的 root 账号可登录
- 可以执行一次完整 `mongodump`
- 业务允许一次短时写入冻结或维护窗口

如果不能接受短暂停写，不建议直接做“单机迁移切换”。

## 推荐迁移步骤

### 第一步：在 serverC 准备新 Mongo 运行环境

在 `infra` 仓库里先完成：

```bash
make init-serverC
make mongo-keyfile
make serverC-up
make mongo-rs-init
make mongo-rs-status
```

确认：

- `serverC` 上 `mongo` 容器已启动
- `rs0` 状态正常
- `127.0.0.1:27017` 可本机登录

### 第二步：确认新库的业务用户和密码

如果你要沿用当前生产库的业务用户名 / 密码，先把它们写进：

- [serverC.env](../../compose/env/prod/serverC.env)

至少确认这些值正确：

- `MONGO_INITDB_ROOT_USERNAME`
- `MONGO_INITDB_ROOT_PASSWORD`
- `MONGO_DATABASE`
- `MONGO_APP_USER`
- `MONGO_APP_PASSWORD`
- `MONGO_READONLY_USER`
- `MONGO_READONLY_PASSWORD`

如需重新补业务用户：

```bash
make mongo-init-users
```

### 第三步：在旧 Mongo 上做切换前备份

如果旧 Mongo 还在 `serverA`，先在旧环境上执行一份完整备份。

注意：

- 当前 `infra` 仓库里的 `make mongo-backup` 已经默认绑定 `serverC.env`
- 所以“旧库切换前备份”应在旧节点上手工执行

建议在旧 Mongo 所在机器直接执行：

```bash
docker exec mongo mongodump \
  --username=root \
  --password='你的密码' \
  --authenticationDatabase=admin \
  --archive \
  --gzip > /data/backup/mongo/pre_migration.archive.gz
```

切换建议：

- 在备份前先暂停最主要的写流量
- 备份完成后，不要让旧库继续承接新的业务写入

### 第四步：把备份恢复到 serverC 新库

推荐先清空新库测试数据，再导入正式备份：

```bash
source compose/env/prod/serverC.env

docker exec -i mongo mongorestore \
  --username="$MONGO_INITDB_ROOT_USERNAME" \
  --password="$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase=admin \
  --archive \
  --gzip \
  --drop < /path/to/pre_migration.archive.gz
```

导入后检查：

```bash
make mongo-shell
```

在 shell 里至少验证：

- `show dbs`
- 关键业务库存在
- 核心集合文档数大致正常

### 第五步：先验证 overlay 网络下的容器访问

在任一已接入 `infra-network` 的容器里验证：

```bash
docker exec <container-name> ping -c 2 mongo
docker exec <container-name> sh -c 'nc -zv mongo 27017'
```

如果容器里没有 `ping` 或 `nc`，至少做一次应用级连接验证。

这一步的目标是确认：

- `serverA/serverB/serverD` 上的业务容器能解析 `mongo`
- 能连到 `27017`

### 第六步：逐个业务仓库切 Mongo 地址

建议按风险从低到高切：

1. `operating`
3. `IAM`（如果依赖 Mongo）
4. `qs-worker`
5. `qs-collection-server`
6. `qs-apiserver`

统一改成：

```bash
MONGO_HOST=mongo
MONGO_PORT=27017
```

如果业务仓库直接用完整连接串，就改成：

```text
mongodb://<user>:<password>@mongo:27017/<db>?authSource=<db>&replicaSet=rs0&directConnection=true
```

### 第七步：切流后做业务回归

至少回归：

- `qs-apiserver` 依赖 Mongo 的读写链路
- `qs-worker` 的异步任务
- `IAM` 的 Mongo 相关逻辑（如果有）
- `operating` 的后台读写

建议重点盯：

- 连接超时
- 认证失败
- 集合不存在
- 索引缺失

### 第八步：确认稳定后，再下线旧 Mongo

不要一切完就删旧库。

建议保留旧库一段只读观察期，确认：

- 新库业务稳定
- 监控正常
- 没有继续写到旧库的残留服务

确认没有残留后，再停止旧 Mongo 容器并回收旧卷。

## 迁移期间的资源口径

当前仓库已经把 Mongo 的默认资源基线收口为：

- 宿主机：`serverC 4C4G`
- `mem_limit=3072M`
- `cpus=3.00`
- `WiredTiger cache=2.0GB`

如果迁移后观察到：

- `Mongo CPU` 长时间接近上限
- `WiredTiger eviction` 明显升高
- `qs-worker` 或 `qs-apiserver` 出现更多超时

再评估提高：

- `MONGO_MEMORY_LIMIT`
- `MONGO_CPUS`

这版已经属于“把 `serverC` 大部分资源给 Mongo”，但仍保留宿主机缓冲，不建议再直接给满 `4G/4C`。

## 回滚方案

如果新库切换后异常，按这个顺序回滚：

1. 停止写入新库的业务发布
2. 把业务仓库里的 Mongo 地址改回旧落点
3. 重启对应业务容器
4. 再观察旧库是否恢复承接流量

不要在未确认数据一致性的情况下，双向写新旧两套 Mongo。

## 最终检查清单

- `serverC` 上 `mongo` 容器正常
- `make mongo-rs-status` 正常
- `serverC.env` 密码已替换默认占位值
- 业务仓库不再写死旧 Mongo 主机
- 所有业务统一使用 `mongo:27017`
- 旧 Mongo 不再接收新的业务写入
- 迁移前备份文件已保留

## 相关文档

- [MongoDB 组件说明](../../components/mongo/README.md)
- [MongoDB 快速入门](../components/mongodb-quickstart.md)
- [服务器架构设计](./architecture.md)
- [四节点 Swarm 搭建](../network/swarm-setup.md)
