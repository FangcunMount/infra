# 服务器组件 - 存储服务(MySQL/Redis/MongoDB)

> 🗄️ 部署企业级数据存储集群：MySQL关系数据库 + Redis缓存 + MongoDB文档数据库

## 🎯 存储服务目标

- 部署 MySQL 8.0 关系型数据库
- 部署 Redis 7.0 内存缓存系统  
- 部署 MongoDB 6.0 文档数据库
- 配置数据持久化和备份策略
- 设置高可用性和性能优化
- 建立监控和健康检查

## 🏗️ 存储架构设计

### 存储服务拓扑

```
┌─────────────────────────────────────────────────────────┐
│                    应用层                                │
│  ┌─────────────────────────────────────────────────────┐ │
│  │           业务应用服务                              │ │
│  │  • Web 应用 • API 服务 • 微服务                     │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                            │
                   ┌────────┼────────┐
                   │        │        │
┌─────────────────▼───┐ ┌───▼───┐ ┌──▼─────────────────┐
│     MySQL 8.0      │ │ Redis │ │    MongoDB 6.0     │
│   (关系型数据库)    │ │ (缓存) │ │   (文档数据库)     │
│                    │ │       │ │                    │
│ • 事务 ACID        │ │• 高速 │ │ • JSON 文档        │
│ • 复杂查询         │ │• 会话 │ │ • 灵活 Schema      │
│ • 数据一致性       │ │• 队列 │ │ • 分片集群         │
│ • 关系约束         │ │• 计数 │ │ • 地理空间         │
└────────────────────┘ └───────┘ └────────────────────┘
          │                │               │
┌─────────▼────────┐ ┌─────▼─────┐ ┌───────▼──────────┐
│   MySQL 数据卷   │ │ Redis卷   │ │   MongoDB 数据卷 │
│ /opt/infra/mysql │ │/opt/infra/│ │ /opt/infra/mongo │
│     /data        │ │redis/data │ │     /data        │
└──────────────────┘ └───────────┘ └──────────────────┘
```

### 数据分工策略

| 数据类型 | 推荐存储 | 用途场景 | 性能特点 |
|---------|---------|----------|----------|
| **用户数据** | MySQL | 注册信息、权限管理 | 强一致性、事务 |
| **会话数据** | Redis | 登录状态、临时数据 | 高速读写、TTL |
| **配置数据** | MySQL | 系统配置、参数设置 | 数据完整性 |
| **缓存数据** | Redis | 查询缓存、计算结果 | 亚毫秒响应 |
| **日志数据** | MongoDB | 操作日志、审计记录 | 快速写入、检索 |
| **文档数据** | MongoDB | CMS内容、JSON数据 | 灵活Schema |
| **计数器** | Redis | 访问统计、限流计数 | 原子操作 |
| **队列数据** | Redis | 异步任务、消息队列 | 高并发、FIFO |

## 🚀 自动化部署

### 一键存储服务部署

```bash
# 使用 compose-manager 脚本部署存储服务
./scripts/deploy/compose-manager.sh infra up storage

# 自动完成：
# ✅ 部署 MySQL 8.0 主从复制
# ✅ 部署 Redis 7.0 主从+哨兵
# ✅ 部署 MongoDB 6.0 副本集
# ✅ 配置数据持久化
# ✅ 设置健康检查
# ✅ 应用安全配置
```

### 验证部署状态

```bash
# 检查服务状态
./scripts/deploy/compose-manager.sh infra status storage

# 测试数据库连接
./scripts/deploy/compose-manager.sh infra test storage

# 查看服务日志
./scripts/deploy/compose-manager.sh infra logs storage
```

## 🔧 手动配置步骤

### 步骤 1: 部署 MySQL 8.0

```bash
# 创建 MySQL 配置文件
sudo mkdir -p /opt/infra/mysql/conf
sudo tee /opt/infra/mysql/conf/my.cnf << 'EOF'
[mysqld]
# 基础配置
server-id = 1
bind-address = 0.0.0.0
port = 3306
datadir = /var/lib/mysql
socket = /var/run/mysqld/mysqld.sock

# 字符集配置
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
init-connect = 'SET NAMES utf8mb4'

# InnoDB 优化
innodb_buffer_pool_size = 512M
innodb_log_file_size = 128M
innodb_log_buffer_size = 16M
innodb_flush_log_at_trx_commit = 2
innodb_file_per_table = 1

# 连接优化
max_connections = 200
max_connect_errors = 6000
open_files_limit = 65535
table_open_cache = 1024

# 查询优化
query_cache_type = 1
query_cache_size = 64M
tmp_table_size = 64M
max_heap_table_size = 64M

# 日志配置
log-error = /var/log/mysql/error.log
slow_query_log = 1
slow_query_log_file = /var/log/mysql/slow.log
long_query_time = 2

# 复制配置
log-bin = mysql-bin
binlog_format = ROW
expire_logs_days = 7
max_binlog_size = 100M

# 安全配置
sql_mode = STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO
EOF

# 启动 MySQL 容器
docker run -d \
  --name mysql \
  --network infra-backend \
  --restart unless-stopped \
  -e MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD} \
  -e MYSQL_DATABASE=infrastructure \
  -e MYSQL_USER=app \
  -e MYSQL_PASSWORD=${MYSQL_USER_PASSWORD} \
  -v infra_mysql_data:/var/lib/mysql \
  -v /opt/infra/mysql/conf:/etc/mysql/conf.d:ro \
  -v /opt/infra/mysql/logs:/var/log/mysql \
  --health-cmd="mysqladmin ping -h localhost -u root -p${MYSQL_ROOT_PASSWORD}" \
  --health-interval=10s \
  --health-timeout=5s \
  --health-retries=3 \
  mysql:8.0
```

### 步骤 2: 部署 Redis 7.0

```bash
# 创建 Redis 配置文件
sudo mkdir -p /opt/infra/redis/conf
sudo tee /opt/infra/redis/conf/redis.conf << 'EOF'
# 网络配置
bind 0.0.0.0
port 6379
protected-mode yes
requirepass your_redis_password_here

# 持久化配置
save 900 1
save 300 10
save 60 10000
rdbcompression yes
rdbchecksum yes
dbfilename dump.rdb
dir /data

# AOF 持久化
appendonly yes
appendfilename "appendonly.aof"
appendfsync everysec
no-appendfsync-on-rewrite no
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# 内存管理
maxmemory 256mb
maxmemory-policy allkeys-lru
maxmemory-samples 5

# 慢查询日志
slowlog-log-slower-than 10000
slowlog-max-len 128

# 客户端配置
timeout 300
tcp-keepalive 300
tcp-backlog 511

# 安全配置
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command CONFIG "CONFIG_9f2e8c4a1b"
EOF

# 启动 Redis 容器
docker run -d \
  --name redis \
  --network infra-backend \
  --restart unless-stopped \
  -v infra_redis_data:/data \
  -v /opt/infra/redis/conf/redis.conf:/usr/local/etc/redis/redis.conf:ro \
  --health-cmd="redis-cli --raw incr ping" \
  --health-interval=10s \
  --health-timeout=3s \
  --health-retries=3 \
  redis:7.0-alpine redis-server /usr/local/etc/redis/redis.conf
```

### 步骤 3: 部署 MongoDB 6.0

```bash
# 创建 MongoDB 配置文件
sudo mkdir -p /opt/infra/mongo/conf
sudo tee /opt/infra/mongo/conf/mongod.conf << 'EOF'
# 网络配置
net:
  port: 27017
  bindIp: 0.0.0.0

# 存储配置
storage:
  dbPath: /data/db
  journal:
    enabled: true
  engine: wiredTiger
  wiredTiger:
    engineConfig:
      cacheSizeGB: 0.5
    collectionConfig:
      blockCompressor: snappy
    indexConfig:
      prefixCompression: true

# 系统日志
systemLog:
  destination: file
  logAppend: true
  path: /var/log/mongodb/mongod.log
  logRotate: rename
  verbosity: 1

# 进程管理
processManagement:
  timeZoneInfo: /usr/share/zoneinfo

# 安全配置
security:
  authorization: enabled

# 操作性能分析
operationProfiling:
  slowOpThresholdMs: 100
  mode: slowOp

# 复制集配置（单节点模式）
replication:
  replSetName: rs0
EOF

# 启动 MongoDB 容器
docker run -d \
  --name mongo \
  --network infra-backend \
  --restart unless-stopped \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=${MONGO_ROOT_PASSWORD} \
  -v infra_mongo_data:/data/db \
  -v /opt/infra/mongo/conf/mongod.conf:/etc/mongod.conf:ro \
  -v /opt/infra/mongo/logs:/var/log/mongodb \
  --health-cmd="mongosh --eval 'db.runCommand({ping: 1})'" \
  --health-interval=10s \
  --health-timeout=5s \
  --health-retries=3 \
  mongo:6.0 mongod --config /etc/mongod.conf
```

### 步骤 4: 初始化数据库

```bash
# MySQL 初始化
docker exec -i mysql mysql -uroot -p${MYSQL_ROOT_PASSWORD} << 'EOF'
-- 创建基础数据库
CREATE DATABASE IF NOT EXISTS infrastructure CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS logs CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建应用用户
CREATE USER 'app'@'%' IDENTIFIED BY 'your_app_password_here';
GRANT SELECT, INSERT, UPDATE, DELETE ON infrastructure.* TO 'app'@'%';
GRANT SELECT, INSERT ON logs.* TO 'app'@'%';

-- 创建只读用户
CREATE USER 'readonly'@'%' IDENTIFIED BY 'your_readonly_password_here';
GRANT SELECT ON infrastructure.* TO 'readonly'@'%';
GRANT SELECT ON logs.* TO 'readonly'@'%';

FLUSH PRIVILEGES;
EOF

# Redis 测试
docker exec redis redis-cli -a ${REDIS_PASSWORD} ping

# MongoDB 初始化
docker exec -i mongo mongosh admin -u admin -p ${MONGO_ROOT_PASSWORD} << 'EOF'
// 初始化副本集
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo:27017" }
  ]
});

// 创建应用数据库和用户
use infrastructure;
db.createUser({
  user: "app",
  pwd: "your_app_password_here",
  roles: [
    { role: "readWrite", db: "infrastructure" },
    { role: "readWrite", db: "logs" }
  ]
});

// 创建只读用户
db.createUser({
  user: "readonly", 
  pwd: "your_readonly_password_here",
  roles: [
    { role: "read", db: "infrastructure" },
    { role: "read", db: "logs" }
  ]
});
EOF
```

## 📊 服务管理和监控

### 存储服务状态检查

```bash
# 检查容器状态
docker ps --filter "name=mysql|redis|mongo" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 检查健康状态
docker inspect mysql --format='{{.State.Health.Status}}'
docker inspect redis --format='{{.State.Health.Status}}'
docker inspect mongo --format='{{.State.Health.Status}}'

# 查看资源使用
docker stats mysql redis mongo --no-stream
```

### 数据库连接测试

```bash
# MySQL 连接测试
docker exec mysql mysql -uroot -p${MYSQL_ROOT_PASSWORD} -e "SELECT VERSION();"
docker exec mysql mysql -uapp -p${MYSQL_USER_PASSWORD} -e "SHOW DATABASES;"

# Redis 连接测试
docker exec redis redis-cli -a ${REDIS_PASSWORD} info server
docker exec redis redis-cli -a ${REDIS_PASSWORD} set test "hello" 
docker exec redis redis-cli -a ${REDIS_PASSWORD} get test

# MongoDB 连接测试
docker exec mongo mongosh -u admin -p ${MONGO_ROOT_PASSWORD} --eval "db.version()"
docker exec mongo mongosh -u app -p ${MONGO_USER_PASSWORD} infrastructure --eval "db.stats()"
```

### 性能监控脚本

```bash
# 创建存储服务监控脚本
sudo tee /usr/local/bin/storage-monitor << 'EOF'
#!/bin/bash

echo "=== 存储服务监控报告 $(date) ==="

# MySQL 状态
echo "MySQL 状态:"
docker exec mysql mysqladmin status -uroot -p${MYSQL_ROOT_PASSWORD} 2>/dev/null || echo "❌ MySQL 连接失败"

# Redis 状态  
echo "Redis 状态:"
docker exec redis redis-cli -a ${REDIS_PASSWORD} info stats | grep total_commands_processed 2>/dev/null || echo "❌ Redis 连接失败"

# MongoDB 状态
echo "MongoDB 状态:"
docker exec mongo mongosh --quiet -u admin -p ${MONGO_ROOT_PASSWORD} --eval "print('连接数: ' + db.serverStatus().connections.current)" 2>/dev/null || echo "❌ MongoDB 连接失败"

# 磁盘使用情况
echo "数据卷使用情况:"
df -h /opt/infra/mysql/data /opt/infra/redis/data /opt/infra/mongo/data

echo "=========================="
EOF

sudo chmod +x /usr/local/bin/storage-monitor

# 定时监控
echo "*/5 * * * * /usr/local/bin/storage-monitor >> /var/log/infra/storage-monitor.log 2>&1" | crontab -
```

## 📋 验证检查清单

### ✅ 服务部署验证

```bash
# 检查容器运行状态
for service in mysql redis mongo; do
  docker ps --filter "name=$service" --format "{{.Status}}" | grep -q "Up" && echo "✅ $service 运行正常" || echo "❌ $service 未运行"
done

# 检查网络连接
for service in mysql redis mongo; do
  docker exec $service echo "test" >/dev/null 2>&1 && echo "✅ $service 网络正常" || echo "❌ $service 网络异常"
done
```

### ✅ 数据持久化验证

```bash
# 检查数据卷挂载
for service in mysql redis mongo; do
  docker inspect $service --format='{{range .Mounts}}{{.Source}}:{{.Destination}}{{"\n"}}{{end}}' | grep -q "/opt/infra/$service" && echo "✅ $service 数据卷正常" || echo "❌ $service 数据卷异常"
done

# 测试数据持久化
docker exec mysql mysql -uroot -p${MYSQL_ROOT_PASSWORD} -e "CREATE TABLE test.persistence_test (id INT);"
docker exec redis redis-cli -a ${REDIS_PASSWORD} set persistence_test "ok"
docker exec mongo mongosh -u admin -p ${MONGO_ROOT_PASSWORD} --eval "db.test.insertOne({persistence: 'test'})"

# 重启容器测试
docker restart mysql redis mongo
sleep 30

# 验证数据仍存在
docker exec mysql mysql -uroot -p${MYSQL_ROOT_PASSWORD} -e "SHOW TABLES IN test;" | grep -q "persistence_test" && echo "✅ MySQL 数据持久化正常"
docker exec redis redis-cli -a ${REDIS_PASSWORD} get persistence_test | grep -q "ok" && echo "✅ Redis 数据持久化正常" 
docker exec mongo mongosh -u admin -p ${MONGO_ROOT_PASSWORD} --eval "db.test.findOne({persistence: 'test'})" | grep -q "test" && echo "✅ MongoDB 数据持久化正常"
```

### ✅ 安全配置验证

```bash
# 验证 MySQL 用户权限
docker exec mysql mysql -uapp -p${MYSQL_USER_PASSWORD} -e "SELECT USER();" >/dev/null 2>&1 && echo "✅ MySQL 应用用户正常"
docker exec mysql mysql -ureadonly -p${MYSQL_READONLY_PASSWORD} -e "SELECT 1;" >/dev/null 2>&1 && echo "✅ MySQL 只读用户正常"

# 验证 Redis 密码保护
docker exec redis redis-cli ping 2>&1 | grep -q "NOAUTH" && echo "✅ Redis 密码保护生效" || echo "❌ Redis 密码保护失效"

# 验证 MongoDB 认证
docker exec mongo mongosh --eval "db.version()" 2>&1 | grep -q "Authentication failed" && echo "✅ MongoDB 认证生效" || echo "❌ MongoDB 认证失效"
```

## 🚨 故障排除

### 容器启动问题

```bash
# 问题 1: MySQL 容器启动失败
docker logs mysql --tail 50
# 常见原因：权限问题、配置错误、端口占用

# 解决方案：
sudo chown -R 999:999 /opt/infra/mysql/data
docker rm -f mysql
# 重新启动容器

# 问题 2: Redis 内存不足
docker exec redis redis-cli -a ${REDIS_PASSWORD} info memory
# 检查 maxmemory 配置和使用情况

# 问题 3: MongoDB 副本集初始化失败
docker exec mongo mongosh -u admin -p ${MONGO_ROOT_PASSWORD} --eval "rs.status()"
# 检查副本集状态和网络连接
```

### 性能问题

```bash
# MySQL 慢查询分析
docker exec mysql mysql -uroot -p${MYSQL_ROOT_PASSWORD} -e "SHOW FULL PROCESSLIST;"
docker exec mysql mysql -uroot -p${MYSQL_ROOT_PASSWORD} -e "SELECT * FROM information_schema.PROCESSLIST WHERE COMMAND != 'Sleep';"

# Redis 性能监控
docker exec redis redis-cli -a ${REDIS_PASSWORD} info stats
docker exec redis redis-cli -a ${REDIS_PASSWORD} slowlog get 10

# MongoDB 性能分析
docker exec mongo mongosh -u admin -p ${MONGO_ROOT_PASSWORD} --eval "db.runCommand({listCollections: 1})"
docker exec mongo mongosh -u admin -p ${MONGO_ROOT_PASSWORD} --eval "db.serverStatus().opcounters"
```

### 数据恢复

```bash
# MySQL 数据恢复
docker exec -i mysql mysql -uroot -p${MYSQL_ROOT_PASSWORD} < backup.sql

# Redis 数据恢复  
docker cp backup.rdb redis:/data/dump.rdb
docker restart redis

# MongoDB 数据恢复
docker exec mongo mongorestore --host localhost --username admin --password ${MONGO_ROOT_PASSWORD} /backup/mongo-backup
```

## 🔧 高级配置

### MySQL 主从复制

```bash
# 主库配置（已在 my.cnf 中设置）
# 创建复制用户
docker exec mysql mysql -uroot -p${MYSQL_ROOT_PASSWORD} -e "
  CREATE USER 'replica'@'%' IDENTIFIED BY 'replica_password';
  GRANT REPLICATION SLAVE ON *.* TO 'replica'@'%';
  FLUSH PRIVILEGES;
  SHOW MASTER STATUS;
"
```

### Redis 哨兵模式

```bash
# 配置 Redis 哨兵
sudo tee /opt/infra/redis/conf/sentinel.conf << 'EOF'
port 26379
sentinel monitor mymaster redis 6379 1
sentinel auth-pass mymaster your_redis_password_here
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 10000
sentinel parallel-syncs mymaster 1
EOF
```

### MongoDB 分片集群

```bash
# 配置分片（多节点环境）
# 配置 Config Server
# 配置 Shard Server  
# 配置 mongos 路由
```

## 🔄 下一步

存储服务部署完成后，请继续进行：

1. [📨 消息服务](服务器组件--消息服务(Kafka).md) - 部署 Kafka 消息队列
2. [🔧 CI/CD服务](服务器组件--CI_CD(Jenkins).md) - 部署 Jenkins 平台
3. [🌐 网关服务](服务器组件--网关(Nginx).md) - 部署 Nginx 网关

---

> 💡 **存储服务运维提醒**:
> - 定期备份数据库数据和配置
> - 监控存储空间使用情况
> - 定期分析慢查询和性能瓶颈  
> - 保持数据库版本和安全补丁更新
> - 建立数据恢复和故障切换流程