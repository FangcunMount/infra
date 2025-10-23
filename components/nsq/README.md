# NSQ 组件配置

## 概述

NSQ 是一个实时分布式消息平台，用于在大规模环境中处理消息。

## 组件结构

```
nsq/
├── override.yml          # Docker Compose 配置
├── nsqd.conf            # NSQd 配置文件
├── nsqlookupd.conf      # NSQLookupd 配置文件
├── nsqadmin.conf        # NSQAdmin 配置文件
└── README.md            # 本文件
```

## 服务组件

### 1. nsqlookupd
- **端口**: 4160 (TCP), 4161 (HTTP)
- **作用**: 服务发现和拓扑信息管理

### 2. nsqd
- **端口**: 4150 (TCP), 4151 (HTTP)
- **作用**: 消息守护进程，负责消息的接收、队列和传递
- **数据持久化**: `/data` 目录

### 3. nsqadmin
- **端口**: 4171 (HTTP)
- **作用**: Web 管理界面，用于监控和管理 NSQ 集群

## 快速开始

### 启动服务

```bash
# 使用组件安装脚本
bash scripts/components/install.sh

# 或使用 Makefile
make install-nsq
```

### 访问管理界面

```
http://localhost:4171
```

### 发送测试消息

```bash
# HTTP API 方式
curl -d 'test message' 'http://localhost:4151/pub?topic=test_topic'

# 查看所有主题
curl http://localhost:4161/topics
```

### 消费消息

```bash
# 使用 nsq_tail 工具（需要安装 nsq 客户端工具）
nsq_tail --topic=test_topic --channel=test_channel --lookupd-http-address=localhost:4161
```

## 配置说明

### Docker Compose 配置

主要配置在 `override.yml` 中：

- **网络**: 使用 `infra-network` 网络
- **数据卷**: 
  - `infra_nsq_data`: NSQ 数据持久化
  - `infra_app_logs`: 日志存储
- **资源限制**: 
  - nsqd: 512M 内存，1 CPU
  - nsqlookupd/nsqadmin: 128M 内存，0.5 CPU

### NSQ 配置文件

每个组件都有对应的配置文件，可以根据需要调整：

#### nsqd.conf
主要配置项：
- `mem-queue-size`: 内存队列大小（默认 10000）
- `max-msg-size`: 单条消息最大大小（默认 1MB）
- `msg-timeout`: 消息超时时间（默认 60s）
- `data-path`: 数据存储路径
- `sync-every`: 同步到磁盘的频率

#### nsqlookupd.conf
主要配置项：
- `inactive-producer-timeout`: 生产者不活跃超时时间（默认 300s）
- `tombstone-lifetime`: 墓碑生命周期（默认 45s）

#### nsqadmin.conf
主要配置项：
- `notification-http-endpoint`: HTTP 通知端点
- `base-path`: 基础 URL（用于反向代理）

### 自定义配置

修改配置文件后重启服务：
```bash
docker compose restart nsqd
```

## 环境变量

在 `compose/env/prod/.env` 中配置：

```bash
# Server B IP（用于 nsqd 广播地址）
NODE_B_IP=192.168.1.20

# 时区
TZ=Asia/Shanghai
```

## 常用命令

```bash
# 查看服务状态
docker compose ps nsqlookupd nsqd nsqadmin

# 查看日志
docker compose logs -f nsqd

# 重启服务
docker compose restart nsqd

# 健康检查
curl http://localhost:4161/ping  # nsqlookupd
curl http://localhost:4151/ping  # nsqd
curl http://localhost:4171/ping  # nsqadmin
```

## 客户端示例

### Go

```go
import "github.com/nsqio/go-nsq"

// 生产者
config := nsq.NewConfig()
producer, _ := nsq.NewProducer("localhost:4150", config)
producer.Publish("topic", []byte("message"))

// 消费者
consumer, _ := nsq.NewConsumer("topic", "channel", config)
consumer.ConnectToNSQLookupd("localhost:4161")
```

### Python

```python
import nsq

# 生产者
writer = nsq.Writer(['localhost:4150'])
writer.pub('topic', 'message')

# 消费者
def handler(message):
    print(message.body)
    return True

r = nsq.Reader(
    message_handler=handler,
    nsqlookupd_http_addresses=['http://localhost:4161'],
    topic='topic',
    channel='channel'
)
```

## 参考文档

- [完整文档](../../docs/服务器组件--消息队列(NSQ).md)
- [NSQ 官方文档](https://nsq.io/)
