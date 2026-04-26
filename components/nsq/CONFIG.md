# NSQ 配置文件说明

## 1. 概述

NSQ 支持通过配置文件或命令行参数进行配置。本项目同时使用两种方式：

- **配置文件**: 管理通用的、稳定的配置项
- **命令行参数**: 管理环境相关的配置（如 IP 地址、服务发现地址等）

## 1.1 配置文件位置

```text
components/nsq/
├── nsqd.conf           # NSQd 消息守护进程配置
├── nsqlookupd.conf     # NSQLookupd 服务发现配置
└── nsqadmin.conf       # NSQAdmin 管理界面配置
```

容器内挂载位置：`/etc/nsq/`

## 2. NSQd 配置 (nsqd.conf)

### 2.1 核心参数

| 参数 | 默认值 | 说明 |
|-----|--------|------|
| `log-level` | info | 日志级别: debug, info, warn, error, fatal |
| `mem-queue-size` | 10000 | 内存队列大小，超过后写入磁盘 |
| `max-msg-size` | 1048576 | 单条消息最大大小（1MB） |
| `msg-timeout` | 60s | 消息超时时间 |
| `data-path` | /data | 数据存储路径 |

### 2.2 性能调优参数

```conf
# 内存队列大小（影响性能和内存占用）
mem-queue-size=10000

# 消息大小限制
max-msg-size=1048576

# 同步到磁盘的频率（消息数量）
sync-every=2500

# 最大处理中消息数量
max-rdy-count=2500
```

### 2.3 适用场景调整

**高吞吐量场景**:

```conf
mem-queue-size=50000
sync-every=5000
max-rdy-count=5000
```

**低延迟场景**:

```conf
mem-queue-size=5000
sync-every=1000
msg-timeout=30s
```

**大消息场景**:

```conf
max-msg-size=10485760  # 10MB
max-output-buffer-size=131072
```

## 3. NSQLookupd 配置 (nsqlookupd.conf)

### 核心参数

| 参数 | 默认值 | 说明 |
|-----|--------|------|
| `log-level` | info | 日志级别 |
| `inactive-producer-timeout` | 300s | 生产者不活跃超时时间 |
| `tombstone-lifetime` | 45s | 墓碑生命周期（已删除主题/频道标记） |

### 3.1 调整建议

NSQLookupd 是轻量级组件，大部分场景使用默认配置即可。

如果 nsqd 节点经常掉线重连：

```conf
inactive-producer-timeout=600s  # 增加到 10 分钟
```

## 4. NSQAdmin 配置 (nsqadmin.conf)

### 4.1 核心参数

| 参数 | 默认值 | 说明 |
|-----|--------|------|
| `log-level` | info | 日志级别 |
| `notification-http-endpoint` | - | HTTP 通知端点 |
| `base-path` | / | 基础 URL（反向代理时使用） |

### 4.2 反向代理配置

如果通过 Nginx 反向代理访问 NSQAdmin：

```conf
base-path=/nsqadmin
```

对应的 Nginx 配置：

```nginx
location /nsqadmin/ {
    proxy_pass http://nsqadmin:4171/;
}
```

### 4.3 通知集成

配置 Webhook 接收管理操作通知：

```conf
notification-http-endpoint=http://your-webhook-service/nsq-notifications
```

## 5. 配置优先级

配置的优先级从高到低：

1. **命令行参数** - 在 `docker-compose.yml` 的 `command` 中指定
2. **配置文件** - 在 `.conf` 文件中指定
3. **默认值** - NSQ 内置的默认值

例如，在 `override.yml` 中：

```yaml
command: /nsqd --config=/etc/nsq/nsqd.conf --broadcast-address=${NODE_D_IP}
```

这里 `--broadcast-address` 会覆盖配置文件中的设置。

## 6. 修改配置

### 6.1 修改配置文件

1. 编辑对应的 `.conf` 文件
2. 重启服务：

```bash
docker compose restart nsqd
# 或
docker restart nsqd
```

### 6.2 查看当前配置

```bash
# 查看容器内的配置文件
docker exec nsqd cat /etc/nsq/nsqd.conf

# 查看运行时参数
docker logs nsqd | head -20
```

## 7. 配置示例

### 7.1 生产环境配置 (nsqd.conf)

```conf
# 日志
log-level=info

# 性能
mem-queue-size=20000
max-msg-size=2097152  # 2MB
msg-timeout=120s
max-msg-timeout=30m

# 持久化
data-path=/data
sync-every=5000
sync-timeout=5s

# 客户端
max-rdy-count=5000
client-timeout=120s
heartbeat-interval=30s

# 压缩
deflate=true
max-deflate-level=6
snappy=true

# 统计
e2e-processing-latency-percentile=1.0,0.99,0.95
```

### 7.2 开发环境配置 (nsqd.conf)

```conf
# 日志
log-level=debug

# 性能（较小的值，便于测试）
mem-queue-size=1000
max-msg-size=1048576
msg-timeout=60s

# 持久化
data-path=/data
sync-every=1000

# 客户端
max-rdy-count=2500
```

## 8. 配置验证

### 8.1语法检查

NSQ 没有内置的配置验证工具，但可以通过启动来验证：

```bash
# 测试启动（如果配置有误会报错）
docker compose up nsqd
```

### 8.2 配置对比

查看默认配置和当前配置的差异：

```bash
# 查看默认配置
docker run --rm nsqio/nsq:v1.3.0 /nsqd --help

# 查看当前配置
docker exec nsqd cat /etc/nsq/nsqd.conf
```

## 9. 常见配置问题

### 9.1 问题 1: 消息持续堆积

**原因**: `mem-queue-size` 太小或消费者处理太慢

**解决**:

```conf
# 增加内存队列
mem-queue-size=50000

# 增加超时时间
msg-timeout=300s
```

### 9.2 问题 2: 内存占用过高

**原因**: `mem-queue-size` 设置过大

**解决**:

```conf
# 减小内存队列，增加磁盘使用
mem-queue-size=5000
sync-every=2000
```

### 9.3 问题 3: 消息丢失

**原因**: 同步到磁盘不够频繁

**解决**:

```conf
# 增加同步频率
sync-every=1000
sync-timeout=2s
```

### 问题 4: 磁盘 I/O 过高

**原因**: 同步到磁盘过于频繁

**解决**:

```conf
# 减少同步频率，增加内存队列
mem-queue-size=20000
sync-every=5000
```

## 10. 监控配置效果

查看配置效果的关键指标：

```bash
# 查看统计信息
curl http://localhost:4151/stats?format=json | jq '.topics[] | {
  topic_name,
  depth,           # 队列深度
  message_count,   # 消息总数
  e2e_processing_latency  # 端到端延迟
}'
```

## 11. 配置备份

建议将配置文件纳入版本控制：

```bash
git add components/nsq/*.conf
git commit -m "Update NSQ configuration"
```

## 12. 参考资料

- [NSQd 配置文档](https://nsq.io/components/nsqd.html)
- [NSQLookupd 配置文档](https://nsq.io/components/nsqlookupd.html)
- [NSQAdmin 配置文档](https://nsq.io/components/nsqadmin.html)
- [NSQ 性能调优](https://nsq.io/deployment/performance.html)
