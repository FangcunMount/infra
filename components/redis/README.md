# Redis 7.0 缓存组件

## 📋 组件概述

提供高性能的 Redis 内存数据库服务，支持多应用共享、数据持久化和内存限制管理。

## 🔧 配置文件

- **redis.conf**: Redis 主配置文件，包含内存限制和持久化设置

## 🌐 端口配置

- **Redis**: `${REDIS_PORT:-6379}:6379`

## 📊 关键参数 (可通过环境变量调整)

- **内存限制**: `${REDIS_MAXMEMORY:-384mb}` (节点 A 优化)
- **淘汰策略**: `allkeys-lru` (最近最少使用)
- **持久化**: `appendonly` AOF 模式
- **数据库数量**: `16` 个逻辑数据库 (DB0-DB15)

## 💾 存储配置

- **数据目录**: `/data/redis` (AOF 文件存储)
- **日志目录**: `/data/logs/redis`
- **AOF 同步**: `everysec` (每秒同步)
- **AOF 重写**: 100% 增长时触发，最小 64MB

## 🔗 多应用支持

Redis 通过数据库索引隔离不同应用：

```bash
# DB0: 保留给临时使用
# DB1-DB15: 自动分配给应用
# 应用连接示例: redis://redis:6379/1
```

## 🛡️ 安全配置

- **受保护模式**: 禁用 (内网环境)
- **密码认证**: 可选配置 `${REDIS_PASSWORD}`
- **危险命令**: 生产环境可考虑重命名 FLUSHALL/FLUSHDB

## 🚀 启动与管理

```bash
# 连接 Redis CLI
docker exec -it redis redis-cli

# 查看信息
docker exec redis redis-cli info server

# 查看内存使用
docker exec redis redis-cli info memory

# 查看连接数
docker exec redis redis-cli info clients
```

## 📋 健康检查

- **连接测试**: `redis-cli ping` 每 30 秒
- **响应验证**: 返回 `PONG`
- **重试次数**: 3 次

## 🔧 性能监控

```bash
# 查看内存使用详情
docker exec redis redis-cli info memory | grep used_memory

# 查看命中率
docker exec redis redis-cli info stats | grep keyspace

# 查看慢查询
docker exec redis redis-cli slowlog get 10

# 查看客户端连接
docker exec redis redis-cli client list

# 监控实时命令
docker exec redis redis-cli monitor
```

## 📈 性能调优建议

### 内存不足时的调整

```bash
# 降低内存限制
REDIS_MAXMEMORY=256mb

# 调整淘汰策略
maxmemory-policy volatile-lru  # 仅淘汰有过期时间的键

# 禁用持久化节省内存
appendonly no
```

### 高并发优化

```bash
# 增加客户端连接数
maxclients 20000

# 调整输出缓冲区
client-output-buffer-limit normal 0 0 0
```

## 🔄 备份与恢复

```bash
# AOF 备份 (通过 scripts/backup.sh)
make redis-backup BACKUP_NAME=daily

# 手动触发 AOF 重写
docker exec redis redis-cli bgrewriteaof

# 手动生成 RDB 快照  
docker exec redis redis-cli bgsave

# 恢复 AOF 文件
# 1. 停止 Redis
# 2. 替换 /data/redis/appendonly.aof
# 3. 重启 Redis
```

## 🚨 故障排除

```bash
# 查看错误日志
docker logs redis
tail -f /data/logs/redis/redis.log

# 检查内存使用是否超限
docker exec redis redis-cli info memory | grep used_memory_peak

# 检查 AOF 文件完整性
docker exec redis redis-check-aof /data/appendonly.aof

# 检查配置
docker exec redis redis-cli config get "*"
```

## 📊 应用数据库分配

应用通过 `scripts/add-app.sh` 自动分配 DB 索引：

| DB 索引 | 应用名称 | 用途 |
|---------|---------|------|
| 0 | 系统保留 | 临时缓存、测试 |
| 1-15 | 自动分配 | 应用专用缓存 |

## 🔧 双节点配置

- **节点 A**: 运行 Redis 主实例，提供缓存服务
- **节点 B**: 通过内网连接节点 A 的 Redis
- **连接字符串**: `redis://${NODE_A_IP}:6379/db_index`

## 🔒 生产环境安全

```bash
# 启用密码认证 (.env 文件)
REDIS_PASSWORD=your_secure_password

# 重命名危险命令 (redis.conf)
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command CONFIG "CONFIG_8a7b2c3d"
```

## 📝 变更记录

- 2024-09-26: 重构为组件化配置，优化节点 A 内存分配
- 2024-09-25: 调整内存限制为 384MB，启用 AOF 持久化  
- 2024-09-24: 添加多应用 DB 索引自动分配机制