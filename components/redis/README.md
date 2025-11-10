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
REDIS_CACHE_MAXMEMORY=512mb
REDIS_CACHE_POLICY=allkeys-lfu
REDIS_CACHE_MEM_LIMIT=800m
REDIS_CACHE_CPUS=0.20

# Redis Store 实例
REDIS_STORE_PORT=6380
REDIS_STORE_MAXMEMORY=192mb
REDIS_STORE_MEM_LIMIT=350m
REDIS_STORE_CPUS=0.15

# Redis ACL 用户密码（生产环境必须修改）
REDIS_ADMIN_PASSWORD=your_strong_admin_password
REDIS_APP_PASSWORD=your_strong_app_password
REDIS_READONLY_PASSWORD=your_strong_readonly_password
REDIS_CACHE_USER_PASSWORD=your_strong_cache_password
REDIS_MONITOR_PASSWORD=your_strong_monitor_password
```

## ACL 访问控制

本项目使用 Redis 7.x 的 ACL（Access Control List）功能来管理用户权限，替代了传统的 `requirepass` 方式。

### ACL 用户说明

| 用户 | 权限 | 用途 | 环境变量 |
|------|------|------|---------|
| **default** | 已禁用 | 安全起见已禁用 | - |
| **admin** | 完全权限 | 运维管理、配置变更 | `REDIS_ADMIN_PASSWORD` |
| **app** | 常规读写（排除危险命令） | 应用程序日常使用 | `REDIS_APP_PASSWORD` |
| **readonly** | 仅读取 | 数据查询、监控脚本 | `REDIS_READONLY_PASSWORD` |
| **cache** | 读写+过期管理 | 缓存服务 | `REDIS_CACHE_USER_PASSWORD` |
| **monitor** | 仅状态查询 | 监控系统、性能分析 | `REDIS_MONITOR_PASSWORD` |

### ACL 配置文件

- **文件位置**: `users.acl`
- **重要**: ACL 文件不支持注释行，每行必须以 `user` 关键字开头
- **配置引用**: 在 `redis-cache.conf` 和 `redis-store.conf` 中通过 `aclfile /etc/redis/users.acl` 引入

**users.acl 文件内容**:

```acl
user default off nopass ~* &* +@all
user admin on >${REDIS_ADMIN_PASSWORD} ~* &* +@all
user app on >${REDIS_APP_PASSWORD} ~* &* +@all -@dangerous -@admin -flushall -flushdb -keys -config -shutdown -bgsave -bgrewriteaof -save -debug -migrate -slaveof -replicaof
user readonly on >${REDIS_READONLY_PASSWORD} ~* &* +@read +@connection +ping +info +auth
user cache on >${REDIS_CACHE_USER_PASSWORD} ~* &* +@read +@write +@string +@hash +@list +@set +@sortedset +@connection +@transaction +del +expire +ttl +persist +unlink
user monitor on >${REDIS_MONITOR_PASSWORD} ~* &* +@connection +ping +info +client +cluster +slowlog +latency +memory +config|get +auth
```

### ACL 语法说明

**基本规则**:

- `on` / `off` - 启用/禁用用户
- `>password` - 设置密码（明文）
- `#<hash>` - 设置密码（SHA256 哈希）
- `nopass` - 无需密码

**键权限**:

- `~*` - 访问所有键
- `~prefix:*` - 只能访问特定前缀的键
- `&*` - 访问所有 Pub/Sub 频道

**命令权限**:

- `+@all` - 允许所有命令
- `+@read` / `+@write` - 允许读/写命令
- `-@dangerous` - 禁止危险命令（flushall, keys 等）
- `+command` / `-command` - 允许/禁止特定命令

## 使用方式

### 连接配置

**重要**: 现在所有连接都必须指定用户名（default 用户已禁用）。

#### Python (redis-py)

```python
import redis

# Cache 实例 - 使用 app 用户
cache_client = redis.Redis(
    host='redis-cache',
    port=6379,
    username='app',
    password=os.getenv('REDIS_APP_PASSWORD'),
    db=0,
    decode_responses=True
)

# Store 实例 - 使用 app 用户
store_client = redis.Redis(
    host='redis-store',
    port=6380,
    username='app',
    password=os.getenv('REDIS_APP_PASSWORD'),
    db=0,
    decode_responses=True
)

# 或使用 URI
cache_client = redis.from_url(f'redis://app:{password}@redis-cache:6379/0')
```

#### Node.js (ioredis)

```javascript
const Redis = require('ioredis');

// Cache 实例
const cacheClient = new Redis({
  host: 'redis-cache',
  port: 6379,
  username: 'app',
  password: process.env.REDIS_APP_PASSWORD,
  db: 0
});

// Store 实例
const storeClient = new Redis({
  host: 'redis-store',
  port: 6380,
  username: 'app',
  password: process.env.REDIS_APP_PASSWORD,
  db: 0
});

// 或使用 URI
const cacheClient = new Redis(`redis://app:${process.env.REDIS_APP_PASSWORD}@redis-cache:6379/0`);
```

#### Go (go-redis)

```go
import "github.com/go-redis/redis/v8"

// Cache 实例
cacheClient := redis.NewClient(&redis.Options{
    Addr:     "redis-cache:6379",
    Username: "app",
    Password: os.Getenv("REDIS_APP_PASSWORD"),
    DB:       0,
})

// Store 实例
storeClient := redis.NewClient(&redis.Options{
    Addr:     "redis-store:6380",
    Username: "app",
    Password: os.Getenv("REDIS_APP_PASSWORD"),
    DB:       0,
})
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

### 1. ACL 管理

**查看所有用户**:

```bash
docker exec redis-cache redis-cli --user admin --pass ${REDIS_ADMIN_PASSWORD} ACL LIST
```

**查看用户权限**:

```bash
docker exec redis-cache redis-cli --user admin --pass ${REDIS_ADMIN_PASSWORD} ACL GETUSER app
```

**运行时添加用户（临时）**:

```bash
docker exec redis-cache redis-cli --user admin --pass ${REDIS_ADMIN_PASSWORD} \
  ACL SETUSER newuser on >password ~* +@all
```

**保存 ACL 到文件**:

```bash
docker exec redis-cache redis-cli --user admin --pass ${REDIS_ADMIN_PASSWORD} ACL SAVE
```

**重新加载 ACL 文件**:

```bash
docker exec redis-cache redis-cli --user admin --pass ${REDIS_ADMIN_PASSWORD} ACL LOAD
```

**查看 ACL 日志（失败的认证）**:

```bash
docker exec redis-cache redis-cli --user admin --pass ${REDIS_ADMIN_PASSWORD} ACL LOG
```

### 2. 监控指标

**Cache 实例关注**:

- `evicted_keys`: 淘汰的键数量（正常现象）
- `keyspace_hits/misses`: 缓存命中率
- `used_memory`: 内存使用量（接近 512MB 时淘汰加速）

**Store 实例关注**:

- `aof_current_size`: AOF 文件大小（定期 BGREWRITEAOF）
- `used_memory`: 内存使用量（接近 192MB 需扩容或清理）
- `rejected_connections`: 拒绝连接数（noeviction 时会发生）

**监控命令**:

```bash
# 使用 monitor 用户查看状态
docker exec redis-cache redis-cli --user monitor --pass ${REDIS_MONITOR_PASSWORD} INFO
docker exec redis-cache redis-cli --user monitor --pass ${REDIS_MONITOR_PASSWORD} INFO memory
docker exec redis-cache redis-cli --user monitor --pass ${REDIS_MONITOR_PASSWORD} SLOWLOG GET 10
```

### 3. AOF 维护

Store 实例需要定期重写 AOF：

```bash
# 手动触发 AOF 重写（使用 admin 用户）
docker exec redis-store redis-cli --user admin --pass ${REDIS_ADMIN_PASSWORD} BGREWRITEAOF

# 查看 AOF 状态（使用 monitor 用户）
docker exec redis-store redis-cli --user monitor --pass ${REDIS_MONITOR_PASSWORD} INFO persistence
```

### 4. 内存告警

当 Store 实例内存接近上限时：

```bash
# 查看内存占用 TOP 100（使用 admin 用户）
docker exec redis-store redis-cli --user admin --pass ${REDIS_ADMIN_PASSWORD} --bigkeys

# 清理过期键（使用 app 用户）
docker exec redis-store redis-cli --user app --pass ${REDIS_APP_PASSWORD} \
  --scan --pattern "expired:*" | xargs redis-cli --user app --pass ${REDIS_APP_PASSWORD} DEL
```

### 5. 备份策略

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

# 连接测试（使用 app 用户）
docker exec -it redis-cache redis-cli --user app --pass ${REDIS_APP_PASSWORD}
docker exec -it redis-store redis-cli --user app --pass ${REDIS_APP_PASSWORD}

# 使用 admin 用户进行管理操作
docker exec -it redis-cache redis-cli --user admin --pass ${REDIS_ADMIN_PASSWORD}

# 停止服务
docker-compose down  # 注意：cache 数据会丢失，store 数据保留
```

## ACL 安全建议

1. ✅ **default 用户已禁用** - 强制使用具名用户，提高安全性
2. ✅ **使用强密码** - 建议至少 16 位，包含大小写字母、数字、特殊字符
3. ✅ **最小权限原则** - 根据应用需求分配最小必要权限
4. ⚠️ **定期轮换密码** - 建议每 3-6 个月更换一次
5. ⚠️ **监控访问日志** - 定期检查 `ACL LOG` 查看失败的认证尝试
6. ⚠️ **生产环境使用密码哈希**:

   ```bash
   # 生成密码哈希
   echo -n "your_password" | sha256sum
   
   # 在 users.acl 中使用 #<hash> 替代 >password
   user app on #5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8 ~* &* +@all
   ```

## ACL 故障排查

### 问题 1: 连接被拒绝

**症状**:

```text
Error: NOAUTH Authentication required
```

**解决**: 确保提供了正确的用户名和密码

```bash
# 错误方式（不再支持）
redis-cli -a password_only

# 正确方式
redis-cli --user app --pass your_password
```

### 问题 2: 权限不足

**症状**:

```text
Error: NOPERM this user has no permissions to run the 'flushall' command
```

**解决**: 当前用户没有执行该命令的权限，使用 `admin` 用户或修改 ACL 配置

### 问题 3: 密码错误

**症状**:

```text
Error: WRONGPASS invalid username-password pair
```

**解决**: 检查环境变量中的密码配置是否正确

### 问题 4: ACL 文件解析失败

**症状**:

```text
Aborting Redis startup because of ACL errors: /etc/redis/users.acl:1 should start with user keyword
```

**解决**: `users.acl` 文件不支持注释行，确保每行都是 `user` 命令或空行

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

### 从 requirepass 迁移到 ACL

如果您之前使用 `requirepass` 方式：

1. **ACL 配置已自动替换** `requirepass`
2. **环境变量变更**:
   - 旧: `REDIS_CACHE_PASSWORD`、`REDIS_STORE_PASSWORD`
   - 新: `REDIS_ADMIN_PASSWORD`、`REDIS_APP_PASSWORD` 等
3. **应用程序更新**: 需要在连接配置中添加 `username` 参数
4. **Healthcheck 更新**: 已更新为使用 `admin` 用户

**应用程序连接配置示例**:

```javascript
// 旧方式（不再支持）
const redis = new Redis({
  host: 'redis-cache',
  port: 6379,
  password: process.env.REDIS_CACHE_PASSWORD  // ❌
});

// 新方式（ACL）
const redis = new Redis({
  host: 'redis-cache',
  port: 6379,
  username: 'app',  // ✅ 添加用户名
  password: process.env.REDIS_APP_PASSWORD  // ✅ 使用新环境变量
});
```

### 从单实例迁移到双实例

**步骤 1**: 备份现有数据

```bash
docker exec redis redis-cli --user admin --pass ${REDIS_PASSWORD} --rdb /data/dump.rdb
```

**步骤 2**: 分析数据分类

```bash
# 导出所有键
docker exec redis redis-cli --user admin --pass ${REDIS_PASSWORD} KEYS "*" > all_keys.txt

# 手动分类：cache_keys.txt vs auth_keys.txt
```

**步骤 3**: 启动新实例并导入

```bash
# 启动双实例
docker-compose up -d redis-cache redis-store

# 导入 Cache 数据（可选，缓存可重建）
# 导入 Store 数据（必须）
cat auth_keys.txt | while read key; do
  docker exec redis redis-cli --user admin --pass ${OLD_PASSWORD} DUMP "$key" | \
  docker exec -i redis-store redis-cli --user admin --pass ${REDIS_ADMIN_PASSWORD} RESTORE "$key" 0
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
- ⚠️ 所有连接必须使用具名用户（default 已禁用）

## 参考文档

- [Redis ACL 官方文档](https://redis.io/docs/management/security/acl/)
- [Redis 7.0 新特性](https://redis.io/docs/about/releases/)
- [Redis 持久化配置](https://redis.io/docs/management/persistence/)
- [Redis 内存优化](https://redis.io/docs/management/optimization/memory-optimization/)
