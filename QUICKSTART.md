# 快速开始指南

## 项目概述

这是一个组件化的基础设施项目，使用 Docker Compose 管理多个基础服务。支持双节点部署架构：

- **节点 A (Web/事务侧)**: nginx, mysql, redis, mongo
- **节点 B (计算侧)**: kafka, zookeeper

## 项目结构

```
📦 shared-infra/
├── 🐳 compose/
│   ├── base/                   # 基础服务定义
│   │   └── docker-compose.yml
│   ├── nodes/                  # 节点特定配置
│   │   ├── a.override.yml      # 节点 A 覆盖
│   │   └── b.override.yml      # 节点 B 覆盖
│   └── env/
│       └── prod/               # 生产环境配置
├── 🔧 components/              # 组件配置
│   ├── nginx/
│   ├── mysql/
│   ├── redis/
│   ├── mongo/
│   └── kafka/
├── 🚀 scripts/                 # 自动化脚本
│   ├── deploy_a.sh            # 节点 A 部署
│   └── deploy_b.sh            # 节点 B 部署
└── 📋 Makefile                 # 管理命令
```

## 快速部署

### 🌐 节点 A (Web/事务侧)

```bash
# 1. 克隆并初始化
git clone <repo-url> shared-infra
cd shared-infra
make init-node-a

# 2. 配置环境变量
vim compose/env/prod/.env
# 填写必要的配置项

# 3. 自动部署
./scripts/deploy_a.sh
```

### ⚡ 节点 B (计算侧)

```bash
# 1. 克隆并初始化
git clone <repo-url> shared-infra
cd shared-infra
make init-node-b

# 2. 配置环境变量
vim compose/env/prod/.env
# 配置 Kafka 相关参数

# 3. 自动部署
./scripts/deploy_b.sh
```

## 常用命令

### 基础管理

```bash
# 查看帮助
make help

# 检查服务状态
make status

# 查看日志
make logs

# 停止所有服务
make down
```

### 开发调试

```bash
# 启动单个服务
make dev-start NODE=a SERVICE=nginx

# 查看服务日志
make dev-logs NODE=a SERVICE=mysql

# 进入容器shell
make dev-shell NODE=a SERVICE=redis

# 验证配置
make config-validate
```

### SSL 证书配置

```bash
# 创建证书目录
make ssl-setup DOMAIN=example.com

# 然后将证书文件放入：
# components/nginx/ssl/example.com/fullchain.pem
# components/nginx/ssl/example.com/privkey.pem
```

### 备份和维护

```bash
# 备份配置
make backup-config

# 测试网络连通性
make network-test

# 清理资源
make clean
```

## 环境配置说明

### 节点 A 环境变量

```bash
# MySQL 配置
MYSQL_ROOT_PASSWORD=your_secure_password
MYSQL_DATABASE=main_db
MYSQL_USER=app_user
MYSQL_PASSWORD=app_password

# Redis 配置
REDIS_PASSWORD=redis_secure_password

# MongoDB 配置
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=mongo_password

# 网络配置
NODE_A_IP=10.0.1.10
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443
MYSQL_PORT=3306
REDIS_PORT=6379
MONGO_PORT=27017
```

### 节点 B 环境变量

```bash
# Kafka 配置
KAFKA_PORT=9092
ZOOKEEPER_PORT=2181

# 网络配置  
NODE_B_IP=10.0.1.20
NODE_A_IP=10.0.1.10  # 用于连接节点 A
```

## 网络架构

```
   Internet
       │
   [Load Balancer]
       │
   ┌───▼───┐         ┌─────────┐
   │Node A │◄────────┤ Node B  │
   │Web侧  │         │计算侧   │  
   └───────┘         └─────────┘
   
Node A: nginx, mysql, redis, mongo
Node B: kafka, zookeeper
```

## 安全注意事项

1. **敏感文件已加入 .gitignore**：
   - SSL 证书和私钥
   - 环境配置文件
   - 数据库文件

2. **建议使用 SOPS 加密**：
   ```bash
   # 加密环境文件
   sops -e compose/env/prod/.env > .env.encrypted
   ```

3. **定期备份**：
   ```bash
   # 自动备份脚本
   ./scripts/backup.sh
   ```

## 故障排查

### 常见问题

1. **服务启动失败**
   ```bash
   make config-validate  # 检查配置
   make logs            # 查看错误日志
   ```

2. **网络连接问题**
   ```bash
   make network-test    # 测试网络连通性
   ```

3. **端口冲突**
   ```bash
   # 检查端口占用
   netstat -tulpn | grep :80
   ```

### 日志位置

- 应用日志：`logs/` 目录
- Docker 日志：`make logs SERVICE=service_name`
- 系统日志：`/var/log/`

## 性能优化

### 资源限制

每个服务都配置了合理的资源限制：

```yaml
deploy:
  resources:
    limits:
      memory: 1G
      cpus: '0.5'
    reservations:
      memory: 512M
```

### 监控建议

1. 使用 `docker stats` 监控资源使用
2. 配置日志轮转防止磁盘占满
3. 定期清理未使用的镜像和容器

## 扩展和自定义

### 添加新组件

1. 在 `components/` 创建新目录
2. 添加 `override.yml` 文件
3. 更新相应节点的覆盖文件
4. 测试配置：`make config-validate`

### 自定义配置

所有配置文件都支持自定义修改，修改后使用：

```bash
make config-show NODE=a  # 预览配置
make deploy-a           # 重新部署
```

---

📝 **需要帮助？** 运行 `make help` 查看所有可用命令