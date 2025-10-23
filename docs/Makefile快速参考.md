# Makefile 快速参考

## 🚀 核心命令

```bash
make help              # 显示帮助
make help-all          # 显示详细帮助
make quick-start       # 快速启动 (Nginx + MySQL + Redis)
make full-install      # 完整安装所有服务
make status            # 查看所有服务状态
make test-all          # 测试所有服务连接
make troubleshoot      # 运行故障诊断
```

## 📦 环境管理

```bash
make env-init               # 初始化环境配置
make env-show               # 显示当前环境配置
make env-edit               # 编辑环境配置
make env-copy FROM=dev TO=prod  # 复制环境
make dev                    # 切换到开发环境
make prod                   # 切换到生产环境
```

## 🗄️ 服务管理

### MySQL

```bash
make mysql-start/stop/restart
make mysql-logs
make mysql-shell
make mysql-backup DB=database_name
```

### Redis

```bash
make redis-start/stop/restart
make redis-logs
make redis-cli           # 进入 Redis CLI
make redis-info
```

### MongoDB

```bash
make mongo-start/stop/restart
make mongo-logs
make mongo-shell         # 进入 MongoDB Shell
```

### Kafka

```bash
make kafka-start/stop/restart
make kafka-topics        # 列出所有 Topics
make kafka-create-topic TOPIC=name PARTITIONS=3 REPLICAS=1
make kafka-delete-topic TOPIC=name
make kafka-describe-topic TOPIC=name
```

### NSQ

```bash
make nsq-start/stop/restart
make nsq-admin           # 打开 Web UI
```

## 🌐 网络管理

```bash
make net-list                    # 列出所有网络
make net-create NAME=network     # 创建网络
make net-delete NAME=network     # 删除网络
make swarm-init                  # 初始化 Swarm
make port-check PORT=80          # 检查端口占用
```

## 🔒 SSL 证书

```bash
make ssl-obtain DOMAIN=example.com EMAIL=admin@example.com
make ssl-import DOMAIN=example.com CERT=/path/cert.pem KEY=/path/key.pem
make ssl-renew DOMAIN=example.com
make ssl-list
make ssl-remove DOMAIN=example.com
```

## 🔧 Nginx 应用

```bash
make nginx-reload               # 重载配置
make nginx-test                 # 测试配置
make app-deploy APP=myapp DOMAIN=example.com PORT=3000 SSL=yes
make app-remove APP=myapp
make app-list
make app-enable APP=myapp
make app-disable APP=myapp
```

## 📊 监控诊断

```bash
make stats                # 容器资源统计
make top                  # 容器进程
make disk-usage           # 磁盘使用
make logs SERVICE=name    # 查看日志
make troubleshoot         # 完整诊断 (5步)
make service-ports        # 显示端口映射
```

## 🧪 测试验证

```bash
make test-all             # 测试所有服务
make test-mysql           # 测试 MySQL
make test-redis           # 测试 Redis
make test-mongo           # 测试 MongoDB
make test-kafka           # 测试 Kafka
make test-nsq             # 测试 NSQ
make test-nginx           # 测试 Nginx
```

## 🧹 维护清理

```bash
make backup TARGET=/backup/dir    # 备份所有数据卷
make clean                        # 清理停止的容器
make clean-all                    # 清理所有未使用资源 (需确认)
make clean-volumes                # 清理数据卷 (需确认)
make clean-networks               # 清理网络
make shell NAME=container         # 进入容器 Shell
```

## 🎯 常用工作流

### 开发环境启动

```bash
make dev-setup           # 配置开发环境
make quick-start         # 启动核心服务
make status              # 检查状态
```

### 查看日志

```bash
make mysql-logs          # 查看 MySQL 日志
make redis-logs          # 查看 Redis 日志
make logs                # 查看所有服务日志
```

### 故障排查

```bash
make troubleshoot        # 运行诊断
make stats               # 查看资源使用
make test-all            # 测试连接
```

### 清理重置

```bash
make down                # 停止所有服务
make clean               # 清理容器和镜像
make reset               # 重置基础设施
```

### 生产部署

```bash
make ENV=prod env-init         # 初始化生产配置
make ENV=prod env-edit         # 编辑配置
make ENV=prod full-install     # 完整安装
make ENV=prod test-all         # 测试连接
```

## 💡 提示

### 环境变量

```bash
ENV=prod make status           # 在生产环境执行命令
LOG_LINES=500 make mysql-logs  # 查看更多日志行
```

### 参数传递

大多数命令支持参数，例如：

```bash
make kafka-create-topic TOPIC=my-topic PARTITIONS=3 REPLICAS=1
make port-check PORT=8080
make backup TARGET=/backups
```

### 别名

许多命令有简短别名：

```bash
make net-list    == make network-list
make prune       == make clean
make help-simple == make help
```

### 获取帮助

```bash
make help              # 快速概览
make help-all          # 详细列表
make <command>         # 不带参数会显示示例
```

## 🔍 示例场景

### 场景 1: 第一次使用

```bash
make help                  # 了解可用命令
make dev-setup             # 配置开发环境
make quick-start           # 启动服务
make test-all              # 验证安装
```

### 场景 2: 添加新的 Kafka Topic

```bash
make kafka-status          # 检查 Kafka 状态
make kafka-topics          # 查看现有 Topics
make kafka-create-topic TOPIC=orders PARTITIONS=6
make kafka-describe-topic TOPIC=orders
```

### 场景 3: 部署新应用到 Nginx

```bash
make ssl-obtain DOMAIN=myapp.com EMAIL=admin@myapp.com
make app-deploy APP=myapp DOMAIN=myapp.com PORT=3000 SSL=yes
make nginx-test            # 测试配置
make nginx-reload          # 应用配置
```

### 场景 4: 数据库备份

```bash
make mysql-status          # 确认 MySQL 运行
make mysql-backup DB=production
make backup TARGET=/mnt/backups  # 备份所有卷
```

### 场景 5: 服务重启

```bash
make mysql-restart         # 重启 MySQL
make nginx-reload          # 重载 Nginx (无停机)
make restart               # 重启所有服务
```

## 📚 更多信息

- 查看 `docs/Makefile重构报告.md` 了解详细改进说明
- 查看 `README.md` 了解项目结构
- 查看 `scripts/` 目录了解底层实现

---

**版本**: v2.0  
**总命令数**: 120+  
**总模块数**: 10
