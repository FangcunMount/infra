# 安全加固快速参考 (v2.1)

## 📋 TL;DR

```bash
# 三账户安全模型
yangshujie  → sudo 权限，不进 docker 组，使用 'sudo docker'
deploy      → 禁止登录，受限 SSH，白名单命令
www         → 仅运行服务，不可登录
```

## 🚀 快速部署流程

### 1. 创建用户账户

```bash
# 在服务器上（需要 root 权限）
cd /opt/infra
sudo ./scripts/server/init-users.sh
```

**结果**:
- ✅ yangshujie: sudo 权限，不在 docker 组
- ✅ deploy: 不可登录（shell: /usr/sbin/nologin，密码已锁定）
- ✅ www: 系统用户，UID/GID 导出到 `/opt/infra/.env`

### 2. 安装 Docker

```bash
sudo ./scripts/server/install-docker.sh
```

**结果**:
- ✅ Docker Engine 和 Docker Compose 已安装
- ✅ 无用户被自动添加到 docker 组（安全策略）
- ✅ 运维人员使用 `sudo docker` 命令

### 3. 配置 deploy 受限 SSH (可选，用于 CI/CD)

```bash
# 1. 在本地生成 SSH 密钥对
ssh-keygen -t ed25519 -C "github-actions@deploy" -f ~/.ssh/deploy_key

# 2. 在服务器上配置受限 SSH
sudo ./scripts/server/setup-deploy-ssh.sh "$(cat ~/.ssh/deploy_key.pub)"

# 3. 在 GitHub 仓库添加 Secrets
# - SERVER_HOST: 服务器 IP
# - DEPLOY_SSH_KEY: deploy_key 私钥内容
```

**结果**:
- ✅ deploy 仅能执行白名单命令
- ✅ 所有操作记录到 `/var/log/deployctl.log`
- ✅ GitHub Actions 可以自动部署

## 🔑 运维人员日常操作

### yangshujie 账户

```bash
# SSH 登录
ssh yangshujie@server

# Docker 操作（需要 sudo）
sudo docker ps
sudo docker compose up -d
sudo docker logs mysql

# 使用 Makefile（内部自动使用 sudo）
make mysql-start
make nginx-restart
make redis-logs
```

**重要**: 不要尝试将 yangshujie 加入 docker 组！docker 组 = root 等价权限。

## 🤖 CI/CD 部署

### GitHub Actions 工作流

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            docker compose -f /srv/apps/myapp/docker-compose.yml up -d
            systemctl restart myapp.service
```

**允许的命令** (白名单):
- `rsync` - 文件传输
- `docker compose *` - 容器管理
- `systemctl restart/status <service>` - 服务管理
- `git pull` (仅 /srv/apps/*)

## 📊 验证检查清单

### 用户组检查

```bash
# ✅ yangshujie: 仅 sudo 组
groups yangshujie
# 预期: yangshujie : yangshujie sudo

# ✅ deploy: 无特殊组
groups deploy
# 预期: deploy : deploy

# ✅ www: 无特殊组
groups www
# 预期: www : www
```

### 登录检查

```bash
# ✅ yangshujie: 可登录
su - yangshujie  # 成功

# ❌ deploy: 不可登录
su - deploy
# This account is currently not available.

# ❌ www: 不可登录
su - www
# This account is currently not available.
```

### Docker 权限检查

```bash
# yangshujie: 需要 sudo
su - yangshujie
docker ps  # ❌ permission denied
sudo docker ps  # ✅ 成功

# root: 直接可用
docker ps  # ✅ 成功
```

### deploy 受限 SSH 检查

```bash
# 测试白名单命令
ssh -i ~/.ssh/deploy_key deploy@server "docker compose version"
# ✅ 成功

# 测试被拒绝的命令
ssh -i ~/.ssh/deploy_key deploy@server "bash"
# ❌ Error: Command not allowed: bash
```

## 📁 关键文件和路径

### 脚本

| 脚本 | 用途 | 位置 |
|-----|------|-----|
| `init-users.sh` | 创建三账户 | `/opt/infra/scripts/server/` |
| `install-docker.sh` | 安装 Docker | `/opt/infra/scripts/server/` |
| `setup-deploy-ssh.sh` | 配置 deploy 受限 SSH | `/opt/infra/scripts/server/` |

### 配置文件

| 文件 | 用途 | 位置 |
|-----|------|-----|
| `.env` | WWW_UID/GID | `/opt/infra/.env` |
| `deployctl` | deploy 白名单入口 | `/usr/local/bin/deployctl` |
| `deploy-cicd` | deploy sudoers 白名单 | `/etc/sudoers.d/deploy-cicd` |
| `authorized_keys` | deploy SSH 公钥 | `/home/deploy/.ssh/authorized_keys` |

### 日志

| 日志 | 内容 | 位置 |
|-----|------|-----|
| `deployctl.log` | deploy 命令执行记录 | `/var/log/deployctl.log` |
| `auth.log` | SSH 认证日志 | `/var/log/auth.log` |
| `syslog` | deployctl 系统日志 | `journalctl -t deployctl` |

## 🚨 常见错误和修复

### 错误 1: docker: permission denied

```bash
# 错误
yangshujie$ docker ps
# permission denied while trying to connect to the Docker daemon socket

# ✅ 解决: 使用 sudo
yangshujie$ sudo docker ps
```

### 错误 2: GitHub Actions 连接失败

```bash
# 错误: Permission denied (publickey)

# ✅ 检查
1. GitHub Secrets 中的 DEPLOY_SSH_KEY 是否完整
2. 服务器上的 /home/deploy/.ssh/authorized_keys 是否存在
3. authorized_keys 权限是否为 600
```

### 错误 3: deploy 命令被拒绝

```bash
# 错误: Command not allowed

# ✅ 查看日志
sudo tail -20 /var/log/deployctl.log | grep DENIED

# ✅ 添加到白名单
sudo vi /usr/local/bin/deployctl
# 在 case 语句中添加新的白名单规则
```

### 错误 4: sudo: a tty is required

```bash
# 错误: sudo: sorry, you must have a tty to run sudo

# ✅ 检查 sudoers 配置
sudo cat /etc/sudoers.d/deploy-cicd | grep requiretty
# 应该有: Defaults:deploy !requiretty
```

## 📚 详细文档链接

- 🔐 [用户权限安全加固](./user-security-hardening.md) - 完整的安全模型说明
- 🤖 [GitHub Actions 部署指南](./github-actions-deploy.md) - CI/CD 集成详解
- 👥 [www 用户使用指南](./www-user-guide.md) - 业务容器配置
- 📋 [容器用户策略](./container-user-strategy.md) - 基础设施 vs 业务应用

## 🎓 安全原则记忆

```text
❌ 不要: 将运维人员加入 docker 组（docker 组 = root 等价）
✅ 使用: sudo docker 操作容器（有审计、需密码）

❌ 不要: 让 CI 账号可以交互登录（shell: /bin/bash）
✅ 使用: 受限 SSH + 白名单命令（shell: /usr/sbin/nologin）

❌ 不要: 在服务器上生成 CI 的 GitHub SSH 密钥
✅ 使用: 密钥在 GitHub Secrets 中管理，服务器只有公钥

❌ 不要: 让 www 账号有任何特权（sudo/docker 组）
✅ 使用: www 仅作为容器内运行用户（user: "${WWW_UID}:${WWW_GID}"）
```

---

**版本**: v2.1  
**更新**: 2025-10-24  
**状态**: 生产就绪 ✅
