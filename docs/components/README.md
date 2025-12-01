# 组件总览

本文档提供所有基础设施组件的快速参考。

## 部署架构

```text
ServerA (121.43.138.102)          ServerB (112.126.82.123)
┌─────────────────────────┐       ┌──────────────────────────┐
│  Web & 存储服务          │       │  消息队列服务             │
│                         │       │                          │
│  • Nginx :80 :443      │       │  • NSQ :4150-4171        │
│  • MySQL :3306         │       │                          │
│  • Redis :6379         │       │                          │
│  • MongoDB :27017      │       │                          │
└─────────────────────────┘       └──────────────────────────┘
         │                                   │
         └──── infra-network (Overlay) ─────┘
```

## 存储服务 (ServerA)

### MySQL

**作用**: 关系型数据库

**版本**: 8.0  
**端口**: 3306  
**资源**: CPU 1.0核 / 内存 1.5GB

**快速命令**:

```bash
make mysql-start          # 启动MySQL
make mysql-stop           # 停止MySQL
make mysql-shell          # 进入MySQL Shell
make mysql-logs           # 查看日志
```

**配置文件**: `components/mysql/my.cnf`

**数据目录**: `infra_mysql_data` volume

### Redis

**作用**: 缓存和会话存储

**版本**: 7.2-alpine  
**端口**: 6379  
**资源**: CPU 0.5核 / 内存 512MB

**快速命令**:

```bash
make redis-start          # 启动Redis
make redis-stop           # 停止Redis
make redis-cli            # 进入Redis CLI
make redis-auth-cli       # 带认证的CLI
make redis-logs           # 查看日志
```

**配置文件**:

- `components/redis/redis-cache.conf` (缓存)
- `components/redis/redis-auth.conf` (带认证)

**数据目录**: `infra_redis_data` volume

### MongoDB

**作用**: 文档数据库

**版本**: 6.0  
**端口**: 27017  
**资源**: CPU 1.0核 / 内存 1GB

**快速命令**:

```bash
make mongo-start          # 启动MongoDB
make mongo-stop           # 停止MongoDB
make mongo-shell          # 进入Mongo Shell
make mongo-logs           # 查看日志
```

**配置文件**: `components/mongo/mongod.conf`

**数据目录**: `infra_mongo_data` volume

**详细文档**: [快速入门](./mongodb-quickstart.md)

## Web服务 (ServerA)

### Nginx

**作用**: Web服务器和反向代理

**版本**: alpine  
**端口**: 80 (HTTP), 443 (HTTPS)  
**资源**: CPU 0.5核 / 内存 256MB

**快速命令**:

```bash
make nginx-start          # 启动Nginx
make nginx-stop           # 停止Nginx
make nginx-reload         # 重载配置
make nginx-test           # 测试配置
make nginx-logs           # 查看日志
```

**配置文件**:

- `components/nginx/nginx.conf` (主配置)
- `components/nginx/conf.d/` (站点配置)

## 消息队列 (ServerB)

### NSQ

**作用**: 轻量级实时消息队列

**版本**: v1.3.0  
**端口**: 4150-4151 (nsqd), 4160-4161 (nsqlookupd), 4171 (nsqadmin)  
**资源**: CPU 0.80核 / 内存 512MB (nsqd)

**组件**:

- **nsqd**: 消息存储和传递
- **nsqlookupd**: 服务发现
- **nsqadmin**: Web管理界面

**快速命令**:

```bash
make nsq-start            # 启动NSQ
make nsq-stop             # 停止NSQ
make nsq-admin            # 打开管理界面 (SSH隧道)
make nsq-shell            # 进入nsqd容器
make nsq-topics           # 查看主题列表
make nsq-stats            # 查看统计信息
make nsq-logs             # 查看日志
```

**配置文件**:

- `components/nsq/nsqd.conf`
- `components/nsq/nsqlookupd.conf`
- `components/nsq/nsqadmin.conf`

**数据目录**: `infra_nsq_data` volume

**详细文档**: [NSQ配置](./nsq.md)

## 组件状态检查

### 健康检查

```bash
# 检查所有服务状态
make status

# 检查特定服务
docker ps | grep <service_name>

# 查看资源使用
make stats
docker stats
```

### 健康检查端点

```bash
# MySQL
mysql -h 127.0.0.1 -u root -p -e "SELECT 1"

# Redis
redis-cli ping

# MongoDB
mongosh --eval "db.adminCommand('ping')"

# NSQ
curl http://112.126.82.123:4151/ping
curl http://112.126.82.123:4161/ping

# Nginx
curl http://localhost
```

## 数据持久化

所有服务的数据都通过Docker Volume持久化:

```bash
# 查看所有卷
docker volume ls | grep infra

# 检查卷详情
docker volume inspect infra_mysql_data
docker volume inspect infra_redis_data
docker volume inspect infra_mongo_data
docker volume inspect infra_nsq_data
```

## 备份和恢复

### 数据库备份

```bash
# 备份所有数据库
make backup

# 备份MySQL
make mysql-backup

# 备份MongoDB
make mongo-backup

# 备份Redis
make redis-backup
```

### 配置备份

```bash
# 备份所有配置
tar -czf config-backup-$(date +%Y%m%d).tar.gz \
  compose/ components/ Makefile

# 恢复配置
tar -xzf config-backup-YYYYMMDD.tar.gz
```

## 日志管理

### 查看日志

```bash
# 查看所有服务日志
make logs

# 查看特定服务日志
make mysql-logs
make redis-logs
make mongo-logs
make nginx-logs
make nsq-logs

# 实时跟踪日志
docker logs -f <container_name>

# 查看最近N行
docker logs --tail=100 <container_name>
```

### 日志位置

```yaml
MySQL: /var/log/mysql/
Redis: stdout (Docker logs)
MongoDB: /var/log/mongodb/
Nginx: /var/log/nginx/
NSQ: stdout (Docker logs)
```

## 监控

### 资源监控

```bash
# 查看所有容器资源使用
docker stats

# 查看特定容器
docker stats <container_name>

# 系统资源
top
htop
free -h
df -h
```

### 关键指标

| 组件 | CPU | 内存 | 磁盘 | 网络 |
|------|-----|------|------|------|
| MySQL | < 80% | < 1.2GB | 监控增长 | 连接数 |
| Redis | < 50% | < 400MB | N/A | QPS |
| MongoDB | < 80% | < 800MB | 监控增长 | 连接数 |
| Nginx | < 50% | < 200MB | 日志大小 | 请求数 |
| NSQ | < 80% | < 450MB | 监控增长 | 消息深度 |

## 安全配置

### 数据库认证

```bash
# MySQL
MYSQL_ROOT_PASSWORD=<strong_password>

# MongoDB
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=<strong_password>

# Redis
# 编辑 redis-auth.conf
requirepass <strong_password>
```

### 网络安全

```bash
# 只监听内网 (已配置)
MySQL: bind-address = 127.0.0.1
Redis: bind 127.0.0.1
MongoDB: bindIp: 127.0.0.1

# NSQ仅内网访问
nsqadmin: 127.0.0.1:4171
```

### 防火墙

```bash
# ServerA
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow from <trusted_ip> to any port 3306
sudo ufw allow from <trusted_ip> to any port 6379
sudo ufw allow from <trusted_ip> to any port 27017

# ServerB
# NSQ不对外开放端口,只通过Overlay网络访问
```

## 升级和维护

### 停机维护

```bash
# 1. 停止所有服务
make down

# 2. 备份数据
make backup

# 3. 升级组件
docker compose pull

# 4. 启动服务
make up

# 5. 验证
make status
```

### 滚动更新

```bash
# 逐个服务更新,减少停机时间
make nginx-restart
make redis-restart
make mysql-restart
make mongo-restart
make nsq-restart
```

## 故障处理

### 快速诊断

```bash
# 1. 检查服务状态
make status

# 2. 查看日志
make logs

# 3. 检查资源
docker stats

# 4. 检查网络
make network-status

# 5. 检查磁盘
df -h
```

### 常见问题

| 问题 | 症状 | 解决方案 |
|------|------|----------|
| 服务无法启动 | 容器不断重启 | 查看日志,检查配置 |
| 无法连接 | 连接超时/拒绝 | 检查防火墙,网络配置 |
| 性能下降 | 响应慢 | 检查资源使用,优化配置 |
| 磁盘满 | 空间不足 | 清理日志,扩展磁盘 |
| 内存不足 | OOM错误 | 增加内存限制,优化应用 |

## 性能优化

### MySQL优化

```ini
# my.cnf
innodb_buffer_pool_size = 1G
max_connections = 200
query_cache_size = 64M
```

### Redis优化

```conf
# redis.conf
maxmemory 512mb
maxmemory-policy allkeys-lru
save 900 1
```

### MongoDB优化

```yaml
# mongod.conf
storage:
  wiredTiger:
    engineConfig:
      cacheSizeGB: 0.5
```

### NSQ优化

```conf
# nsqd.conf
mem-queue-size = 3000
max-msg-size = 262144
msg-timeout = "60s"
```

## 相关文档

### 组件详细文档

- [MongoDB快速入门](./mongodb-quickstart.md)
- [NSQ配置](./nsq.md)

### 架构和网络

- [服务器架构](../server/architecture.md)
- [网络架构](../network/architecture.md)
- [网络管理](../network/management.md)

---

**更新时间**: 2025-12-01  
**文档版本**: v2.0
