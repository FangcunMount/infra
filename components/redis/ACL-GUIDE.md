# Redis ACL 用户配置说明

## 概述

本项目使用 Redis 7.x 的 ACL（Access Control List）功能来管理用户权限，替代了传统的 `requirepass` 方式。ACL 文件位于 `users.acl`，在容器启动时会自动加载。

## 配置文件

- **ACL 文件**: `users.acl` - 定义所有用户及其权限
- **配置引用**: 在 `redis-cache.conf` 和 `redis-store.conf` 中通过 `aclfile /etc/redis/users.acl` 引入

## 预定义用户

### 1. default（默认用户）

- **用户名**: `default`
- **密码**: 无密码
- **权限**: 完全权限
- **用途**: 向后兼容，**生产环境建议禁用或设置强密码**

### 2. admin（管理员用户）

- **用户名**: `admin`
- **密码**: 通过环境变量 `${REDIS_ADMIN_PASSWORD}` 设置（默认: change_me_admin_pass）
- **权限**: 完全权限（所有命令、所有键）
- **用途**: 运维管理、配置变更
- **连接示例**:

  ```bash
  redis-cli -h localhost -p 6379 --user admin --pass your_admin_password
  # 或使用 URI
  redis-cli -u redis://admin:your_admin_password@localhost:6379
  ```

### 3. app（应用用户）

- **用户名**: `app`
- **密码**: 通过环境变量 `${REDIS_APP_PASSWORD}` 设置（默认: change_me_app_pass）
- **权限**: 常规读写权限，排除危险命令（flushall, flushdb, keys, config, shutdown 等）
- **用途**: 应用程序日常使用
- **连接示例**:

  ```bash
  redis-cli -h localhost -p 6379 --user app --pass your_app_password
  ```

### 4. readonly（只读用户）

- **用户名**: `readonly`
- **密码**: 通过环境变量 `${REDIS_READONLY_PASSWORD}` 设置（默认: change_me_readonly_pass）
- **权限**: 仅读取权限 + 连接命令 + 状态查询
- **用途**: 数据查询、监控脚本
- **连接示例**:

  ```bash
  redis-cli -h localhost -p 6379 --user readonly --pass your_readonly_password
  ```

### 5. cache（缓存用户）

- **用户名**: `cache`
- **密码**: 通过环境变量 `${REDIS_CACHE_USER_PASSWORD}` 设置（默认: change_me_cache_pass）
- **权限**: 读写 + 过期管理（适合缓存场景）
- **用途**: 缓存服务、临时数据存储
- **连接示例**:

  ```bash
  redis-cli -h localhost -p 6379 --user cache --pass your_cache_password
  ```

### 6. monitor（监控用户）

- **用户名**: `monitor`
- **密码**: 通过环境变量 `${REDIS_MONITOR_PASSWORD}` 设置（默认: change_me_monitor_pass）
- **权限**: 仅查询状态信息（info, slowlog, client 等）
- **用途**: 监控系统、性能分析
- **连接示例**:

  ```bash
  redis-cli -h localhost -p 6379 --user monitor --pass your_monitor_password INFO
  ```

## 环境变量配置

在 `.env` 文件中设置密码（**生产环境必须修改**）：

```env
# Redis ACL 用户密码
REDIS_ADMIN_PASSWORD=your_strong_admin_password
REDIS_APP_PASSWORD=your_strong_app_password
REDIS_READONLY_PASSWORD=your_strong_readonly_password
REDIS_CACHE_USER_PASSWORD=your_strong_cache_password
REDIS_MONITOR_PASSWORD=your_strong_monitor_password
```

## 应用程序连接

### Python (redis-py)

```python
import redis

# 使用 admin 用户
r = redis.Redis(
    host='localhost',
    port=6379,
    username='admin',
    password='your_admin_password',
    decode_responses=True
)

# 或使用 URI
r = redis.from_url('redis://app:your_app_password@localhost:6379/0')
```

### Node.js (ioredis)

```javascript
const Redis = require('ioredis');

const redis = new Redis({
  host: 'localhost',
  port: 6379,
  username: 'app',
  password: 'your_app_password',
  db: 0
});

// 或使用 URI
const redis = new Redis('redis://app:your_app_password@localhost:6379/0');
```

### Go (go-redis)

```go
import "github.com/go-redis/redis/v8"

rdb := redis.NewClient(&redis.Options{
    Addr:     "localhost:6379",
    Username: "app",
    Password: "your_app_password",
    DB:       0,
})
```

## ACL 命令管理

### 查看所有用户

```bash
redis-cli --user admin --pass your_admin_password ACL LIST
```

### 查看当前用户

```bash
redis-cli --user app --pass your_app_password ACL WHOAMI
```

### 查看用户权限

```bash
redis-cli --user admin --pass your_admin_password ACL GETUSER app
```

### 运行时添加用户（临时，重启后失效）

```bash
redis-cli --user admin --pass your_admin_password ACL SETUSER newuser on >password ~* +@all
```

### 保存 ACL 到文件

```bash
redis-cli --user admin --pass your_admin_password ACL SAVE
```

### 重新加载 ACL 文件

```bash
redis-cli --user admin --pass your_admin_password ACL LOAD
```

## 修改 ACL 配置

1. **编辑 `users.acl` 文件**，修改用户权限或添加新用户
2. **重启容器**使配置生效：

   ```bash
   docker-compose restart redis-cache redis-store
   ```
   
   或者在不重启的情况下重新加载（需要 admin 权限）：

   ```bash
   redis-cli --user admin --pass your_admin_password ACL LOAD
   ```

## ACL 规则语法

### 基本规则

- `on` - 启用用户
- `off` - 禁用用户
- `>password` - 添加密码（明文）
- `#<hash>` - 添加密码（SHA256 哈希）
- `nopass` - 无需密码

### 键权限

- `~*` - 访问所有键
- `~prefix:*` - 只能访问特定前缀的键
- `%R~*` - 只读所有键
- `%W~prefix:*` - 写特定前缀的键

### 命令权限

- `+@all` - 允许所有命令
- `+@read` - 允许所有读命令
- `+@write` - 允许所有写命令
- `+@dangerous` - 允许危险命令（flushall, keys 等）
- `-@dangerous` - 禁止危险命令
- `+command` - 允许特定命令
- `-command` - 禁止特定命令

### 完整示例

```acl
# 自定义用户：只能访问 session: 开头的键，只有读写权限
user sessionuser on >sessionpass ~session:* +@read +@write +del +expire
```

## 安全建议

1. **禁用默认用户**或设置强密码
2. **使用强密码**，建议至少 16 位，包含大小写字母、数字、特殊字符
3. **最小权限原则**，根据应用需求分配最小权限
4. **定期轮换密码**
5. **使用密码哈希**（生产环境）：

   ```bash
   echo -n "your_password" | sha256sum
   # 在 users.acl 中使用 #<hash> 而不是 >password
   ```

6. **监控 ACL 使用**：

   ```bash
   redis-cli --user admin --pass your_admin_password ACL LOG
   ```

## 迁移说明

如果您之前使用 `requirepass` 方式：

1. ACL 配置已自动替换 `requirepass`
2. 旧的 `REDIS_CACHE_PASSWORD` 和 `REDIS_STORE_PASSWORD` 环境变量不再使用
3. 需要更新应用程序连接配置，添加 `username` 参数
4. Healthcheck 已更新为使用 `admin` 用户

## 故障排查

### 连接被拒绝

```text
Error: NOAUTH Authentication required
```

→ 检查是否提供了用户名和密码

### 权限不足

```text
Error: NOPERM this user has no permissions to run the 'flushall' command
```

→ 当前用户没有执行该命令的权限，使用具有相应权限的用户

### 密码错误

```text
Error: WRONGPASS invalid username-password pair
```

→ 检查用户名或密码是否正确

### 查看日志

```bash
docker logs redis-cache
docker logs redis-store
```

## 参考文档

- [Redis ACL 官方文档](https://redis.io/docs/management/security/acl/)
- [Redis 7.0 新特性](https://redis.io/docs/about/releases/)
