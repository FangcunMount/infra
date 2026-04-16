# MongoDB 性能优化与运维指南

> 基于 ServerA (2C/4G) 的生产环境配置

## 📋 目录

1. [配置概览](#配置概览)
2. [系统调优](#系统调优)
3. [安全加固](#安全加固)
4. [备份与恢复](#备份与恢复)
5. [监控告警](#监控告警)
6. [性能优化建议](#性能优化建议)
7. [故障排查](#故障排查)

---

## 配置概览

### 资源配额（ServerA）

| 资源类型 | 配置值 | 说明 |
|---------|--------|------|
| **容器内存** | 1024M | 约占宿主机 4G 的 25% |
| **WiredTiger 缓存** | 512MB | 约占容器内存的 50% |
| **CPU 配额** | 0.50 核 | 适合中等负载场景 |
| **最大连接数** | 100 | 适合小团队/低并发场景 |
| **文件描述符** | 100000 | ulimit -n |

### 内存分配策略

```text
总内存 4GB
├── 系统保留     ~800MB  (20%)
├── Nginx        128MB   (3%)
├── Redis Cache  192MB   (5%)
├── MongoDB     1024MB  (25%)
│   ├── WiredTiger Cache  512MB  (50% of 1024MB)
│   ├── Journal Buffer    ~100MB
│   ├── 连接栈/Page Cache ~412MB
└── 应用/其他    ~1856MB  (47%)
```

> 注：Redis-Store 已迁移至阿里云 Redis，本地不再部署。

### 端口与网络

- **端口映射**: `127.0.0.1:27017:27017` (仅本地访问)
- **远程访问**: 通过 SSH 隧道 `ssh -L 27017:localhost:27017 user@server`
- **网络**: `infra-network` (172.20.0.0/16)

### 用户与权限

MongoDB 支持自动初始化创建业务用户（仅首次启动时执行）：

| 用户类型 | 用户名 | 权限 | 用途 |
|---------|--------|------|------|
| **管理员** | `root` | `root` (所有数据库) | 数据库管理、备份恢复 |
| **应用用户** | `app_user` | `readWrite + dbAdmin` | 业务读写、索引管理 |
| **只读用户** | `readonly_user` | `read` | 数据查询、报表统计 |

**环境变量配置** (在 `.env` 文件中):

```bash
# 管理员账户（容器自动创建）
MONGO_INITDB_ROOT_USERNAME=root
MONGO_INITDB_ROOT_PASSWORD=your_root_password

# 业务用户（初始化脚本创建）
MONGO_APP_USER=app_user
MONGO_APP_PASSWORD=your_app_password
MONGO_READONLY_USER=readonly_user
MONGO_READONLY_PASSWORD=your_readonly_password
```

**连接字符串示例**:

```bash
# 应用连接
mongodb://app_user:password@localhost:27017/infrastructure_dev?authSource=infrastructure_dev&replicaSet=rs0&directConnection=true

# 只读连接
mongodb://readonly_user:password@localhost:27017/infrastructure_dev?authSource=infrastructure_dev&replicaSet=rs0&directConnection=true
```

**手动重新初始化用户**（如需要）:

```bash
cd /path/to/infra
source compose/env/dev/.env
docker exec -i mongo mongosh -u "$MONGO_INITDB_ROOT_USERNAME" -p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin < components/mongo/init-mongo.js
```

---

## 系统调优

### 1. 宿主机内核调优

**执行脚本**:

```bash
sudo bash scripts/components/tune-mongo.sh
```

**手动配置**:

```bash
# 1. 禁用透明大页（THP）
echo never > /sys/kernel/mm/transparent_hugepage/enabled
echo never > /sys/kernel/mm/transparent_hugepage/defrag

# 2. 设置 vm.swappiness
echo "vm.swappiness=1" >> /etc/sysctl.conf
sysctl -w vm.swappiness=1

# 3. 提升网络连接队列
echo "net.core.somaxconn=65535" >> /etc/sysctl.conf
sysctl -w net.core.somaxconn=65535

# 4. 优化 TCP keepalive
cat >> /etc/sysctl.conf << EOF
net.ipv4.tcp_keepalive_time=300
net.ipv4.tcp_keepalive_intvl=30
net.ipv4.tcp_keepalive_probes=3
EOF
sysctl -p

# 5. 提升文件描述符限制
cat >> /etc/security/limits.conf << EOF
* soft nofile 100000
* hard nofile 100000
EOF
```

### 2. Docker 日志管理

已配置 JSON 日志滚动（与其他服务一致）:

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

### 3. 数据卷优化（可选）

**默认**: Docker managed volumes (`/var/lib/docker/volumes`)

**高 I/O 场景**: 绑定挂载到宿主机 SSD 路径

```yaml
volumes:
  - /data/mongo/db:/data/db
  - /data/mongo/log:/data/log/mongodb
```

添加 `noatime` 挂载选项到 `/etc/fstab`:

```bash
/dev/sda1  /data  ext4  defaults,noatime  0  2
```

---

## 安全加固

### 1. 认证配置

✅ 已启用 `--auth` 认证模式
✅ Root 账户通过环境变量创建

**验证 root 账户**:

```bash
docker exec -it mongo mongosh \
  -u root \
  -p 'pBy2xT2r3D8JU@GF' \
  --authenticationDatabase admin
```

### 2. 创建业务用户（最小权限原则）

**使用脚本**:

```bash
bash scripts/components/init-mongo-users.sh
```

**手动创建**:

```javascript
use infrastructure_prod;

db.createUser({
  user: "app_user",
  pwd: "strong_password_here",
  roles: [
    { role: "readWrite", db: "infrastructure_prod" }
  ]
});
```

**角色说明**:

- `read`: 只读权限
- `readWrite`: 读写权限（推荐业务应用使用）
- `dbAdmin`: 数据库管理（索引、统计等）
- `dbOwner`: 数据库所有权（包含 readWrite + dbAdmin）

### 3. 网络安全

✅ 端口绑定到 `127.0.0.1`，不对公网暴露
✅ `bindIp: 0.0.0.0` 在容器内，由 Docker 限制外部访问

**如需公网访问**:

1. 配置防火墙白名单（iptables/firewalld）
2. 使用 VPN 或 Wireguard
3. 配置 TLS/SSL 加密连接

### 4. 单节点副本集（当前启用）

```yaml
# mongod.conf
replication:
  replSetName: "rs0"
```

初始化/校验副本集:

```bash
make mongo-keyfile
make mongo-rs-init
make mongo-rs-status
```

> 当前部署是“单节点副本集”，目的不是高可用，而是启用 MongoDB 事务能力，供业务系统写入文档 + outbox 等场景使用。
> 启用 `authorization + replica set` 时必须同时提供 `security.keyFile`；仓库已通过 `make mongo-keyfile` / `make mongo-start` 自动处理。

---

## 备份与恢复

### 1. 自动备份

**配置定时任务**:

```bash
# 编辑 crontab
crontab -e

# 每天凌晨 2 点备份
0 2 * * * /path/to/infra/scripts/components/backup-mongo.sh >> /var/log/mongo-backup.log 2>&1
```

**手动备份**:

```bash
bash scripts/components/backup-mongo.sh
```

**备份特性**:

- 使用 `mongodump --gzip` 压缩
- 保留最近 7 天备份
- 自动生成备份元数据
- 支持 tar.gz 二次压缩

### 2. 备份策略

| 场景 | 频率 | 保留期 | 方式 |
|-----|------|--------|------|
| **全量备份** | 每天 02:00 | 7 天 | mongodump (本地) |
| **增量备份** | - | - | 暂不支持（单节点） |
| **异地备份** | 每周 | 30 天 | rsync 到对象存储 |

### 3. 数据恢复

```bash
# 1. 解压备份
cd /data/backup/mongo
tar -xzf 20250124_020000.tar.gz

# 2. 恢复到 MongoDB
docker exec -i mongo mongorestore \
  --username=root \
  --password='pBy2xT2r3D8JU@GF' \
  --authenticationDatabase=admin \
  --gzip \
  --dir=/tmp/restore \
  --drop  # 可选：删除现有集合

# 3. 复制备份到容器
docker cp 20250124_020000/ mongo:/tmp/restore
```

**恢复单个数据库**:

```bash
mongorestore \
  --username=root \
  --password='xxx' \
  --authenticationDatabase=admin \
  --nsInclude="infrastructure_prod.*" \
  --gzip \
  --dir=/tmp/restore
```

---

## 监控告警

### 1. 实时监控

**使用监控脚本**:

```bash
# 单次执行
bash scripts/components/monitor-mongo.sh

# 持续监控（5秒刷新）
watch -n 5 bash scripts/components/monitor-mongo.sh
```

### 2. 关键指标

| 指标 | 说明 | 告警阈值 |
|-----|------|---------|
| **缓存使用率** | `wiredTiger.cache / maxCache` | > 85% |
| **脏数据** | `tracked dirty bytes` | > 400MB |
| **连接数** | `connections.current` | > 80 |
| **队列等待** | `globalLock.currentQueue` | > 10 |
| **Page Faults** | 缺页中断（累计） | 快速增长 |
| **慢查询** | 操作耗时 > 100ms | 频繁出现 |

### 3. 监控命令

```bash
# 服务器状态
docker exec mongo mongosh \
  -u root -p 'xxx' --authenticationDatabase admin \
  --eval "db.serverStatus()" | less

# 当前操作
docker exec mongo mongosh \
  -u root -p 'xxx' --authenticationDatabase admin \
  --eval "db.currentOp()"

# 慢查询日志
docker exec mongo mongosh \
  -u root -p 'xxx' --authenticationDatabase admin \
  --eval "db.system.profile.find().sort({ts:-1}).limit(10).pretty()"

# 数据库大小
docker exec mongo mongosh \
  -u root -p 'xxx' --authenticationDatabase admin \
  --eval "db.adminCommand({listDatabases:1})"
```

### 4. 日志分析

```bash
# 容器日志
docker logs mongo --tail 100 -f

# MongoDB 日志文件
docker exec mongo tail -f /data/log/mongodb/mongod.log

# 查找慢查询
docker exec mongo grep -i "slow" /data/log/mongodb/mongod.log | tail -20
```

---

## 性能优化建议

### 1. 索引优化

```javascript
// 查看索引使用情况
db.collection.getIndexes()

// 分析查询计划
db.collection.find({field: value}).explain("executionStats")

// 创建复合索引
db.collection.createIndex({field1: 1, field2: -1})

// 后台创建索引（不阻塞读写）
db.collection.createIndex({field: 1}, {background: true})
```

**索引建议**:

- 频繁查询的字段必须建索引
- 复合索引遵循 ESR 原则（Equality、Sort、Range）
- 避免过多索引（写入性能下降）
- 定期检查未使用的索引

### 2. 查询优化

```javascript
// 使用投影，只返回需要的字段
db.collection.find({}, {field1: 1, field2: 1, _id: 0})

// 使用 limit 限制返回数量
db.collection.find({}).limit(100)

// 避免全表扫描
db.collection.find({unindexed_field: value})  // ❌ 慢
db.collection.find({indexed_field: value})    // ✅ 快

// 使用聚合管道优化复杂查询
db.collection.aggregate([
  {$match: {field: value}},
  {$group: {_id: "$category", count: {$sum: 1}}},
  {$sort: {count: -1}},
  {$limit: 10}
])
```

### 3. 写入优化

```javascript
// 批量插入（性能提升 10-100 倍）
db.collection.insertMany([
  {doc1},
  {doc2},
  ...
], {ordered: false})  // 无序插入更快

// 更新多个文档
db.collection.updateMany(
  {status: "pending"},
  {$set: {status: "processed"}}
)

// 使用 bulkWrite 批量操作
db.collection.bulkWrite([
  {insertOne: {document: {}}},
  {updateOne: {filter: {}, update: {}}},
  {deleteOne: {filter: {}}}
], {ordered: false})
```

### 4. 临时性能提升

**大批量导入/索引构建时**:

```bash
# 1. 临时提升 CPU 配额
# 编辑 compose/env/prod/env
MONGO_CPUS=1.0

# 2. 重启容器
cd components/mongo
docker compose down && docker compose up -d

# 3. 操作完成后改回 0.30
MONGO_CPUS=0.30
docker compose restart
```

### 5. 文档设计优化

**避免**:

- 超大文档（> 16MB 限制）
- 深层嵌套（> 100 层）
- 无界数组（持续增长的数组字段）

**推荐**:

- 合理的文档大小（< 1MB）
- 适度反规范化（减少 join）
- 使用引用代替嵌入（大对象）

---

## 故障排查

### 1. 容器无法启动

```bash
# 查看日志
docker logs mongo --tail 100

# 常见问题：
# - 端口被占用: lsof -i :27017
# - 权限问题: chown -R 999:999 /data/mongo
# - 配置错误: 检查 mongod.conf 语法
```

### 2. 认证失败

```bash
# 检查环境变量
docker exec mongo env | grep MONGO

# 重新创建 admin 用户（首次启动失败）
docker compose down -v  # 清空数据
docker compose up -d    # 重新初始化
```

### 3. 性能问题

```bash
# 1. 检查缓存使用率
bash scripts/components/monitor-mongo.sh

# 2. 查看慢查询
docker exec mongo mongosh -u root -p 'xxx' \
  --authenticationDatabase admin \
  --eval "db.system.profile.find({millis: {\$gt: 100}}).sort({ts:-1}).limit(10)"

# 3. 检查索引
docker exec mongo mongosh -u root -p 'xxx' \
  --authenticationDatabase admin \
  infrastructure_prod \
  --eval "db.collection.getIndexes()"
```

### 4. 磁盘空间不足

```bash
# 检查数据库大小
docker exec mongo mongosh -u root -p 'xxx' \
  --authenticationDatabase admin \
  --eval "db.adminCommand({listDatabases: 1})"

# 压缩数据库（回收空间）
docker exec mongo mongosh -u root -p 'xxx' \
  --authenticationDatabase admin \
  infrastructure_prod \
  --eval "db.runCommand({compact: 'collection_name'})"

# 删除旧数据
docker exec mongo mongosh -u root -p 'xxx' \
  --authenticationDatabase admin \
  infrastructure_prod \
  --eval "db.collection.deleteMany({createdAt: {\$lt: ISODate('2024-01-01')}})"
```

### 5. 连接池耗尽

```bash
# 查看当前连接
docker exec mongo mongosh -u root -p 'xxx' \
  --authenticationDatabase admin \
  --eval "db.currentOp()"

# 临时增加连接数（需重启）
# 编辑 mongod.conf
maxIncomingConnections: 200

# 重启容器
docker compose restart
```

---

## 快速命令参考

```bash
# 🚀 启动/停止
cd components/mongo
docker compose up -d        # 启动
docker compose down         # 停止
docker compose restart      # 重启
docker compose logs -f      # 查看日志

# 🔧 系统调优（首次部署执行）
sudo bash scripts/components/tune-mongo.sh

# 👥 创建业务用户
bash scripts/components/init-mongo-users.sh

# 💾 备份
bash scripts/components/backup-mongo.sh

# 📊 监控
bash scripts/components/monitor-mongo.sh
watch -n 5 bash scripts/components/monitor-mongo.sh

# 🔍 连接数据库
docker exec -it mongo mongosh \
  -u root -p 'pBy2xT2r3D8JU@GF' \
  --authenticationDatabase admin

# 📈 查看状态
docker exec mongo mongosh \
  -u root -p 'pBy2xT2r3D8JU@GF' \
  --authenticationDatabase admin \
  --eval "db.serverStatus()" | less
```

---

## 相关文档

- [服务器组件--存储服务(MySQL_Redis_MongoDB).md](../../docs/服务器组件--存储服务(MySQL_Redis_MongoDB).md)
- [网络设计.md](../../docs/网络设计.md)
- [Makefile快速参考.md](../../docs/Makefile快速参考.md)

---

**最后更新**: 2025-01-24  
**适用版本**: MongoDB 7.x  
**环境**: ServerA (2C/4G)
