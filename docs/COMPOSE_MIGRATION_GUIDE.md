# Docker Compose 架构重构迁移指南

## 📋 重构概览

### 🎯 重构目标
- **职责分离**: 基础设施与应用服务分离
- **模块化管理**: 每个组件独立配置和部署
- **环境一致性**: 统一的环境配置管理
- **扩展性**: 易于添加新服务和环境

### 📂 新架构结构
```
compose/
├── infra/                          # 基础设施层
│   ├── docker-compose.yml          # 核心网络和卷
│   ├── docker-compose.nginx.yml    # 网关服务
│   ├── docker-compose.storage.yml  # 存储服务
│   ├── docker-compose.message.yml  # 消息服务
│   └── docker-compose.cicd.yml     # CI/CD 服务
├── apps/                           # 应用服务层
│   ├── miniblog/
│   ├── qs-api/
│   ├── qs-collection/
│   └── qs-evaluation/
├── env/                            # 环境配置层
│   ├── dev/
│   ├── staging/
│   └── prod/
└── base/                           # 原始文件 (已废弃)
    └── docker-compose.yml
```

## 🚀 迁移步骤

### 第一步：备份原始配置
```bash
# 备份原始 compose 文件
cp compose/base/docker-compose.yml compose/base/docker-compose.yml.backup

# 停止现有服务（如果正在运行）
docker-compose -f compose/base/docker-compose.yml down
```

### 第二步：使用新架构启动基础设施
```bash
# 使用新的管理脚本
./scripts/deploy/compose-manager.sh infra up all

# 或者手动启动
cd compose
docker compose -f infra/docker-compose.yml \
                -f infra/docker-compose.nginx.yml \
                -f infra/docker-compose.storage.yml \
                --env-file env/dev/.env up -d
```

### 第三步：验证基础设施服务
```bash
# 检查服务状态
./scripts/deploy/compose-manager.sh status

# 检查网络
docker network ls --filter "name=infra-"

# 检查卷
docker volume ls --filter "name=compose_"
```

### 第四步：迁移应用服务
```bash
# 启动应用服务
./scripts/deploy/compose-manager.sh app up miniblog

# 或批量启动
./scripts/deploy/compose-manager.sh app up all
```

## 🔧 配置迁移

### 环境变量迁移
原始配置 → 新配置映射：

| 原始位置 | 新位置 | 说明 |
|---------|--------|------|
| 各组件 override.yml | compose/env/{env}/.env | 统一环境配置 |
| hardcoded 值 | 环境变量 | 所有配置可配置化 |
| 端口映射在 override | 应用层 compose | 应用独立端口管理 |

### 网络配置更新
```yaml
# 旧配置
networks:
  backend:
    name: infra-backend
    internal: false

# 新配置
networks:
  backend:
    external: true
    name: infra-backend
```

### 卷配置更新
```yaml
# 旧配置 - 在每个 override 中定义
volumes:
  - /data/mysql:/var/lib/mysql

# 新配置 - 使用命名卷
volumes:
  - mysql_data:/var/lib/mysql
```

## 📋 功能对比

| 功能 | 旧架构 | 新架构 | 改进 |
|------|--------|--------|------|
| 服务部署 | 全部一起 | 分层独立 | ✅ 可选择性部署 |
| 配置管理 | 分散在多个文件 | 统一环境配置 | ✅ 集中管理 |
| 环境隔离 | 部分支持 | 完全支持 | ✅ 多环境支持 |
| 服务发现 | 依赖容器名 | 使用服务名 | ✅ 标准化命名 |
| 扩展性 | 修改基础文件 | 添加新文件 | ✅ 无侵入扩展 |
| 维护性 | 复杂 | 简单清晰 | ✅ 职责明确 |

## 🎮 新管理方式

### 基础设施管理
```bash
# 启动所有基础设施
./scripts/deploy/compose-manager.sh infra up all

# 仅启动存储服务
./scripts/deploy/compose-manager.sh infra up storage

# 仅启动网关
./scripts/deploy/compose-manager.sh infra up nginx

# 重启 CI/CD 服务
./scripts/deploy/compose-manager.sh infra restart cicd
```

### 应用服务管理
```bash
# 启动特定应用
./scripts/deploy/compose-manager.sh app up miniblog

# 更新应用镜像
./scripts/deploy/compose-manager.sh app pull miniblog
./scripts/deploy/compose-manager.sh app up miniblog

# 查看应用日志
./scripts/deploy/compose-manager.sh logs miniblog
```

### 环境切换
```bash
# 切换到生产环境
./scripts/deploy/compose-manager.sh -e prod infra up all
./scripts/deploy/compose-manager.sh -e prod app up all

# 切换到测试环境
./scripts/deploy/compose-manager.sh -e staging infra up storage
```

## 🔍 验证清单

### 基础设施验证
- [ ] 网络创建成功 (infra-frontend, infra-backend)
- [ ] 卷创建成功 (mysql_data, redis_data, etc.)
- [ ] 数据库连接正常
- [ ] Redis 缓存正常
- [ ] Nginx 代理正常
- [ ] Jenkins 启动正常

### 应用服务验证
- [ ] 应用容器启动成功
- [ ] 数据库连接正常
- [ ] 服务间通信正常
- [ ] 健康检查通过
- [ ] 端口映射正确

### 网络连通性验证
```bash
# 测试应用到数据库连接
docker exec miniblog ping mysql

# 测试 Nginx 到应用连接
docker exec nginx curl -f http://miniblog:8080/health

# 测试外部访问
curl -f http://localhost:8001/health
```

## 🔄 回滚计划

如果迁移出现问题，可以快速回滚：

```bash
# 停止新架构服务
./scripts/deploy/compose-manager.sh infra down all
./scripts/deploy/compose-manager.sh app down all

# 恢复原始配置
docker-compose -f compose/base/docker-compose.yml.backup \
               -f components/*/override.yml up -d
```

## 📚 后续优化

1. **监控集成**: 添加 Prometheus + Grafana
2. **日志聚合**: 集成 ELK Stack
3. **服务网格**: 考虑 Istio 或 Linkerd
4. **自动化部署**: 完善 CI/CD 流水线
5. **配置管理**: 集成 Consul 或 etcd

## 💡 最佳实践

1. **渐进式迁移**: 先迁移基础设施，再迁移应用
2. **充分测试**: 每个步骤都要验证功能正常
3. **保留备份**: 保留原始配置文件
4. **文档更新**: 及时更新部署文档
5. **团队培训**: 确保团队了解新的管理方式