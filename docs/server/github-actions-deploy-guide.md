# GitHub Actions 使用 deploy 账户部署指南 (v2.2)

## 📋 前置条件

1. ✅ 服务器已配置 deploy 账户（运行过 `init-users.sh`）
2. ✅ deploy 可 SSH 登录（仅密钥认证）
3. ✅ deploy 有受限 sudo 权限（docker/systemctl等）
4. ✅ 已生成 SSH 密钥对（`ssh-keygen -t ed25519 -f ~/.ssh/deploy_key`）
5. ✅ 私钥已添加到 GitHub Secrets（名称：`DEPLOY_SSH_KEY`）

## 🔑 配置说明

### deploy 账户特性（v2.2）

- ✅ **可 SSH 登录**: 使用 SSH 密钥认证（密码已锁定）
- ✅ **受限 sudo**: 可无密码执行白名单命令
- ❌ **不在 docker 组**: 避免 root 等价权限
- ✅ **审计日志**: 所有 sudo 操作有日志

### 允许的 sudo 命令

deploy 可以无密码执行：

- `sudo docker` / `sudo docker-compose`
- `sudo systemctl start|stop|restart|reload|status|enable|disable`
- `sudo rsync`
- `sudo chown` / `sudo chmod` / `sudo mkdir`

## 🔧 GitHub Actions 配置示例

### 示例 1: 基础部署流程

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Deploy to server
        uses: appleboy/ssh-action@master
        with:
          host: 47.94.204.124
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            # 使用 sudo 执行 Docker 命令
            cd /srv/apps/myapp
            sudo docker compose pull
            sudo docker compose up -d
            
            # 清理旧镜像
            sudo docker image prune -f
```

### 示例 2: 构建并推送镜像 + 部署

```yaml
# .github/workflows/build-and-deploy.yml
name: Build and Deploy

on:
  push:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
  
  deploy:
    needs: build
    runs-on: ubuntu-latest
    
    steps:
      - name: Deploy to server
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          envs: REGISTRY,IMAGE_NAME,GITHUB_SHA
          script: |
            # 更新镜像
            docker compose -f /srv/apps/myapp/docker-compose.yml pull
            
            # 重启服务
            docker compose -f /srv/apps/myapp/docker-compose.yml up -d
            
            # 清理旧镜像
            docker image prune -f
```

### 示例 3: 使用 systemd 服务部署

```yaml
# .github/workflows/deploy-systemd.yml
name: Deploy with systemd

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Deploy and restart service
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            # 拉取代码
            cd /srv/apps/myapp && git pull
            
            # 重启服务
            systemctl restart myapp.service
            
            # 检查状态
            systemctl status myapp.service
```

### 示例 4: 多步骤部署（自定义脚本）

```yaml
# .github/workflows/deploy-custom.yml
name: Deploy with Custom Script

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Deploy using custom script
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            # 执行自定义部署脚本（需提前放在 /srv/deploy/ 目录）
            /srv/deploy/deploy-myapp.sh
```

## 🛡️ 安全限制说明

### deploy 账户的白名单命令

| 命令类型 | 允许的格式 | 示例 |
|---------|----------|------|
| **Docker Compose** | `docker compose ...` | `docker compose up -d` |
| **systemd 服务** | `systemctl start\|stop\|restart\|status\|reload <service>` | `systemctl restart nginx.service` |
| **日志查看** | `tail\|cat\|less\|head\|grep /var/log/...` | `tail -f /var/log/app.log` |
| **Git 拉取** | `git pull` | `cd /srv/apps/myapp && git pull` |
| **自定义脚本** | `/srv/deploy/*` | `/srv/deploy/deploy-app.sh` |

### 禁止的操作

❌ 交互式登录（Shell: `/usr/sbin/nologin`）  
❌ 端口转发（`no-port-forwarding`）  
❌ X11 转发（`no-X11-forwarding`）  
❌ Agent 转发（`no-agent-forwarding`）  
❌ 分配 TTY（`no-pty`）  
❌ 白名单外的任何命令

## 📝 自定义部署脚本

如果需要执行复杂的部署流程，可以创建自定义脚本：

### 1. 在服务器上创建部署脚本

```bash
# SSH 登录到服务器（使用 yangshujie）
ssh yangshujie@server

# 创建部署脚本
sudo tee /srv/deploy/deploy-myapp.sh << 'EOF'
#!/bin/bash
set -euo pipefail

APP_DIR="/srv/apps/myapp"
COMPOSE_FILE="$APP_DIR/docker-compose.yml"

echo "开始部署 myapp..."

# 1. 拉取最新代码
cd "$APP_DIR"
git pull

# 2. 拉取最新镜像
docker compose -f "$COMPOSE_FILE" pull

# 3. 重启服务
docker compose -f "$COMPOSE_FILE" up -d

# 4. 清理旧镜像
docker image prune -f

# 5. 检查服务状态
sleep 3
docker compose -f "$COMPOSE_FILE" ps

echo "部署完成！"
EOF

# 设置权限
sudo chmod +x /srv/deploy/deploy-myapp.sh
sudo chown deploy:deploy /srv/deploy/deploy-myapp.sh
```

### 2. 在 GitHub Actions 中调用

```yaml
- name: Deploy
  uses: appleboy/ssh-action@master
  with:
    host: ${{ secrets.SERVER_HOST }}
    username: deploy
    key: ${{ secrets.DEPLOY_SSH_KEY }}
    script: |
      /srv/deploy/deploy-myapp.sh
```

## 🔍 故障排查

### 查看部署日志

```bash
# SSH 登录到服务器（使用 yangshujie）
ssh yangshujie@server

# 查看 deployctl 执行日志
sudo tail -f /var/log/deployctl.log
```

日志格式：

```log
2025-10-25 10:30:15 [deploy] EXEC: docker compose -f /srv/apps/myapp/docker-compose.yml up -d
2025-10-25 10:30:15 [deploy] ALLOWED: docker compose
```

### 常见错误

#### 错误 1: 命令不在白名单中

```text
错误: 命令不在白名单中: rm
允许的命令:
  - docker compose ...
  - systemctl start|stop|restart|status|reload <service>
  - tail|cat|less|head|grep /var/log/...
  - git pull
  - /srv/deploy/* (自定义脚本)
```

**解决**: 将命令封装到 `/srv/deploy/` 下的脚本中

#### 错误 2: Permission denied

```text
Error: docker: permission denied
```

**原因**: deploy 没有 docker 组权限（这是正常的安全限制）

**解决**: deployctl 会自动使用 `sudo docker compose`，确保命令格式正确

#### 错误 3: sudo 密码提示

```text
[sudo] password for deploy:
```

**原因**: sudoers 配置错误或命令不在 NOPASSWD 列表中

**解决**: 检查 `/etc/sudoers.d/deploy-cicd` 配置

## 🧪 测试部署配置

### 本地测试 SSH 连接

```bash
# 使用生成的私钥测试连接
ssh -i ~/.ssh/deploy_key deploy@47.94.204.124
```

应该看到：

```text
错误: 不允许交互式登录
This account is currently not available.
```

这是正常的！deploy 不能交互登录。

### 测试白名单命令

```bash
# 测试 docker compose 命令
ssh -i ~/.ssh/deploy_key deploy@47.94.204.124 "docker compose --version"

# 测试 systemctl 命令
ssh -i ~/.ssh/deploy_key deploy@47.94.204.124 "systemctl status nginx.service"

# 测试被拒绝的命令
ssh -i ~/.ssh/deploy_key deploy@47.94.204.124 "ls -la"
# 应该看到: 错误: 命令不在白名单中: ls
```

### 测试 GitHub Actions

创建一个测试工作流：

```yaml
# .github/workflows/test-deploy.yml
name: Test Deploy

on:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Test SSH connection
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            echo "测试白名单命令..."
            docker compose --version
            echo "✅ deploy 账户配置正常！"
```

## 📊 配置对比

| 项目 | 旧版本（不安全）❌ | 新版本（安全）✅ |
|------|-----------------|----------------|
| **SSH 密钥位置** | 服务器上生成 | 本地/CI 生成，私钥在 GitHub Secrets |
| **可否交互登录** | 可以 | 不可以（`/usr/sbin/nologin`） |
| **密码** | 有密码 | 无密码（已锁定） |
| **docker 组** | 在 docker 组（= root） | 不在 docker 组 |
| **命令执行** | 无限制 | 白名单限制（deployctl） |
| **审计日志** | 无 | 有（`/var/log/deployctl.log`） |
| **风险** | 高（相当于 root 权限） | 低（最小权限原则） |

## 📚 相关文档

- [用户权限安全加固说明](./user-security-hardening.md)
- deploy 账户白名单命令列表（参见上文"安全限制说明"章节）
- 自定义部署脚本（参见上文"自定义部署脚本"章节）

---

**最后更新**: 2025-10-25  
**适用版本**: infra v2.1+
