# Docker 组件安装方案总结

## 🎯 核心方案

### 推荐用户：`www`
- ✅ **安全性**：非 root 用户运行
- ✅ **权限管理**：统一文件权限控制
- ✅ **生产就绪**：符合生产环境最佳实践

### 安装架构
- **配置驱动**：基于 `components/` 目录配置自动安装
- **用户友好**：自动生成密码、目录权限、环境配置
- **模块化**：支持单独或批量安装组件

## 📋 可用脚本

| 脚本 | 功能 | 使用场景 |
|------|------|----------|
| `install-components.sh` | 主安装脚本 | 灵活安装任意组件 |
| `install-nginx.sh` | Nginx 安装 | 单独安装 Web 服务 |
| `install-mysql.sh` | MySQL 安装 | 单独安装数据库 |
| `install-redis.sh` | Redis 安装 | 单独安装缓存 |
| `install-mongo.sh` | MongoDB 安装 | 单独安装 NoSQL |
| `install-kafka.sh` | Kafka 安装 | 单独安装消息队列 |
| `install-all-components.sh` | 全量安装 | 一键安装所有组件 |

## 🚀 快速使用

### 基本安装
```bash
# 1. 确保 Docker 已安装
bash install-docker.sh

# 2. 安装单个组件
bash install-nginx.sh        # Web 服务器
bash install-mysql.sh        # 数据库
bash install-redis.sh        # 缓存

# 3. 一键安装所有
bash install-all-components.sh
```

### 高级选项
```bash
# 指定用户安装
bash install-components.sh nginx --user www

# 预览模式（不实际执行）
bash install-components.sh mysql --dry-run

# 自定义数据目录
bash install-components.sh redis --data-dir /opt/data
```

## 📂 自动创建的目录结构

```
/data/
├── mysql/          # 数据库数据
├── redis/          # 缓存数据
├── mongodb/        # NoSQL 数据
├── kafka/          # 消息队列数据
├── nginx/          # Web 服务数据
└── logs/           # 所有日志
    ├── mysql/
    ├── redis/
    ├── mongodb/
    ├── kafka/
    └── nginx/
```

**权限自动配置**：
- 所有者：`www:www`
- 权限：`755`

## ⚙️ 自动配置功能

### 1. 环境变量自动生成
- ✅ **随机密码**：MySQL、Redis、MongoDB 密码
- ✅ **用户配置**：PUID/PGID 自动设置
- ✅ **网络配置**：Docker 网络自动创建

### 2. Docker Compose 集成
- ✅ **基础服务**：使用 `compose/base/docker-compose.yml`
- ✅ **组件覆盖**：使用 `components/{name}/override.yml`
- ✅ **项目管理**：统一项目名称 `infra`

### 3. 健康检查
- ✅ **服务状态**：自动检查容器运行状态
- ✅ **启动等待**：等待服务完全启动
- ✅ **错误报告**：详细的错误信息

## 🔧 管理命令

### 服务管理
```bash
# 查看所有服务状态
docker compose -p infra ps

# 查看服务日志
docker compose -p infra logs nginx
docker compose -p infra logs -f mysql

# 重启服务
docker compose -p infra restart redis

# 停止/启动
docker compose -p infra stop mongo
docker compose -p infra start mongo
```

### 故障排除
```bash
# 检查配置
docker compose -p infra config

# 检查用户权限
groups www
id www

# 检查数据目录
ls -la /data/
```

## 💡 使用建议

### 1. 安装前准备
```bash
# 确保 www 用户存在并在 docker 组中
sudo usermod -aG docker www
su - www  # 刷新权限
```

### 2. 推荐安装顺序
```bash
bash install-nginx.sh    # 1. Web 服务
bash install-mysql.sh    # 2. 主数据库
bash install-redis.sh    # 3. 缓存
bash install-mongo.sh    # 4. NoSQL（可选）
bash install-kafka.sh    # 5. 消息队列（可选）
```

### 3. 生产环境
- ✅ 使用 `www` 用户
- ✅ 定期备份 `/data` 目录
- ✅ 监控服务状态
- ✅ 配置防火墙规则

## 🎉 优势特点

### 1. **完全自动化**
- 自动创建目录和设置权限
- 自动生成配置文件和密码
- 自动健康检查和错误处理

### 2. **生产就绪**
- 非 root 用户运行
- 合理的安全配置
- 完整的日志管理

### 3. **灵活性强**
- 支持单独安装任意组件
- 支持自定义用户和目录
- 支持预览模式

### 4. **维护友好**
- 统一的项目管理
- 清晰的目录结构
- 标准的 Docker Compose 命令

---

**下次使用只需一条命令即可完成所有组件的安装和配置！** 🚀

*状态: ✅ 已完成*