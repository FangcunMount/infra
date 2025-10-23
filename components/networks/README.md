# 共享网络定义

## 概述

此目录包含所有基础设施组件使用的共享网络定义。

## 网络说明

### infra-backend (基础设施网络)

- **用途**: 所有基础设施服务的内部通信网络
- **子网**: 172.20.0.0/16
- **网关**: 172.20.0.1
- **特性**:
  - 启用容器间通信 (ICC=true)
  - 基础设施服务（MySQL、Redis、Kafka、NSQ 等）互联
  - 业务应用可以加入此网络访问基础设施服务

### 设计理念

**为什么只有一个网络？**

- ✅ **业务层自治**: 每个业务应用创建自己的网络（如 `miniblog-network`）
- ✅ **跨网络访问**: 业务应用通过加入 `infra-backend` 网络来访问基础设施
- ✅ **简化架构**: 避免不必要的网络复杂度
- ✅ **灵活隔离**: 业务应用之间通过各自的网络自然隔离

**网络拓扑示例：**

```
infra-backend 网络
├── MySQL
├── Redis
├── MongoDB
├── Kafka
├── NSQ
└── Jenkins

miniblog-network 网络          qsapi-network 网络
├── miniblog 应用              ├── qsapi 应用
└─[加入]→ infra-backend       └─[加入]→ infra-backend
```

## 使用方式

在启动任何组件之前，需要先创建这些网络：

```bash
# 使用初始化脚本
bash scripts/components/init-infrastructure.sh create

# 或手动创建
cd components/networks
docker compose up -d
```

## 数据卷说明

**数据卷已分散到各组件！** 每个组件在自己的 `docker-compose.yml` 中声明所需的数据卷：

- `components/mysql/` - 声明 `infra_mysql_data`
- `components/redis/` - 声明 `infra_redis_data`
- `components/mongo/` - 声明 `infra_mongo_data`
- `components/kafka/` - 声明 `infra_kafka_data`
- `components/nsq/` - 声明 `infra_nsq_data`
- `components/jenkins/` - 声明 `infra_jenkins_data`
- `components/nginx/` - 声明 `infra_nginx_logs`

这样设计的好处：
- ✅ 组件完全自包含
- ✅ 数据卷生命周期跟随组件
- ✅ 易于理解和维护
- ✅ 组件可独立迁移

## 注意事项

- 网络是唯一的共享资源，在删除前请确保所有服务已停止
- 数据卷由各组件管理，删除组件时会提示是否删除数据
