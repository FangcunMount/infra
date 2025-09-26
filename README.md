# 🏗️ 组件化基础设施项目# 🏗️ 组件化基础设施项目



专用的基础设施服务项目，采用组件化架构设计，支持双节点分布式部署。专门为基础设施服务（数据库、缓存、消息队列等）而设计，不包含业务应用。专用的基础设施服务项目，采用组件化架构设计，支持双节点分布式部署。专门为基础设施服务（数据库、缓存、消息队列等）而设计，不包含业务应用。



## 🎯 项目特色## 🎯 项目特色



- **🏗️ 组件化设计**: 每个服务独立配置，清晰的组件边界- **🏗️ 组件化设计**: 每个服务独立配置，清晰的组件边界

- **🚀 双节点架构**: 节点 A (Web/事务侧) + 节点 B (计算侧)- **🚀 双节点架构**: 节点 A (Web/事务侧) + 节点 B (计算侧) 

- **📦 多文件编排**: Docker Compose 多文件架构，支持灵活组合- **📦 多文件编排**: Docker Compose 多文件架构，支持灵活组合

- **🔧 自动化部署**: 完整的部署脚本和管理命令- **🔧 自动化部署**: 完整的部署脚本和管理命令

- **🛡️ 安全优先**: SSL 证书管理、敏感数据保护、SOPS 就绪- **🛡️ 安全优先**: SSL 证书管理、敏感数据保护、SOPS 就绪

- **📊 生产就绪**: 健康检查、资源限制、日志管理- **📊 生产就绪**: 健康检查、资源限制、日志管理



## 🏗️ 架构概览## 🏗️ 分布式架构设计



```### 🌐 双机分布式拓扑图

   🌐 Internet

       │```mermaid

   [Load Balancer]graph TB

       │    subgraph "🌍 外部访问层"

   ┌───▼───────────────┐         ┌─────────────────────┐        USER[👤 用户请求]

   │    Node A         │◄────────┤      Node B         │        LB[🔄 负载均衡器<br/>可选]

   │   Web/事务侧      │         │     计算侧          │    end

   └───────────────────┘         └─────────────────────┘

       subgraph "🅰️ A 节点 (2C/4G) - Web/事务处理侧"

   📊 Services:              📊 Services:        subgraph "🌐 前端代理层"

   • nginx                   • kafka            NGINX[🌐 Nginx<br/>:80/:443<br/>128MB]

   • mysql                   • zookeeper          end

   • redis        

   • mongo        subgraph "🗄️ 存储/缓存集群"

```            MYSQL[🗄️ MySQL 8.0<br/>:3306<br/>1.2GB Pool]

            REDIS[💾 Redis 7.0<br/>:6379<br/>384MB Max]

## 📁 项目结构        end

        

```        subgraph "📱 轻业务应用层"

📦 shared-infra/            BLOG[📝 MiniBlog<br/>256MB]

├── 🐳 compose/            API[📊 QS-API<br/>256MB] 

│   ├── base/                   # 基础服务定义            COLLECT[📈 QS-Collection<br/>256MB]

│   │   └── docker-compose.yml        end

│   ├── nodes/                  # 节点特定配置    end

│   │   ├── a.override.yml      # 节点 A 覆盖

│   │   └── b.override.yml      # 节点 B 覆盖    subgraph "🅱️ B 节点 (2C/4G) - 计算/流处理侧"

│   └── env/        subgraph "🔄 消息/流处理"

│       └── prod/               # 生产环境配置            KAFKA[⚡ Kafka KRaft<br/>:9092<br/>256MB Heap]

├── 🔧 components/              # 组件配置        end

│   ├── nginx/                  # Nginx 配置        

│   ├── mysql/                  # MySQL 配置        subgraph "📊 文档数据库"

│   ├── redis/                  # Redis 配置            MONGO[🍃 MongoDB 7.0<br/>:27017<br/>1.0GB Cache<br/>+1.6GB 页缓存]

│   ├── mongo/                  # MongoDB 配置        end

│   └── kafka/                  # Kafka 配置        

├── 🚀 scripts/                 # 自动化脚本        subgraph "🧠 重计算应用"

│   ├── deploy_a.sh            # 节点 A 部署            EVAL[🔍 QS-Evaluation<br/>512MB<br/>2C CPU限制<br/>机器学习/数据分析]

│   └── deploy_b.sh            # 节点 B 部署        end

├── 📋 Makefile                 # 管理命令    end

├── 📖 QUICKSTART.md           # 快速开始指南

└── 🗂️ logs/                   # 日志目录    %% 用户访问流

```    USER --> LB

    LB --> NGINX

## 🚀 快速开始    USER -.-> NGINX



### 节点 A (Web/事务侧)    %% A节点内部连接

    NGINX --> BLOG

```bash    NGINX --> API  

# 1. 克隆并初始化    NGINX --> COLLECT

git clone <repo-url> shared-infra    BLOG --> MYSQL

cd shared-infra    BLOG --> REDIS

make init-node-a    API --> MYSQL

    API --> REDIS

# 2. 配置环境变量    COLLECT --> MYSQL

vim compose/env/prod/.env    COLLECT --> REDIS



# 3. 自动部署    %% 跨节点连接 (A -> B)

./scripts/deploy_a.sh    NGINX -.->|代理 /qs/eval/*| EVAL

```    API -.->|数据查询| MONGO

    COLLECT -.->|消息发送| KAFKA

### 节点 B (计算侧)    

    %% 跨节点连接 (B -> A)  

```bash    EVAL -.->|事务数据| MYSQL

# 1. 克隆并初始化    EVAL -.->|缓存查询| REDIS

git clone <repo-url> shared-infra    EVAL --> MONGO

cd shared-infra    EVAL --> KAFKA

make init-node-b

    %% 样式定义

# 2. 配置环境变量      classDef nodeA fill:#e1f5fe,stroke:#0277bd,stroke-width:2px

vim compose/env/prod/.env    classDef nodeB fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px

    classDef database fill:#fff3e0,stroke:#f57c00,stroke-width:2px

# 3. 自动部署    classDef app fill:#e8f5e8,stroke:#388e3c,stroke-width:2px

./scripts/deploy_b.sh    classDef proxy fill:#fce4ec,stroke:#c2185b,stroke-width:2px

```    classDef external fill:#f5f5f5,stroke:#616161,stroke-width:2px



## 🔧 管理命令    class NGINX,MYSQL,REDIS,BLOG,API,COLLECT nodeA

    class KAFKA,MONGO,EVAL nodeB  

```bash    class MYSQL,REDIS,MONGO,KAFKA database

# 查看帮助    class BLOG,API,COLLECT,EVAL app

make help    class NGINX,LB proxy

    class USER external

# 服务管理```

make status          # 查看服务状态

make logs           # 查看日志### 🔄 数据流向图

make down           # 停止服务

```mermaid

# 开发调试sequenceDiagram

make dev-start NODE=a SERVICE=nginx    participant U as 👤 用户

make dev-logs NODE=a SERVICE=mysql    participant N as 🌐 Nginx (A节点)

make dev-shell NODE=a SERVICE=redis    participant B as 📝 MiniBlog (A节点)  

    participant M as 🗄️ MySQL (A节点)

# 配置管理    participant R as 💾 Redis (A节点)

make config-validate    # 验证配置    participant E as 🔍 QS-Eval (B节点)

make config-show NODE=a # 显示配置    participant Mo as 🍃 MongoDB (B节点)

make ssl-setup DOMAIN=example.com    participant K as ⚡ Kafka (B节点)



# 维护工具    Note over U,K: 典型用户请求流

make backup-config     # 备份配置

make network-test     # 网络测试    %% 轻量级请求 (A节点处理)

```    U->>N: GET /blog/posts

    N->>B: 转发请求

## 📋 服务清单    B->>R: 检查缓存

    R-->>B: 缓存命中/未命中

### 节点 A 服务    alt 缓存未命中

        B->>M: 查询数据库

| 服务 | 端口 | 描述 | 资源限制 |        M-->>B: 返回数据

|------|------|------|----------|        B->>R: 更新缓存

| **nginx** | 80,443 | 反向代理 | 512MB |    end

| **mysql** | 3306 | 关系数据库 | 1GB |    B-->>N: 返回响应

| **redis** | 6379 | 缓存数据库 | 512MB |    N-->>U: 返回页面

| **mongo** | 27017 | 文档数据库 | 1GB |

    %% 重计算请求 (跨节点处理)  

### 节点 B 服务    U->>N: POST /qs/eval/analyze

    N->>E: 代理到B节点

| 服务 | 端口 | 描述 | 资源限制 |    E->>Mo: 获取原始数据

|------|------|------|----------|    Mo-->>E: 返回数据集

| **kafka** | 9092 | 消息队列 | 1GB |    E->>K: 发送处理任务

| **zookeeper** | 2181 | 协调服务 | 512MB |    Note over E: 🧠 机器学习算法处理

    E->>Mo: 保存结果

## 🛡️ 安全配置    E->>R: 缓存计算结果 (跨节点)

    E-->>N: 返回分析结果

### SSL 证书管理    N-->>U: 返回分析报告

```

```bash

# 1. 创建证书目录### 🌐 网络架构图

make ssl-setup DOMAIN=example.com

```mermaid

# 2. 放置证书文件graph LR

components/nginx/ssl/example.com/    subgraph "🌍 公网环境"

├── fullchain.pem    # 完整证书链        INTERNET[🌍 Internet]

└── privkey.pem      # 私钥文件        DNS[🔍 DNS解析]

```    end



### 敏感数据保护    subgraph "🔥 防火墙层"

        FW[�️ 防火墙<br/>仅开放 80/443]

```bash    end

# 已配置 .gitignore 忽略:

compose/env/prod/.env        # 环境变量    subgraph "🏢 内网环境 (192.168.1.0/24)"

components/nginx/ssl/        # SSL 证书        subgraph "🅰️ A节点 (192.168.1.10)"

components/mysql/data/       # 数据库文件            A_PUB[🌐 公网接口<br/>80/443]

components/redis/data/       # Redis 数据            A_PRIV[🔒 内网接口<br/>3306/6379]

```        end

        

### SOPS 加密支持        subgraph "🅱️ B节点 (192.168.1.11)" 

            B_PRIV[🔒 内网接口<br/>27017/9092/8080]

```bash        end

# 加密环境文件        

sops -e compose/env/prod/.env > .env.encrypted        subgraph "🔧 运维跳板机"

            JUMP[🖥️ 跳板机<br/>SSH管理]

# 解密使用        end

sops -d .env.encrypted > compose/env/prod/.env    end

```

    %% 网络连接

## 🔌 组件说明    INTERNET --> DNS

    DNS --> FW

### 多文件 Compose 架构    FW --> A_PUB

    

项目使用多层 Docker Compose 文件组织：    A_PUB -.->|跨节点代理| B_PRIV

    A_PRIV <-.->|内网通信<br/>MySQL/Redis| B_PRIV

1. **基础层** (`compose/base/docker-compose.yml`)    

   - 定义所有服务的基本配置    JUMP -.->|SSH 22| A_PRIV

   - 不包含端口映射和敏感信息    JUMP -.->|SSH 22| B_PRIV



2. **节点层** (`compose/nodes/*.override.yml`)    %% 网络样式

   - 节点 A: Web 服务配置    classDef public fill:#ffcdd2,stroke:#d32f2f,stroke-width:2px

   - 节点 B: 计算服务配置    classDef private fill:#c8e6c9,stroke:#388e3c,stroke-width:2px  

    classDef security fill:#fff3e0,stroke:#f57c00,stroke-width:2px

3. **组件层** (`components/*/override.yml`)    classDef management fill:#e1f5fe,stroke:#0277bd,stroke-width:2px

   - 每个组件的具体配置

   - 卷挂载和端口映射    class INTERNET,DNS,A_PUB public

    class A_PRIV,B_PRIV private

### 自动化部署    class FW security

    class JUMP management

部署脚本提供完整的自动化流程：```



- 环境检测和验证### �💡 架构设计理念

- 服务启动和健康检查

- 网络连通性测试```mermaid

- 错误处理和回滚mindmap

  root((🏗️ 分布式架构))

## 🔧 开发指南    🎯 负载分离

      事务 vs 计算

### 添加新组件      I/O特性隔离

      资源竞争避免

1. 在 `components/` 创建新目录    ⚡ 链路优化

2. 添加 `override.yml` 配置文件      服务就近部署

3. 更新相应节点的覆盖文件      网络延迟最小化

4. 测试配置：`make config-validate`      数据传输优化

    🔄 弹性扩展

### 自定义配置      独立扩展节点

      水平扩展支持

所有配置文件都支持自定义：      渐进式迁移

    🛡️ 故障隔离

```bash      单点故障容忍

# 修改组件配置      服务独立运行

vim components/nginx/nginx.conf      快速故障恢复

```

# 预览合成配置

make config-show NODE=a### 📊 资源分配策略



# 重新部署#### 内存分配可视化

make deploy-a

``````mermaid

%%{init: {'theme':'base', 'themeVariables': { 'pie1': '#ff6b6b', 'pie2': '#4ecdc4', 'pie3': '#45b7d1', 'pie4': '#96ceb4', 'pie5': '#feca57', 'pie6': '#ff9ff3', 'pie7': '#54a0ff', 'pie8': '#5f27cd'}}}%%

## 🐛 故障排查pie title A节点内存分配 (4GB)

    "MySQL 1.2GB" : 30

### 常见问题    "机动缓冲 920MB" : 23  

    "系统预留 600MB" : 15

```bash    "Redis 384MB" : 9.6

# 1. 服务启动失败    "MiniBlog 256MB" : 6.4

make config-validate  # 检查配置    "QS-API 256MB" : 6.4

make logs SERVICE=mysql # 查看错误日志    "QS-Collection 256MB" : 6.4

    "Nginx 128MB" : 3.2

# 2. 网络连接问题  ```

make network-test     # 测试网络

```mermaid

# 3. 端口冲突%%{init: {'theme':'base', 'themeVariables': { 'pie1': '#a8e6cf', 'pie2': '#dcedc1', 'pie3': '#ffd3a5', 'pie4': '#fd8a85', 'pie5': '#c7ceea', 'pie6': '#f8b195'}}}%%

netstat -tulpn | grep :80  # 检查端口占用pie title B节点内存分配 (4GB)

```    "页缓存优化 1.6GB" : 40

    "MongoDB 1.0GB" : 25

### 日志管理    "系统预留 600MB" : 15

    "QS-Evaluation 512MB" : 12.8

```bash    "Kafka 256MB" : 6.4

# 查看服务日志    "机动缓冲 32MB" : 0.8

make logs SERVICE=nginx```



# 查看实时日志#### CPU 资源分配

make dev-logs NODE=a SERVICE=mysql

```mermaid

# 日志文件位置gantt

ls logs/    title CPU 资源分配时间线 (2C/4G 每节点)

```    dateFormat X

    axisFormat %s

## 📈 性能优化

    section A节点 (Web侧)

### 资源配置    系统进程     :active, sys-a, 0, 1

    Nginx       :active, nginx, 0, 2  

每个服务都配置了合理的资源限制：    MySQL       :active, mysql, 0, 2

    轻业务应用   :active, apps-a, 0, 2

```yaml

deploy:    section B节点 (计算侧)  

  resources:    系统进程     :active, sys-b, 0, 1

    limits:    MongoDB I/O  :active, mongo, 0, 1

      memory: 1G    QS-Evaluation:crit, eval, 0, 2

      cpus: '0.5'    Kafka       :active, kafka, 0, 1

    reservations:```

      memory: 512M

```#### 详细资源配置



### 监控建议##### 🅰️ A 节点 (Web/事务侧) - 4GB 内存分配



- 使用 `docker stats` 监控资源使用- **系统预留**: 600MB (OS + 网络栈)

- 配置日志轮转防止磁盘占满- **MySQL**: 1.2GB (InnoDB Buffer Pool)  

- 定期清理未使用的镜像和容器- **Redis**: 384MB (缓存 + AOF持久化)

- **Nginx**: 128MB (代理 + 连接池)

## 🤝 贡献指南- **MiniBlog**: 256MB (个人博客)

- **QS-API**: 256MB (接口服务)

1. Fork 项目- **QS-Collection**: 256MB (数据收集)

2. 创建特性分支- **机动缓冲**: 920MB (页缓存 + swap预留)

3. 提交更改

4. 推送到分支##### 🅱️ B 节点 (计算/流侧) - 4GB 内存分配

5. 创建 Pull Request

- **系统预留**: 600MB (OS + 文件系统缓存)

## 📄 许可证- **MongoDB**: 1.0GB (WiredTiger Cache)

- **Kafka**: 256MB (JVM Heap)

此项目基于 MIT 许可证开源。- **QS-Evaluation**: 512MB (机器学习算法)

- **页缓存优化**: 1.6GB (MongoDB 文件I/O加速)

---- **机动缓冲**: 32MB (系统突发)



📚 **更多信息**: 查看 [QUICKSTART.md](./QUICKSTART.md) 获取详细的使用指南## 🚀 快速开始

### 🏗️ 部署架构选择

#### 🌐 双机分布式部署 (生产推荐)

- **节点 A** (Web/事务侧): 2核4G + 100GB磁盘 + 公网IP
  - 服务: Nginx, MySQL, Redis, MongoDB, MiniBlog, QS-API, QS-Collection, Jenkins
- **节点 B** (计算/流侧): 2核4G + 100GB磁盘 + 内网IP  
  - 服务: Kafka, QS-Evaluation
- **网络**: 千兆内网互联 (延迟 < 1ms)

#### 📦 单机部署 (开发/测试)

- **硬件配置**: 4核8G 内存 (向后兼容)
- **磁盘空间**: 至少 100GB 可用空间

#### 💻 软件环境 (通用要求)

- **操作系统**: Ubuntu 20.04+ / CentOS 8+ / RHEL 8+
- **Docker**: 20.10+
- **Docker Compose**: 2.0+
- **网络工具**: curl, netcat (连通性测试)

### 1. 环境准备

```bash
# 克隆项目 (两台服务器都需要)
git clone <your-repository-url> shared-infra
cd shared-infra

# 🌐 双机部署初始化
# 节点 A (Web/事务侧):
make init-node-a

# 节点 B (计算侧):  
make init-node-b

# 📦 单机部署初始化
make init-single

# 复制并配置环境变量
vim .env  # 🔴 重要：修改节点IP和密码
```

**🔴 必须修改的配置项：**

```bash
# 数据库密码 (必须修改!)
MYSQL_ROOT_PASSWORD=your_super_strong_password_here

# 业务应用镜像 (根据实际情况配置)
MINIBLOG_IMAGE=your-registry/miniblog:v1.0.0
QS_API_IMAGE=your-registry/qs-api:v1.0.0
QS_COLLECTION_IMAGE=your-registry/qs-collection:v1.0.0  
QS_EVALUATION_IMAGE=your-registry/qs-evaluation:v1.0.0
```

### 2. 部署策略选择

#### 🌐 双机分布式部署 (生产推荐)

**节点 A 部署 (Web/事务侧):**

```bash
# 1. 配置环境变量 (.env 文件)
NODE_A_IP=192.168.1.10
NODE_B_IP=192.168.1.11
MYSQL_ROOT_PASSWORD=强密码

# 2. 启动节点 A 所有服务
make up-node-a

# 包含: Nginx + MySQL + Redis + MongoDB + MiniBlog + QS-API + QS-Collection + Jenkins
```

**节点 B 部署 (计算/流侧):**

```bash  
# 1. 配置环境变量 (.env 文件)
NODE_A_IP=192.168.1.10  
NODE_B_IP=192.168.1.11
MYSQL_ROOT_PASSWORD=强密码  # 与节点A相同

# 2. 启动节点 B 服务
make up-node-b

# 包含: Kafka + QS-Evaluation
```

**跨节点连通性验证:**

```bash
# 节点 A 测试
make health-check-node-a

# 节点 B 测试  
make health-check-node-b
```

#### 🖥️ 单机部署 (开发/测试)

```bash
# 🚀 智能启动 (自动检测节点类型)
make up

# 🏃 分阶段启动 (推荐)
make staged-up

# 🔧 手动控制启动顺序
make infra-up    # 先启动基础设施
make nginx-up    # 最后启动前端代理
```

### 3. 服务验证

```bash
# 检查所有服务状态
make status

# 完整健康检查
make health-check-all  

# 查看资源使用情况
make stats

# 查看服务信息
make info
```

### 4. 应用接入

#### 自动化接入 (推荐)

```bash
# 一键添加新应用 (自动配置数据库、Nginx、Redis)
make add-app APP_NAME=myapp APP_PORT=8080 APP_PATH=/myapp

# 这会自动创建:
# ✅ Nginx 反向代理配置 (nginx/conf.d/apps/myapp.conf)
# ✅ MySQL 数据库和专用用户 (myapp/myapp_user)  
# ✅ Redis DB 索引分配 (自动分配可用索引)
# ✅ 应用注册记录 (infrastructure_mgmt.app_registry)

# 重新加载配置
make nginx-reload
```

## 📋 管理命令

### 🚀 核心部署命令

| 命令 | 说明 | 适用场景 |
|------|------|----------|
| `make prod-setup` | 生产环境完整初始化 + 系统优化 | 🏗️ 首次生产部署 |
| `make staged-up` | 分阶段启动 (基础设施→应用→代理) | ⭐ 单机生产环境 |
| `make up` | 一键启动所有服务 | 🔧 开发/测试环境 |
| `make down` | 停止所有服务 | 🛑 维护/停机 |
| `make restart` | 重启所有服务 | 🔄 配置更新后 |

### 🌐 双机集群管理命令

| 命令 | 说明 | 节点 |
|------|------|------|
| `make cluster-web-up` | 启动 Web/事务层服务 | 🅰️ A节点 |
| `make cluster-compute-up` | 启动计算/流处理层服务 | 🅱️ B节点 |
| `make cluster-health-check` | 跨节点连通性和服务健康检查 | 🔄 任意节点 |
| `make cluster-sync-config` | 同步配置文件到对端节点 | 🔄 任意节点 |
| `make cluster-failover` | 故障转移 (实验性) | ⚠️ 运维操作 |

### 📊 监控与状态命令

| 命令 | 说明 | 输出信息 |
|------|------|----------|
| `make status` | 查看容器运行状态 | 🟢 UP/🔴 DOWN/🟡 RESTARTING |
| `make health-check-all` | 完整健康检查 | 各服务连通性测试 |
| `make stats` | 实时资源使用统计 | CPU/内存/网络/磁盘IO |
| `make resource-monitor` | 资源监控 (持续模式) | 实时性能数据流 |
| `make info` | 显示服务端口和管理入口 | 📡 连接信息汇总 |

### 🔧 单服务管理命令

| 命令 | 说明 | 场景 |
|------|------|------|
| `make infra-up` | 启动基础设施 (数据库+消息队列) | 🗄️ 数据层优先启动 |
| `make apps-up` | 启动业务应用 | 🚀 应用层部署 |
| `make nginx-up` | 启动 Nginx 代理 | 🌐 前端代理层 |
| `make mysql-up/redis-up/mongo-up/kafka-up` | 启动单个基础服务 | 🔍 单点调试 |

### 📱 应用接入命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `make add-app APP_NAME=xxx APP_PORT=xxx APP_PATH=xxx` | 自动接入新应用 | `make add-app APP_NAME=blog APP_PORT=3000 APP_PATH=/blog` |
| `make remove-app APP_NAME=xxx` | 移除应用配置 | `make remove-app APP_NAME=blog` |
| `make list-apps` | 列出已接入应用 | 查看当前应用清单 |
| `make nginx-reload` | 重载 Nginx 配置 | 应用配置更新后 |
| `make nginx-test` | 测试 Nginx 配置语法 | 配置验证 |

## 🔧 应用接入指南

### 🤖 自动化接入 (推荐)

使用内置脚本可以零配置接入新应用：

```bash
# 完整示例
make add-app APP_NAME=miniblog APP_PORT=8080 APP_PATH=/blog

# 这个命令会自动完成以下工作:
# ✅ 生成 Nginx 反向代理配置 (nginx/conf.d/apps/miniblog.conf)
# ✅ 创建专用数据库 `miniblog` 和用户 `miniblog_xxx`
# ✅ 分配 Redis DB 索引 (自动选择可用索引)  
# ✅ 生成安全的随机密码
# ✅ 配置健康检查路径
# ✅ 添加应用注册记录
# ✅ 重新加载 Nginx 配置
```

**生成的连接配置示例：**

```bash
# 数据库连接 (自动生成)
DB_DSN="mysql://miniblog_1735123456_789:generated_password@mysql:3306/miniblog?charset=utf8mb4"

# Redis 连接 (自动分配DB索引)
REDIS_URL="redis://redis:6379/1"  # 自动分配DB1

# MongoDB 连接
MONGO_URI="mongodb://mongo:27017/miniblog"

# Kafka 连接
KAFKA_BROKERS="kafka:9092"
```

### 📋 应用管理

```bash
# 查看已接入的应用
make list-apps

# 移除应用 (会清理所有相关配置)
make remove-app APP_NAME=miniblog

# 重新加载 Nginx 配置
make nginx-reload

# 测试 Nginx 配置语法
make nginx-test
```

### 🔧 手动接入 (高级用户)

如需自定义配置，可以手动创建配置：

1. **Nginx 配置**: 在 `nginx/conf.d/apps/` 创建 `{app_name}.conf`
2. **数据库配置**: 使用现有数据库或创建新数据库
3. **应用容器**: 确保应用在 `backend` 网络中

**手动配置示例：**

```nginx
# nginx/conf.d/apps/custom-app.conf
upstream custom_app_backend {
    server custom-app:3000;
}

server {
    listen 80;
    server_name _;
    
    location /custom/ {
        rewrite ^/custom/(.*)$ /$1 break;
        proxy_pass http://custom_app_backend;
        # ... 其他代理配置
    }
}
```

## 🌐 服务端口映射

### 🌍 双机分布式端口布局

#### A 节点 (Web/事务侧) 对外端口

- **Nginx HTTP**: `80` → 主入口，智能路由到本地或B节点
- **Nginx HTTPS**: `443` → SSL/TLS 加密访问
- **MySQL**: `3306` → 主数据库 (仅内网访问)
- **Redis**: `6379` → 缓存服务 (仅内网访问)

#### B 节点 (计算/流侧) 对外端口

- **MongoDB**: `27017` → 文档数据库 (仅内网访问)
- **Kafka**: `9092` → 消息队列 (仅内网访问)
- **QS-Eval API**: `8080` → 评估服务直连 (可选)

### 🔗 统一访问地址 (通过A节点)

- **基础设施状态页**: `http://A节点IP/`
- **MiniBlog**: `http://A节点IP/blog/` (A节点本地)
- **QS API 文档**: `http://A节点IP/qs/api/docs/` (A节点本地)
- **QS 数据收集**: `http://A节点IP/qs/collect/` (A节点本地)
- **QS 数据评估**: `http://A节点IP/qs/eval/` (自动代理到B节点)
- **Nginx 状态**: `http://A节点IP/nginx_status`

### 📊 跨节点服务通信

#### A → B 节点访问

```bash
# 应用配置中使用B节点内网IP
MONGO_URI="mongodb://B节点IP:27017/dbname"  
KAFKA_BROKERS="B节点IP:9092"
QS_EVAL_URL="http://B节点IP:8080"  # 内部调用
```

#### B → A 节点访问

```bash
# 应用配置中使用A节点内网IP
MYSQL_DSN="mysql://user:pass@A节点IP:3306/dbname"
REDIS_URL="redis://A节点IP:6379/db"
```

### 🔒 网络安全策略

- **公网访问**: 仅A节点 80/443 端口
- **内网通信**: 节点间全端口互通 (防火墙白名单)
- **数据库端口**: 仅集群内访问，外网完全隔离

## 📊 监控和维护

### 🔍 实时监控

```bash
# 📈 查看资源使用统计
make stats

# 🩺 完整健康检查
make health-check-all

# 📊 持续资源监控 (类似 htop)
make resource-monitor

# 📋 查看服务状态
make status
```

### 📝 日志管理

```bash
# 🔍 查看所有服务日志
make logs

# 🎯 查看单个服务日志
make nginx-logs
make mysql-logs  
make redis-logs
make mongo-logs
make kafka-logs
make app-logs    # 查看所有业务应用日志

# 📤 追踪实时日志
docker compose logs -f nginx mysql redis
```

### 💾 数据备份与恢复

```bash
# 🗄️ 全量备份所有数据
make backup-all

# 🎯 备份特定服务
make mysql-backup BACKUP_NAME=daily_backup
make redis-backup BACKUP_NAME=redis_snapshot

# 📁 备份数据存储位置
# /data/backups/{service}/{timestamp}/
```

### 🔧 维护操作

```bash
# 🧹 清理未使用的 Docker 资源
make clean

# 🔄 重新启动特定服务  
docker compose restart nginx
docker compose restart mysql

# 📊 查看容器资源限制
docker compose config --services | xargs -I {} docker inspect {} --format '{{.Name}}: {{.HostConfig.Memory}}'
```

## 🔒 生产环境安全配置

### 🔐 必须修改的安全配置

#### 1. 数据库密码安全

```bash
# 🔴 重要: 修改默认密码 (强制要求)
vim .env

# 设置强密码 (至少12位，包含大小写+数字+特殊字符)
MYSQL_ROOT_PASSWORD='MyStr0ng_P@ssw0rd_2024!'

# MySQL 8.0 密码验证策略已启用
# 自动生成的应用数据库密码包含时间戳+随机数
```

#### 2. SSL/HTTPS 配置

```bash
# 生产环境必须启用 HTTPS
# 1. 获取 SSL 证书 (Let's Encrypt 推荐)
sudo apt install certbot
certbot --nginx -d yourdomain.com

# 2. 或手动配置证书
cp your_domain.crt nginx/ssl/
cp your_domain.key nginx/ssl/
chmod 600 nginx/ssl/*

# 3. 更新 Nginx 配置启用 HTTPS
# 编辑 nginx/conf.d/apps/*.conf 文件，取消 HTTPS server 块注释
```

#### 3. 网络安全策略

```bash
# 🛡️ 防火墙配置 (推荐)
# 仅开放必要端口
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP  
ufw allow 443/tcp  # HTTPS
ufw enable

# 🚫 数据库端口不对外开放 (仅内部访问)
# 3306, 6379, 27017, 9092 端口仅在 Docker 内部网络可访问
```

### 🛡️ 内置安全特性

- **Nginx 安全头**: XSS保护、内容类型嗅探防护、点击劫持防护
- **访问控制**: IP限流、连接数限制、上传大小限制
- **网络隔离**: 前端/后端网络分离，数据库服务仅内部可访问
- **容器安全**: 非root用户运行、只读文件系统、资源限制
- **密码策略**: 自动生成强密码、时间戳+随机数组合

## 🚨 故障排除

### 🔧 常见问题诊断

#### 启动失败问题

```bash
# 1. 检查端口占用
make port-check
lsof -i :80,:443,:3306,:6379,:27017,:9092

# 2. 检查 Docker 和资源
docker system df          # 磁盘使用
docker system info        # Docker 信息
free -h                   # 内存使用

# 3. 检查权限问题
sudo chown -R $USER:$USER /data
chmod 755 /data
```

#### 服务连接问题

```bash
# 网络连通性测试
make network-diagnose

# 容器网络诊断
docker network inspect frontend
docker network inspect backend

# 服务间连接测试
docker compose exec nginx ping mysql
docker compose exec nginx ping redis
```

#### 配置问题

```bash
# Nginx 配置测试
make nginx-test
docker compose exec nginx nginx -T

# 查看生效的配置
docker compose config
```

### 📋 分层日志查看

```bash
# 🔍 应用层日志
make app-logs           # 所有业务应用
docker logs miniblog    # 单个应用

# 🌐 代理层日志  
make nginx-logs
tail -f /data/logs/nginx/access.log
tail -f /data/logs/nginx/error.log

# 🗄️ 数据层日志
make mysql-logs
make redis-logs
make mongo-logs
make kafka-logs

# 🚨 错误日志集中查看
find /data/logs -name "*.log" -exec grep -l "ERROR\|FATAL\|Exception" {} \;
```

### ⚠️ 性能调优建议

#### 内存不足处理

```bash
# 检查内存使用
make stats
docker stats --no-stream

# 如果内存不足，可以调整以下配置:
# 1. MySQL: 降低 innodb_buffer_pool_size (当前2G)
# 2. MongoDB: 降低 wiredTigerCacheSizeGB (当前1.5G)  
# 3. Redis: 降低 maxmemory (当前512MB)
# 4. 业务应用: 降低内存限制
```

#### 磁盘空间清理

```bash
# Docker 资源清理
make clean
docker system prune -af --volumes

# 日志清理
sudo find /data/logs -name "*.log" -mtime +7 -delete

# 数据备份后清理
make backup-all
# 清理旧的备份文件
```

## 📁 项目结构

```text
shared-infra/                 # 🏗️ 共享基础设施根目录
├── 📋 核心配置文件
│   ├── README.md             # 📖 项目文档 (本文件)
│   ├── PRODUCTION.md         # 🚀 生产部署指南  
│   ├── Makefile              # 🔧 管理命令集合 (66个命令)
│   ├── docker-compose.yml    # 🐳 服务编排定义 (9个服务)
│   ├── .env.example          # ⚙️ 环境变量模板
│   └── .env                  # 🔐 实际环境配置 (需创建)
├── 🌐 Nginx 配置 (生产级代理)
│   ├── nginx.conf            # 📄 主配置 (性能优化+安全加固)
│   ├── conf.d/               # 📁 虚拟主机配置
│   │   ├── default.conf      # 🏠 默认站点
│   │   ├── apps.conf         # 📱 应用路由配置
│   │   └── apps/             # 📂 应用独立配置目录
│   │       ├── miniblog.conf # 📝 博客配置 (自动生成)
│   │       └── *.conf        # 🔧 其他应用配置
│   └── ssl/                  # 🔒 SSL 证书存储
├── 🗄️ MySQL 配置 (8.0 优化)
│   ├── my.cnf               # ⚙️ 数据库配置 (2G缓冲池)
│   └── init/                # 🚀 初始化脚本
│       ├── 01-init-infrastructure.sql  # 🏗️ 基础设施初始化
│       └── 02-init-*.sql    # 📱 应用数据库 (自动生成)
├── 💾 Redis 配置 (7.0 + AOF)
│   ├── redis.conf           # ⚙️ 缓存配置 (512MB限制)
│   └── data/                # 📁 持久化数据
├── 🔧 管理脚本
│   ├── add-app.sh           # ➕ 应用接入脚本 (297行)
│   ├── remove-app.sh        # ➖ 应用移除脚本  
│   └── backup.sh            # 💾 数据备份脚本
└── 📊 运行时目录 (Docker挂载)
    └── logs/                # 📝 日志集中存储
        ├── nginx/           # 🌐 代理日志
        ├── mysql/           # 🗄️ 数据库日志
        ├── redis/           # 💾 缓存日志
        └── apps/            # 📱 业务应用日志
```

### 🎯 关键特性统计

#### 🏗️ 架构统计

- **📦 服务数量**: 9个 (分布在2个节点，支持单机向后兼容)
- **🌐 部署模式**: 双机分布式 (推荐) + 单机部署 (开发)
- **🔧 管理命令**: 70+ 个 Makefile 命令 (新增集群管理)
- **📝 配置文件**: 101行 Nginx + 84行 SQL + 集群配置模板

#### 💾 资源优化策略

- **A节点 (2C4G)**: 1.9G 基础设施 + 0.8G 轻应用 = 2.7G (预留1.3G)
- **B节点 (2C4G)**: 1.3G 基础设施 + 0.5G 重应用 = 1.8G (预留2.2G 页缓存)
- **总资源**: 双机8G，单点故障容忍，性能线性扩展

#### 🛡️ 安全与可靠性

- **网络隔离**: 公网仅暴露A节点80/443，数据库完全内网
- **故障隔离**: Web层与计算层物理分离，单点故障不全局影响  
- **数据安全**: 跨节点备份，SSL加密，访问控制策略

## 🤝 贡献指南

### 🐛 问题反馈

- 使用 Issues 报告 bug 或提出功能需求
- 提供详细的错误日志和环境信息
- 标注是否为生产环境问题

### 🔧 开发贡献

- Fork 项目并创建特性分支
- 遵循现有的代码风格和注释规范
- 更新相关文档和测试
- 提交 Pull Request 前请先测试

### 📋 待办事项

- [ ] 支持 Docker Swarm 集群模式
- [ ] 添加 Prometheus + Grafana 监控栈
- [ ] 集成 ELK 日志分析栈
- [ ] 支持自动 SSL 证书申请和续期
- [ ] 添加更多数据库支持 (PostgreSQL, ClickHouse)

## 📄 开源协议

MIT License - 详见 [LICENSE](LICENSE) 文件

---

🏗️ **为中小型项目而生的生产级基础设施**

开箱即用 · 安全可靠 · 易于维护
