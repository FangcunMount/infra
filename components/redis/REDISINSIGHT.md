# RedisInsight 使用指南

## 概述

RedisInsight 是 Redis 官方提供的可视化管理工具，用于监控和管理 Redis 实例。

## 配置说明

### Docker Compose 配置

```yaml
redisinsight:
  image: redis/redisinsight:latest
  container_name: redisinsight
  restart: unless-stopped
  networks:
    - backend
  ports:
    - "${REDISINSIGHT_PORT:-127.0.0.1:5540}:5540"
  volumes:
    - redisinsight_data:/data
  mem_limit: 256M
  cpus: 0.10
  profiles:
    - management  # 可选启动
```

### 关键特性

- **仅本机访问**: 默认绑定 `127.0.0.1:5540`，仅本机可访问
- **可选启动**: 使用 `profiles: management`，需手动启动
- **资源限制**: 256MB 内存 + 0.10 CPU
- **健康检查**: 自动检测服务可用性
- **日志滚动**: 50MB × 2 文件

---

## 启动方式

### 方式 1：使用 Profile 启动（推荐）

```bash
# 启动 Redis + RedisInsight
cd /Users/yangshujie/workspace/infra/components/redis
docker-compose --profile management up -d

# 仅启动 Redis（不包含 RedisInsight）
docker-compose up -d
```

### 方式 2：修改配置去掉 Profile

```yaml
# 删除这两行
profiles:
  - management
```

然后正常启动：

```bash
docker-compose up -d
```

---

## 访问方式

### 1. 本机访问（默认）

```bash
# 浏览器打开
open http://localhost:5540

# 或直接访问
http://127.0.0.1:5540
```

### 2. 远程访问（需修改配置）

**修改 `.env` 文件**：

```bash
# 允许外部访问
REDISINSIGHT_PORT=0.0.0.0:5540
```

**重启服务**：

```bash
docker-compose --profile management restart redisinsight
```

**访问地址**：

```text
http://<ServerA_IP>:5540
```

---

## 添加 Redis 连接

### 1. 首次访问

打开 `http://localhost:5540`，按照向导添加 Redis 实例。

### 2. 添加 Cache 实例

| 字段 | 值 |
|------|-----|
| **Host** | `redis-cache` (容器名) 或 `ServerA_IP` |
| **Port** | `6379` |
| **Name** | `Redis Cache (缓存)` |
| **Username** | 留空 |
| **Password** | `${REDIS_CACHE_PASSWORD}` (从 .env 查看) |

### 3. 添加 Auth 实例

| 字段 | 值 |
|------|-----|
| **Host** | `redis-auth` |
| **Port** | `6380` |
| **Name** | `Redis Auth (认证)` |
| **Username** | 留空 |
| **Password** | `${REDIS_AUTH_PASSWORD}` |

---

## 功能说明

### 1. 数据浏览器

- **查看键空间**: 浏览所有键
- **按模式过滤**: 支持通配符搜索
- **查看键详情**: 查看值、TTL、类型
- **编辑数据**: 修改键值

### 2. 性能监控

- **实时指标**: 内存使用、命中率、QPS
- **慢查询日志**: 查看慢命令
- **客户端连接**: 监控活跃连接

### 3. CLI 工具

- **内置 CLI**: 无需 `docker exec`
- **命令历史**: 保存执行记录
- **语法高亮**: 便于阅读

### 4. 分析工具

- **内存分析**: 查看大键、键类型分布
- **键分析**: 统计键模式
- **推荐优化**: 提供优化建议

---

## 常用操作

### 查看缓存命中率

1. 进入 RedisInsight
2. 选择 `Redis Cache` 实例
3. 查看 Dashboard → `Hit Rate`

### 查找大键

1. 进入 `Browser` 标签
2. 使用过滤器: `*` (所有键)
3. 按大小排序
4. 查看前 100 个大键

### 执行命令

1. 进入 `CLI` 标签
2. 执行命令:

   ```redis
   INFO memory
   DBSIZE
   KEYS test:*
   GET test:key
   ```

### 清理过期键

```redis
# 查看过期键数量
INFO stats | grep expired_keys

# 手动触发清理（Cache 实例）
SCAN 0 MATCH expired:* COUNT 1000
# 然后逐个删除或批量删除
```

---

## 安全建议

### 1. 网络隔离

**生产环境**：

```bash
# 仅允许本机访问
REDISINSIGHT_PORT=127.0.0.1:5540
```

**开发环境**：

```bash
# 允许内网访问
REDISINSIGHT_PORT=0.0.0.0:5540
```

### 2. 密码保护

RedisInsight 本身无密码保护，建议：

- 使用反向代理（Nginx）添加 HTTP Basic Auth
- 使用 VPN 访问
- 仅在需要时启动

### 3. 只读用户（推荐）

为 RedisInsight 创建只读 ACL 用户：

```redis
# 在 Redis CLI 中执行
ACL SETUSER redisinsight on >readonly_password ~* -@all +@read +info +ping +client|list

# 使用只读用户连接 RedisInsight
Username: redisinsight
Password: readonly_password
```

---

## 故障排查

### 问题 1: 无法访问 5540 端口

**检查容器状态**：

```bash
docker ps | grep redisinsight
```

**查看日志**：

```bash
docker logs redisinsight --tail 50
```

**检查端口绑定**：

```bash
netstat -tuln | grep 5540
```

### 问题 2: 无法连接 Redis 实例

**检查网络**：

```bash
docker exec redisinsight ping redis-cache
docker exec redisinsight ping redis-auth
```

**测试连接**：

```bash
docker exec redisinsight redis-cli -h redis-cache -p 6379 -a "${REDIS_CACHE_PASSWORD}" PING
```

### 问题 3: 内存占用过高

**限制内存**：

```yaml
mem_limit: 256M  # 已配置
```

**重启服务**：

```bash
docker-compose --profile management restart redisinsight
```

---

## 资源占用

| 指标 | 值 | 说明 |
|------|-----|------|
| **内存限制** | 256MB | 足够日常使用 |
| **CPU 限制** | 0.10 核 | 轻量级工具 |
| **磁盘空间** | ~50MB | 存储配置和缓存 |
| **网络** | 极低 | 仅 Web UI 流量 |

---

## Makefile 命令（待添加）

```makefile
# 启动 RedisInsight
redis-insight-start: ## 启动 RedisInsight 管理界面
 @cd components/redis && docker-compose --profile management up -d redisinsight
 $(call success_msg,RedisInsight 已启动: http://localhost:5540)

# 停止 RedisInsight
redis-insight-stop: ## 停止 RedisInsight
 @docker stop redisinsight 2>/dev/null || true
 $(call success_msg,RedisInsight 已停止)

# 查看日志
redis-insight-logs: ## 查看 RedisInsight 日志
 @docker logs -f --tail=50 redisinsight

# 打开浏览器
redis-insight-open: ## 打开 RedisInsight Web UI
 @open http://localhost:5540 || echo "请手动打开: http://localhost:5540"
```

---

## 最佳实践

### 开发环境

- ✅ 保持启动，方便调试
- ✅ 允许外部访问（团队共享）
- ✅ 使用默认密码连接

### 测试环境

- ✅ 按需启动
- ✅ 仅内网访问
- ✅ 定期清理数据

### 生产环境

- ⚠️ 仅在排查问题时启动
- ⚠️ 仅本机访问或通过 VPN
- ⚠️ 使用只读 ACL 用户
- ⚠️ 使用后立即停止

---

## 替代方案

如果不需要图形界面，可以使用：

### 1. redis-cli（命令行）

```bash
make redis-cache-cli
make redis-auth-cli
```

### 2. 第三方工具

- **RedisDesktopManager**: 桌面客户端
- **Medis**: macOS 客户端
- **AnotherRedisDesktopManager**: 开源客户端

### 3. 监控系统

- **Prometheus + Grafana**: 生产级监控
- **redis_exporter**: 指标导出

---

## 总结

**优势**：

- 🎯 官方工具，功能全面
- 🚀 开箱即用，无需配置
- 📊 实时监控，直观易用
- 🔧 内置 CLI，方便调试

**注意**：

- ⚠️ 生产环境谨慎使用
- ⚠️ 注意网络安全
- ⚠️ 定期清理数据
- ⚠️ 监控资源占用

---

**文档版本**: 1.0  
**最后更新**: 2025-10-24  
**维护者**: Infrastructure Team
