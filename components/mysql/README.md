# MySQL 8.0 数据库组件

## 📋 组件概述

提供高性能的 MySQL 8.0 数据库服务，针对多应用共享和双节点架构进行优化。

## 🔧 配置文件

- **my.cnf**: MySQL 主配置文件，包含性能优化参数
- **init/**: 数据库初始化脚本目录
  - `01-init-infrastructure.sql`: 基础设施数据库和表
  - `02-init-*.sql`: 应用专用数据库 (自动生成)

## 🌐 端口配置

- **MySQL**: `${MYSQL_PORT:-3306}:3306`

## 📊 关键参数 (可通过环境变量调整)

- **缓冲池**: `${MYSQL_INNODB_BUFFER_POOL_SIZE:-1200M}` (节点A)
- **最大连接数**: `${MYSQL_MAX_CONNECTIONS:-150}`
- **字符集**: `utf8mb4` + `utf8mb4_unicode_ci`
- **日志文件**: `128M` InnoDB 日志
- **Binlog 保留**: 24 小时

## 💾 存储配置

- **数据目录**: `/data/mysql` (持久化存储)
- **日志目录**: `/data/logs/mysql`
- **每表一文件**: `innodb_file_per_table = 1`
- **刷新方式**: `O_DIRECT` (避免双重缓冲)

## 🛡️ 安全配置

- **root 密码**: `${MYSQL_ROOT_PASSWORD}` (必须设置)
- **跳过域名解析**: `skip-name-resolve`
- **SQL 模式**: `STRICT_TRANS_TABLES` (严格模式)
- **应用隔离**: 每个应用独立数据库和用户

## 🚀 启动与管理

```bash
# 连接数据库
docker exec -it mysql mysql -uroot -p

# 查看数据库状态
docker exec mysql mysqladmin status -uroot -p

# 备份数据库
docker exec mysql mysqldump -uroot -p --all-databases > backup.sql

# 查看慢查询
docker exec mysql tail -f /var/log/mysql/slow.log
```

## 📋 健康检查

- **连接测试**: `mysqladmin ping` 每 30 秒
- **启动时间**: 60 秒容忍期
- **重试次数**: 5 次

## 🔧 性能监控

```bash
# 查看连接数
docker exec mysql mysql -uroot -p -e "SHOW STATUS LIKE 'Threads_connected';"

# 查看缓冲池状态  
docker exec mysql mysql -uroot -p -e "SHOW ENGINE INNODB STATUS\G" | grep -A 10 "BUFFER POOL"

# 查看慢查询统计
docker exec mysql mysql -uroot -p -e "SHOW STATUS LIKE 'Slow_queries';"

# 查看表空间使用
docker exec mysql mysql -uroot -p -e "SELECT table_schema, ROUND(SUM(data_length+index_length)/1024/1024, 2) AS 'DB Size MB' FROM information_schema.tables GROUP BY table_schema;"
```

## 📈 性能调优建议

### 内存不足时的调整

```bash
# 降低缓冲池大小
MYSQL_INNODB_BUFFER_POOL_SIZE=800M

# 减少连接数
MYSQL_MAX_CONNECTIONS=100

# 调整其他缓存参数
key_buffer_size=256M
sort_buffer_size=2M
```

### 高并发优化

```bash
# 增加连接数
MYSQL_MAX_CONNECTIONS=300

# 优化连接池
thread_cache_size=32
max_connect_errors=1000000
```

## 🔄 备份与恢复

```bash
# 完整备份 (通过 scripts/backup.sh)
make mysql-backup BACKUP_NAME=daily

# 手动备份单个数据库
docker exec mysql mysqldump -uroot -p database_name > backup.sql

# 恢复数据库
docker exec -i mysql mysql -uroot -p database_name < backup.sql
```

## 🚨 故障排除

```bash
# 查看错误日志
docker logs mysql
tail -f /data/logs/mysql/error.log

# 检查磁盘空间
df -h /data/mysql

# 检查内存使用
docker stats mysql

# 检查配置语法
docker exec mysql mysqld --verbose --help | head -20
```

## 📝 应用接入

通过 `scripts/add-app.sh` 自动创建：
- 应用专用数据库
- 应用专用用户和密码  
- 权限配置
- 应用注册记录

## 🔧 双节点配置

- **节点 A**: 运行 MySQL 主实例，提供读写服务
- **节点 B**: 通过内网连接节点 A 的 MySQL
- **连接字符串**: `mysql://user:pass@${NODE_A_IP}:3306/dbname`

## 📝 变更记录

- 2024-09-26: 重构为组件化配置，优化双节点架构
- 2024-09-25: 调整缓冲池大小适配节点 A 内存限制
- 2024-09-24: 添加应用隔离和自动用户管理