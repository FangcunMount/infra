# Infra - 企业级基础设施即代码

> 🏗️ 生产级基础设施平台，为业务应用提供稳定可靠的运行环## 🚀 核心特性

- **🧩 模块化架构**: 每个服务独立配置、独立部署、独立扩展
- **🐳 完全容器化**: 基于 Docker Compose 的编排管理
- **🎛️ 自动化部署**: 完整的脚本化部署和健康检查体系
- **🌐 环境一致性**: 开发、测试、生产环境配置标准化
- **📊 运维友好**: 内置监控、日志、管理界面

## 📚 文档导航

### 🚀 快速上手
- [📖 项目概览](README.md) - 项目介绍和架构概述（本文档）

### 🔧 服务器初始化
- [👥 用户环境配置](docs/服务器初始化--用户.md) - 用户权限、SSH密钥等基础配置
- [🌐 网络环境配置](docs/网络管理/服务器初始化--网络环境.md) - VPN代理、防火墙、网络优化
- [🐳 Docker 安装配置](docs/服务器初始化--docker.md) - Docker环境安装和配置优化

### � 网络管理 ⭐ 重要
- [📖 网络管理完整指南](docs/网络管理/网络管理完整指南.md) - 业务网络创建、Makefile命令、故障排查
- [🐳 Docker Swarm 部署](docs/网络管理/Docker_Swarm部署指南.md) - 跨主机集群部署指南
- [� 更多网络文档](docs/网络管理/README.md) - 完整网络文档索引

### 🏗️ 基础设施部署（推荐顺序）
1. [🗄️ 存储服务](docs/服务器组件--存储服务(MySQL_Redis_MongoDB).md) - MySQL/Redis/MongoDB数据库集群
2. [📨 消息服务 - Kafka](docs/服务器组件--消息服务(Kafka).md) - Kafka消息队列系统
3. [📬 消息队列 - NSQ](docs/服务器组件--消息队列(NSQ).md) - NSQ实时分布式消息平台
4. [🔧 CI/CD服务](docs/服务器组件--CI_CD(Jenkins).md) - Jenkins持续集成平台
5. [🌐 网关服务](docs/服务器组件--网关(Nginx).md) - Nginx反向代理和SSL终端

### 🎯 部署策略

**单机部署**: 初始化网络 → 存储服务 → 消息服务 → CI/CD → 网关服务

**跨主机部署**: Docker Swarm 集群 → 初始化网络 → 各节点部署服务

> 💡 **重要提示**: 
> - 单机部署使用 bridge 网络，跨主机部署使用 overlay 网络
> - 跨主机部署**必须先配置 Docker Swarm**，详见[网络管理文档](docs/网络管理/README.md)
> - 业务应用网络创建请参考[网络管理完整指南](docs/网络管理/网络管理完整指南.md)

## 🎯 项目定位

本项目专注于**纯基础设施服务**，遵循"基础设施与应用分离"的设计原则：
- ✅ **包含**: 数据库、缓存、消息队列、网关、CI/CD等共享基础服务
- ❌ **不包含**: 具体业务应用的部署配置（应在各自项目中管理）

## 🏗️ 服务器架构设计

### 🔧 基础设施服务矩阵

| 服务类型 | 服务组件 | 端口 | 用途 | 环境 |
|---------|---------|------|------|------|
| **🗄️ 数据存储** | MySQL | 3306 | 关系型数据库 | 内网 |
| | Redis | 6379 | 内存缓存 | 内网 |
| | MongoDB | 27017 | 文档数据库 | 内网 |
| **📨 消息队列** | Kafka | 9092 | 大数据流处理 | 内网 |
| | NSQ | 4150/4151 | 实时消息分发 | 内网 |
| **🌐 网关代理** | Nginx | 80/443 | 反向代理+SSL | 公网 |
| **🔧 CI/CD** | Jenkins | 8080 | 持续集成 | 内网 |

### 🏢 网络架构拓扑

```
🌍 Internet
     │
┌────▼────┐     ┌─────────────────────────────────────────┐
│ Nginx   │────▶│          infra-frontend 网络            │
│ (网关)  │     │  ┌─────────────────────────────────────┐ │
└─────────┘     │  │         应用服务区域                 │ │
                │  │    (业务应用容器部署区)              │ │
                │  └─────────────────────────────────────┘ │
                └─────────────────────────────────────────┘
                            │
                ┌───────────▼────────────────────────────┐
                │        infra-network 网络              │
                │  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
                │  │  MySQL   │ │  Redis   │ │ MongoDB │ │
                │  └──────────┘ └──────────┘ └─────────┘ │
                │  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
                │  │  Kafka   │ │ Jenkins  │ │  管理UI │ │
                │  └──────────┘ └──────────┘ └─────────┘ │
                └────────────────────────────────────────┘
```

### 🔒 安全设计原则
- **网络隔离**: 前后端网络分离，基础设施服务不直接暴露
- **最小权限**: 只开放必要的服务端口
- **数据持久化**: 所有数据使用独立 Docker 卷存储
- **环境隔离**: 开发/生产环境完全分离配置

## 🚀 核心特性

- **🧩 模块化架构**: 每个服务独立配置、独立部署、独立扩展
- **� 完全容器化**: 基于 Docker Compose 的编排管理
- **🎛️ 自动化部署**: 完整的脚本化部署和健康检查体系
- **🌐 环境一致性**: 开发、测试、生产环境配置标准化
- **📊 运维友好**: 内置监控、日志、管理界面

## 🏢 架构概览

### 网络架构
```
┌─────────────────────────────────────────────────────┐
│                  外部访问层                          │
│  ┌─────────────────────────────────────────────┐   │
│  │            Nginx (端口 80/443)              │   │
│  │         SSL终结 + 反向代理                   │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────┐
│                 基础设施服务层                       │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐│
│  │    MySQL     │  │    Redis     │  │   MongoDB   ││
│  │   (3306)     │  │   (6379)     │  │   (27017)   ││
│  └──────────────┘  └──────────────┘  └─────────────┘│
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐│
│  │    Kafka     │  │   Jenkins    │  │   管理界面   ││
│  │   (9092)     │  │   (8080)     │  │   (开发)    ││
│  └──────────────┘  └──────────────┘  └─────────────┘│
└─────────────────────────────────────────────────────┘
                         │
┌─────────────────────────────────────────────────────┐
│                   应用服务层                         │
│           (由各应用项目自行管理)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐│
│  │   miniblog   │  │    qs-api    │  │     ...     ││
│  │   (8001)     │  │   (8002)     │  │             ││
│  └──────────────┘  └──────────────┘  └─────────────┘│
└─────────────────────────────────────────────────────┘
```

### 职责分离
- **Infra 项目**: 仅管理基础设施服务
- **应用项目**: 各自管理部署配置，连接到基础设施网络
    class Internet,LB internet
```

## 服务清单

| 服务 | 节点 | 端口 | 用途 | 资源限制 |
|------|------|------|------|----------|
| **Nginx** | A | 80, 443 | 反向代理/SSL终结 | 512MB |
| **MySQL** | A | 3306 | 关系型数据库 | 1GB |
| **Redis** | A | 6379 | 缓存/会话存储 | 512MB |
| **MongoDB** | A | 27017 | 文档数据库 | 1GB |
| **Kafka** | B | 9092 | 大数据流处理 | 1GB |
| **NSQ** | B | 4150-4151, 4160-4161, 4171 | 实时消息分发 | 768MB |
| **Zookeeper** | B | 2181 | 集群协调 | 512MB |

## 部署要求

- Docker >= 20.x 和 Docker Compose
- Linux 系统（推荐 Ubuntu/CentOS）
- 足够的磁盘空间用于数据存储

## 快速开始

### 1. 克隆代码

```bash
git clone <repo-url> infra && cd infra
```

### 2. 创建基础设施（网络+卷）

**这是所有服务的基础，必须首先执行：**

```bash
# 创建 Docker 网络和数据卷
./scripts/components/init-infrastructure.sh create

# 检查基础设施状态
./scripts/components/init-infrastructure.sh status
```

### 3. 配置环境变量

```bash
# 开发环境
cp compose/env/dev/.env.example compose/env/dev/.env
vim compose/env/dev/.env

# 生产环境
cp compose/env/prod/.env.example compose/env/prod/.env
vim compose/env/prod/.env
```

### 4. 部署基础设施服务

```bash
# 安装所有核心服务
./scripts/components/install.sh all

# 或分步安装
./scripts/components/install.sh nginx     # 网关
./scripts/components/install.sh mysql    # 数据库
./scripts/components/install.sh redis    # 缓存
./scripts/components/install.sh kafka    # Kafka消息队列
./scripts/components/install.sh nsq      # NSQ消息队列
./scripts/components/install.sh jenkins  # CI/CD
```

### 5. 管理服务

```bash
# 查看所有服务状态
./scripts/components/compose-manager.sh status

# 启动/停止服务
./scripts/components/compose-manager.sh infra up all
./scripts/components/compose-manager.sh infra down all

# 查看日志
./scripts/components/compose-manager.sh logs nginx
```

### 6. 验证部署

```bash
# 检查基础设施
./scripts/components/init-infrastructure.sh status

# 检查服务健康状态
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

## 环境配置

复制环境变量模板并修改：

```bash
cp compose/env/prod/.env.example compose/env/prod/.env
vim compose/env/prod/.env
```

主要配置项：

- `MYSQL_ROOT_PASSWORD` - MySQL root 密码
- `REDIS_PASSWORD` - Redis 密码  
- `MONGO_INITDB_ROOT_PASSWORD` - MongoDB 密码
- `NODE_A_IP` / `NODE_B_IP` - 节点 IP 地址

## 📁 项目结构

```text
infra/
├── components/                    # 🧩 基础设施组件（完全自包含）
│   ├── networks/                 # 共享网络定义（唯一的共享资源）
│   │   ├── docker-compose.yml   # 网络定义
│   │   └── README.md
│   ├── nginx/                    # Nginx 网关服务
│   │   ├── docker-compose.yml   # 服务定义 + 数据卷声明
│   │   ├── nginx.conf           # 主配置文件
│   │   ├── conf.d/              # 配置目录
│   │   └── README.md
│   ├── mysql/                    # MySQL 数据库
│   │   ├── docker-compose.yml   # 服务定义 + 数据卷声明
│   │   ├── my.cnf
│   │   └── README.md
│   ├── redis/                    # Redis 缓存
│   │   ├── docker-compose.yml   # 服务定义 + 数据卷声明
│   │   ├── redis.conf
│   │   └── README.md
│   ├── mongo/                    # MongoDB 数据库
│   │   ├── docker-compose.yml   # 服务定义 + 数据卷声明
│   │   ├── mongod.conf
│   │   └── README.md
│   ├── kafka/                    # Kafka 消息队列
│   │   ├── docker-compose.yml   # 服务定义 + 数据卷声明
│   │   └── README.md
│   ├── nsq/                      # NSQ 消息队列
│   │   ├── docker-compose.yml   # 服务定义 + 数据卷声明
│   │   ├── nsqd.conf
│   │   ├── nsqlookupd.conf
│   │   ├── nsqadmin.conf
│   │   └── README.md
│   └── jenkins/                  # Jenkins CI/CD
│       ├── docker-compose.yml   # 服务定义 + 数据卷声明
│       ├── Dockerfile
│       ├── plugins.txt
│       └── README.md
├── compose/                       # 环境配置
│   └── env/                      # 环境变量配置
│       ├── dev/                  # 开发环境
│       └── prod/                 # 生产环境
├── scripts/                       # 🤖 自动化脚本
│   ├── server/                   # 服务器环境管理
│   │   ├── init-users.sh        # 用户初始化
│   │   ├── install-docker.sh    # Docker安装
│   │   └── initialize.sh        # 服务器初始化总控
│   ├── network/                  # 网络管理
│   │   ├── setup.sh             # 网络环境配置(VPN)
│   │   ├── uninstall.sh         # 网络环境卸载
│   │   ├── vpn-manager.sh       # VPN管理
│   │   ├── optimize.sh          # 网络优化
│   │   └── diagnose.sh          # 网络诊断
│   ├── components/               # 组件管理
│   │   ├── install.sh           # 组件安装总控
│   │   ├── compose-manager.sh   # Compose管理工具
│   │   ├── init-infrastructure.sh  # 基础设施初始化
│   │   └── init-apps-config.sh  # 应用配置初始化
│   └── tools/                    # 工具脚本
│       ├── ssl-manager.sh       # SSL证书管理
│       ├── nginx-app-manager.sh # Nginx应用管理
│       ├── test-*.sh            # 各种测试脚本
│       ├── update-static-files.sh  # 静态文件更新
│       └── demo-env-variables.sh   # 环境变量示例
├── docs/                          # 📖 文档
│   ├── 服务器初始化--*.md        # 初始化文档
│   └── 服务器组件--*.md          # 组件部署文档
├── static/                        # 静态资源文件
├── logs/                          # 日志目录
└── Makefile                       # 管理命令
```

### 🎯 组件完全自包含设计

每个组件目录包含该组件的**所有**配置和资源定义：
- ✅ `docker-compose.yml` - 服务定义 + 数据卷声明
- ✅ `*.conf` - 配置文件
- ✅ `README.md` - 组件文档

**唯一的共享资源**: `components/networks/` - 网络定义（因为多个组件需要互联）

**优势**:
- 📦 组件完全自包含，易于理解和维护
- 🔍 配置文件路径简单（使用相对路径 `./config.conf`）
- 💾 数据卷生命周期跟随组件（删除组件时清楚数据归属）
- 🚀 可独立部署、测试和迁移
- 📋 清晰的组织结构，便于团队协作
```

## 自动化脚本

项目提供完整的服务器初始化脚本：

```bash
# 1. 安装 Docker 环境
sudo ./scripts/server/install-docker.sh

# 2. 初始化用户环境
sudo ./scripts/server/init-users.sh

# 3. 配置网络环境（VPN）- 自动使用静态文件
sudo ./scripts/network/setup.sh

# 4. 故障诊断（如遇问题）
sudo ./scripts/network/diagnose.sh

# 5. 更新静态文件（可选）
./scripts/tools/update-static-files.sh
```

## 管理命令

```bash
make help          # 查看帮助
make status        # 查看状态
make logs          # 查看日志
make down          # 停止服务
make clean         # 清理资源

# VPN 管理命令
mihomo-control start|stop|restart|status|logs
mihomo-update      # 更新订阅配置
```

## 内网环境部署

本项目完全支持无外网连接的内网环境部署：

### 特性支持

- ✅ **自动检测内网环境**：脚本会自动识别是否处于内网环境
- ✅ **依赖包离线安装**：支持跳过外网依赖，使用本地包管理
- ✅ **Docker镜像预加载**：支持预先导入的镜像，无需在线拉取
- ✅ **地理数据文件替代**：提供基础规则配置替代在线数据文件
- ✅ **配置文件手动部署**：支持离线配置文件部署

### 内网部署指南

详细的内网环境安装指南请参考：**[INTRANET_SETUP_GUIDE.md](./INTRANET_SETUP_GUIDE.md)**

### 快速内网部署

#### 方案1：使用本地静态文件（推荐）

```bash
# 1. 在有网络的机器上更新静态文件
./scripts/update-static-files.sh

# 2. 传输整个项目到内网服务器（包含 static/ 目录）

# 3. 在内网服务器上运行（脚本自动使用静态文件）
sudo ./scripts/network/setup.sh
```

#### 方案2：传统离线部署

```bash
# 1. 预先准备资源（在有网络的机器上）
# - Docker 镜像：docker save metacubex/mihomo:latest > mihomo.tar
# - 地理数据：下载 GeoSite.dat 和 GeoIP.metadb
# - 配置文件：下载订阅配置文件

# 2. 传输资源到内网服务器

# 3. 导入镜像
docker load < mihomo.tar

# 4. 运行安装脚本（自动检测内网环境）
sudo ./scripts/network/setup.sh
```

---

更多详情请参考 [QUICKSTART.md](./QUICKSTART.md)
