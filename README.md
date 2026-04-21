# Infra - 基础设施即代码

> 🏗️ 双服务器分布式架构的基础设施管理平台

## 🚀 快速开始

```bash
# 查看所有可用命令
make help

# 查看服务端口映射
make service-ports

# 各组件快速参考
make help-mongo    # MongoDB
make help-redis    # Redis
make help-nsq      # NSQ
make help-vpn      # VPN
make help-ssl      # SSL 证书
```

## 📖 文档

详细文档请参阅 **[docs/INDEX.md](docs/INDEX.md)**

| 文档 | 说明 |
|------|------|
| [架构设计](docs/server/architecture.md) | 双机部署规划、资源分配、云服务连接 |
| [升降配操作手册](docs/server/scaling-runbook.md) | 服务器升配/降配时要改哪些文件、按什么顺序发 |
| [初始化指南](docs/server/initialization.md) | 服务器用户配置、Docker 安装 |
| [组件总览](docs/components/README.md) | MongoDB、Redis、NSQ 等组件参考 |
| [网络架构](docs/network/architecture.md) | Overlay 网络设计 |
| [CI/CD 部署](docs/server/github-actions-deploy-guide.md) | GitHub Actions 配置 |

## 🏗️ 架构概览

```text
                    Internet
                        │
                        ▼
┌───────────────────────────────────────────────────────────┐
│                   ServerA (2C4G)                          │
│              主力业务 + 网关 + 存储                        │
│  ┌─────────┐ ┌─────────────┐ ┌─────────────────────────┐ │
│  │  Nginx  │ │ Redis-Cache │ │        MongoDB          │ │
│  │ 80/443  │ │    6379     │ │         27017           │ │
│  └─────────┘ └─────────────┘ └─────────────────────────┘ │
│  + qs-apiserver, qs-collection, qs-worker, iam-apiserver │
└─────────────────────────┬─────────────────────────────────┘
                          │ infra-network (Overlay)
┌─────────────────────────┴─────────────────────────────────┐
│                   ServerB (2C2G)                          │
│             消息中间件 + 边缘前端 + 监控平台               │
│  ┌───────────────────────────────────────────────────┐   │
│  │  nsqlookupd (4160/4161) │ nsqd (4150/4151) │ admin │   │
│  └───────────────────────────────────────────────────┘   │
│  + prometheus, grafana, miniblog-backend, qs-ops         │
└───────────────────────────────────────────────────────────┘
                          │ VPC 内网
┌─────────────────────────┴─────────────────────────────────┐
│                    阿里云托管服务                          │
│         MySQL (RDS)          │       Redis-Store          │
└───────────────────────────────────────────────────────────┘
```

## 📁 项目结构

```text
infra/
├── components/           # 基础设施组件
│   ├── mongo/           # MongoDB
│   ├── redis/           # Redis Cache
│   ├── nsq/             # NSQ 消息队列
│   ├── nginx/           # Nginx 网关
│   ├── mysql/           # MySQL (仅开发环境)
│   └── networks/        # 网络定义
├── deploy/              # 服务器部署配置
│   ├── serverA/         # ServerA compose
│   └── serverB/         # ServerB compose
├── compose/env/         # 环境变量
│   ├── dev/             # 开发环境
│   └── prod/            # 生产环境
├── scripts/             # 自动化脚本
│   ├── 00-server/       # 服务器初始化
│   ├── 01-network/      # 网络/VPN 管理
│   ├── 02-components/   # 组件管理
│   ├── 03-nginx/        # Nginx 应用管理
│   ├── 04-ssl/          # SSL 证书管理
│   └── utils/           # 工具脚本
├── docs/                # 文档
├── static/              # 静态资源 (GeoIP, mihomo)
├── examples/            # 示例配置
└── Makefile             # 管理命令入口
```

## 🔧 常用命令

### 基础设施

```bash
make init              # 初始化网络和卷
make status            # 查看所有服务状态
```

### 组件管理

```bash
make mongo-start       # 启动 MongoDB
make redis-start       # 启动 Redis
make nsq-start         # 启动 NSQ
make nginx-start       # 启动 Nginx
```

### VPN 管理

```bash
make vpn-setup         # 安装配置 VPN
make vpn-status        # 查看状态
make vpn-enable        # 启用 VPN
make vpn-disable       # 禁用 (直连)
```

### SSL 证书

```bash
make ssl-wildcard DOMAIN=example.com EMAIL=admin@example.com
make ssl-list          # 列出证书
make ssl-renew         # 续期证书
```

## 📋 服务端口

| 服务 | 端口 | 位置 |
|------|------|------|
| Nginx | 80, 443 | ServerA |
| MongoDB | 27017 | ServerA |
| Redis | 6379 | ServerA |
| NSQ | 4150-4171 | ServerB |
| MySQL | 3306 | 云 RDS / 开发环境 |

## 📄 License

MIT
