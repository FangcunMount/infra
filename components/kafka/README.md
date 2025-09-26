# Kafka 3.7 消息队列组件

## 📋 组件概述

提供高性能的 Apache Kafka 消息队列服务，采用 KRaft 模式 (无 Zookeeper)，专门部署在节点 B 进行流处理。

## 🔧 配置文件

- **override.yml**: Kafka 服务配置，包含 KRaft 模式和性能参数
- **server.properties.tmpl**: 配置模板 (如需要)

## 🌐 端口配置

- **Kafka Broker**: `${KAFKA_PORT:-9092}:9092`
- **Controller**: `9093` (内部端口)

## 📊 关键参数 (可通过环境变量调整)

- **内存分配**: `256M-512M` JVM 堆内存
- **消息保留**: `${KAFKA_RETENTION_MS:-86400000}` (24小时)
- **存储保留**: `${KAFKA_RETENTION_BYTES:-64424509440}` (60GB)
- **分段大小**: `67108864` (64MB)
- **广告地址**: `${KAFKA_ADVERTISED:-0.0.0.0}` (节点B IP)

## 💾 存储配置

- **数据目录**: `/data/kafka` (主题分区数据)
- **日志目录**: `/data/logs/kafka`
- **压缩算法**: `snappy` (默认)
- **清理策略**: `delete` (超时删除)

## 🚀 启动与管理

```bash
# 列出主题
docker exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --list

# 创建主题
docker exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --create --topic test-topic --partitions 1 --replication-factor 1

# 查看主题详情
docker exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic test-topic

# 删除主题
docker exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --delete --topic test-topic
```

## 📋 健康检查

- **主题列表**: `kafka-topics.sh --list` 每 30 秒
- **启动容忍**: 30 秒预热时间
- **重试次数**: 3 次

## 🔧 性能监控

```bash
# 查看 Broker 信息
docker exec kafka kafka-broker-api-versions.sh --bootstrap-server localhost:9092

# 查看消费者组
docker exec kafka kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list

# 查看消费者组详情
docker exec kafka kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group group-name

# 查看日志大小
docker exec kafka kafka-log-dirs.sh --bootstrap-server localhost:9092 --describe

# 性能基准测试
docker exec kafka kafka-producer-perf-test.sh --topic test-topic --num-records 1000 --record-size 1000 --throughput 100 --producer-props bootstrap.servers=localhost:9092
```

## 📈 性能调优建议

### 内存不足时的调整

```bash
# 降低 JVM 堆内存
KAFKA_HEAP_OPTS=-Xms128m -Xmx256m

# 减少保留时间
KAFKA_RETENTION_MS=43200000  # 12小时

# 减少存储限制
KAFKA_RETENTION_BYTES=32212254720  # 30GB
```

### 高并发优化

```bash
# 增加内存
KAFKA_HEAP_OPTS=-Xms512m -Xmx1g

# 增加分区数
--partitions 3

# 调整批次大小
batch.size=32768
linger.ms=5
```

## 🔄 备份与恢复

```bash
# 导出主题数据 (使用 kafka-console-consumer)
docker exec kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic topic-name \
  --from-beginning \
  --max-messages 1000 > topic_backup.txt

# 导入主题数据 (使用 kafka-console-producer)  
docker exec -i kafka kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic topic-name < topic_backup.txt

# 主题配置备份
docker exec kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe --topic topic-name > topic_config.txt
```

## 🚨 故障排除

```bash
# 查看错误日志
docker logs kafka
tail -f /data/logs/kafka/server.log

# 检查磁盘使用  
du -sh /data/kafka

# 检查网络连接
docker exec kafka netstat -tlnp | grep 9092

# 检查 JVM 内存
docker exec kafka jps -v

# 验证配置
docker exec kafka kafka-configs.sh --bootstrap-server localhost:9092 --entity-type brokers --entity-name 1 --describe
```

## 📊 主题管理

```bash
# 修改主题配置
docker exec kafka kafka-configs.sh \
  --bootstrap-server localhost:9092 \
  --entity-type topics \
  --entity-name topic-name \
  --alter --add-config retention.ms=3600000

# 增加分区数 (不可减少)
docker exec kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter --topic topic-name --partitions 3

# 查看主题消费滞后
docker exec kafka kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group group-name
```

## 🔧 双节点配置

- **节点 B**: 运行 Kafka 主实例，处理消息队列
- **节点 A**: 应用通过内网连接到节点 B 的 Kafka
- **连接字符串**: `${NODE_B_IP}:9092`
- **广告地址**: 必须设置为节点 B 的内网 IP

## 🌐 KRaft 模式 (无 Zookeeper)

Kafka 3.7+ 使用 KRaft 模式，无需 Zookeeper：

```bash
# Controller 相关配置
KAFKA_CFG_PROCESS_ROLES=controller,broker
KAFKA_CFG_CONTROLLER_QUORUM_VOTERS=1@kafka:9093
KAFKA_CFG_CONTROLLER_LISTENER_NAMES=CONTROLLER
```

## 🔒 生产环境安全

```bash
# 启用 SASL 认证 (可选)
KAFKA_CFG_SECURITY_INTER_BROKER_PROTOCOL=SASL_PLAINTEXT
KAFKA_CFG_SASL_MECHANISM_INTER_BROKER_PROTOCOL=PLAIN

# 启用 SSL (可选)
KAFKA_CFG_LISTENERS=SSL://:9093,PLAINTEXT://:9092
KAFKA_CFG_SSL_KEYSTORE_LOCATION=/etc/kafka/ssl/keystore.jks
```

## 📱 应用集成示例

```python
# Python 客户端示例
from kafka import KafkaProducer, KafkaConsumer

# 生产者
producer = KafkaProducer(
    bootstrap_servers=[f'{NODE_B_IP}:9092'],
    value_serializer=lambda x: json.dumps(x).encode('utf-8')
)
producer.send('topic-name', {'key': 'value'})

# 消费者  
consumer = KafkaConsumer(
    'topic-name',
    bootstrap_servers=[f'{NODE_B_IP}:9092'],
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)
for message in consumer:
    print(message.value)
```

## 📝 变更记录

- 2024-09-26: 重构为组件化配置，专门部署到节点 B
- 2024-09-25: 采用 KRaft 模式，优化内存和存储配置
- 2024-09-24: 调整保留策略适配节点 B 磁盘限制