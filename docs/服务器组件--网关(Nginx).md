# 服务器组件 - 网关 (Nginx)

## 概述

Nginx 作为基础设施的 Web 网关服务，负责：
- HTTP/HTTPS 反向代理
- 静态文件服务
- 负载均衡
- SSL 终结（证书由 Jenkins 管理）

## 架构设计

### 职责分离

1. **infra 项目职责**：
   - 提供 Nginx 容器和基础配置
   - 提供应用配置管理工具
   - 管理共享配置目录和权限
   - **SSL 证书集中管理和自动续期**
   - 提供 SSL 证书管理工具

2. **应用项目职责**：
   - 编写自己的 Nginx 站点配置文件
   - 通过 infra 工具部署配置
   - 管理应用相关的前端/后端服务
   - 在需要 HTTPS 时申请 SSL 证书

3. **Jenkins 职责**：
   - 代码构建和部署
   - 应用配置文件的 CI/CD
   - 部署后的服务健康检查

## 目录结构

```
components/nginx/
├── nginx.conf              # 主配置文件
├── override.yml           # 本地开发覆盖配置  
└── conf.d/                # 站点配置目录
    ├── README.md          # 配置说明文档
    ├── default.conf       # 默认兜底配置
    └── apps/              # 应用配置目录
        └── README.md      # 应用配置说明

/data/apps/nginx-configs/   # 宿主机应用配置目录
├── README.txt             # 使用说明
├── blog.conf              # MiniBlog 配置
├── api.conf               # API 服务配置
└── admin.conf             # 管理后台配置
```

## 部署步骤

### 1. 初始化应用配置目录

```bash
# 创建并设置应用配置目录权限
bash scripts/init-components/init-apps-config.sh
```

这将创建 `/data/apps/nginx-configs/` 目录并设置正确的权限。

### 2. 部署 Nginx 服务

```bash
# 安装 Nginx 组件
make install-nginx

# 启动 Nginx 服务
make up-nginx

# 检查服务状态
make status
```

### 3. 验证部署

```bash
# 测试 Nginx 配置
make nginx-test

# 访问默认页面
curl http://localhost
# 响应: Infrastructure Gateway Ready

# 健康检查
curl http://localhost/health  
# 响应: healthy
```

## 应用配置管理

### 配置工作原理

1. **共享目录挂载**：
   - infra 将 `/data/apps/nginx-configs/` 挂载到 nginx 容器的 `/etc/nginx/conf.d/apps/`
   
2. **配置部署流程**：
   - 应用项目编写 nginx 配置文件
   - 使用 infra 工具将配置复制到共享目录
   - 自动测试配置有效性
   - 自动重载 nginx 配置

3. **原子操作**：
   - 配置有误时自动回滚
   - 确保 nginx 服务稳定性

### 管理命令

#### 部署应用配置

```bash
# 部署 MiniBlog 配置
make app-deploy APP=blog CONFIG=./path/to/blog.conf

# 部署 API 服务配置  
make app-deploy APP=api CONFIG=./path/to/api.conf
```

#### 管理现有配置

```bash
# 列出所有已部署的配置
make app-list

# 移除应用配置
make app-remove APP=blog

# 测试 nginx 配置
make nginx-test

# 重载 nginx 配置
make nginx-reload
```

#### 直接使用脚本

```bash
# 部署配置
bash scripts/utils/nginx-app-manager.sh deploy blog ./nginx/blog.conf

# 移除配置
bash scripts/utils/nginx-app-manager.sh remove blog

# 列出配置
bash scripts/utils/nginx-app-manager.sh list

# 重载配置
bash scripts/utils/nginx-app-manager.sh reload
```

## 应用项目集成示例

### MiniBlog 项目集成

#### 1. 创建配置文件

在 MiniBlog 项目中创建 `nginx/blog.conf`：

```nginx
# MiniBlog 前端服务配置
server {
    listen 80;
    server_name blog.example.com;
    
    # 静态文件根目录
    root /var/www/blog;
    index index.html;
    
    # SPA 路由处理
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }
    
    # 安全头
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
}
```

#### 2. 部署配置

```bash
# 在 infra 项目目录中执行
make app-deploy APP=blog CONFIG=/path/to/miniblog/nginx/blog.conf
```

#### 3. MiniBlog docker-compose.yml 配置

```yaml
services:
  blog:
    image: miniblog:latest
    networks:
      - infra-frontend
    volumes:
      - ./dist:/var/www/blog:ro

networks:
  infra-frontend:
    external: true
```

### API 服务集成

#### 1. 创建 API 配置文件

```nginx
# API 服务配置
upstream api_backend {
    server api:3000;
    keepalive 32;
}

server {
    listen 80;
    server_name api.example.com;
    
    # API 代理
    location / {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # API 特定配置
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
    
    # 健康检查
    location /health {
        proxy_pass http://api_backend/health;
        access_log off;
    }
}
```

#### 2. 部署 API 配置

```bash
make app-deploy APP=api CONFIG=./nginx/api.conf
```

## SSL 证书管理

### 证书管理策略

- **所有 SSL 证书由 infra 项目统一管理**
- **使用专用的 ssl-manager.sh 脚本管理证书**
- **证书存储在 `/data/ssl` 目录**
- **支持 Let's Encrypt 自动申请和续期**

### SSL 证书管理流程

1. **证书申请**：
   ```bash
   # 申请新证书
   make ssl-obtain DOMAIN=blog.example.com EMAIL=admin@example.com
   
   # 或直接使用脚本
   ./scripts/utils/ssl-manager.sh obtain blog.example.com admin@example.com
   ```

2. **证书续期**：
   ```bash
   # 手动续期所有证书
   make ssl-renew
   
   # 设置自动续期（推荐）
   make ssl-setup
   ```

3. **证书管理**：
   ```bash
   # 列出所有证书
   make ssl-list
   
   # 删除证书
   make ssl-remove DOMAIN=blog.example.com
   
   # 生成 SSL 配置模板
   make ssl-config DOMAIN=blog.example.com > /data/apps/nginx-configs/blog-ssl.conf
   ```

### SSL 证书目录结构

```
/data/ssl/
├── certs/                  # 证书文件
│   ├── blog.example.com.crt
│   └── api.example.com.crt
├── private/                # 私钥文件
│   ├── blog.example.com.key
│   └── api.example.com.key
├── archive/                # 证书存档
├── renewal/                # 续期配置
└── renew-certs.sh         # 自动续期脚本
```

### 自动续期设置

SSL 证书会自动设置每周一凌晨 2 点的续期任务：

```bash
# 查看 crontab
crontab -l

# 续期任务
0 2 * * 1 /data/ssl/renew-certs.sh
```

## 网络配置

### Docker 网络

```yaml
# 前端网络（用于 Web 流量）
networks:
  infra-frontend:
    external: true
    name: infra-frontend

# 后端网络（用于服务间通信）
networks:
  infra-backend:
    external: true
    name: infra-backend
```

### 端口配置

```yaml
ports:
  - "${NGINX_HTTP_PORT:-80}:80"      # HTTP 端口
  - "${NGINX_HTTPS_PORT:-443}:443"   # HTTPS 端口
```

### 环境变量

```bash
# .env 文件配置
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443
```

## 日志管理

### 日志配置

- **主日志**：`/data/log/nginx/access.log`, `/data/log/nginx/error.log`
- **应用日志**：每个应用可配置独立的日志文件

### 日志查看

```bash
# 查看 nginx 日志
make logs SERVICE=nginx

# 查看实时日志
docker logs -f nginx

# 查看应用特定日志
tail -f /data/log/nginx/blog.access.log
```

## 性能优化

### 主要优化配置

1. **Worker 进程**：`worker_processes auto`
2. **连接数**：`worker_connections 4096`
3. **文件句柄**：`worker_rlimit_nofile 100000`
4. **Gzip 压缩**：自动压缩文本类型文件
5. **静态文件缓存**：合理的缓存策略

### 内存限制

```yaml
deploy:
  resources:
    limits:
      memory: 256M
    reservations:
      memory: 128M
```

## 故障排除

### 常见问题

#### 1. 配置文件语法错误

```bash
# 测试配置
make nginx-test

# 查看错误日志
docker logs nginx
```

#### 2. 应用配置未生效

```bash
# 检查配置是否存在
make app-list

# 重新部署配置
make app-deploy APP=blog CONFIG=./nginx/blog.conf

# 重载配置
make nginx-reload
```

#### 3. 权限问题

```bash
# 检查应用配置目录权限
ls -la /data/apps/nginx-configs/

# 重新初始化目录权限
bash scripts/init-components/init-apps-config.sh
```

#### 4. 网络连接问题

```bash
# 检查 Docker 网络
docker network ls | grep infra

# 检查容器网络连接
docker exec nginx ping api
```

### 调试命令

```bash
# 进入容器调试
docker exec -it nginx /bin/bash

# 检查配置文件
docker exec nginx ls -la /etc/nginx/conf.d/
docker exec nginx cat /etc/nginx/conf.d/apps/blog.conf

# 检查进程状态
docker exec nginx ps aux

# 重新加载配置
docker exec nginx nginx -s reload

# 测试配置
docker exec nginx nginx -t
```

## 监控指标

### 关键指标

1. **服务状态**：nginx 进程运行状态
2. **响应时间**：请求响应延迟
3. **错误率**：4xx/5xx 错误比例
4. **连接数**：并发连接数量
5. **流量**：请求 QPS 和带宽使用

### 健康检查

```bash
# HTTP 健康检查
curl -f http://localhost/health

# 通过 Docker 检查
docker exec nginx nginx -t
```

## 最佳实践

### 配置文件管理

1. **命名规范**：使用应用名称作为配置文件名
2. **版本控制**：配置文件纳入 Git 版本控制
3. **配置验证**：部署前自动测试配置有效性
4. **原子操作**：配置有误时自动回滚

### 安全配置

1. **安全头**：强制添加安全 HTTP 头
2. **隐藏文件保护**：禁止访问 `.` 开头的文件
3. **备份文件保护**：禁止访问 `~` 结尾的文件
4. **SSL 配置**：由 Jenkins 统一管理证书

### 性能优化

1. **静态资源缓存**：合理设置缓存策略
2. **Gzip 压缩**：启用文本类型压缩
3. **连接复用**：启用 keepalive 连接
4. **缓冲配置**：根据应用特点调整缓冲区

### 日志管理

1. **访问日志**：记录详细的访问信息
2. **错误日志**：适当的错误日志级别
3. **应用隔离**：不同应用使用独立日志文件
4. **日志轮转**：配置日志文件轮转策略

---

*本文档记录了 Nginx 网关服务的完整部署和管理流程。如有问题，请参考故障排除章节或查看相关日志文件。*