# Nginx 配置管理

## 目录结构

```
conf.d/
├── default.conf          # 默认兜底配置
└── apps/                # 应用配置目录
    └── README.md        # 使用说明
```

## 配置管理策略

### 1. infra 项目职责

- 提供 Nginx 容器和基础配置
- 提供应用配置管理工具
- 管理基础网络和安全配置

### 2. 应用项目职责

- 编写自己的 Nginx 配置文件
- 通过 infra 提供的工具部署配置
- 管理应用相关的前端/后端服务

### 3. Jenkins 职责（SSL 证书管理）

- 集中管理所有域名的 SSL 证书
- 自动化续期和部署流程
- 与 CI/CD 流程集成
- 统一的安全策略和访问控制

## 使用方式

### 应用项目部署配置

```bash
# 在 infra 项目中执行
make app-deploy APP=blog CONFIG=./path/to/blog.conf

# 或直接使用脚本
bash scripts/utils/nginx-app-manager.sh deploy blog ./nginx/blog.conf
```

### 配置管理命令

```bash
# 部署配置
make app-deploy APP=blog CONFIG=./nginx/blog.conf

# 移除配置
make app-remove APP=blog

# 列出所有配置
make app-list

# 测试配置
make nginx-test

# 重载配置
make nginx-reload
```

## 工作原理

1. **infra 项目**：预先挂载 `/data/apps/nginx-configs/` 目录到 nginx 容器
2. **应用项目**：将配置文件复制到共享目录
3. **自动重载**：配置复制后自动重载 nginx

## SSL 证书管理

SSL 证书管理完全由 Jenkins 负责：

### Jenkins 管理的优势

- **集中化管理**: 所有域名证书统一管理
- **自动化流程**: 证书获取、续期、部署全自动
- **CI/CD 集成**: 与部署流程无缝集成
- **安全控制**: 统一的安全策略和访问控制
- **监控告警**: 证书状态监控和到期提醒

### 实施方式

- Jenkins Pipeline 自动获取 Let's Encrypt 证书
- 定时任务自动续期证书
- 通过 Docker 卷或配置管理将证书部署到 Nginx
- 证书更新后自动重载 Nginx 配置

## 最佳实践

1. **命名规范**: 使用应用名称作为配置文件名
2. **配置验证**: 部署前自动测试 nginx 配置
3. **原子操作**: 配置有误时自动回滚
4. **备份策略**: 配置文件纳入版本控制
5. **监控告警**: 监控 nginx 配置加载状态
6. **证书管理**: 通过 Jenkins 管理 SSL 证书生命周期