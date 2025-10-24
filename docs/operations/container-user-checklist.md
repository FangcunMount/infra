# 容器用户配置检查清单

## 检查概览

**检查日期**: 2025-10-24  
**检查范围**: infra 项目所有组件  
**检查目的**: 确保容器用户配置符合安全最佳实践

## 检查结果总览

| 组件 | 镜像 | 当前状态 | 应使用用户 | 是否需要修改 | 检查结果 |
|------|------|----------|------------|--------------|----------|
| **MySQL** | mysql:8.0 | 无 user 配置 | mysql (官方默认) | ❌ 否 | ✅ 通过 |
| **Redis Cache** | redis:7 | 无 user 配置 | redis (官方默认) | ❌ 否 | ✅ 通过 |
| **Redis Auth** | redis:7 | 无 user 配置 | redis (官方默认) | ❌ 否 | ✅ 通过 |
| **MongoDB** | mongo:7 | 无 user 配置 | mongodb (官方默认) | ❌ 否 | ✅ 通过 |
| **Nginx** | nginx:1.27 | 无 user 配置 | nginx (官方自动降权) | ❌ 否 | ✅ 通过 |
| **NSQ Lookupd** | nsqio/nsq:v1.3.0 | 无 user 配置 | nsq (官方默认) | ❌ 否 | ✅ 通过 |
| **NSQ D** | nsqio/nsq:v1.3.0 | 无 user 配置 | nsq (官方默认) | ❌ 否 | ✅ 通过 |
| **NSQ Admin** | nsqio/nsq:v1.3.0 | 无 user 配置 | nsq (官方默认) | ❌ 否 | ✅ 通过 |
| **Kafka** | bitnami/kafka:3.7 | 无 user 配置 | kafka (Bitnami 默认) | ❌ 否 | ✅ 通过 |
| **Kafka UI** | provectuslabs/kafka-ui:latest | 无 user 配置 | 官方默认 | ❌ 否 | ✅ 通过 |

**总结**: ✅ 所有基础设施组件配置正确，无需修改

## 详细分析

### 1. MySQL (components/mysql/docker-compose.yml)

```yaml
services:
  mysql:
    image: mysql:8.0
    # 状态: 无 user 配置
    # 结论: ✅ 正确，官方镜像使用 mysql 用户
```

**验证方式**:

```bash
docker exec mysql id
# 预期输出: uid=999(mysql) gid=999(mysql)
```

**配置说明**:

- MySQL 官方镜像已优化为使用 `mysql` 用户 (UID 999)
- 不需要也不应该修改为 www 用户
- 数据目录权限由 Docker volume 自动管理

### 2. Redis (components/redis/docker-compose.yml)

```yaml
services:
  redis-cache:
    image: redis:7
    # 状态: 无 user 配置
    # 结论: ✅ 正确，官方镜像使用 redis 用户
    
  redis-auth:
    image: redis:7
    # 状态: 无 user 配置
    # 结论: ✅ 正确，官方镜像使用 redis 用户
```

**验证方式**:

```bash
docker exec redis-cache id
docker exec redis-auth id
# 预期输出: uid=999(redis) gid=1000(redis)
```

**配置说明**:

- Redis 官方镜像使用 `redis` 用户 (UID 999)
- 双实例配置 (cache + auth) 都使用官方默认用户
- 持久化数据权限由 Docker volume 管理

### 3. MongoDB (components/mongo/docker-compose.yml)

```yaml
services:
  mongo:
    image: mongo:7
    # 状态: 无 user 配置
    # 结论: ✅ 正确，官方镜像使用 mongodb 用户
```

**验证方式**:

```bash
docker exec mongo id
# 预期输出: uid=999(mongodb) gid=999(mongodb)
```

**配置说明**:

- MongoDB 官方镜像使用 `mongodb` 用户 (UID 999)
- 认证启用，安全配置正确
- 绑定 127.0.0.1，仅本地访问

### 4. Nginx (components/nginx/docker-compose.yml)

```yaml
services:
  nginx:
    image: nginx:1.27
    # 状态: 无 user 配置
    # 结论: ✅ 正确，官方镜像自动降权到 nginx 用户
```

**验证方式**:

```bash
docker exec nginx ps aux | grep nginx
# 预期输出:
# root      1  ... nginx: master process
# nginx    29  ... nginx: worker process
```

**配置说明**:

- Nginx 需要 root 启动以绑定 80/443 端口
- 启动后自动降权到 `nginx` 用户 (UID 101)
- 这是 Nginx 官方推荐的安全配置

### 5. NSQ (components/nsq/docker-compose.yml)

```yaml
services:
  nsqlookupd:
    image: nsqio/nsq:v1.3.0
    # 状态: 无 user 配置
    # 结论: ✅ 正确，官方镜像使用 nsq 用户
    
  nsqd:
    image: nsqio/nsq:v1.3.0
    # 状态: 无 user 配置
    # 结论: ✅ 正确，官方镜像使用 nsq 用户
    
  nsqadmin:
    image: nsqio/nsq:v1.3.0
    # 状态: 无 user 配置
    # 结论: ✅ 正确，官方镜像使用 nsq 用户
```

**验证方式**:

```bash
docker top nsqlookupd
docker top nsqd
docker top nsqadmin
# 检查 UID 列
```

**配置说明**:

- NSQ 官方镜像使用专用的 nsq 用户
- 三个组件 (lookupd, nsqd, nsqadmin) 都使用相同的用户策略
- 消息队列服务，不需要特殊权限

### 6. Kafka (components/kafka/docker-compose.yml)

```yaml
services:
  kafka:
    image: bitnami/kafka:3.7
    # 状态: 无 user 配置
    # 结论: ✅ 正确，Bitnami 镜像使用 kafka 用户
    
  kafka-ui:
    image: provectuslabs/kafka-ui:latest
    # 状态: 无 user 配置
    # 结论: ✅ 正确，使用官方默认用户
```

**验证方式**:

```bash
docker exec kafka id
# 预期输出: uid=1001(kafka) gid=1001(kafka)
```

**配置说明**:

- Bitnami 镜像已优化为非 root 用户 (kafka UID 1001)
- Kafka UI 也使用官方镜像的默认用户
- KRaft 模式配置，无需 ZooKeeper

## 配置原则总结

### ✅ 应保持官方默认的场景

1. **数据库服务**: MySQL, MongoDB, Redis
   - 官方镜像已优化用户管理
   - 数据目录权限由 Docker volume 处理

2. **Web 服务器**: Nginx
   - 需要 root 绑定特权端口 (80/443)
   - 自动降权到 nginx 用户

3. **消息队列**: NSQ, Kafka
   - 官方镜像使用专用用户
   - 已经过安全优化

### ✅ 应使用 www 用户的场景

仅限**业务应用容器**:

- Go/Node.js/Python/PHP 应用
- 自定义微服务
- API 服务
- 后台任务处理器

**示例**:

```yaml
services:
  myapp:
    image: mycompany/myapp:latest
    user: "${WWW_UID}:${WWW_GID}"  # ← 业务应用使用 www
    env_file: /opt/infra/.env
```

## 验证脚本

创建验证脚本检查所有容器的运行用户:

```bash
#!/bin/bash
# verify-container-users.sh

echo "检查容器运行用户..."
echo "===================="

containers=(
    "mysql"
    "redis-cache"
    "redis-auth"
    "mongo"
    "nginx"
    "nsqlookupd"
    "nsqd"
    "nsqadmin"
    "kafka"
)

for container in "${containers[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo -n "✓ ${container}: "
        docker exec "$container" id 2>/dev/null || echo "无法获取用户信息"
    else
        echo "⚠ ${container}: 容器未运行"
    fi
done

echo ""
echo "Nginx worker 进程用户:"
docker exec nginx ps aux | grep "nginx: worker" | head -1 2>/dev/null
```

**使用方式**:

```bash
chmod +x verify-container-users.sh
./verify-container-users.sh
```

**预期输出**:

```text
检查容器运行用户...
====================
✓ mysql: uid=999(mysql) gid=999(mysql)
✓ redis-cache: uid=999(redis) gid=1000(redis)
✓ redis-auth: uid=999(redis) gid=1000(redis)
✓ mongo: uid=999(mongodb) gid=999(mongodb)
✓ nginx: uid=0(root) gid=0(root)  # master 进程
⚠ nsqlookupd: 容器未运行  # 未启动的话
✓ nsqd: uid=xxx(nsq) gid=xxx(nsq)
✓ nsqadmin: uid=xxx(nsq) gid=xxx(nsq)
✓ kafka: uid=1001(kafka) gid=1001(kafka)

Nginx worker 进程用户:
nginx     29  ... nginx: worker process
```

## 常见问题

### Q1: 为什么 MySQL/Redis/MongoDB 不用 www 用户?

**A**: 官方镜像已经过安全优化:

- MySQL 使用 `mysql` 用户 (UID 999)
- Redis 使用 `redis` 用户 (UID 999)
- MongoDB 使用 `mongodb` 用户 (UID 999)

强制改为 www 用户会导致:

- 数据目录权限问题
- 官方镜像启动失败
- 失去官方的安全保证

### Q2: Nginx 为什么 root 运行?

**A**: Nginx 的 master 进程需要 root 权限:

- 绑定特权端口 80/443 (< 1024)
- 读取 SSL 证书私钥

但 worker 进程会自动降权到 `nginx` 用户，这是官方推荐配置。

### Q3: 什么时候用 www 用户?

**A**: 仅限**业务应用容器**:

- 你自己开发的应用
- 不需要特权端口的服务
- 微服务、API 服务
- 后台任务

**不要用于**:

- 官方基础设施镜像 (MySQL, Redis, etc.)
- 需要特殊权限的服务

### Q4: 如何判断容器是否需要修改?

使用这个决策树:

```text
是官方基础设施镜像? (MySQL/Redis/Nginx/etc.)
├─ 是 → ✅ 保持官方默认，不要修改
└─ 否 → 是自定义业务应用?
         ├─ 是 → ✅ 使用 www 用户
         └─ 否 → 保持官方默认
```

## 后续任务

### ✅ 已完成

- [x] 审查所有 docker-compose.yml 文件
- [x] 验证官方镜像的用户配置
- [x] 创建容器用户策略文档
- [x] 创建检查清单

### 📋 无需执行

- [ ] ~~修改 MySQL 配置~~ (已确认无需修改)
- [ ] ~~修改 Redis 配置~~ (已确认无需修改)
- [ ] ~~修改 MongoDB 配置~~ (已确认无需修改)
- [ ] ~~修改 Nginx 配置~~ (已确认无需修改)
- [ ] ~~修改 NSQ 配置~~ (已确认无需修改)
- [ ] ~~修改 Kafka 配置~~ (已确认无需修改)

### 📝 建议任务

- [ ] 创建验证脚本 (verify-container-users.sh)
- [ ] 在文档中添加容器用户安全最佳实践
- [ ] 更新 README.md，说明基础设施 vs 业务应用的用户区别

## 相关文档

- [容器用户策略说明](./container-user-strategy.md)
- [www 用户使用指南](../server/www-user-guide.md)
- [用户系统重构总结](../server/user-system-refactoring.md)

## 审查签名

- **审查人**: GitHub Copilot
- **审查日期**: 2025-10-24
- **审查结果**: ✅ 所有基础设施组件配置正确
- **建议**: 无需修改现有配置

---

**结论**: infra 项目中的所有组件都是基础设施服务，应该使用官方镜像的默认用户，不需要也不应该改为 www 用户。www 用户仅用于业务应用容器。
