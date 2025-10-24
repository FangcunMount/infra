# GitHub Actions 与 deploy 账户集成指南

## 概述

本文档说明如何在 GitHub Actions CI/CD 流程中安全地使用 deploy 账户进行自动化部署。

## 🔒 安全模型

```text
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions                            │
│  • 持有 deploy 私钥 (Secrets)                                │
│  • 发起 SSH 连接                                             │
└──────────────┬──────────────────────────────────────────────┘
               │ SSH 连接 (仅公钥认证)
               ▼
┌─────────────────────────────────────────────────────────────┐
│              服务器 - deploy 账户                            │
│                                                              │
│  1. authorized_keys (公钥)                                  │
│     └─ command="/usr/local/bin/deployctl"                  │
│        强制所有命令通过白名单过滤                             │
│                                                              │
│  2. /usr/local/bin/deployctl (白名单入口)                   │
│     ├─ rsync              ✅ 允许文件传输                    │
│     ├─ docker compose     ✅ 允许容器管理 (通过 sudo)        │
│     ├─ systemctl          ✅ 允许服务管理 (通过 sudo)        │
│     ├─ git pull           ✅ 允许代码更新 (/srv/apps/* 仅)   │
│     └─ 其他命令           ❌ 全部拒绝                        │
│                                                              │
│  3. /etc/sudoers.d/deploy-cicd (sudo 白名单)               │
│     └─ NOPASSWD: docker, docker compose, rsync, systemctl  │
│                                                              │
│  限制:                                                       │
│  • 禁止交互式登录 (no-pty)                                   │
│  • 禁止 SSH Agent 转发 (no-agent-forwarding)                │
│  • 禁止 X11 转发 (no-X11-forwarding)                        │
│  • Shell: /usr/sbin/nologin (无交互式 shell)                │
└─────────────────────────────────────────────────────────────┘
```

## 📋 前置准备

### 1. 生成 SSH 密钥对（在本地）

```bash
# 生成专用于 CI/CD 的 SSH 密钥对
ssh-keygen -t ed25519 -C "github-actions@deploy" -f ~/.ssh/deploy_key

# 输出:
# ~/.ssh/deploy_key      # 私钥（保存到 GitHub Secrets）
# ~/.ssh/deploy_key.pub  # 公钥（上传到服务器）
```

**安全提醒**:

- ✅ 私钥仅保存在 GitHub Secrets 中
- ✅ 公钥保存在服务器 `/home/deploy/.ssh/authorized_keys`
- ❌ 不要在服务器上生成密钥对
- ❌ 不要将私钥提交到代码仓库

### 2. 在服务器上配置 deploy 受限 SSH

```bash
# 在服务器上执行（需要 root 权限）
sudo ./scripts/server/setup-deploy-ssh.sh "$(cat ~/.ssh/deploy_key.pub)"

# 脚本会自动:
# 1. 创建 /usr/local/bin/deployctl（白名单入口）
# 2. 配置 /home/deploy/.ssh/authorized_keys（强制命令）
# 3. 配置 /etc/sudoers.d/deploy-cicd（sudo 白名单）
```

### 3. 在 GitHub 仓库中配置 Secrets

进入仓库 Settings → Secrets and variables → Actions → New repository secret

添加以下 Secrets:

| Secret 名称 | 值 | 说明 |
|------------|-----|------|
| `SERVER_HOST` | `112.126.82.123` | 服务器 IP 地址 |
| `DEPLOY_SSH_KEY` | `<deploy_key 私钥内容>` | deploy 账户的 SSH 私钥 |

**获取私钥内容**:

```bash
cat ~/.ssh/deploy_key
# 复制完整输出（包括 BEGIN 和 END 行）
```

## 🚀 GitHub Actions 工作流示例

### 示例 1: 基础部署流程

`.github/workflows/deploy.yml`:

```yaml
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
          host: ${{ secrets.SERVER_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            # 所有命令都会通过 deployctl 白名单过滤
            docker compose -f /srv/apps/myapp/docker-compose.yml pull
            docker compose -f /srv/apps/myapp/docker-compose.yml up -d
            systemctl restart myapp.service
```

### 示例 2: 使用 rsync 部署静态文件

```yaml
name: Deploy Static Files

on:
  push:
    paths:
      - 'dist/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Build
        run: |
          npm install
          npm run build
      
      - name: Deploy via rsync
        uses: burnett01/rsync-deployments@6.0.0
        with:
          switches: -avzr --delete
          path: dist/
          remote_path: /srv/apps/myapp/static/
          remote_host: ${{ secrets.SERVER_HOST }}
          remote_user: deploy
          remote_key: ${{ secrets.DEPLOY_SSH_KEY }}
```

### 示例 3: 多步骤部署（代码更新 + 容器重启）

```yaml
name: Full Deployment

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Deploy application
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            # 1. 更新代码
            cd /srv/apps/myapp && git pull
            
            # 2. 重启容器
            docker compose -f /srv/apps/myapp/docker-compose.yml up -d --build
            
            # 3. 健康检查
            sleep 5
            docker compose -f /srv/apps/myapp/docker-compose.yml ps
            
            # 4. 查看服务状态
            systemctl status myapp.service
```

### 示例 4: 条件部署（仅特定文件变更时）

```yaml
name: Conditional Deploy

on:
  push:
    branches: [main]

jobs:
  check-changes:
    runs-on: ubuntu-latest
    outputs:
      backend: ${{ steps.changes.outputs.backend }}
      frontend: ${{ steps.changes.outputs.frontend }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v2
        id: changes
        with:
          filters: |
            backend:
              - 'backend/**'
            frontend:
              - 'frontend/**'
  
  deploy-backend:
    needs: check-changes
    if: needs.check-changes.outputs.backend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            docker compose -f /srv/apps/backend/docker-compose.yml up -d
  
  deploy-frontend:
    needs: check-changes
    if: needs.check-changes.outputs.frontend == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            docker compose -f /srv/apps/frontend/docker-compose.yml up -d
```

## 🛡️ 安全最佳实践

### 1. 最小权限原则

deploy 账户仅能执行白名单命令:

```bash
# ✅ 允许的操作
docker compose up -d
systemctl restart myapp.service
rsync files
cd /srv/apps/myapp && git pull

# ❌ 禁止的操作
bash                           # 无交互式 shell
docker exec -it app bash       # no-pty 限制
docker system prune            # sudoers 明确拒绝
rm -rf /                       # 不在白名单
```

### 2. 审计日志

所有 deploy 操作都会记录到 `/var/log/deployctl.log`:

```bash
# 查看部署日志
sudo tail -f /var/log/deployctl.log

# 示例输出:
[2025-10-24 10:30:15] ALLOWED: docker compose - docker compose -f /srv/apps/myapp/docker-compose.yml up -d
[2025-10-24 10:30:20] ALLOWED: systemctl restart myapp.service
[2025-10-24 10:31:05] DENIED: Command not in whitelist: bash
```

同时也记录到系统日志:

```bash
# 查看系统日志
sudo journalctl -t deployctl -f
```

### 3. 定期轮换密钥

```bash
# 生成新的 SSH 密钥对
ssh-keygen -t ed25519 -C "github-actions@deploy-$(date +%Y%m)" -f ~/.ssh/deploy_key_new

# 更新服务器
sudo ./scripts/server/setup-deploy-ssh.sh "$(cat ~/.ssh/deploy_key_new.pub)"

# 更新 GitHub Secrets
# Settings → Secrets → DEPLOY_SSH_KEY → Update

# 测试新密钥
ssh -i ~/.ssh/deploy_key_new deploy@server "docker compose version"

# 删除旧密钥
rm ~/.ssh/deploy_key ~/.ssh/deploy_key.pub
```

### 4. 监控异常访问

```bash
# 创建告警脚本
cat > /usr/local/bin/monitor-deploy.sh <<'EOF'
#!/bin/bash
# 检查最近 5 分钟的 DENIED 记录
denied_count=$(grep -c "DENIED" /var/log/deployctl.log | tail -10)
if [[ $denied_count -gt 5 ]]; then
    echo "WARNING: $denied_count denied access attempts in last 5 minutes" | \
        mail -s "Deploy Security Alert" admin@example.com
fi
EOF

chmod +x /usr/local/bin/monitor-deploy.sh

# 添加到 cron（每 5 分钟检查一次）
echo "*/5 * * * * /usr/local/bin/monitor-deploy.sh" | sudo crontab -
```

## 🧪 测试和调试

### 测试 SSH 连接

```bash
# 测试基本连接
ssh -i ~/.ssh/deploy_key deploy@server "docker compose version"

# 预期输出:
# Docker Compose version v2.x.x

# 测试被拒绝的命令
ssh -i ~/.ssh/deploy_key deploy@server "bash"

# 预期输出:
# Error: Command not allowed: bash
```

### 本地测试 deployctl

```bash
# 在服务器上测试（需要 root）
sudo su - deploy -s /bin/bash -c 'SSH_ORIGINAL_COMMAND="docker compose version" /usr/local/bin/deployctl'
```

### 查看 deploy 的 sudo 权限

```bash
# 查看 deploy 可以执行的 sudo 命令
sudo -l -U deploy

# 预期输出:
# User deploy may run the following commands on server:
#     (root) NOPASSWD: /usr/bin/docker, /usr/bin/docker compose *, /usr/bin/rsync, ...
```

### 调试 GitHub Actions

在 workflow 中添加调试步骤:

```yaml
- name: Debug SSH connection
  uses: appleboy/ssh-action@master
  with:
    host: ${{ secrets.SERVER_HOST }}
    username: deploy
    key: ${{ secrets.DEPLOY_SSH_KEY }}
    debug: true  # 启用调试输出
    script: |
      echo "Testing connection..."
      docker compose version
```

## 🚨 故障排查

### 问题 1: Permission denied (publickey)

**症状**: GitHub Actions 无法连接到服务器

**排查**:

```bash
# 1. 检查服务器上的公钥
sudo cat /home/deploy/.ssh/authorized_keys

# 2. 检查公钥指纹
ssh-keygen -lf /home/deploy/.ssh/authorized_keys

# 3. 在本地测试连接
ssh -i ~/.ssh/deploy_key -v deploy@server
```

**解决**:

- 确认 GitHub Secrets 中的私钥完整（包括 BEGIN/END 行）
- 确认服务器上的公钥正确
- 检查 `/home/deploy/.ssh/authorized_keys` 权限为 600

### 问题 2: Command not allowed

**症状**: 命令被 deployctl 拒绝

**排查**:

```bash
# 查看被拒绝的命令
sudo tail -20 /var/log/deployctl.log | grep DENIED
```

**解决**:

- 检查命令是否在 deployctl 白名单中
- 修改 `/usr/local/bin/deployctl` 添加新的白名单规则
- 重新测试

### 问题 3: sudo: sorry, you must have a tty

**症状**: sudo 命令要求 tty

**排查**:

```bash
# 检查 sudoers 配置
sudo cat /etc/sudoers.d/deploy-cicd | grep requiretty
```

**解决**:
确保有 `Defaults:deploy !requiretty` 配置

### 问题 4: Docker socket permission denied

**症状**: deploy 无法连接 Docker socket

**排查**:

```bash
# 检查 docker 组
groups deploy

# 检查 socket 权限
ls -la /var/run/docker.sock
```

**解决**:
deploy 不应该在 docker 组中，应该通过 `sudo docker` 执行（deployctl 会自动添加 sudo）

## 📊 监控和维护

### 日志轮转

创建日志轮转配置:

```bash
sudo cat > /etc/logrotate.d/deployctl <<'EOF'
/var/log/deployctl.log {
    weekly
    rotate 12
    compress
    delaycompress
    missingok
    notifempty
    create 0640 root adm
}
EOF
```

### 统计信息

```bash
# 部署次数统计
grep "ALLOWED" /var/log/deployctl.log | wc -l

# 最近 10 次部署
grep "ALLOWED" /var/log/deployctl.log | tail -10

# 拒绝次数统计
grep "DENIED" /var/log/deployctl.log | wc -l
```

## 📚 相关文档

- [用户权限安全加固](./user-security-hardening.md) - deploy 账户的安全设计
- [用户系统重构总结](./user-system-refactoring.md) - 三账户系统说明
- [GitHub Actions 官方文档](https://docs.github.com/en/actions)

---

**更新时间**: 2025-10-24  
**版本**: v1.0
