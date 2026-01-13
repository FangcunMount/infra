# Redis 单实例部署

Redis 现采用**单实例**模式，统一承载缓存、会话、分布式锁等状态型数据，开启 AOF+周期性 RDB 以保证可恢复性。

## 实例配置

- 端口：`6379`
- 持久化：AOF `everysec` + RDB（900/300/60 秒）
- 淘汰策略：默认 `volatile-lru`（仅淘汰带过期时间的键）
- 资源：CPU `0.15` 核；内存 `256MB`（可通过环境变量调整）
- 配置文件：`components/redis/redis-cache.conf`
- 数据卷：`infra_redis_cache_data`
- 容器名：`redis-cache`

## 环境变量

`compose/env/*` 示例（生产）：

```env
REDIS_CACHE_PORT=6379
REDIS_CACHE_MAXMEMORY=256mb
REDIS_CACHE_POLICY=volatile-lru
REDIS_CACHE_MEM_LIMIT=256M
REDIS_CACHE_CPUS=0.15

# ACL 用户密码（必须修改为强密码）
REDIS_ADMIN_PASSWORD=...
REDIS_APP_PASSWORD=...
REDIS_READONLY_PASSWORD=...
REDIS_CACHE_USER_PASSWORD=...
REDIS_MONITOR_PASSWORD=...
```

## ACL 用户

| 用户 | 权限 | 用途 | 变量 |
|------|------|------|------|
| `admin` | 完全权限 | 运维管理 | `REDIS_ADMIN_PASSWORD` |
| `app` | 常规读写，屏蔽危险命令 | 应用访问 | `REDIS_APP_PASSWORD` |
| `readonly` | 只读 | 查询/排障 | `REDIS_READONLY_PASSWORD` |
| `cache` | 读写+过期管理 | 缓存场景 | `REDIS_CACHE_USER_PASSWORD` |
| `monitor` | 状态查询 | 监控/巡检 | `REDIS_MONITOR_PASSWORD` |

生成 ACL：

```bash
cd components/redis
ENV=prod ./generate-acl.sh   # 或传入 env 文件路径
```

## 连接示例

Python（redis-py）：

```python
import os, redis

r = redis.Redis(
    host="redis-cache",
    port=6379,
    username="app",
    password=os.getenv("REDIS_APP_PASSWORD"),
    db=0,
    decode_responses=True,
)
r.ping()
```

Node.js（ioredis）：

```javascript
const Redis = require("ioredis");
const client = new Redis({
  host: "redis-cache",
  port: 6379,
  username: "app",
  password: process.env.REDIS_APP_PASSWORD,
});
await client.ping();
```

Go（go-redis）：

```go
client := redis.NewClient(&redis.Options{
    Addr:     "redis-cache:6379",
    Username: "app",
    Password: os.Getenv("REDIS_APP_PASSWORD"),
    DB:       0,
})
_, _ = client.Ping(ctx).Result()
```

## 运维常用命令

```bash
# 启停
make redis-start        # docker compose up -d redis-cache
make redis-stop
make redis-restart

# 交互/查看
make redis-cli          # 无用户名/密码时会被拒绝
docker exec -it redis-cache redis-cli --user admin --pass "$REDIS_ADMIN_PASSWORD"
make redis-logs

# ACL
docker exec redis-cache redis-cli --user admin --pass "$REDIS_ADMIN_PASSWORD" ACL LIST
make redis-acl-regenerate

# 测试
make redis-test
```

## 迁移说明

- 旧的 `redis-store` 实例已移除，所有会话/状态类数据统一存放在当前单实例中。
- 原有 `REDIS_STORE_*` 配置可删除；应用直接指向 `redis-cache:6379`。
- 如需分离持久化/缓存，可在未来再拆分，但默认推荐单实例降低复杂度。 
