# 存储服务(MySQL/Redis/MongoDB) 全面检查报告

## 📊 **检查范围**
- ✅ 环境变量配置 (`dev/.env`, `prod/.env`)
- ✅ 组件配置文件 (`components/*/override.yml`)
- ✅ Docker Compose 主配置 (`docker-compose.storage.yml`)
- ✅ 服务配置文件 (`my.cnf`, `redis.conf`, `mongod.conf`)
- ✅ 基础设施脚本和卷管理

---

## 🚨 **发现的关键问题**

### ❌ **1. 环境变量空值问题**

#### **问题描述**
```bash
# compose/env/dev/.env 和 prod/.env 中
MYSQL_DATABASE=          # 空值！
MONGO_DATABASE=          # 空值！
```

#### **实际解析结果**
```yaml
# Docker Compose 实际解析为默认值
environment:
  MYSQL_DATABASE: infrastructure      # 使用了默认值
  MONGO_INITDB_DATABASE: infrastructure  # 使用了默认值
```

#### **问题影响**
- ⚠️ **配置不明确**: 依赖默认值而非显式配置
- ⚠️ **环境一致性**: 开发和生产环境都使用相同数据库名
- ⚠️ **维护困难**: 不清楚实际使用的数据库名称

### ❌ **2. 用户名配置不一致**

#### **MySQL 配置**
```bash
# 环境变量中
MYSQL_USER=www           # 用户名为 www

# 但在 override.yml 默认值中  
MYSQL_USER=${MYSQL_USER:-infra}    # 默认值为 infra
```

#### **MongoDB 配置**
```bash
# 环境变量中
MONGO_ROOT_USERNAME=www     # 管理员用户名为 www

# 但在 override.yml 默认值中
MONGO_INITDB_ROOT_USERNAME=${MONGO_ROOT_USERNAME:-admin}  # 默认值为 admin
```

### ❌ **3. 数据库服务端口配置缺失**

#### **问题描述**
```yaml
# components/mysql/override.yml 中
ports:
  - "${MYSQL_PORT:-3306}:3306"     # 引用了 MYSQL_PORT

# 但环境变量文件中没有定义
# MYSQL_PORT=         # 缺失！
# REDIS_PORT=         # 缺失！  
# MONGO_PORT=         # 缺失！
```

### ❌ **4. Redis 密码配置问题**

#### **Redis 配置文件问题**
```properties
# components/redis/redis.conf 中没有 requirepass 配置
# 但环境变量中定义了
REDIS_PASSWORD=T2XFVfU3DCenEnL
```

#### **需要更新**
Redis 配置文件需要添加密码认证配置。

---

## ✅ **配置正确的部分**

### ✅ **1. 数据卷管理**
```bash
# init-infrastructure.sh 正确创建了所有需要的卷
infra_mysql_data -> /data/infra/mysql/data
infra_redis_data -> /data/infra/redis/data  
infra_mongo_data -> /data/infra/mongo/data
infra_app_logs   -> /data/infra/logs
```

### ✅ **2. 网络配置**
```yaml
# 所有服务正确连接到 backend 网络
networks:
  backend:
    external: true
    name: infra-backend
```

### ✅ **3. 配置文件路径**
```yaml
# 所有服务都正确使用项目内配置文件
- ./components/mysql/my.cnf:/etc/mysql/conf.d/my.cnf:ro
- ./components/redis/redis.conf:/usr/local/etc/redis/redis.conf:ro  
- ./components/mongo/mongod.conf:/etc/mongod.conf:ro
```

### ✅ **4. 健康检查和资源限制**
- MySQL: mysqladmin ping 检查 + 内存限制 1.4GB
- Redis: redis-cli ping 检查 + 内存限制 450MB
- MongoDB: mongosh ping 检查 + 内存限制 1GB

---

## 🔧 **需要修复的配置**

### **1. 环境变量修复**

#### **开发环境 (dev/.env)**
```bash
# 数据库配置
MYSQL_DATABASE=infrastructure_dev
MYSQL_USER=infra_dev
MYSQL_PORT=3306

# Redis 配置  
REDIS_PORT=6379

# MongoDB 配置
MONGO_DATABASE=infrastructure_dev
MONGO_ROOT_USERNAME=mongo_admin
MONGO_PORT=27017
```

#### **生产环境 (prod/.env)**
```bash
# 数据库配置
MYSQL_DATABASE=infrastructure_prod
MYSQL_USER=infra_prod  
MYSQL_PORT=3306

# Redis 配置
REDIS_PORT=6379

# MongoDB 配置
MONGO_DATABASE=infrastructure_prod
MONGO_ROOT_USERNAME=mongo_admin
MONGO_PORT=27017
```

### **2. Redis 配置文件修复**

需要在 `components/redis/redis.conf` 中添加：
```properties
# 认证配置
requirepass ${REDIS_PASSWORD}
```

### **3. 配置一致性修复**

确保所有默认值与环境变量一致，避免依赖 `:-` 默认值语法。

---

## 🎯 **修复优先级**

### **高优先级 🔴**
1. **补充缺失的端口环境变量** (`MYSQL_PORT`, `REDIS_PORT`, `MONGO_PORT`)
2. **明确数据库名称** (不使用空值)
3. **统一用户名配置** (环境变量与默认值一致)

### **中优先级 🟡**  
4. **Redis 密码认证配置**
5. **区分开发和生产环境的数据库名称**

### **低优先级 🟢**
6. **配置文档更新**
7. **示例环境变量文件**

---

## 📝 **验证命令**

### **配置语法检查**
```bash
# 开发环境
docker compose -f compose/infra/docker-compose.storage.yml --env-file compose/env/dev/.env config --quiet

# 生产环境  
docker compose -f compose/infra/docker-compose.storage.yml --env-file compose/env/prod/.env config --quiet
```

### **环境变量解析检查**
```bash
# 检查实际使用的数据库名称
docker compose -f compose/infra/docker-compose.storage.yml --env-file compose/env/dev/.env config | grep -E "MYSQL_DATABASE|MONGO_INITDB_DATABASE"
```

---

## 🎉 **总结**

**存储服务配置整体上是功能性的，但存在多个配置一致性和明确性问题需要修复。**

**主要问题**:
- 🔴 环境变量空值依赖默认值
- 🔴 缺失端口配置变量  
- 🟡 Redis 密码认证未配置
- 🟡 用户名配置不一致

**修复后将获得**:
- ✅ 明确的环境配置
- ✅ 完整的端口管理
- ✅ 安全的认证机制
- ✅ 一致的配置标准

---

*检查完成时间: 2025-09-29*  
*发现问题: 4个关键问题*  
*配置文件: 8个检查通过*