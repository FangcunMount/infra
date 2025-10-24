# 用户账户体系重构总结

## 概述

本次重构将原有的单一用户体系升级为三种账户类型,实现职责分离和安全加固。

## 账户体系设计

### 账户类型对比

| 账户 | 类型 | 可登录 | sudo | docker | 用途 |
|------|------|--------|------|--------|------|
| **yangshujie** | 运维账户 | ✅ | ✅ | ✅ | 人工运维和系统管理 |
| **deploy** | CI/CD账户 | ✅ | ❌ | ✅ | 自动化部署和容器管理 |
| **www** | 系统用户 | ❌ | ❌ | ❌ | 运行业务进程 |

### 1. yangshujie (运维账户)

**用途**: 日常运维和系统管理

**特点**:

- Shell: `/bin/bash` (可登录)
- 权限: `sudo` + `docker`
- 主目录: `/home/yangshujie`
- 工作目录: `/home/yangshujie/workspace`

**使用场景**:

```bash
# 登录服务器
ssh yangshujie@server

# 系统管理
sudo apt update
sudo systemctl restart nginx

# 容器管理
docker ps
docker logs <container>
```

### 2. deploy (CI/CD 账户)

**用途**: 自动化部署和 CI/CD 流程

**特点**:

- Shell: `/bin/bash` (可登录)
- 权限: `docker` (无 sudo)
- SSH 密钥: `/home/deploy/.ssh/id_ed25519`
- 主目录: `/home/deploy`
- 工作目录: `/home/deploy/workspace`

**使用场景**:

```bash
# GitHub Actions 或其他 CI 通过 SSH 登录
ssh deploy@server

# 部署容器 (无需 sudo)
docker compose up -d
docker restart app
docker pull image:latest

# 不能执行系统管理操作
sudo apt update  # ❌ Permission denied
```

**GitHub Deploy Key 配置**:

```bash
# 查看公钥
cat /home/deploy/.ssh/id_ed25519.pub

# 添加到 GitHub 仓库:
# Settings → Deploy keys → Add deploy key
```

### 3. www (业务进程账户)

**用途**: 运行业务进程和容器

**特点**:

- Shell: `/usr/sbin/nologin` (不可登录)
- 权限: 无特殊权限
- UID/GID: 自动分配 (通常 999)
- 主目录: `/var/www`
- 业务目录: `/srv/apps`, `/var/log/apps`

**使用场景**:

1. **原生 systemd 服务**

   ```ini
   [Service]
   User=www
   Group=www
   ExecStart=/usr/local/bin/app
   ```

2. **Docker Compose 容器**

   ```yaml
   services:
     app:
       user: "${WWW_UID}:${WWW_GID}"
       env_file: /opt/infra/.env
   ```

## 重构内容

### 1. 脚本重构

**文件**: `scripts/server/init-users.sh`

**新增功能**:

- 支持三种账户类型创建
- `--non-interactive` 模式 (CI 环境)
- 自动导出 `WWW_UID/WWW_GID` 到环境文件
- 创建业务目录并设置权限
- 分离的权限管理函数

**使用方式**:

```bash
# 交互式创建所有账户
sudo ./scripts/server/init-users.sh

# 非交互式 (CI 环境)
sudo ./scripts/server/init-users.sh --non-interactive

# 查看帮助
sudo ./scripts/server/init-users.sh --help
```

### 2. 文档创建

创建了以下文档:

1. **www 用户使用指南** (`docs/server/www-user-guide.md`)
   - 详细的使用方法
   - systemd 服务配置
   - Docker Compose 配置
   - 目录权限管理
   - 故障排查

2. **示例文件** (`examples/`)
   - systemd 服务配置示例
   - Docker Compose 配置示例
   - 示例说明文档

### 3. 目录结构

新增目录结构:

```text
/srv/apps/          # 应用部署目录 (www:www 750)
/var/log/apps/      # 应用日志目录 (www:www 750)
/var/www/           # www 用户主目录
/opt/infra/.env     # 环境变量文件 (包含 WWW_UID/WWW_GID)

examples/
├── systemd/
│   ├── qs-api.service      # 原生服务示例
│   └── qs-stack.service    # Docker Compose 服务示例
└── docker-compose/
    └── www-user-example.yml # www 用户 Compose 示例
```

## 安全改进

### 1. 权限最小化

```yaml
www 用户:
  - 不可登录 (Shell: /usr/sbin/nologin)
  - 不在 sudo 组
  - 不在 docker 组
  - 只用于运行进程

deploy 用户:
  - 可登录但无 sudo
  - 只有 docker 权限
  - 不能管理系统

yangshujie 用户:
  - 完整权限 (人工操作)
```

### 2. 容器安全加固

```yaml
# Docker Compose 安全配置
user: "${WWW_UID}:${WWW_GID}"
read_only: true
cap_drop: ["ALL"]
security_opt: ["no-new-privileges:true"]
tmpfs: ["/tmp"]
```

### 3. systemd 安全加固

```ini
# systemd 服务安全配置
NoNewPrivileges=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/var/log/apps /srv/apps/data
```

## 使用流程

### 初始化服务器

```bash
# 1. 运行初始化脚本
sudo ./scripts/server/init-users.sh

# 2. 设置 yangshujie 和 deploy 密码 (交互式)
# 3. 记录 deploy 的 SSH 公钥
# 4. 记录 www 的 UID/GID

# 5. 验证账户
id yangshujie  # 应有 sudo, docker 组
id deploy      # 应有 docker 组
id www         # UID/GID 已知, Shell: nologin
```

### 配置 CI/CD

```bash
# 1. 将 deploy 的 SSH 公钥添加到 GitHub Deploy Keys
cat /home/deploy/.ssh/id_ed25519.pub

# 2. 在 GitHub Actions 中配置:
# - SSH_HOST: 服务器 IP
# - SSH_USER: deploy
# - SSH_PRIVATE_KEY: deploy 用户的私钥

# 3. GitHub Actions 工作流示例:
- name: Deploy
  run: |
    ssh deploy@${{ secrets.SSH_HOST }} << 'EOF'
      cd /srv/apps/myapp
      docker compose pull
      docker compose up -d
    EOF
```

### 部署应用

```bash
# 1. 准备目录
sudo mkdir -p /srv/apps/myapp/{data,config}
sudo mkdir -p /var/log/apps/myapp

# 2. 设置权限
sudo chown -R www:www /srv/apps/myapp /var/log/apps/myapp
sudo chmod 750 /srv/apps/myapp /var/log/apps/myapp

# 3. 创建 docker-compose.yml
cat > /srv/apps/myapp/docker-compose.yml << 'EOF'
version: '3.8'
services:
  app:
    image: myapp:latest
    user: "${WWW_UID}:${WWW_GID}"
    env_file: /opt/infra/.env
    volumes:
      - /srv/apps/myapp/data:/data:rw
      - /var/log/apps/myapp:/var/log:rw
    networks:
      - infra-network
    restart: unless-stopped
networks:
  infra-network:
    external: true
EOF

# 4. 启动服务
cd /srv/apps/myapp
docker compose up -d

# 5. 验证
docker exec -it myapp id  # 应显示 www 的 UID/GID
docker top myapp          # 应显示 www 用户
```

## 迁移指南

### 从旧版本迁移

如果你已经使用旧版脚本创建了用户,需要迁移:

```bash
# 1. 备份现有配置
sudo cp -r /home/www /home/www.backup

# 2. 删除旧的 www 用户
sudo userdel -r www

# 3. 创建 deploy 用户
sudo useradd -m -s /bin/bash deploy
sudo usermod -aG docker deploy

# 4. 重新创建 www 系统用户
sudo useradd --system --home /var/www --shell /usr/sbin/nologin --user-group www

# 5. 设置业务目录权限
sudo mkdir -p /srv/apps /var/log/apps /var/www
sudo chown -R www:www /srv/apps /var/log/apps /var/www

# 6. 导出 WWW_UID/WWW_GID
WWW_UID=$(id -u www)
WWW_GID=$(id -g www)
echo "WWW_UID=$WWW_UID" | sudo tee -a /opt/infra/.env
echo "WWW_GID=$WWW_GID" | sudo tee -a /opt/infra/.env

# 7. 更新 docker-compose.yml
# 添加: user: "${WWW_UID}:${WWW_GID}"
# 添加: env_file: /opt/infra/.env

# 8. 重启服务
docker compose down
docker compose up -d
```

## 验证清单

### 账户验证

```bash
# yangshujie
✓ id yangshujie | grep sudo
✓ id yangshujie | grep docker
✓ ls -la /home/yangshujie/workspace

# deploy  
✓ id deploy | grep docker
✓ ls -la /home/deploy/.ssh/id_ed25519
✓ ssh deploy@localhost id

# www
✓ id www
✓ getent passwd www | grep nologin
✓ ls -ld /var/www /srv/apps /var/log/apps
✓ stat -c '%U:%G' /srv/apps
✓ grep WWW_UID /opt/infra/.env
```

### 权限验证

```bash
# www 用户不应该有这些权限
✗ id www | grep sudo     # 应该没有
✗ id www | grep docker   # 应该没有
✗ su - www              # 应该失败

# deploy 用户不应该有 sudo
✗ sudo -u deploy sudo ls  # 应该失败
✓ sudo -u deploy docker ps  # 应该成功
```

### 容器验证

```bash
# 验证容器内用户
docker exec -it <container> id
# 应显示: uid=999(www) gid=999(www)

# 验证文件权限
docker exec -it <container> touch /data/test
ls -la /srv/apps/*/data/test
# 应显示: www www

# 验证只读挂载
docker exec -it <container> touch /etc/config/test
# 应失败: Read-only file system
```

## 故障排查

### 问题 1: www 用户 UID/GID 不匹配

**症状**: 容器内无法写文件

**解决**:

```bash
# 1. 确认 www 用户 UID/GID
id www

# 2. 检查环境文件
grep WWW /opt/infra/.env

# 3. 更新环境文件
WWW_UID=$(id -u www)
WWW_GID=$(id -g www)
sudo sed -i "s/^WWW_UID=.*/WWW_UID=$WWW_UID/" /opt/infra/.env
sudo sed -i "s/^WWW_GID=.*/WWW_GID=$WWW_GID/" /opt/infra/.env

# 4. 重启容器
docker compose down && docker compose up -d
```

### 问题 2: deploy 无法部署

**症状**: deploy 用户无法执行 docker 命令

**解决**:

```bash
# 1. 检查 docker 组
id deploy | grep docker

# 2. 添加到 docker 组
sudo usermod -aG docker deploy

# 3. 重新登录或重启 SSH 会话
```

### 问题 3: 目录权限错误

**症状**: Permission denied

**解决**:

```bash
# 修复业务目录权限
sudo chown -R www:www /srv/apps /var/log/apps /var/www
sudo find /srv/apps -type d -exec chmod 750 {} \;
sudo find /srv/apps -type f -exec chmod 640 {} \;
```

## 相关文档

- [服务器初始化](../docs/server/initialization.md)
- [www 用户使用指南](../docs/server/www-user-guide.md)
- [示例配置](../examples/README.md)

---

**更新时间**: 2025-10-24  
**版本**: v2.0
