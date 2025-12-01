# 基础设施文档导航

## 🚀 快速开始

```bash
make help              # 查看所有可用命令
make help-mongo        # MongoDB 命令参考
make help-redis        # Redis 命令参考
make help-nsq          # NSQ 命令参考
make help-vpn          # VPN 命令参考
make help-ssl          # SSL 证书命令参考
make service-ports     # 查看服务端口
```

## 📖 文档结构

```text
docs/
├── INDEX.md                    # 本文档 - 导航入口
│
├── server/                     # 服务器配置
│   ├── architecture.md         # 架构设计 + 资源规划
│   ├── initialization.md       # 初始化指南
│   ├── www-user-guide.md       # www 用户使用指南
│   ├── ssl-guide.md            # SSL 证书使用指南
│   └── github-actions-deploy-guide.md  # CI/CD 部署指南
│
├── components/                 # 组件文档
│   ├── README.md               # 组件总览
│   ├── mongodb-quickstart.md   # MongoDB 快速入门
│   └── nsq.md                  # NSQ 配置指南
│
└── network/                    # 网络管理
    ├── architecture.md         # 网络架构
    └── management.md           # 管理指南
```

## 🖥️ 服务器架构

- [架构设计](./server/architecture.md) - 双机部署规划、资源分配、云服务连接
- [初始化指南](./server/initialization.md) - 用户配置、Docker 安装

## 🔧 组件文档

- [组件总览](./components/README.md) - 所有组件快速参考
- [MongoDB 快速入门](./components/mongodb-quickstart.md)
- [NSQ 消息队列](./components/nsq.md)

## 🌐 网络管理

- [网络架构](./network/architecture.md) - Overlay 网络设计
- [网络管理指南](./network/management.md) - VPN、Swarm 配置

## 🔒 安全与部署

- [www 用户指南](./server/www-user-guide.md) - 业务进程账户使用
- [CI/CD 部署指南](./server/github-actions-deploy-guide.md) - GitHub Actions 配置
- [SSL 证书指南](./server/ssl-guide.md) - 通配符证书申请

## 🎯 快速查找

| 我想... | 参考文档 |
|---------|----------|
| 了解整体架构 | [架构设计](./server/architecture.md) |
| 初始化新服务器 | [初始化指南](./server/initialization.md) |
| 启动/管理 MongoDB | [MongoDB 快速入门](./components/mongodb-quickstart.md) |
| 配置 NSQ 消息队列 | [NSQ 配置指南](./components/nsq.md) |
| 申请 SSL 证书 | [SSL 证书指南](./SSL证书申请指南-通配符证书.md) |
| 配置 CI/CD 部署 | [CI/CD 部署指南](./server/github-actions-deploy-guide.md) |
| 配置网络/VPN | [网络管理指南](./network/management.md) |
