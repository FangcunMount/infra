# Redis 双实例部署方案

## 架构说明

为了优化不同业务场景的性能和可靠性，Redis 被拆分为两个独立实例：

### 1. redis-cache（缓存实例）

**用途**：高频访问的临时数据缓存

- **端口**: 6379
- **持久化**: 禁用（`save ""`，`appendonly no`）
- **淘汰策略**: `allkeys-lfu`（访问频率最低的键优先淘汰）
- **内存限制**: 512MB 数据 + 288MB 余量 = 800MB 容器
- **CPU**: 0.20 核
- **适用场景**:
  - 会话缓存（Session）
  - 热点数据缓存（热门商品、文章等）
  - 接口响应缓存
  - 计数器（允许丢失）
  - 排行榜（允许重建）

**特点**:

- ✅ 高性能，无磁盘 I/O 开销
- ✅ 内存不足时自动淘汰旧数据
- ⚠️ 重启后数据丢失
- ⚠️ 不保证数据持久性

### 2. redis-store（存储实例）

**用途**：关键业务数据存储

- **端口**: 6380
- **持久化**: AOF（`appendonly yes`，`appendfsync everysec`）
- **淘汰策略**: `noeviction`（内存满时拒绝写入，保证数据不丢失）
- **内存限制**: 192MB 数据 + 158MB 余量 = 350MB 容器
- **CPU**: 0.15 核
- **适用场景**:
  - 用户认证令牌（JWT Token、Refresh Token）
  - 权限缓存（用户角色、权限列表）
  - 重要业务状态（订单状态、支付状态）
  - 分布式锁
  - 消息队列（待处理任务）

**特点**:

- ✅ 数据持久化，重启不丢失
- ✅ 内存满时拒绝写入，保证关键数据安全
- ⚠️ 有 AOF 写入开销（但 everysec 模式影响较小）
- ⚠️ 需要定期检查 AOF 文件大小

## 资源分配

| 实例 | 数据内存 | 容器内存 | CPU | 余量说明 |
|------|---------|---------|-----|---------|
| redis-cache | 512MB | 800MB | 0.20 | 1.56x（fork/COW 余量） |
| redis-store | 192MB | 350MB | 0.15 | 1.82x（AOF 重写余量） |
| **总计** | 704MB | **1150MB** | **0.35** | ServerA 总内存占用 |

## 环境变量配置

### env/prod/.env 示例

```bash
# Redis Cache 实例
REDIS_CACHE_PORT=6379
REDIS_CACHE_PASSWORD=your_cache_password_here
REDIS_CACHE_MAXMEMORY=512mb
REDIS_CACHE_POLICY=allkeys-lfu
REDIS_CACHE_MEM_LIMIT=800m
REDIS_CACHE_CPUS=0.20

# Redis Store 实例
REDIS_STORE_PORT=6380
REDIS_STORE_PASSWORD=your_store_password_here
REDIS_STORE_MAXMEMORY=192mb
REDIS_STORE_MEM_LIMIT=350m
REDIS_STORE_CPUS=0.15
```

## 使用方式

### 连接配置

**应用配置示例（以 Node.js 为例）**:

```javascript
// redis-cache（缓存）
const cacheClient = redis.createClient({
  host: 'redis-cache',  // Docker 容器名
  port: 6379,
  password: process.env.REDIS_CACHE_PASSWORD,
  db: 0
});

// redis-store（存储）
const storeClient = redis.createClient({
  host: 'redis-store',
  port: 6380,
  password: process.env.REDIS_STORE_PASSWORD,
  db: 0
});
```

### 业务代码示例

```javascript
// 缓存热门文章（可淘汰）
await cacheClient.setex('article:hot:123', 3600, JSON.stringify(article));

// 存储用户 Token（不可淘汰）
await storeClient.setex('auth:token:abc123', 7200, userId);

// 分布式锁（关键操作）
const lockKey = 'lock:order:456';
const acquired = await storeClient.set(lockKey, workerId, 'NX', 'EX', 30);
```

## 运维建议

### 1. 监控指标

**Cache 实例关注**:

- `evicted_keys`: 淘汰的键数量（正常现象）
- `keyspace_hits/misses`: 缓存命中率
- `used_memory`: 内存使用量（接近 512MB 时淘汰加速）

**Store 实例关注**:

- `aof_current_size`: AOF 文件大小（定期 BGREWRITEAOF）
- `used_memory`: 内存使用量（接近 192MB 需扩容或清理）
- `rejected_connections`: 拒绝连接数（noeviction 时会发生）

### 2. AOF 维护

Store 实例需要定期重写 AOF：

```bash
# 手动触发 AOF 重写
docker exec redis-store redis-cli -a ${REDIS_STORE_PASSWORD} BGREWRITEAOF

# 查看 AOF 状态
docker exec redis-store redis-cli -a ${REDIS_STORE_PASSWORD} INFO persistence
```

### 3. 内存告警

当 Store 实例内存接近上限时：

```bash
# 查看内存占用 TOP 100
docker exec redis-store redis-cli -a ${REDIS_STORE_PASSWORD} --bigkeys

# 清理过期键
docker exec redis-store redis-cli -a ${REDIS_STORE_PASSWORD} --scan --pattern "expired:*" | xargs redis-cli -a ${REDIS_STORE_PASSWORD} DEL
```

### 4. 备份策略

Store 实例需要定期备份 AOF 文件：

```bash
# 备份命令（建议每日凌晨执行）
docker cp redis-store:/data/appendonly.aof /backup/redis-store-$(date +%Y%m%d).aof
```

## 部署命令

```bash
# 启动双实例
cd /path/to/components/redis
docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f redis-cache
docker-compose logs -f redis-store

# 连接测试
docker exec -it redis-cache redis-cli -a ${REDIS_CACHE_PASSWORD}
docker exec -it redis-store redis-cli -a ${REDIS_STORE_PASSWORD}

# 停止服务
docker-compose down  # 注意：cache 数据会丢失，store 数据保留
```

## 故障排查

### 问题 1: Cache 实例淘汰过快

**症状**: `evicted_keys` 增长迅速，缓存命中率低

**解决**:

1. 增加 `REDIS_CACHE_MAXMEMORY`（如 512mb）
2. 调整淘汰策略为 `volatile-lfu`（仅淘汰有 TTL 的键）
3. 优化业务代码，减少冷数据缓存

### 问题 2: Store 实例拒绝写入

**症状**: 应用报错 `OOM command not allowed`

**解决**:

1. 立即清理过期数据：`redis-cli DEL <expired_keys>`
2. 扩大 `REDIS_STORE_MAXMEMORY`（如 256mb）
3. 检查是否有内存泄漏（未设置 TTL 的键）

### 问题 3: AOF 文件过大

**症状**: AOF 文件超过 1GB

**解决**:

```bash
# 执行 AOF 重写
docker exec redis-store redis-cli -a ${REDIS_STORE_PASSWORD} BGREWRITEAOF

# 配置自动重写（修改 redis-store.conf）
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
```

## 性能优化

### 1. 系统参数优化

在宿主机执行：

```bash
# 禁用 Transparent Huge Pages（THP）
echo never > /sys/kernel/mm/transparent_hugepage/enabled

# 调整 TCP backlog
sysctl -w net.core.somaxconn=65535

# 调整文件描述符限制
ulimit -n 65535
```

### 2. Redis 配置优化

根据业务负载调整 `redis-cache.conf` 和 `redis-auth.conf`：

```conf
# 连接数（根据并发量调整）
maxclients 10000

# 慢查询（定位性能问题）
slowlog-log-slower-than 10000  # 10ms
slowlog-max-len 256

# 碎片整理（Cache 实例可启用）
activedefrag yes
```

## 迁移指南

### 从单实例迁移到双实例

**步骤 1**: 备份现有数据

```bash
docker exec redis redis-cli -a ${REDIS_PASSWORD} --rdb /data/dump.rdb
```

**步骤 2**: 分析数据分类

```bash
# 导出所有键
docker exec redis redis-cli -a ${REDIS_PASSWORD} KEYS "*" > all_keys.txt

# 手动分类：cache_keys.txt vs auth_keys.txt
```

**步骤 3**: 启动新实例并导入

```bash
# 启动双实例
docker-compose up -d redis-cache redis-store

# 导入 Cache 数据（可选，缓存可重建）
# 导入 Store 数据（必须）
cat auth_keys.txt | while read key; do
  docker exec redis redis-cli -a ${OLD_PASSWORD} DUMP "$key" | \
  docker exec -i redis-store redis-cli -a ${REDIS_STORE_PASSWORD} RESTORE "$key" 0
done
```

**步骤 4**: 更新应用配置

修改应用连接配置，指向不同实例。

**步骤 5**: 下线旧实例

确认业务正常后，停止旧 Redis 实例。

---

## 总结

**优势**:

- 🎯 **职责分离**: 缓存和持久化分离，避免相互影响
- 🚀 **性能提升**: Cache 无 AOF 开销，Store 不受淘汰影响
- 🔒 **数据安全**: 关键数据 noeviction + AOF 双重保障
- 💰 **成本优化**: 总内存 1150MB，适配 ServerA 2C4G 配置

**注意事项**:

- ⚠️ 应用需明确区分缓存和持久化数据
- ⚠️ Store 实例需定期维护 AOF 文件
- ⚠️ 两个实例需要独立监控和告警
