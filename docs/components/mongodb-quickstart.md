# MongoDB 快速入门

> 🍃 MongoDB 7.0 生产环境部署与管理速查表

## 🚀 快速开始（3 分钟）

### 1. 首次部署

```bash
# 1️⃣ 系统调优（只需执行一次，重启后也有效）
cd /path/to/infra
sudo make mongo-tune

# 2️⃣ 启动 MongoDB
make mongo-start

# 3️⃣ 验证状态
make mongo-status

# 4️⃣ 测试连接
make test-mongo
```

### 2. 创建业务用户

```bash
# 交互式创建用户（推荐）
make mongo-init-users

# 手动创建（在 mongo-shell 中）
make mongo-shell
> use infrastructure_prod
> db.createUser({
    user: "app_user",
    pwd: "strong_password",
    roles: [{role: "readWrite", db: "infrastructure_prod"}]
  })
```

---

## 📋 常用命令速查

### 基础操作

```bash
make mongo-start          # 启动 MongoDB
make mongo-stop           # 停止 MongoDB
make mongo-restart        # 重启 MongoDB
make mongo-status         # 查看状态
make mongo-logs           # 查看日志
```

### 连接与管理

```bash
make mongo-shell          # 连接 Shell（自动认证）
make mongo-stats          # 查看服务器统计
make test-mongo           # 测试连接
```

### 监控与维护

```bash
make mongo-monitor        # 实时性能监控
make mongo-backup         # 立即备份
make mongo-init-users     # 创建业务用户
```

---

## 🔐 连接字符串

### 应用连接

```bash
# 标准格式
mongodb://用户名:密码@localhost:27017/数据库名?authSource=admin

# Root 用户（管理）
mongodb://root:pBy2xT2r3D8JU@GF@localhost:27017/admin?authSource=admin

# 业务用户（应用）
mongodb://app_user:密码@localhost:27017/infrastructure_prod?authSource=infrastructure_prod
```

### 远程连接（SSH 隧道）

```bash
# 1. 建立 SSH 隧道
ssh -L 27017:localhost:27017 user@47.94.204.124

# 2. 本地连接
mongosh "mongodb://root:密码@localhost:27017/admin?authSource=admin"
```

---

## 📊 性能监控

### 关键指标

```bash
# 实时监控（推荐）
make mongo-monitor

# 或 watch 持续监控
watch -n 5 make mongo-monitor
```

### 监控内容

- ✅ 缓存使用率（目标 < 85%）
- ✅ 脏数据量（目标 < 400MB）
- ✅ 连接数（目标 < 80）
- ✅ 锁队列（目标 < 10）
- ✅ Page Faults

---

## 💾 备份与恢复

### 自动备份（推荐）

```bash
# 配置定时任务
crontab -e

# 每天凌晨 2 点备份
0 2 * * * cd /path/to/infra && make mongo-backup >> /var/log/mongo-backup.log 2>&1
```

### 手动备份

```bash
# 立即备份
make mongo-backup

# 备份保存在
/data/backup/mongo/YYYYMMDD_HHMMSS/
```

### 恢复数据

```bash
# 1. 找到备份
cd /data/backup/mongo
ls -lh

# 2. 解压（如果是 .tar.gz）
tar -xzf 20250124_020000.tar.gz

# 3. 恢复
docker exec -i mongo mongorestore \
  --username=root \
  --password='pBy2xT2r3D8JU@GF' \
  --authenticationDatabase=admin \
  --gzip \
  --dir=/path/to/backup \
  --drop  # 可选：删除现有数据
```

---

## 🔧 常见问题

### 1. 无法连接（认证失败）

```bash
# 检查环境变量
make env-show ENV=prod | grep MONGO

# 确保以下变量存在：
# MONGO_INITDB_ROOT_USERNAME=root
# MONGO_INITDB_ROOT_PASSWORD=xxx
```

### 2. 容器无法启动

```bash
# 查看日志
make mongo-logs

# 常见原因：
# - 端口被占用：lsof -i :27017
# - 权限问题：检查数据卷权限
# - 配置错误：检查 mongod.conf 语法
```

### 3. 性能问题

```bash
# 1. 检查缓存使用率
make mongo-monitor

# 2. 查看慢查询
make mongo-shell
> db.system.profile.find({millis: {$gt: 100}}).sort({ts: -1}).limit(10)

# 3. 检查索引
> db.collection.getIndexes()
```

### 4. 磁盘空间不足

```bash
# 检查数据库大小
make mongo-shell
> db.adminCommand({listDatabases: 1})

# 压缩数据库（回收空间）
> use infrastructure_prod
> db.runCommand({compact: 'collection_name'})
```

---

## 📝 配置说明

### 资源配额（ServerA 2C/4G）

| 配置项 | 值 | 说明 |
|-------|-----|------|
| 容器内存 | 1536M | 约占宿主机 38% |
| WiredTiger 缓存 | 900MB | 约占容器 60% |
| CPU 配额 | 0.30 核 | 轻载场景 |
| 最大连接数 | 100 | 足够小团队使用 |
| 端口映射 | 127.0.0.1:27017 | 仅本地访问 |

### 环境变量

```bash
# 在 compose/env/prod/env 中配置
MONGO_PORT=27017
MONGO_INITDB_ROOT_USERNAME=root
MONGO_INITDB_ROOT_PASSWORD=pBy2xT2r3D8JU@GF
MONGO_DATABASE=infrastructure_prod
MONGO_MEMORY_LIMIT=1536M
MONGO_CPUS=0.30
```

---

## 🎯 最佳实践

### 1. 安全

- ✅ 使用 SSH 隧道远程访问，不要暴露公网端口
- ✅ 创建业务用户，限制权限（readWrite/read）
- ✅ 定期更换密码（建议 90 天）
- ✅ 启用审计日志（生产环境）

### 2. 性能

- ✅ 频繁查询字段必须建索引
- ✅ 使用投影只返回需要的字段
- ✅ 批量操作使用 `insertMany`、`bulkWrite`
- ✅ 避免全表扫描（使用 `explain()` 检查）

### 3. 运维

- ✅ 配置自动备份（每天）
- ✅ 异地备份（rsync 到对象存储）
- ✅ 监控关键指标（缓存、连接、慢查询）
- ✅ 定期检查日志和错误

---

## 📚 完整文档

- **[MongoDB 完整运维指南](../components/mongo/README.md)** - 详细配置、优化、故障排查
- **[为什么需要宿主机调优](../docs/为什么需要宿主机调优.md)** - 系统调优原理解析
- **[Makefile 快速参考](../docs/Makefile快速参考.md)** - 所有命令说明

---

## 💡 更多帮助

```bash
# MongoDB 完整命令列表
make help-mongo

# 查看所有可用命令
make help-all | grep mongo
```

**技术支持**：参考 [components/mongo/README.md](../components/mongo/README.md) 或提交 Issue

---

**最后更新**: 2025-01-24  
**适用版本**: MongoDB 7.x  
**环境**: ServerA (2C/4G)
