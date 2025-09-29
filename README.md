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
- [🌐 网络环境配置](docs/服务器初始化--网络环境.md) - VPN代理、防火墙、网络优化
- [🐳 Docker 安装配置](docs/服务器初始化--docker.md) - Docker环境安装和配置优化

### 🏗️ 基础设施部署（推荐顺序）
1. [🔧 网络&基础卷](docs/服务器组件--网络&基础卷.md) - Docker网络和数据卷初始化
2. [🗄️ 存储服务](docs/服务器组件--存储服务(MySQL_Redis_MongoDB).md) - MySQL/Redis/MongoDB数据库集群
3. [📨 消息服务](docs/服务器组件--消息服务(Kafka).md) - Kafka消息队列系统  
4. [🔧 CI/CD服务](docs/服务器组件--CI_CD(Jenkins).md) - Jenkins持续集成平台
5. [🌐 网关服务](docs/服务器组件--网关(Nginx).md) - Nginx反向代理和SSL终端

### 🎯 部署策略
**推荐部署顺序**: 网络&基础卷 → 存储服务 → 消息服务 → CI/CD → 网关服务

> 💡 **重要提示**: 请按照推荐顺序进行部署，确保服务间依赖关系得到正确处理。
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
| **📨 消息队列** | Kafka | 9092 | 分布式消息 | 内网 |
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
                │        infra-backend 网络              │
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
| **Kafka** | B | 9092 | 消息队列 | 1GB |
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
./scripts/init-components/init-infrastructure.sh create

# 检查基础设施状态
./scripts/init-components/init-infrastructure.sh status
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
./scripts/init-components/install-components.sh all

# 或分步安装
./scripts/init-components/install-components.sh nginx     # 网关
./scripts/init-components/install-components.sh mysql    # 数据库
./scripts/init-components/install-components.sh redis    # 缓存
./scripts/init-components/install-components.sh kafka    # 消息队列
./scripts/init-components/install-components.sh jenkins  # CI/CD
```

### 5. 管理服务

```bash
# 查看所有服务状态
./scripts/init-components/compose-manager.sh status

# 启动/停止服务
./scripts/init-components/compose-manager.sh infra up all
./scripts/init-components/compose-manager.sh infra down all

# 查看日志
./scripts/init-components/compose-manager.sh logs nginx
```

### 6. 验证部署

```bash
# 检查基础设施
./scripts/init-components/init-infrastructure.sh status

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

## 项目结构

```text
├── compose/              # Docker Compose 配置
├── components/           # 组件配置文件  
├── scripts/             # 自动化脚本
│   ├── init-server/     # 服务器初始化脚本
│   │   ├── init-users.sh        # 用户环境初始化
│   │   ├── install-docker.sh    # Docker 安装
│   │   ├── setup-network.sh     # 网络环境配置
│   │   ├── diagnose-network.sh  # 网络环境诊断
│   │   └── update-static-files.sh # 静态文件更新
│   └── deploy/          # 应用部署脚本
├── static/              # 静态资源文件
│   ├── geosite.dat      # 域名分流规则数据库
│   └── geoip.metadb     # IP地理位置数据库
├── logs/               # 日志目录
└── Makefile            # 管理命令
```

## 自动化脚本

项目提供完整的服务器初始化脚本：

```bash
# 1. 安装 Docker 环境
sudo ./scripts/init-server/install-docker.sh

# 2. 初始化用户环境
sudo ./scripts/init-server/init-users.sh

# 3. 配置网络环境（VPN）- 自动使用静态文件
sudo ./scripts/init-server/setup-network.sh

# 4. 故障诊断（如遇问题）
sudo ./scripts/init-server/diagnose-network.sh

# 5. 更新静态文件（可选）
./scripts/init-server/update-static-files.sh
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
sudo ./scripts/init-server/setup-network.sh
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
sudo ./scripts/init-server/setup-network.sh
```

---

更多详情请参考 [QUICKSTART.md](./QUICKSTART.md)
