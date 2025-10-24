# 容器用户策略说明

## 概述

本文档说明 infra 项目中不同类型容器的用户策略。

## 容器分类

### 1. 基础设施组件 (Infrastructure Components)

**特点**: 官方镜像，已经过安全优化，有自己的用户管理机制

**策略**: ✅ **保持官方镜像默认用户，不使用 www**

| 组件 | 镜像 | 默认用户 | 说明 |
|------|------|----------|------|
| **MySQL** | mysql:8.0 | mysql (uid 999) | 官方镜像，以 mysql 用户运行 |
| **Redis** | redis:7 | redis (uid 999) | 官方镜像，以 redis 用户运行 |
| **MongoDB** | mongo:7 | mongodb (uid 999) | 官方镜像，以 mongodb 用户运行 |
| **Nginx** | nginx:1.27 | nginx (uid 101) | root 启动后自动降权到 nginx |
| **NSQ** | nsqio/nsq:v1.3.0 | nsq | 官方镜像 |
| **Kafka** | bitnami/kafka:3.7 | kafka (uid 1001) | Bitnami 镜像，非 root 用户 |

**为什么不用 www?**

1. **官方镜像已优化**: 这些镜像已经使用非 root 用户运行，安全性有保障
2. **避免权限冲突**: 官方镜像的用户 UID/GID 与 www 不同，强制改变会导致权限问题
3. **维护成本**: 修改官方镜像的用户配置需要额外的维护工作
4. **最佳实践**: Docker 官方推荐使用镜像自带的用户

**配置示例**:

```yaml
# ✅ 正确: 使用官方镜像默认用户
services:
  mysql:
    image: mysql:8.0
    # 不设置 user，使用官方默认
    volumes:
      - mysql_data:/var/lib/mysql

  nginx:
    image: nginx:1.27
    # 不设置 user，官方镜像会自动降权
    ports:
      - "80:80"
```

### 2. 业务应用容器 (Business Applications)

**特点**: 自定义应用，需要统一的用户管理

**策略**: ✅ **必须使用 www 用户**

适用场景:

- Go/Node.js/Python/PHP 等业务应用
- 微服务
- API 服务
- 后台任务处理器
- 自定义工具

**配置示例**:

```yaml
# ✅ 正确: 业务应用使用 www 用户
services:
  myapp:
    image: mycompany/myapp:latest
    user: "${WWW_UID}:${WWW_GID}"  # ← 使用 www 用户
    env_file: /opt/infra/.env
    volumes:
      - /srv/apps/myapp/data:/data:rw
      - /var/log/apps:/var/log:rw
    networks:
      - app-network
      - infra-network
```

## 当前 infra 项目组件分析

### 组件清单

所有组件都是**基础设施组件**，应保持官方镜像默认用户:

```text
✅ MySQL       - 使用 mysql 用户 (官方镜像)
✅ Redis       - 使用 redis 用户 (官方镜像)
✅ MongoDB     - 使用 mongodb 用户 (官方镜像)
✅ Nginx       - 使用 nginx 用户 (官方镜像自动降权)
✅ NSQ         - 使用 nsq 用户 (官方镜像)
✅ Kafka       - 使用 kafka 用户 (Bitnami 镜像)
```

**结论**: infra 项目中的所有组件都**不需要**也**不应该**使用 www 用户。

### 验证组件用户

```bash
# 查看容器内实际运行用户
docker exec mysql id
# uid=999(mysql) gid=999(mysql) groups=999(mysql)

docker exec redis-cache id
# uid=999(redis) gid=1000(redis) groups=1000(redis)

docker exec mongo id
# uid=999(mongodb) gid=999(mongodb) groups=999(mongodb)

docker exec nginx ps aux | grep nginx
# nginx      1  ... nginx: master process
# nginx     29  ... nginx: worker process

docker top nsqd
# UID列显示 nsq 或对应的 UID
```

## 目录权限管理

### 基础设施组件目录

由 Docker volume 管理，不需要手动设置 www 权限:

```bash
# 这些目录由 Docker 管理，不要改为 www:www
/var/lib/docker/volumes/infra_mysql_data/
/var/lib/docker/volumes/infra_redis_data/
/var/lib/docker/volumes/infra_mongo_data/
/var/lib/docker/volumes/infra_nsq_data/
```

### 业务应用目录

需要设置为 www:www:

```bash
# 业务应用的数据和日志目录
sudo chown -R www:www /srv/apps
sudo chown -R www:www /var/log/apps
sudo chmod 750 /srv/apps
sudo chmod 750 /var/log/apps
```

## 混合场景: 业务应用访问基础设施

业务应用容器（使用 www 用户）通过网络访问基础设施服务:

```yaml
version: '3.8'

services:
  # 业务应用 - 使用 www 用户
  myapp:
    image: mycompany/myapp:latest
    user: "${WWW_UID}:${WWW_GID}"
    environment:
      # 通过网络访问基础设施服务
      - DATABASE_URL=mysql://user:pass@mysql:3306/db
      - REDIS_URL=redis://redis:6379
      - MONGO_URL=mongodb://mongo:27017
    networks:
      - app-network
      - infra-network  # ← 连接基础设施网络
  
  # 基础设施 - 使用官方默认用户
  mysql:
    image: mysql:8.0
    # 不设置 user
    networks:
      - infra-network

networks:
  app-network:
    driver: bridge
  infra-network:
    external: true
    name: infra-network
```

## 安全最佳实践

### 基础设施组件

```yaml
# 1. 使用官方镜像
image: mysql:8.0  # 已优化

# 2. 限制资源
mem_limit: 1024M
cpus: '0.5'

# 3. 只读挂载配置
volumes:
  - ./my.cnf:/etc/mysql/conf.d/custom.cnf:ro

# 4. 健康检查
healthcheck:
  test: ["CMD", "mysqladmin", "ping"]
  interval: 30s
```

### 业务应用

```yaml
# 1. 使用 www 用户
user: "${WWW_UID}:${WWW_GID}"

# 2. 删除所有 capabilities
cap_drop: ["ALL"]

# 3. 只读根文件系统
read_only: true
tmpfs: ["/tmp"]

# 4. 禁止权限提升
security_opt: ["no-new-privileges:true"]
```

## 常见错误

### ❌ 错误 1: 给基础设施组件设置 www 用户

```yaml
# ❌ 错误
services:
  mysql:
    image: mysql:8.0
    user: "${WWW_UID}:${WWW_GID}"  # 会导致启动失败
```

**问题**: MySQL 需要 mysql 用户才能正确运行

**解决**: 移除 user 配置，使用官方默认

### ❌ 错误 2: 给业务应用使用 root

```yaml
# ❌ 错误
services:
  myapp:
    image: mycompany/myapp:latest
    user: "0:0"  # root 用户，不安全
```

**问题**: 容器以 root 运行，安全风险高

**解决**: 使用 www 用户

```yaml
# ✅ 正确
services:
  myapp:
    image: mycompany/myapp:latest
    user: "${WWW_UID}:${WWW_GID}"
```

### ❌ 错误 3: 混淆目录权限

```bash
# ❌ 错误: 把基础设施数据目录改为 www
sudo chown -R www:www /var/lib/docker/volumes/infra_mysql_data/

# ❌ 错误: 把业务目录改为 mysql
sudo chown -R mysql:mysql /srv/apps/myapp/
```

**解决**:

- 基础设施数据目录 → 由 Docker 管理，不要手动修改
- 业务应用目录 → 设置为 www:www

## 总结

### 快速判断

| 问题 | 答案 |
|------|------|
| MySQL/Redis/MongoDB 用 www? | ❌ 否，用官方默认 |
| Nginx 用 www? | ❌ 否，用官方默认（自动降权） |
| NSQ/Kafka 用 www? | ❌ 否，用官方默认 |
| 业务 API 服务用 www? | ✅ 是 |
| 自定义应用用 www? | ✅ 是 |

### 记忆口诀

```text
官方镜像不乱动，业务应用统一用。
基础设施各自管，www 只管业务端。
```

## 参考文档

- [www 用户使用指南](./www-user-guide.md)
- [用户系统重构总结](./user-system-refactoring.md)
- [Docker 安全最佳实践](https://docs.docker.com/engine/security/)

---

**更新时间**: 2025-10-24  
**版本**: v1.0
