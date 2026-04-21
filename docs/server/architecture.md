# 服务器架构设计

## 概述

本项目采用**双服务器分布式架构**，将服务按功能分布在两台 ECS 上，结合阿里云托管服务实现高可用和成本优化。

**核心原则**：

- 核心数据与核心业务集中在 ServerA
- 消息中间件 + 边缘业务 + 前端站点集中在 ServerB
- 数据库使用云托管，Redis 采用单实例自管，ECS 以计算/缓存为主

## 架构图

```text
                         ┌─────────────────────┐
                         │   Internet/客户端   │
                         └──────────┬──────────┘
                                    │ HTTPS/HTTP
                                    ▼
┌───────────────────────────────────────────────────────────────┐
│                      ServerA (2C4G)                           │
│                    主力业务 + 网关 + 存储                      │
├───────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │   Nginx     │  │   Redis     │  │      MongoDB        │   │
│  │  80/443     │  │    6379     │  │       27017         │   │
│  │ 128M/0.10C  │  │ 256M/0.15C  │  │    1024M/0.50C      │   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
│                                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ ┌─────────┐ │
│  │qs-apiserver │  │qs-collection│  │ qs-worker │ │iam-api  │ │
│  │ 384M/0.25C  │  │ 256M/0.20C  │  │256M/0.15C │ │384M/0.25│ │
│  └─────────────┘  └─────────────┘  └───────────┘ └─────────┘ │
│                                                               │
│                    容器合计: ~2.7GB / ~1.60C                  │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            │ infra-network (Overlay)
                            │ NSQ: 4150/4160
                            ▼
┌───────────────────────────────────────────────────────────────┐
│                      ServerB (2C2G)                           │
│                   消息中间件 + 边缘前端                        │
├───────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐     │
│  │                   NSQ 三件套                         │     │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐       │     │
│  │  │nsqlookupd │  │   nsqd    │  │ nsqadmin  │       │     │
│  │  │ 96M/0.04C │  │384M/0.20C │  │ 96M/0.04C │       │     │
│  │  │4160/4161  │  │4150/4151  │  │   4171    │       │     │
│  │  └───────────┘  └───────────┘  └───────────┘       │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
│  ┌───────────────────┐  ┌────────────┐  ┌────────────┐       │
│  │ miniblog-backend  │  │frontend-   │  │frontend-   │       │
│  │    448M/0.15C     │  │admin 128M  │  │blog 128M   │       │
│  └───────────────────┘  └────────────┘  └────────────┘       │
│                                                               │
│  ┌────────────────────┐                                      │
│  │qs-operating-system │                                      │
│  │     128M/0.04C     │                                      │
│  └────────────────────┘                                      │
│                                                               │
│                    容器合计: ~1.4GB / ~0.55C                  │
└───────────────────────────┬───────────────────────────────────┘
                            │
                            │ VPC 内网
                            ▼
┌───────────────────────────────────────────────────────────────┐
│                      阿里云托管服务                            │
├───────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────┐                                  │
│  │      MySQL (RDS)        │                                  │
│  │  - miniblog 库          │                                  │
│  │  - qs 相关业务库         │                                  │
│  │  - IAM 用户库           │                                  │
│  └─────────────────────────┘                                  │
└───────────────────────────────────────────────────────────────┘
```

## ServerA (2C4G) - 主力业务机

### 部署服务（ServerA）

| 服务 | CPU 上限 | 内存上限 | 说明 |
|------|---------|---------|------|
| `nginx-gateway` | 0.10 | 128MB | 统一反向代理 + TLS 终止 |
| `redis` | 0.15 | 256MB | 单实例，AOF 开启，默认 volatile-lru |
| `mongodb` | 0.50 | 1024MB | 问卷/量表文档数据 |
| `qs-apiserver` | 0.50 | 768MB | 问卷&量表核心 API（临时降配档） |
| `qs-collection` | 0.25 | 384MB | 小程序/前端收集入口（收紧内部并发） |
| `qs-worker` | 0.20 | 256MB | 单实例异步任务 Worker |
| `iam-apiserver` | 0.25 | 384MB | 用户中心 + 认证授权（降配档） |

**资源汇总**：

- qs 三件套合计（上限）：~0.95C / ~1.4GB（mem_limit 768m / 384m / 256m，cpus 0.5 / 0.25 / 0.20）
- 基础组件 + IAM：~1.00C / ~1.75GB（Nginx 128M/0.10C、Redis 256M/0.15C、Mongo 1024M/0.50C、IAM 384M/0.25C）
- 容器合计（上限）：~1.95C / ~3.2GB，可为 OS 与 page cache 预留约 0.7~0.8GB
- 监控栈（Prometheus / Grafana）迁移到 ServerB，避免继续挤占 ServerA 的业务缓冲

### 目录结构（ServerA）

```text
/opt/qs-server/          # 问卷服务
├── qs-apiserver/
├── qs-collection-server/
└── qs-worker/
/opt/iam/                # IAM 服务
└── iam-apiserver/
/data/
├── mongodb/             # MongoDB 数据
├── ssl/                 # SSL 证书
└── logs/                # 日志目录
```

## ServerB (2C2G) - 边缘/消息机

### 部署服务（ServerB）

| 服务 | CPU 上限 | 内存上限 | 说明 |
|------|---------|---------|------|
| `nsqd` | 0.20 | 384MB | 核心消息进程 |
| `nsqlookupd` | 0.04 | 96MB | 路由组件 |
| `nsqadmin` | 0.04 | 96MB | Web 控制台 |
| `prometheus` | 0.10 | 256MB | 集中抓取容器指标（7d 保留，30s 抓取） |
| `grafana` | 0.05 | 128MB | 监控面板 |
| `miniblog-backend` | 0.15 | 448MB | 博客后端 |
| `miniblog-frontend-admin` | 0.04 | 128MB | 博客管理前端 |
| `miniblog-frontend-blog` | 0.04 | 128MB | 博客前端 |
| `qs-operating-system` | 0.04 | 128MB | 问卷后台前端 |

**资源汇总**：

- 容器合计：~0.70C / ~1.8GB
- OS 预留：~0.2C / ~0.2GB
- 总计：~0.90C / ~2.0GB（监控栈迁入后余量较小，保留短周期指标与轻量面板）

### 目录结构（ServerB）

```text
/opt/nsq/                # NSQ 服务
├── nsqd/
├── nsqlookupd/
└── nsqadmin/
/opt/miniblog/           # Miniblog 服务
├── backend/
├── frontend-admin/
└── frontend-blog/
/opt/qs-ops/             # 问卷后台前端
/data/
├── nsq/                 # NSQ 数据
└── logs/                # 日志目录
```

## 网络通信

### Overlay 网络 (infra-network)

| 属性 | 值 |
|------|-----|
| 子网 | `172.20.0.0/16` |
| 网关 | `172.20.0.1` |
| 驱动 | overlay |
| 加密 | enabled |

### 端口映射

#### ServerA 开放端口

| 服务 | 端口 | 外部访问 |
|------|------|----------|
| Nginx | 80, 443 | ✅ 公网 |
| Redis | 6379 | 🔒 内网 |
| MongoDB | 27017 | 🔒 内网 |

#### ServerB 开放端口

| 服务 | 端口 | 外部访问 |
|------|------|----------|
| nsqlookupd | 4160, 4161 | �� 内网 |
| nsqd | 4150, 4151 | 🔒 内网 |
| nsqadmin | 4171 | 🔒 127.0.0.1 |
| 前端服务 | 8081-8083 | 🔒 内网 |

> 🔒 内网 = 仅限 Overlay 网络或 VPC 内网访问

## 域名路由

所有域名解析到 ServerA 公网 IP，由 Nginx 统一代理：

| 域名 | 目标服务 | 位置 |
|------|---------|------|
| `iam.fangcunmount.cn` | iam-apiserver | ServerA |
| `qs.fangcunmount.cn` | qs-apiserver | ServerA |
| `collect.fangcunmount.cn` | qs-collection | ServerA |
| `operating.fangcunmount.cn` | qs-operating-system | ServerB |
| `blog.yangshujie.com` | miniblog-frontend-blog | ServerB |
| `blog-admin.yangshujie.com` | miniblog-frontend-admin | ServerB |
| `nsqadmin.yangshujie.com` | nsqadmin | ServerB |

## 云服务连接

### 云 MySQL (RDS)

```env
MYSQL_HOST=your-rds.mysql.rds.aliyuncs.com
MYSQL_PORT=3306
MYSQL_USERNAME=xxx
MYSQL_PASSWORD=xxx
```

### Redis 单实例

```env
REDIS_HOST=redis-cache
REDIS_PORT=6379
REDIS_USERNAME=app
REDIS_PASSWORD=${REDIS_APP_PASSWORD}
```

## 相关文档

- [服务器初始化](./initialization.md)
- [网络架构](../network/architecture.md)
- [组件文档](../components/README.md)

---

**更新时间**: 2025-02-18  
**架构版本**: v2.1
