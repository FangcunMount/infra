# 服务器组件 - 消息队列 (NSQ)

## 概述

NSQ 是一个实时分布式消息平台，设计用于在大规模环境中处理数十亿条消息。本文档说明如何在 Server B 上部署和管理 NSQ 组件。

## 组件说明

NSQ 由三个核心组件组成：

### 1. nsqd
- **作用**: 消息守护进程，负责接收、队列和传递消息
- **端口**: 
  - 4150: TCP 接口（客户端连接）
  - 4151: HTTP 接口（管理和统计）
- **特点**: 
  - 去中心化，每个 nsqd 实例独立运行
  - 消息持久化到磁盘
  - 支持消息去重和重试

### 2. nsqlookupd
- **作用**: 服务发现，管理拓扑信息
- **端口**:
  - 4160: TCP 接口
  - 4161: HTTP 接口
- **特点**:
  - 提供运行时发现服务
  - 生产者和消费者通过它找到 nsqd
  - 轻量级，无状态

### 3. nsqadmin
- **作用**: Web 管理界面
- **端口**: 4171
- **特点**:
  - 实时查看主题和频道统计
  - 管理和监控消息队列
  - 清空队列、删除主题等操作

## 部署架构

NSQ 可以与其他消息队列服务一起部署，提供轻量级的实时消息传递。

```
消息队列服务
├── Kafka (9092) - 大数据流处理
└── NSQ 组件
    ├── nsqlookupd (4160/4161) - 服务发现
    ├── nsqd (4150/4151) - 消息服务
    └── nsqadmin (4171) - Web 管理
```

## 部署步骤

### 1. 配置环境变量

编辑环境配置文件 `compose/env/prod/.env`：

```bash
# NSQd 广播地址（服务器外网 IP）
NSQD_BROADCAST_ADDRESS=your_server_ip

# 时区设置
TZ=Asia/Shanghai
```

### 2. 安装 NSQ 组件

使用组件安装脚本：

```bash
cd /path/to/infra

# 交互式安装
bash scripts/components/install.sh

# 或直接使用 Makefile
make install-nsq
```

安装过程会按以下顺序启动服务：
1. NSQLookupd (先启动服务发现)
2. NSQd 和 NSQAdmin

### 3. 验证部署

检查服务状态：

```bash
# 查看所有容器状态
docker compose ps

# 检查 NSQ 服务健康状态
curl http://localhost:4161/ping  # nsqlookupd
curl http://localhost:4151/ping  # nsqd
curl http://localhost:4171/ping  # nsqadmin

# 查看注册的 nsqd 节点
curl http://localhost:4161/nodes
```

## 使用方式

### Web 管理界面

访问 NSQAdmin：
```
http://localhost:4171
```

功能包括：
- 查看所有主题（Topics）和频道（Channels）
- 实时消息统计
- 消息深度（队列中的消息数量）
- 暂停/恢复频道
- 清空队列

### 生产者（Producer）示例

#### Go 语言
```go
import "github.com/nsqio/go-nsq"

config := nsq.NewConfig()
producer, err := nsq.NewProducer("localhost:4150", config)
if err != nil {
    log.Fatal(err)
}

// 发布消息
err = producer.Publish("topic_name", []byte("message body"))
```

#### Python
```python
import nsq

# 发送消息
writer = nsq.Writer(['localhost:4150'])
writer.pub('topic_name', 'message body')
```

#### HTTP API
```bash
curl -d 'message body' 'http://localhost:4151/pub?topic=topic_name'
```

### 消费者（Consumer）示例

#### Go 语言
```go
import "github.com/nsqio/go-nsq"

config := nsq.NewConfig()
consumer, err := nsq.NewConsumer("topic_name", "channel_name", config)
if err != nil {
    log.Fatal(err)
}

consumer.AddHandler(nsq.HandlerFunc(func(message *nsq.Message) error {
    log.Printf("Got a message: %v", string(message.Body))
    return nil
}))

// 连接到 nsqlookupd
err = consumer.ConnectToNSQLookupd("localhost:4161")
```

#### Python
```python
import nsq

def handler(message):
    print(message.body)
    return True

r = nsq.Reader(
    message_handler=handler,
    nsqlookupd_http_addresses=['http://localhost:4161'],
    topic='topic_name',
    channel='channel_name',
    lookupd_poll_interval=15
)

nsq.run()
```

## 配置说明

### 配置文件

NSQ 支持配置文件和命令行参数两种配置方式，项目中为每个组件提供了配置文件：

- `components/nsq/nsqd.conf` - NSQd 配置
- `components/nsq/nsqlookupd.conf` - NSQLookupd 配置  
- `components/nsq/nsqadmin.conf` - NSQAdmin 配置

详细配置说明请参考：[NSQ 配置文档](../components/nsq/CONFIG.md)

### 常用配置项

#### NSQd 核心配置

```conf
# 内存队列大小（超过后写入磁盘）
mem-queue-size=10000

# 单条消息最大大小
max-msg-size=1048576

# 消息超时时间
msg-timeout=60s

# 数据存储路径
data-path=/data

# 同步到磁盘的频率
sync-every=2500
```

#### 配置修改

修改配置文件后重启服务：
```bash
docker compose restart nsqd
```

### 资源限制

在 `components/nsq/override.yml` 中配置：

```yaml
# nsqd - 主要消息处理服务
nsqd:
  deploy:
    resources:
      limits:
        memory: 512M
        cpus: '1.0'
      reservations:
        memory: 256M

# nsqlookupd - 轻量级服务发现
nsqlookupd:
  deploy:
    resources:
      limits:
        memory: 128M
        cpus: '0.5'

# nsqadmin - Web 界面
nsqadmin:
  deploy:
    resources:
      limits:
        memory: 128M
        cpus: '0.5'
```

### 数据持久化

NSQd 的数据目录：
- 容器内路径: `/data`
- 宿主机路径: Docker Volume `infra_nsq_data`
- 日志路径: Docker Volume `infra_app_logs`

### 网络配置

所有 NSQ 组件连接到 `infra-network` 网络，可以与其他基础设施服务通信。

## 管理操作

### 查看主题和频道

```bash
# 列出所有主题
curl http://localhost:4161/topics

# 查看主题详情
curl http://localhost:4161/lookup?topic=topic_name

# 查看 nsqd 统计信息
curl http://localhost:4151/stats?format=json
```

### 创建主题

主题会在第一次发布消息时自动创建，也可以手动创建：

```bash
curl -X POST http://localhost:4151/topic/create?topic=new_topic
```

### 删除主题

```bash
curl -X POST http://localhost:4151/topic/delete?topic=topic_name
```

### 清空频道消息

```bash
curl -X POST http://localhost:4151/channel/empty?topic=topic_name&channel=channel_name
```

### 暂停/恢复频道

```bash
# 暂停
curl -X POST http://localhost:4151/channel/pause?topic=topic_name&channel=channel_name

# 恢复
curl -X POST http://localhost:4151/channel/unpause?topic=topic_name&channel=channel_name
```

## 监控

### 健康检查

服务内置健康检查：
```bash
# nsqlookupd
curl http://localhost:4161/ping

# nsqd
curl http://localhost:4151/ping

# nsqadmin
curl http://localhost:4171/ping
```

### 统计信息

```bash
# nsqd 详细统计
curl http://localhost:4151/stats?format=json

# nsqlookupd 节点信息
curl http://localhost:4161/nodes
```

### 日志查看

```bash
# 查看所有 NSQ 服务日志
docker compose logs nsqlookupd nsqd nsqadmin

# 实时跟踪日志
docker compose logs -f nsqd

# 查看特定服务的最近日志
docker compose logs --tail=100 nsqadmin
```

## 性能调优

### NSQd 参数调优

可以在 `components/nsq/override.yml` 中添加更多命令行参数：

```yaml
nsqd:
  command: >
    /nsqd 
    --lookupd-tcp-address=nsqlookupd:4160
    --broadcast-address=${NODE_B_IP}
    --mem-queue-size=10000
    --max-msg-size=1048576
    --max-msg-timeout=15m
    --max-req-timeout=1h
    --msg-timeout=60s
```

常用参数说明：
- `--mem-queue-size`: 内存队列大小（超过后写入磁盘）
- `--max-msg-size`: 单条消息最大大小
- `--max-msg-timeout`: 消息最大超时时间
- `--msg-timeout`: 默认消息超时时间
- `--sync-every`: 同步到磁盘的消息数量

## 故障排除

### 问题 1: NSQd 无法连接到 NSQLookupd

**症状**: NSQd 启动后在 nsqlookupd 中看不到节点

**解决方案**:
```bash
# 检查网络连通性
docker exec nsqd ping nsqlookupd

# 检查 nsqlookupd 是否正常运行
curl http://localhost:4161/ping

# 查看 nsqd 日志
docker logs nsqd
```

### 问题 2: 消费者无法发现生产者

**症状**: Consumer 连接到 nsqlookupd 但找不到 nsqd

**解决方案**:
```bash
# 确认 nsqd 已注册到 nsqlookupd
curl http://localhost:4161/nodes

# 检查主题是否存在
curl http://localhost:4161/topics

# 确认 broadcast-address 配置正确
docker inspect nsqd | grep -i args
```

### 问题 3: 消息堆积

**症状**: 消息深度持续增长，消费者处理不过来

**解决方案**:
```bash
# 查看频道统计
curl http://localhost:4151/stats?format=json

# 增加消费者实例数
# 或者清空队列（注意：会丢失消息）
curl -X POST http://localhost:4151/channel/empty?topic=topic_name&channel=channel_name
```

### 问题 4: 磁盘空间不足

**症状**: NSQd 日志显示磁盘写入错误

**解决方案**:
```bash
# 检查磁盘使用情况
docker exec nsqd df -h /data

# 清理旧数据或增加磁盘空间
# 设置消息过期时间
curl -X PUT http://localhost:4151/config/nsqd -d '{"msg_timeout":"60s"}'
```

## 与 Kafka 的对比

| 特性 | NSQ | Kafka |
|-----|-----|-------|
| 架构 | 去中心化 | 分布式（需要 ZooKeeper/KRaft） |
| 消息顺序 | 无保证 | 分区内有序 |
| 持久化 | 支持 | 强持久化 |
| 性能 | 高（简单场景） | 高（大规模场景） |
| 运维复杂度 | 低 | 中等 |
| 适用场景 | 实时任务分发、异步处理 | 大数据流处理、日志收集 |

## 最佳实践

1. **主题命名**: 使用清晰的命名规范，如 `service_name.event_type`
2. **频道设计**: 每个消费者应用使用独立的频道名
3. **消息大小**: 保持消息体小于 1MB，大文件应通过引用传递
4. **错误处理**: 消费者应实现重试逻辑和死信队列
5. **监控**: 定期检查 nsqadmin 的消息深度和处理速率
6. **备份**: 定期备份 `/data/nsq` 目录的消息数据

## 参考资料

- [NSQ 官方文档](https://nsq.io/)
- [NSQ 设计文档](https://nsq.io/overview/design.html)
- [Go NSQ 客户端](https://github.com/nsqio/go-nsq)
- [Python NSQ 客户端](https://github.com/nsqio/pynsq)

## 相关文档

- [服务器组件--消息服务(Kafka)](./服务器组件--消息服务(Kafka).md)
- [服务器组件--网络&基础卷](./服务器组件--网络&基础卷.md)
- [服务器初始化--docker](./服务器初始化--docker.md)
