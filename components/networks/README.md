# 共享网络定义

## 概述

此目录包含所有基础设施组件使用的共享网络定义。

**🌐 现在支持 Docker Swarm Overlay 网络,实现跨主机容器通信!**

## 网络说明

### infra-network (基础设施网络)

- **驱动**: overlay (支持跨主机通信)
- **用途**: 所有基础设施服务的内部通信网络
- **子网**: 172.20.0.0/16
- **MTU**: 1450 (overlay 推荐值)
- **特性**:
  - ✅ 跨主机容器直接通信
  - ✅ attachable: 允许非 swarm 服务连接
  - ✅ 基础设施服务（MongoDB、Redis、NSQ 等）互联
  - ✅ 业务应用可以加入此网络访问基础设施服务
  - 🔒 可选加密传输 (encrypted: false 默认,可改为 true)

### 设计理念

**为什么使用 Docker Swarm Overlay?**

- ✅ **跨主机通信**: ServerA 和 ServerB 的容器可以直接通信
- ✅ **服务发现**: 容器间通过服务名访问,自动 DNS 解析
- ✅ **无需端口映射**: 不需要暴露服务端口到宿主机
- ✅ **简化配置**: 不需要配置跨主机网络的复杂路由
- ✅ **动态扩展**: 可轻松添加更多节点

**网络拓扑示例：**

```text
                   Docker Swarm Overlay Network
                      (infra-network)
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
    ServerA                                 ServerB
        │                                       │
   ┌────┴────┐                            ┌────┴────┐
   │ MySQL   │                            │  NSQ    │
   │ Redis   │◄──────容器直接通信──────────►│ nsqd   │
   │ MongoDB │                            │ lookup  │
   └─────────┘                            └─────────┘
        │                                       │
   ┌────┴────┐                            ┌────┴────┐
   │ miniblog│                            │  qsapi  │
   │  应用   │                            │   应用   │
   └─────────┘                            └─────────┘
```

**业务应用网络示例：**

```text
ServerA:
  miniblog-network 网络          
  ├── miniblog 应用              
  └─[加入]→ infra-network (访问 MySQL/Redis)

ServerB:
  qsapi-network 网络
  ├── qsapi 应用
  └─[加入]→ infra-network (访问 NSQ/MongoDB)
```

## 使用方式

### 前提条件

**必须先初始化 Docker Swarm 集群!**

```bash
# 1. 在 ServerA (管理节点) 上初始化
sudo ./scripts/network/swarm-manager.sh init-manager

# 2. 获取加入令牌
sudo ./scripts/network/swarm-manager.sh get-join-token

# 3. 在 ServerB (工作节点) 上加入集群
sudo ./scripts/network/swarm-manager.sh init-worker <ServerA-IP> <join-token>

# 4. 验证集群状态 (在管理节点)
sudo ./scripts/network/swarm-manager.sh status
```

### 创建网络

在 Swarm 初始化完成后,创建 overlay 网络：

```bash
# 方式1: 使用初始化脚本 (推荐)
bash scripts/components/init-infrastructure.sh create

# 方式2: 使用 Swarm 管理脚本
sudo ./scripts/network/swarm-manager.sh create-network

# 方式3: 手动创建
cd components/networks
docker compose up -d
```

### 验证网络

```bash
# 查看网络信息
docker network inspect infra-network

# 测试跨主机连通性
sudo ./scripts/network/swarm-manager.sh test
```

## 数据卷说明

**数据卷已分散到各组件！** 每个组件在自己的 `docker-compose.yml` 中声明所需的数据卷：

- `components/mysql/` - 声明 `infra_mysql_data`
- `components/redis/` - 声明 `infra_redis_data`
- `components/mongo/` - 声明 `infra_mongo_data`
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
