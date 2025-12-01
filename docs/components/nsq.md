# NSQ 消息队列

## 概述

NSQ 是一个实时分布式消息平台,设计用于处理大规模消息传递。本项目将 NSQ 部署在 ServerB (112.126.82.123),提供轻量级、高性能的消息队列服务。

## 组件架构

NSQ 由三个核心组件组成:

```text
┌─────────────────────────────────────┐
│           ServerB (2C4G)            │
│        112.126.82.123               │
│                                     │
│  ┌─────────────────────────────┐   │
│  │      nsqlookupd             │   │
│  │    服务发现 (无状态)         │   │
│  │  TCP:4160  HTTP:4161        │   │
│  └──────────┬──────────────────┘   │
│             │                       │
│  ┌──────────▼──────────────────┐   │
│  │        nsqd                 │   │
│  │    消息存储和传递            │   │
│  │  TCP:4150  HTTP:4151        │   │
│  │  Memory: 512MB              │   │
│  └─────────────────────────────┘   │
│                                     │
│  ┌─────────────────────────────┐   │
│  │      nsqadmin               │   │
│  │    Web管理界面 (127.0.0.1)  │   │
│  │       :4171                 │   │
│  └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

### 1. nsqlookupd - 服务发现

**作用**: 管理NSQ拓扑信息,提供服务发现

**端口**:

- `4160/tcp` - TCP接口
- `4161/tcp` - HTTP接口

**特点**:

- 轻量级,无状态
- 生产者和消费者通过它找到nsqd
- 多个nsqlookupd实例提供高可用

**资源配置**:

```yaml
CPU: 0.05核
内存: 32MB
```

### 2. nsqd - 消息守护进程

**作用**: 接收、队列化和传递消息

**端口**:

- `4150/tcp` - TCP接口 (客户端连接)
- `4151/tcp` - HTTP API (管理和统计)

**特点**:

- 去中心化,每个实例独立运行
- 消息持久化到磁盘
- 支持消息重试和去重
- 内存队列 + 磁盘持久化

**资源配置**:

```yaml
CPU: 0.80核
内存: 512MB (限制)
内存队列: 3000条消息
最大消息: 256KB
```

**优化配置** (针对2C4G):

- `mem-queue-size`: 3000 (减少内存使用)
- `max-msg-size`: 262144 (256KB)
- `msg-timeout`: 60s
- `sync-every`: 2500

### 3. nsqadmin - Web管理界面

**作用**: 实时监控和管理NSQ

**端口**:

- `4171/tcp` - Web界面 (仅 127.0.0.1)

**访问方式**:

```bash
# 使用SSH隧道访问
make nsq-admin

# 或手动创建隧道
ssh -L 4171:localhost:4171 user@112.126.82.123

# 浏览器访问
http://localhost:4171
```

**功能**:

- 查看主题(Topics)和频道(Channels)
- 实时消息统计
- 消息深度(队列中的消息数)
- 暂停/恢复频道
- 清空队列

## 部署配置

### 环境变量

`compose/env/prod/env`:

```bash
# NSQ配置
NSQLOOKUPD_TCP_PORT=4160
NSQLOOKUPD_HTTP_PORT=4161

NSQD_TCP_PORT=4150
NSQD_HTTP_PORT=4151
NSQD_BROADCAST_ADDRESS=112.126.82.123  # ServerB IP

NSQADMIN_HTTP_PORT=4171

# 资源限制
NSQD_MEM_LIMIT=512m
NSQD_CPU_LIMIT=0.80
NSQLOOKUPD_MEM_LIMIT=32m
NSQLOOKUPD_CPU_LIMIT=0.05
NSQADMIN_MEM_LIMIT=32m
NSQADMIN_CPU_LIMIT=0.05
```

### Docker Compose 配置

`components/nsq/docker-compose.yml`:

```yaml
version: '3.8'

services:
  nsqlookupd:
    image: nsqio/nsq:v1.3.0
    container_name: nsqlookupd
    command: /nsqlookupd
    ports:
      - "${NSQLOOKUPD_TCP_PORT:-4160}:4160"
      - "${NSQLOOKUPD_HTTP_PORT:-4161}:4161"
    networks:
      - infra-network
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: ${NSQLOOKUPD_MEM_LIMIT:-32m}
          cpus: '${NSQLOOKUPD_CPU_LIMIT:-0.05}'
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "3"

  nsqd:
    image: nsqio/nsq:v1.3.0
    container_name: nsqd
    command: >
      /nsqd 
      --lookupd-tcp-address=nsqlookupd:4160
      --broadcast-address=${NSQD_BROADCAST_ADDRESS}
      --config=/etc/nsq/nsqd.conf
    ports:
      - "${NSQD_TCP_PORT:-4150}:4150"
      - "${NSQD_HTTP_PORT:-4151}:4151"
    volumes:
      - nsq_data:/data
      - ./nsqd.conf:/etc/nsq/nsqd.conf:ro
    networks:
      - infra-network
    depends_on:
      - nsqlookupd
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: ${NSQD_MEM_LIMIT:-512m}
          cpus: '${NSQD_CPU_LIMIT:-0.80}'
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "3"

  nsqadmin:
    image: nsqio/nsq:v1.3.0
    container_name: nsqadmin
    command: /nsqadmin --lookupd-http-address=nsqlookupd:4161
    ports:
      - "127.0.0.1:${NSQADMIN_HTTP_PORT:-4171}:4171"
    networks:
      - infra-network
    depends_on:
      - nsqlookupd
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: ${NSQADMIN_MEM_LIMIT:-32m}
          cpus: '${NSQADMIN_CPU_LIMIT:-0.05}'
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "3"

volumes:
  nsq_data:
    external: true

networks:
  infra-network:
    external: true
```

### nsqd 配置文件

`components/nsq/nsqd.conf`:

```conf
## 消息配置
mem-queue-size = 3000
max-msg-size = 262144
msg-timeout = "60s"

## 持久化配置
data-path = "/data"
sync-every = 2500
sync-timeout = "2s"

## 客户端配置
max-heartbeat-interval = "60s"
max-rdy-count = 2500
max-req-timeout = "1h"

## 性能配置
max-body-size = 5242880
max-bytes-per-file = 104857600

## 日志配置
log-level = "info"
verbose = false

## TLS配置 (未启用)
tls-cert = ""
tls-key = ""
```

## 使用指南

### 启动和停止

```bash
# 启动 NSQ
make nsq-start

# 停止 NSQ
make nsq-stop

# 重启 NSQ
make nsq-restart

# 查看状态
make nsq-status

# 查看日志
make nsq-logs
```

### 管理命令

```bash
# 打开 Web 管理界面 (SSH隧道)
make nsq-admin

# 进入 nsqd 容器
make nsq-shell

# 查看主题列表
make nsq-topics

# 查看统计信息
make nsq-stats
```

### 生产者示例

#### HTTP API (最简单)

```bash
# 发布单条消息
curl -d 'message content' 'http://112.126.82.123:4151/pub?topic=test'

# 发布多条消息
curl -d 'msg1
msg2
msg3' 'http://112.126.82.123:4151/mpub?topic=test&binary=true'
```

#### Go 语言

```go
package main

import (
    "github.com/nsqio/go-nsq"
    "log"
)

func main() {
    config := nsq.NewConfig()
    producer, err := nsq.NewProducer("112.126.82.123:4150", config)
    if err != nil {
        log.Fatal(err)
    }

    // 发布消息
    err = producer.Publish("test_topic", []byte("Hello NSQ!"))
    if err != nil {
        log.Fatal(err)
    }

    producer.Stop()
}
```

#### Python

```python
import nsq

# 创建写入器
writer = nsq.Writer(['112.126.82.123:4150'])

# 发送消息
writer.pub('test_topic', b'Hello NSQ!')

# 关闭连接
writer.close()
```

### 消费者示例

#### Go 语言

```go
package main

import (
    "github.com/nsqio/go-nsq"
    "log"
    "time"
)

type MessageHandler struct{}

func (h *MessageHandler) HandleMessage(m *nsq.Message) error {
    log.Printf("Received: %s", string(m.Body))
    return nil
}

func main() {
    config := nsq.NewConfig()
    consumer, err := nsq.NewConsumer("test_topic", "channel1", config)
    if err != nil {
        log.Fatal(err)
    }

    consumer.AddHandler(&MessageHandler{})

    // 连接到 nsqlookupd
    err = consumer.ConnectToNSQLookupd("112.126.82.123:4161")
    if err != nil {
        log.Fatal(err)
    }

    // 等待
    select {}
}
```

#### Python

```python
import nsq

def handler(message):
    print(f"Received: {message.body}")
    return True

r = nsq.Reader(
    message_handler=handler,
    nsqlookupd_http_addresses=['http://112.126.82.123:4161'],
    topic='test_topic',
    channel='channel1',
    lookupd_poll_interval=15
)

nsq.run()
```

### HTTP API 管理

#### 查看主题

```bash
# 列出所有主题
curl http://112.126.82.123:4161/topics

# 查看主题详情
curl http://112.126.82.123:4161/lookup?topic=test_topic
```

#### 创建主题

```bash
# 主题会在第一次发布时自动创建
# 也可以手动创建
curl -X POST http://112.126.82.123:4151/topic/create?topic=new_topic
```

#### 删除主题

```bash
curl -X POST http://112.126.82.123:4151/topic/delete?topic=old_topic
```

#### 管理频道

```bash
# 创建频道
curl -X POST http://112.126.82.123:4151/channel/create?topic=test&channel=ch1

# 删除频道
curl -X POST http://112.126.82.123:4151/channel/delete?topic=test&channel=ch1

# 清空频道消息
curl -X POST http://112.126.82.123:4151/channel/empty?topic=test&channel=ch1

# 暂停频道
curl -X POST http://112.126.82.123:4151/channel/pause?topic=test&channel=ch1

# 恢复频道
curl -X POST http://112.126.82.123:4151/channel/unpause?topic=test&channel=ch1
```

#### 查看统计信息

```bash
# nsqd 统计
curl http://112.126.82.123:4151/stats?format=json

# nsqlookupd 节点信息
curl http://112.126.82.123:4161/nodes

# 健康检查
curl http://112.126.82.123:4151/ping
curl http://112.126.82.123:4161/ping
```

## 监控和维护

### 关键指标

通过nsqadmin或API监控以下指标:

```yaml
消息深度: 队列中待处理的消息数
处理速率: 每秒消费的消息数
消费者数量: 连接的消费者实例
内存使用: nsqd进程内存占用
磁盘使用: /data目录大小
错误率: 消息处理失败比例
```

### 健康检查

```bash
# 检查服务健康
curl http://112.126.82.123:4151/ping  # nsqd
curl http://112.126.82.123:4161/ping  # nsqlookupd

# 查看统计信息
curl http://112.126.82.123:4151/stats?format=json
```

### 日志管理

```bash
# 查看所有NSQ日志
make nsq-logs

# 实时跟踪nsqd日志
docker logs -f nsqd

# 查看最近100行
docker logs --tail=100 nsqd
```

### 数据备份

```bash
# 备份nsqd数据
docker run --rm \
  -v infra_nsq_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/nsq-backup-$(date +%Y%m%d).tar.gz /data

# 恢复数据
docker run --rm \
  -v infra_nsq_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/nsq-backup-YYYYMMDD.tar.gz -C /
```

## 性能优化

### 针对2C4G服务器的优化

当前配置已针对ServerB (2C4G)优化:

1. **内存队列**: 3000条 (减少内存使用)
2. **消息大小**: 256KB (适合小消息)
3. **CPU限制**: 0.80核 (避免资源竞争)
4. **内存限制**: 512MB (防止OOM)
5. **日志轮转**: 100MB × 3文件

### 进一步优化建议

#### 高吞吐场景

```conf
mem-queue-size = 5000
max-msg-size = 524288  # 512KB
max-rdy-count = 5000
```

#### 低延迟场景

```conf
sync-every = 1000
msg-timeout = "30s"
```

#### 内存受限

```conf
mem-queue-size = 1000
max-body-size = 2097152  # 2MB
```

### 客户端优化

```go
config := nsq.NewConfig()
config.MaxInFlight = 200        // 并发处理数
config.MaxAttempts = 3          // 最大重试次数
config.DefaultRequeueDelay = time.Second * 90
config.DialTimeout = time.Second * 5
```

## 故障排查

### 问题1: nsqd无法连接到nsqlookupd

**症状**: nsqlookupd中看不到nsqd节点

**排查**:

```bash
# 检查网络连通
docker exec nsqd ping nsqlookupd

# 查看nsqd日志
docker logs nsqd | grep -i lookupd

# 检查nsqlookupd状态
curl http://112.126.82.123:4161/nodes
```

**解决**:

```bash
# 重启nsqd
docker restart nsqd

# 检查broadcast-address配置
docker inspect nsqd | grep broadcast
```

### 问题2: 消息堆积

**症状**: 消息深度持续增长

**排查**:

```bash
# 查看频道统计
curl http://112.126.82.123:4151/stats?format=json | jq

# 检查消费者连接
# 在nsqadmin界面查看消费者数量
```

**解决**:

```bash
# 1. 增加消费者实例
# 2. 优化消费者性能
# 3. 暂时暂停生产
# 4. 清空队列 (慎用,会丢消息)
curl -X POST http://112.126.82.123:4151/channel/empty?topic=xxx&channel=yyy
```

### 问题3: 内存不足

**症状**: nsqd容器重启,日志显示OOM

**排查**:

```bash
# 查看内存使用
docker stats nsqd

# 查看消息队列状态
curl http://112.126.82.123:4151/stats?format=json
```

**解决**:

```bash
# 1. 减小mem-queue-size
# 编辑 components/nsq/nsqd.conf
mem-queue-size = 2000

# 2. 增加内存限制
# 编辑 compose/env/prod/env
NSQD_MEM_LIMIT=1024m

# 3. 重启服务
make nsq-restart
```

### 问题4: 磁盘空间不足

**症状**: nsqd无法写入消息

**排查**:

```bash
# 检查磁盘使用
docker exec nsqd df -h /data

# 查看数据目录大小
docker run --rm -v infra_nsq_data:/data alpine du -sh /data
```

**解决**:

```bash
# 1. 清理旧主题
curl -X POST http://112.126.82.123:4151/topic/delete?topic=old_topic

# 2. 缩短消息超时时间
msg-timeout = "30s"

# 3. 扩展磁盘空间
```

## 最佳实践

### 主题和频道设计

1. **主题命名规范**:

   ```text
   <service>.<event>
   例如: user.registered, order.created
   ```

2. **频道命名规范**:

   ```text
   <consumer_service>
   例如: email-service, notification-service
   ```

3. **频道使用**:
   - 每个消费服务使用独立频道
   - 同一频道的多个消费者实现负载均衡

### 消息设计

1. **消息大小**: 保持 < 256KB
2. **消息格式**: 使用JSON或Protobuf
3. **消息ID**: 包含唯一标识符,便于追踪
4. **消息版本**: 包含版本号,支持向后兼容

示例:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "version": "1.0",
  "timestamp": 1704067200,
  "event": "user.registered",
  "data": {
    "user_id": 12345,
    "email": "user@example.com"
  }
}
```

### 错误处理

1. **重试机制**: 使用NSQ的自动重试 (`MaxAttempts`)
2. **死信队列**: 失败消息移到特定主题
3. **幂等性**: 消费者应实现幂等处理
4. **日志记录**: 记录所有错误和重试

### 监控告警

设置告警规则:

```yaml
消息深度 > 10000: 警告
消息深度 > 50000: 严重
消费延迟 > 60s: 警告
nsqd 内存 > 450MB: 警告
nsqd 重启: 通知
```

## 与Kafka对比

| 特性 | NSQ | Kafka |
|-----|-----|-------|
| **架构** | 去中心化 | 集中式 (需要ZooKeeper) |
| **复杂度** | 低 | 高 |
| **消息顺序** | 无保证 | 分区内有序 |
| **持久化** | 支持 | 强持久化 |
| **性能** | 高 (简单场景) | 极高 (复杂场景) |
| **横向扩展** | 简单 | 较复杂 |
| **适用场景** | 实时任务、异步处理 | 大数据流、日志采集 |
| **资源需求** | 低 (512MB) | 高 (2GB+) |

**选择建议**:

- ✅ **使用NSQ**: 实时通知、异步任务、简单消息队列
- ✅ **使用Kafka**: 日志聚合、流处理、大数据管道

## 相关文档

- [服务器架构](../server/architecture.md) - ServerB角色说明
- [网络架构](../network/architecture.md) - Overlay网络配置
- 使用 `make help-nsq` 查看 NSQ 管理命令

## 参考资料

- [NSQ官方文档](https://nsq.io/)
- [NSQ设计文档](https://nsq.io/overview/design.html)
- [Go NSQ客户端](https://github.com/nsqio/go-nsq)
- [Python NSQ客户端](https://github.com/nsqio/pynsq)

---

**更新时间**: 2025-01-24  
**NSQ版本**: v1.3.0  
**文档版本**: v1.0
