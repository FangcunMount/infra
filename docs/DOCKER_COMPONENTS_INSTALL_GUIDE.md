# Docker 组件安装指南

## 📋 概述

基于项目中的 `components` 配置，自动化安装和配置 Docker 服务组件。

## 🏗️ 架构设计

### 目录结构
```
infra/
├── components/           # 组件配置
│   ├── nginx/
│   │   ├── override.yml
│   │   ├── nginx.conf
│   │   └── conf.d/
│   ├── mysql/
│   │   ├── override.yml
│   │   ├── my.cnf
│   │   └── init/
│   └── ...
├── compose/
│   ├── base/             # 基础服务定义
│   │   └── docker-compose.yml
│   └── env/              # 环境配置
│       └── prod/
└── scripts/init-server/  # 安装脚本
```

### 用户权限策略

**推荐使用 `www` 用户**：
- ✅ **安全性**: 非 root 用户运行
- ✅ **权限管理**: 统一的文件权限
- ✅ **Web 服务**: 符合 Web 服务运行惯例
- ✅ **Docker 权限**: 自动验证 docker 组权限

## 🚀 快速开始

### 1. 前置准备

确保已完成基础环境初始化：
```bash
# 1. 安装 Docker
bash install-docker.sh

# 2. 确保 www 用户在 docker 组中
sudo usermod -aG docker www

# 3. www 用户重新登录（刷新组权限）
su - www
```

### 2. 安装单个组件

```bash
# 安装 Nginx
bash install-nginx.sh

# 安装 MySQL
bash install-mysql.sh

# 安装 Redis  
bash install-redis.sh

# 安装 MongoDB
bash install-mongo.sh

# 安装 Kafka
bash install-kafka.sh
```

### 3. 安装所有组件

```bash
# 一键安装所有组件
bash install-all-components.sh

# 或使用主脚本
bash install-components.sh all
```

## 📝 脚本选项

### 统一安装脚本 `install-components.sh`

```bash
# 基本用法
bash install-components.sh <组件名> [选项]

# 选项说明
--user USER        # 指定运行用户 (默认: www)
--project NAME     # Docker Compose 项目名 (默认: infra)  
--data-dir DIR     # 数据目录 (默认: /data)
--env ENV          # 环境类型 (dev/prod, 默认: prod)
--dry-run          # 预览模式，不实际执行
--help, -h         # 显示帮助
```

### 使用示例

```bash
# 1. 默认安装（推荐）
bash install-components.sh nginx

# 2. 指定用户安装
bash install-components.sh mysql --user www

# 3. 预览安装命令
bash install-components.sh redis --dry-run

# 4. 自定义数据目录
bash install-components.sh mongo --data-dir /opt/data

# 5. 开发环境安装
bash install-components.sh kafka --env dev

# 6. 安装所有组件
bash install-components.sh all --user www
```

## 🗂️ 数据目录结构

安装后将创建以下目录结构：

```
/data/
├── mysql/          # MySQL 数据
├── redis/          # Redis 数据  
├── mongodb/        # MongoDB 数据
├── kafka/          # Kafka 数据
├── nginx/          # Nginx 数据
└── logs/           # 日志目录
    ├── mysql/
    ├── redis/
    ├── mongodb/
    ├── kafka/
    └── nginx/
```

**目录权限**：
- 所有者：`www:www`（或指定用户）
- 权限：`755`

## ⚙️ 配置文件

### 环境配置

自动生成的环境配置文件：`compose/env/prod/.env`

```bash
# 项目配置
COMPOSE_PROJECT_NAME=infra
COMPOSE_FILE=/path/to/compose/base/docker-compose.yml

# 用户配置  
INFRA_USER=www
PUID=1000
PGID=1000

# 网络配置
NETWORK_FRONTEND=infra_frontend
NETWORK_BACKEND=infra_backend

# 组件特定配置（自动生成密码）
MYSQL_ROOT_PASSWORD=随机生成
MYSQL_PASSWORD=随机生成
REDIS_PASSWORD=随机生成
# ...
```

### 组件配置

使用 `components/` 目录中的配置：
- **基础服务**：`compose/base/docker-compose.yml`
- **组件覆盖**：`components/{component}/override.yml`
- **配置文件**：`components/{component}/` 下的配置文件

## 🔧 管理命令

### Docker Compose 管理

```bash
# 查看服务状态
docker compose -p infra ps

# 查看日志
docker compose -p infra logs nginx
docker compose -p infra logs -f mysql  # 实时日志

# 重启服务
docker compose -p infra restart redis

# 停止/启动服务
docker compose -p infra stop mongo
docker compose -p infra start mongo

# 更新服务
docker compose -p infra pull nginx
docker compose -p infra up -d nginx
```

### 服务健康检查

```bash
# 检查所有服务
docker compose -p infra ps

# 检查特定服务
docker ps --filter "name=infra-nginx-1"

# 查看服务详细信息
docker inspect infra-nginx-1
```

## 🛡️ 安全配置

### 1. 用户权限
- **运行用户**：`www`（非 root）
- **文件权限**：合理的目录和文件权限
- **Docker 权限**：通过 docker 组授权

### 2. 网络隔离
- **前端网络**：`infra_frontend`
- **后端网络**：`infra_backend`
- **服务隔离**：按需网络访问

### 3. 密码安全
- **自动生成**：随机强密码
- **文件权限**：`.env` 文件 600 权限
- **不明文存储**：敏感信息通过环境变量传递

## 🔍 故障排除

### 1. 权限问题

```bash
# 检查用户权限
id www
groups www

# 检查 docker 组
sudo usermod -aG docker www

# 检查目录权限
ls -la /data/
```

### 2. 服务启动失败

```bash
# 查看容器日志
docker compose -p infra logs [服务名]

# 查看容器状态
docker compose -p infra ps

# 检查配置文件
docker compose -p infra config
```

### 3. 网络问题

```bash
# 检查网络
docker network ls

# 检查端口占用
netstat -tlnp | grep [端口]

# 测试服务连接
curl http://localhost:[端口]
```

## 📊 服务端口

| 服务 | 端口 | 描述 |
|------|------|------|
| Nginx | 80, 443 | HTTP/HTTPS |
| MySQL | 3306 | 数据库 |
| Redis | 6379 | 缓存 |
| MongoDB | 27017 | NoSQL 数据库 |
| Kafka | 9092 | 消息队列 |
| Zookeeper | 2181 | Kafka 依赖 |

## 🎯 最佳实践

### 1. 安装顺序建议
```bash
# 1. 基础服务
bash install-nginx.sh

# 2. 数据库服务  
bash install-mysql.sh
bash install-redis.sh
bash install-mongo.sh

# 3. 消息队列（如需要）
bash install-kafka.sh
```

### 2. 生产环境建议
- ✅ 使用 `www` 用户运行
- ✅ 定期备份 `/data` 目录
- ✅ 监控服务健康状态
- ✅ 定期更新镜像版本
- ✅ 配置日志轮转

### 3. 开发环境
```bash
# 开发环境可以使用 root 用户（不推荐生产）
bash install-components.sh nginx --user root --env dev
```

---

*最后更新: 2025-09-29*
*状态: ✅ 已完成*