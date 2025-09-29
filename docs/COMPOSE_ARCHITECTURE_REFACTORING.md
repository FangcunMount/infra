# Docker Compose 架构重构方案

## 🏗️ 分层架构设计

### 1. 基础设施层 (Infrastructure)
```
compose/
├── infra/
│   ├── docker-compose.yml          # 核心基础设施
│   ├── docker-compose.nginx.yml    # 网关服务
│   ├── docker-compose.storage.yml  # 存储服务 (mysql, redis, mongo)
│   ├── docker-compose.message.yml  # 消息服务 (kafka)
│   └── docker-compose.cicd.yml     # CI/CD 服务 (jenkins)
```

### 2. 应用服务层 (Applications)
```
compose/
├── apps/
│   ├── miniblog/
│   │   └── docker-compose.yml
│   ├── qs-api/
│   │   └── docker-compose.yml
│   ├── qs-collection/
│   │   └── docker-compose.yml
│   └── qs-evaluation/
│   │   └── docker-compose.yml
```

### 3. 环境配置层 (Environment)
```
compose/
├── env/
│   ├── dev/
│   │   ├── .env
│   │   └── override.yml
│   ├── staging/
│   │   ├── .env
│   │   └── override.yml
│   └── prod/
│       ├── .env
│       └── override.yml
```

## 🎯 部署策略

### 基础设施部署
```bash
# 部署完整基础设施
docker compose -f compose/infra/docker-compose.yml \
                -f compose/infra/docker-compose.nginx.yml \
                -f compose/infra/docker-compose.storage.yml \
                -f compose/env/prod/override.yml up -d

# 或按需部署特定服务
docker compose -f compose/infra/docker-compose.storage.yml up -d
```

### 应用服务部署
```bash
# 独立部署应用服务
docker compose -f compose/apps/miniblog/docker-compose.yml up -d

# 批量部署
for app in miniblog qs-api qs-collection qs-evaluation; do
    docker compose -f compose/apps/$app/docker-compose.yml up -d
done
```

## 📋 迁移计划

1. **第一阶段**: 拆分基础设施服务
2. **第二阶段**: 提取业务应用服务  
3. **第三阶段**: 优化环境配置管理
4. **第四阶段**: 更新部署脚本

## ✅ 优势

- **独立部署**: 应用服务可独立更新
- **职责清晰**: 基础设施与业务分离
- **扩展性强**: 易于添加新服务
- **环境一致**: 统一的环境管理
- **维护简单**: 问题定位更精准