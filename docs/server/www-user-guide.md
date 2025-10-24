# www 用户使用指南

本文档说明如何在不同场景下使用 www 系统用户运行业务进程。

## www 用户基本信息

```bash
# 查看 www 用户信息
id www

# 输出示例:
# uid=999(www) gid=999(www) groups=999(www)
```

**特点**:

- **不可登录**: Shell 为 `/usr/sbin/nologin`
- **无特殊权限**: 不在 sudo 或 docker 组
- **仅用于运行进程**: 通过 systemd 或 Docker 使用

## 使用场景

### 场景 1: 原生 systemd 服务

创建 systemd 服务配置文件,让进程以 www 用户运行。

#### 示例: API 服务

文件: `/etc/systemd/system/qs-api.service`

```ini
[Unit]
Description=QS API Service
Documentation=https://github.com/yourorg/qs-api
After=network.target docker.service

[Service]
Type=simple
User=www
Group=www
WorkingDirectory=/srv/apps/qs-api

# 环境变量
Environment="NODE_ENV=production"
Environment="PORT=3000"
EnvironmentFile=/opt/infra/.env

# 启动命令
ExecStart=/usr/local/bin/qs-api --config /etc/qs/config.yaml

# 重启策略
Restart=on-failure
RestartSec=5s
StartLimitInterval=300s
StartLimitBurst=5

# 安全加固
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/var/log/apps /srv/apps/qs-api/data

# 资源限制
LimitNOFILE=65536
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
```

#### 启用和管理

```bash
# 重载 systemd 配置
sudo systemctl daemon-reload

# 启用服务(开机自启)
sudo systemctl enable qs-api

# 启动服务
sudo systemctl start qs-api

# 查看状态
sudo systemctl status qs-api

# 查看日志
sudo journalctl -u qs-api -f

# 验证进程用户
ps -o user,group,uid,gid,cmd -C qs-api
# 应显示: www www 999 999 /usr/local/bin/qs-api...
```

### 场景 2: Docker Compose 服务

在 Docker Compose 中使用 www 用户的 UID/GID 运行容器。

#### 2.1 配置环境变量

www 用户的 UID/GID 已自动写入 `/opt/infra/.env`:

```bash
# 查看 www 用户 UID/GID
cat /opt/infra/.env | grep WWW
# 输出:
# WWW_UID=999
# WWW_GID=999
```

#### 2.2 Docker Compose 配置

文件: `docker-compose.yml`

```yaml
version: '3.8'

services:
  # 业务应用容器
  qs-api:
    image: ghcr.io/yourorg/qs-api:1.2.3
    container_name: qs-api
    
    # ★ 重要: 使用 www 用户运行容器
    user: "${WWW_UID}:${WWW_GID}"
    
    # 环境变量
    env_file: /opt/infra/.env
    environment:
      - NODE_ENV=production
      - PORT=3000
    
    # 挂载目录 (必须是 www:www 权限)
    volumes:
      - /srv/apps/qs-api/data:/var/lib/qs:rw
      - /var/log/apps:/var/log/qs:rw
      - /srv/apps/qs-api/config:/etc/qs:ro
    
    # 端口映射
    ports:
      - "3000:3000"
    
    # 网络
    networks:
      - app-network
      - infra-network
    
    # 安全配置
    read_only: true
    tmpfs:
      - /tmp
      - /var/tmp
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE  # 如果需要绑定 < 1024 端口
    security_opt:
      - no-new-privileges:true
    
    # 重启策略
    restart: unless-stopped
    
    # 健康检查
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  app-network:
    external: true
  infra-network:
    external: true
```

#### 2.3 准备目录权限

```bash
# 创建业务目录并设置 www 权限
sudo mkdir -p /srv/apps/qs-api/{data,config}
sudo mkdir -p /var/log/apps

# 设置所有者为 www:www
sudo chown -R www:www /srv/apps/qs-api /var/log/apps

# 设置权限
sudo find /srv/apps/qs-api -type d -exec chmod 750 {} \;
sudo find /srv/apps/qs-api -type f -exec chmod 640 {} \;
sudo chmod 750 /var/log/apps
```

#### 2.4 启动容器

```bash
# 启动服务
docker compose up -d

# 验证容器内用户
docker exec -it qs-api id
# 应显示: uid=999(www) gid=999(www) groups=999(www)

# 查看进程
docker top qs-api
# UID 列应该是 999 (www)

# 测试写权限
docker exec -it qs-api touch /var/log/qs/test.log
docker exec -it qs-api ls -la /var/log/qs/test.log
# 应显示: -rw-r--r-- 1 www www ...
```

### 场景 3: Nginx 容器 (特殊处理)

Nginx 需要绑定 80/443 端口,有两种方案:

#### 方案 A: 使用官方镜像默认行为 (推荐)

官方 Nginx 镜像会自动:

1. 以 root 启动并绑定 80/443
2. 内部降权到 nginx/www-data 用户

```yaml
services:
  nginx:
    image: nginx:1.27-alpine
    container_name: nginx
    
    # 不设置 user,使用官方镜像默认行为
    
    ports:
      - "80:80"
      - "443:443"
    
    volumes:
      - /srv/apps/nginx/conf.d:/etc/nginx/conf.d:ro
      - /srv/apps/nginx/certs:/etc/nginx/certs:ro
      - /srv/apps/static:/usr/share/nginx/html:ro
    
    networks:
      - infra-network
    
    restart: unless-stopped
```

#### 方案 B: 非特权端口 + www 用户

让 Nginx 监听 8080/8443,宿主机端口映射到 80/443:

```yaml
services:
  nginx:
    image: nginx:1.27-alpine
    container_name: nginx
    
    # 使用 www 用户运行
    user: "${WWW_UID}:${WWW_GID}"
    
    # 端口映射: 宿主机 80/443 → 容器 8080/8443
    ports:
      - "80:8080"
      - "443:8443"
    
    volumes:
      - /srv/apps/nginx/conf.d:/etc/nginx/conf.d:ro
      - /srv/apps/nginx/certs:/etc/nginx/certs:ro
      - /srv/apps/static:/usr/share/nginx/html:ro
    
    networks:
      - infra-network
    
    restart: unless-stopped
```

修改 Nginx 配置文件,监听 8080/8443:

```nginx
# /srv/apps/nginx/conf.d/default.conf
server {
    listen 8080;
    listen [::]:8080;
    server_name example.com;
    # ...
}

server {
    listen 8443 ssl http2;
    listen [::]:8443 ssl http2;
    server_name example.com;
    # ...
}
```

#### 方案 C: 使用 NET_BIND_SERVICE capability

保持 80/443,给容器 NET_BIND_SERVICE 能力:

```yaml
services:
  nginx:
    image: nginx:1.27-alpine
    user: "${WWW_UID}:${WWW_GID}"
    
    ports:
      - "80:80"
      - "443:443"
    
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE  # 允许非 root 绑定特权端口
    
    # ... 其他配置
```

### 场景 4: 使用 systemd 驱动 Docker Compose

用 systemd 管理 Docker Compose 服务栈:

文件: `/etc/systemd/system/qs-stack.service`

```ini
[Unit]
Description=QS Application Stack (Docker Compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/srv/apps/qs
EnvironmentFile=/opt/infra/.env

# 启动
ExecStart=/usr/bin/docker compose up -d

# 停止
ExecStop=/usr/bin/docker compose down

# 重载配置
ExecReload=/usr/bin/docker compose up -d --force-recreate

[Install]
WantedBy=multi-user.target
```

启用服务:

```bash
sudo systemctl daemon-reload
sudo systemctl enable qs-stack
sudo systemctl start qs-stack

# 查看状态
sudo systemctl status qs-stack

# 重启服务栈
sudo systemctl restart qs-stack
```

**注意**: systemd 只是拉起 Docker Compose,容器内用户仍由 `user: "${WWW_UID}:${WWW_GID}"` 决定。

## 目录权限管理

### 标准目录结构

```text
/srv/apps/          # 应用部署目录
├── qs-api/
│   ├── data/       # 应用数据 (rw)
│   └── config/     # 配置文件 (ro)
└── nginx/
    ├── conf.d/     # Nginx 配置 (ro)
    ├── certs/      # SSL 证书 (ro)
    └── ...

/var/log/apps/      # 应用日志目录 (rw)
├── qs-api/
└── nginx/

/var/www/           # www 用户主目录
```

### 权限设置清单

```bash
# 1. 业务可写目录 → www:www 750/640
sudo chown -R www:www /srv/apps /var/log/apps /var/www
sudo find /srv/apps -type d -exec chmod 750 {} \;
sudo find /srv/apps -type f -exec chmod 640 {} \;
sudo chmod 750 /var/log/apps

# 2. 只读配置目录 → root:root 755/644 (容器只读挂载)
sudo chown -R root:root /srv/apps/*/config /srv/apps/nginx/conf.d
sudo find /srv/apps/*/config -type d -exec chmod 755 {} \;
sudo find /srv/apps/*/config -type f -exec chmod 644 {} \;

# 3. 验证权限
ls -la /srv/apps/
ls -la /var/log/apps/
```

### 常见权限问题

#### 问题1: 容器内无法写文件

**症状**: `Permission denied` 错误

**原因**: 宿主机目录不是 www:www 权限

**解决**:

```bash
sudo chown -R www:www /srv/apps/qs-api/data
sudo chmod 750 /srv/apps/qs-api/data
```

#### 问题2: 配置文件被容器修改

**症状**: 配置文件所有者变成 www:www

**原因**: 挂载时没有使用 `:ro` (只读)

**解决**: 在 docker-compose.yml 中使用只读挂载

```yaml
volumes:
  - /srv/apps/qs-api/config:/etc/qs:ro  # ← 添加 :ro
```

## 安全最佳实践

### 1. 最小权限原则

```yaml
# ✅ 正确: www 用户无特殊权限
user: "${WWW_UID}:${WWW_GID}"
cap_drop: ["ALL"]
read_only: true

# ❌ 错误: 给 www 用户 sudo/docker 权限
# 不要将 www 添加到 sudo 或 docker 组
```

### 2. 文件系统只读

```yaml
# 根文件系统只读,需要写的目录用 tmpfs/volumes
read_only: true
tmpfs:
  - /tmp
  - /var/tmp
volumes:
  - /var/log/apps:/var/log/qs:rw  # 只有日志目录可写
```

### 3. 删除所有 capabilities

```yaml
cap_drop:
  - ALL
cap_add:
  - NET_BIND_SERVICE  # 仅在需要绑定 < 1024 端口时添加
```

### 4. 禁止权限提升

```yaml
security_opt:
  - no-new-privileges:true
```

### 5. 健康检查

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

## 故障排查

### 检查容器内用户

```bash
# 查看容器内用户
docker exec -it <container> id

# 查看进程用户
docker top <container>

# 验证 UID/GID
docker exec -it <container> stat -c '%u:%g' /var/log/qs
```

### 检查文件权限

```bash
# 宿主机权限
ls -la /srv/apps/qs-api/data/
stat /srv/apps/qs-api/data/

# 容器内权限
docker exec -it <container> ls -la /var/lib/qs/
docker exec -it <container> stat /var/lib/qs/
```

### 测试写权限

```bash
# 测试容器内写权限
docker exec -it <container> touch /var/log/qs/test.log
docker exec -it <container> echo "test" > /var/lib/qs/test.txt

# 检查生成的文件所有者
ls -la /var/log/apps/test.log
ls -la /srv/apps/qs-api/data/test.txt
```

## 参考资料

### 相关文档

- [服务器初始化](../../docs/server/initialization.md)
- [服务器架构](../../docs/server/architecture.md)
- [Docker安全](https://docs.docker.com/engine/security/)

### 官方文档

- [systemd.service](https://www.freedesktop.org/software/systemd/man/systemd.service.html)
- [Docker Compose user](https://docs.docker.com/compose/compose-file/05-services/#user)
- [Docker security](https://docs.docker.com/engine/security/security/)

---

**更新时间**: 2025-10-24  
**版本**: v1.0
