# 服务器组件 - 消息服务(Kafka)

> 📨 部署 Apache Kafka 分布式消息队列系统

## 🎯 消息服务目标

- 部署 Kafka 3.0+ 消息队列集群
- 配置 Zookeeper 协调服务
- 设置高可用性和数据持久化
- 建立消息监控和管理界面
- 配置安全认证和访问控制

## 🚀 自动化部署

### 一键 Kafka 部署

```bash
# 使用 compose-manager 脚本部署消息服务
./scripts/deploy/compose-manager.sh infra up message

# 自动完成：
# ✅ 部署 Zookeeper 集群
# ✅ 部署 Kafka 集群  
# ✅ 配置数据持久化
# ✅ 设置健康检查
# ✅ 部署管理界面(开发环境)
```

## 🔧 手动配置步骤

### 部署 Kafka 集群

```bash
# 启动 Zookeeper
docker run -d \
  --name zookeeper \
  --network infra-network \
  --restart unless-stopped \
  -e ZOOKEEPER_CLIENT_PORT=2181 \
  -e ZOOKEEPER_TICK_TIME=2000 \
  -v infra_zk_data:/var/lib/zookeeper/data \
  -v infra_zk_logs:/var/lib/zookeeper/log \
  confluentinc/cp-zookeeper:latest

# 启动 Kafka
docker run -d \
  --name kafka \
  --network infra-network \
  --restart unless-stopped \
  -e KAFKA_BROKER_ID=1 \
  -e KAFKA_ZOOKEEPER_CONNECT=zookeeper:2181 \
  -e KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092 \
  -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
  -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 \
  -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 \
  -e KAFKA_LOG_DIRS=/var/lib/kafka/data \
  -v infra_kafka_data:/var/lib/kafka/data \
  --health-cmd="kafka-broker-api-versions --bootstrap-server localhost:9092" \
  --health-interval=10s \
  --health-timeout=10s \
  --health-retries=3 \
  confluentinc/cp-kafka:latest

# 部署 Kafka UI (开发环境)
docker run -d \
  --name kafka-ui \
  --network infra-frontend \
  --restart unless-stopped \
  -p 8081:8080 \
  -e KAFKA_CLUSTERS_0_NAME=local \
  -e KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS=kafka:9092 \
  provectuslabs/kafka-ui:latest
```

## 📋 验证检查清单

### ✅ Kafka 服务验证

```bash
# 检查 Kafka 集群状态
docker exec kafka kafka-broker-api-versions --bootstrap-server localhost:9092

# 创建测试主题
docker exec kafka kafka-topics --bootstrap-server localhost:9092 --create --topic test-topic --partitions 1 --replication-factor 1

# 测试消息发送和接收
docker exec kafka kafka-console-producer --bootstrap-server localhost:9092 --topic test-topic <<< "test message"
docker exec kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic test-topic --from-beginning --timeout-ms 5000
```

## 🔄 下一步

消息服务部署完成后，继续部署：

1. [🔧 CI/CD服务](服务器组件--CI_CD(Jenkins).md) - 部署 Jenkins 平台
2. [🌐 网关服务](服务器组件--网关(Nginx).md) - 部署 Nginx 网关

---

> 💡 **Kafka 运维提醒**: 定期监控磁盘使用、清理过期日志、检查集群健康状态