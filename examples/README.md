# 配置示例文件

本目录包含使用 www 用户运行业务进程的配置示例。

## 目录结构

```text
examples/
├── systemd/                      # systemd 服务配置示例
│   ├── qs-api.service           # 原生服务示例
│   └── qs-stack.service         # Docker Compose 服务示例
│
└── docker-compose/               # Docker Compose 配置示例
    └── www-user-example.yml     # 使用 www 用户的完整示例
```

## systemd 服务示例

### 原生服务 (`qs-api.service`)

将业务二进制程序作为 systemd 服务运行,进程以 www 用户身份执行。

**安装步骤**:

```bash
# 1. 复制服务文件
sudo cp examples/systemd/qs-api.service /etc/systemd/system/

# 2. 创建必要目录
sudo mkdir -p /srv/apps/qs-api/{data,config}
sudo mkdir -p /var/log/apps
sudo chown -R www:www /srv/apps/qs-api /var/log/apps

# 3. 准备配置和二进制文件
# sudo cp config.yaml /etc/qs/
# sudo cp qs-api /usr/local/bin/
# sudo chmod +x /usr/local/bin/qs-api

# 4. 启用和启动服务
sudo systemctl daemon-reload
sudo systemctl enable qs-api
sudo systemctl start qs-api

# 5. 验证
sudo systemctl status qs-api
ps -o user,group,cmd -C qs-api
```

**特点**:

- 进程以 www:www 用户运行
- 包含安全加固配置
- 自动重启策略
- 资源限制

### Docker Compose 服务 (`qs-stack.service`)

使用 systemd 管理整个 Docker Compose 服务栈。

**安装步骤**:

```bash
# 1. 复制服务文件
sudo cp examples/systemd/qs-stack.service /etc/systemd/system/

# 2. 准备 docker-compose.yml
sudo mkdir -p /srv/apps/qs
sudo cp your-docker-compose.yml /srv/apps/qs/docker-compose.yml

# 3. 启用和启动
sudo systemctl daemon-reload
sudo systemctl enable qs-stack
sudo systemctl start qs-stack

# 4. 验证
sudo systemctl status qs-stack
docker ps
```

**特点**:

- 开机自动启动 Docker Compose 栈
- 统一的服务管理接口
- 支持 reload (热更新)

## Docker Compose 示例

### www 用户示例 (`www-user-example.yml`)

展示如何在 Docker Compose 中正确使用 www 用户。

**使用步骤**:

```bash
# 1. 准备目录和权限
sudo mkdir -p /srv/apps/{qs-api,nginx,static}
sudo mkdir -p /srv/apps/qs-api/{data,config}
sudo mkdir -p /srv/apps/nginx/{conf.d,certs}
sudo mkdir -p /var/log/apps

# 设置 www 权限
sudo chown -R www:www /srv/apps /var/log/apps
sudo find /srv/apps -type d -exec chmod 750 {} \;
sudo find /srv/apps -type f -exec chmod 640 {} \;

# 只读配置保持 root:root
sudo chown -R root:root /srv/apps/*/config /srv/apps/nginx/conf.d
sudo chmod 755 /srv/apps/*/config /srv/apps/nginx/conf.d

# 2. 确保环境文件存在
ls -la /opt/infra/.env | grep -E "WWW_UID|WWW_GID"

# 3. 启动服务
cd /srv/apps/qs
docker compose -f examples/docker-compose/www-user-example.yml up -d

# 4. 验证容器内用户
docker exec -it qs-api id
docker top qs-api
```

**示例包含**:

- 业务应用容器 (qs-api)
- Nginx 两种方案:
  - 方案 A: 官方镜像默认行为 (推荐)
  - 方案 B: www 用户 + 非特权端口
- 完整的安全配置
- 健康检查
- 网络和依赖配置

## 关键配置说明

### 1. systemd 服务用户

```ini
[Service]
User=www
Group=www
WorkingDirectory=/srv/apps/qs-api
```

### 2. Docker Compose 用户

```yaml
services:
  app:
    user: "${WWW_UID}:${WWW_GID}"
    env_file: /opt/infra/.env
```

### 3. 安全加固

```yaml
# systemd
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/var/log/apps /srv/apps/data

# Docker
read_only: true
cap_drop: ["ALL"]
security_opt: ["no-new-privileges:true"]
```

### 4. 目录权限

```bash
# 可写目录 - www:www 750
/srv/apps/*/data
/var/log/apps

# 只读配置 - root:root 755
/srv/apps/*/config
/srv/apps/nginx/conf.d
```

## 常见场景

### 场景 1: Node.js 应用

```yaml
services:
  node-app:
    image: node:20-alpine
    user: "${WWW_UID}:${WWW_GID}"
    working_dir: /app
    command: node server.js
    volumes:
      - /srv/apps/node-app:/app:ro
      - /var/log/apps:/app/logs:rw
```

### 场景 2: Python 应用

```yaml
services:
  python-app:
    image: python:3.11-slim
    user: "${WWW_UID}:${WWW_GID}"
    working_dir: /app
    command: python app.py
    volumes:
      - /srv/apps/python-app:/app:ro
      - /var/log/apps:/app/logs:rw
```

### 场景 3: Go 应用

```yaml
services:
  go-app:
    image: alpine:latest
    user: "${WWW_UID}:${WWW_GID}"
    command: /app/server
    volumes:
      - /srv/apps/go-app/bin:/app:ro
      - /srv/apps/go-app/data:/data:rw
      - /var/log/apps:/var/log:rw
```

## 故障排查

### 权限问题

```bash
# 检查目录所有者
ls -la /srv/apps/
ls -la /var/log/apps/

# 修复权限
sudo chown -R www:www /srv/apps/qs-api/data
sudo chmod 750 /srv/apps/qs-api/data
```

### 容器用户验证

```bash
# 查看容器内用户
docker exec -it <container> id

# 查看进程用户
docker top <container>

# 查看文件所有者
docker exec -it <container> ls -la /var/log/
```

### 日志查看

```bash
# systemd 服务日志
sudo journalctl -u qs-api -f

# Docker 容器日志
docker logs -f qs-api
```

## 参考文档

- [www 用户使用指南](../docs/server/www-user-guide.md)
- [服务器初始化](../docs/server/initialization.md)
- [systemd 文档](https://www.freedesktop.org/software/systemd/man/)
- [Docker Compose 文档](https://docs.docker.com/compose/)

---

**更新时间**: 2025-10-24  
**版本**: v1.0
