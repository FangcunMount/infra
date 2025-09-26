# MongoDB 7.0 文档数据库组件

## 📋 组件概述

提供高性能的 MongoDB 文档数据库服务，采用 WiredTiger 存储引擎，优化用于节点 A 的文档存储和查询。

## 🔧 配置文件

- **mongod.conf**: MongoDB 主配置文件，包含存储引擎和缓存优化

## 🌐 端口配置

- **MongoDB**: `${MONGO_PORT:-27017}:27017`

## 📊 关键参数 (可通过环境变量调整)

- **WiredTiger 缓存**: `${MONGO_WIRED_TIGER_CACHE_SIZE_GB:-0.8}` (800MB, 节点 A 优化)
- **最大连接数**: `100` (适合中等并发)
- **压缩算法**: `snappy` (平衡压缩率和性能)
- **日志级别**: `slowOp` (记录慢操作 >100ms)

## 💾 存储配置

- **数据目录**: `/data/mongo` (WiredTiger 数据文件)
- **日志目录**: `/data/logs/mongo`
- **日志压缩**: `snappy` 算法
- **索引压缩**: 启用前缀压缩

## 🔗 应用数据库隔离

每个应用使用独立的 MongoDB 数据库：

```javascript
// 连接字符串示例
mongodb://mongo:27017/miniblog
mongodb://mongo:27017/qs
mongodb://mongo:27017/app_name
```

## 🚀 启动与管理

```bash
# 连接 MongoDB Shell
docker exec -it mongo mongosh

# 查看数据库列表
docker exec mongo mongosh --eval "show dbs"

# 查看服务状态
docker exec mongo mongosh --eval "db.runCommand({serverStatus: 1})"

# 查看连接数
docker exec mongo mongosh --eval "db.runCommand({currentOp: 1}).inprog.length"
```

## 📋 健康检查

- **连接测试**: `mongosh --eval "db.runCommand({ping: 1})"` 每 30 秒
- **响应验证**: 返回 `{ok: 1}`
- **重试次数**: 3 次

## 🔧 性能监控

```bash
# 查看数据库统计
docker exec mongo mongosh --eval "db.stats()"

# 查看 WiredTiger 缓存使用
docker exec mongo mongosh --eval "db.runCommand({serverStatus: 1}).wiredTiger.cache"

# 查看当前操作
docker exec mongo mongosh --eval "db.currentOp()"

# 查看慢查询
docker exec mongo mongosh --eval "db.getProfilingStatus()"

# 查看索引使用统计
docker exec mongo mongosh --eval "db.collection.getIndexes()"
```

## 📈 性能调优建议

### 内存不足时的调整

```bash
# 降低 WiredTiger 缓存
MONGO_WIRED_TIGER_CACHE_SIZE_GB=0.5

# 调整连接数
maxIncomingConnections: 50

# 启用更aggressive压缩
blockCompressor: zstd
```

### 查询性能优化

```javascript
// 创建复合索引
db.collection.createIndex({field1: 1, field2: -1})

// 查看查询计划
db.collection.explain("executionStats").find({query})

// 启用查询分析器
db.setProfilingLevel(2, {slowms: 50})
```

## 🔄 备份与恢复

```bash
# 使用 mongodump 备份
docker exec mongo mongodump --out /var/backups/mongo

# 使用 mongorestore 恢复  
docker exec mongo mongorestore /var/backups/mongo

# 备份单个数据库
docker exec mongo mongodump --db database_name --out /backup

# 恢复单个数据库
docker exec mongo mongorestore --db database_name /backup/database_name
```

## 🚨 故障排除

```bash
# 查看错误日志
docker logs mongo
tail -f /data/logs/mongo/mongod.log

# 检查磁盘使用
du -sh /data/mongo

# 检查内存使用
docker exec mongo mongosh --eval "db.runCommand({serverStatus: 1}).mem"

# 验证数据完整性
docker exec mongo mongosh --eval "db.runCommand({validate: 'collection_name'})"

# 修复数据库 (停机操作)
docker exec mongo mongod --repair --dbpath /data/db
```

## 📊 集合管理

```javascript
// 查看集合统计
db.collection.stats()

// 压缩集合 (回收空间)
db.runCommand({compact: "collection_name"})

// 重建索引
db.collection.reIndex()

// 查看集合大小
db.collection.totalSize()
```

## 🔧 双节点配置

- **节点 A**: 运行 MongoDB 主实例，存储应用文档数据
- **节点 B**: 通过内网连接节点 A 的 MongoDB
- **连接字符串**: `mongodb://${NODE_A_IP}:27017/database_name`

## 🔒 生产环境安全

```yaml
# 启用认证 (mongod.conf)
security:
  authorization: enabled

# 创建管理员用户
use admin
db.createUser({
  user: "admin",
  pwd: "secure_password", 
  roles: ["userAdminAnyDatabase", "dbAdminAnyDatabase"]
})

# 创建应用用户
use app_database
db.createUser({
  user: "app_user",
  pwd: "app_password",
  roles: ["readWrite"]
})
```

## 📈 扩展策略

### 复制集 (高可用)

```yaml
# mongod.conf
replication:
  replSetName: "rs0"
```

### 分片 (水平扩展)

```yaml  
# mongod.conf
sharding:
  clusterRole: shardsvr
```

## 📝 变更记录

- 2024-09-26: 重构为组件化配置，优化节点 A 缓存分配
- 2024-09-25: 调整 WiredTiger 缓存为 800MB，启用 snappy 压缩
- 2024-09-24: 添加应用数据库隔离和性能监控配置