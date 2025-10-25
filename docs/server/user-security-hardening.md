# 用户权限安全加固说明 (v2.1)

## 🔒 安全问题与修复 (v2.2)

### 版本更新说明

**v2.2 (2025-10-25)**: 调整 deploy 账户策略

- **变更**: deploy 从"禁止登录+白名单命令"改为"可登录+受限 sudo"
- **原因**: CI/CD 灵活性需求，白名单维护成本过高
- **安全措施**: 仍不进入 docker 组，通过 sudo 白名单控制权限

**v2.1 (2025-10-24)**: 安全加固版本

- yangshujie 不进入 docker 组
- deploy 禁止交互登录
- www 仅作为服务进程所有者

### 问题概述

之前的 v2.0 版本存在严重的安全/职责边界问题：

1. **yangshujie 和 deploy 都被加入 docker 组** → docker 组 = root 等价权限
2. **deploy 被设置为可登录用户** → CI 账号不应该有交互式 shell
3. **deploy 在服务器上生成 SSH 密钥** → CI 不需要在服务器上出站到 GitHub
4. **install-docker.sh 考虑把 www 加入 docker 组** → 违反"www 仅作为服务进程所有者"的边界

### 核心原则 (v2.2)

```text
✅ yangshujie (人用) → sudo 权限，不进 docker 组，使用 sudo docker
✅ deploy (CI 用) → 可 SSH 登录（仅密钥），受限 sudo，不进 docker 组
✅ www (服务用) → 仅运行服务，不进 docker 组
```

## 📋 详细修复

### 1. init-users.sh (v2.0 → v2.1)

#### 问题 1: yangshujie 被加入 docker 组

**旧代码**:

```bash
add_sudo_privilege "yangshujie"
add_docker_privilege "yangshujie"  # ← 错误: docker 组 = root 等价权限
setup_user_bashrc "yangshujie"
```

**修复后**:

```bash
add_sudo_privilege "yangshujie"
# ❌ 安全加固: 不将 yangshujie 加入 docker 组 (docker 组 = root 等价权限)
# yangshujie 应通过 sudo docker 命令操作容器,避免获得 root 等价权限
# add_docker_privilege "yangshujie"
setup_user_bashrc "yangshujie"
```

**影响**: yangshujie 需要使用 `sudo docker` 而非直接 `docker` 命令

**使用方式**:

```bash
# ✅ 正确
sudo docker ps
sudo docker compose up -d

# ❌ 错误 (无权限)
docker ps
```

#### 问题 2: deploy 账户权限设计

**v2.0 旧代码（不安全）**:

```bash
create_user "deploy"
set_user_password "deploy"
add_docker_privilege "deploy"  # ← 错误: CI 不应有 docker 组权限
create_ssh_keys "deploy"      # ← 错误: CI 不需要在服务器上生成 GitHub 密钥
setup_user_bashrc "deploy"
```

**v2.1 修复（过于严格）**:

```bash
# 禁止 deploy 交互登录 (CI 账号不应该有交互式 shell)
usermod -s /usr/sbin/nologin deploy
passwd -l deploy
# 仅通过受限 SSH + authorized_keys command= 执行白名单命令
```

**问题**: CI/CD 灵活性不足，白名单维护成本高

**v2.2 最终方案（平衡安全与灵活性）**:

```bash
create_user "deploy"
if [[ "$NON_INTERACTIVE" != true ]]; then
    set_user_password "deploy"
else
    log_warn "非交互模式: 跳过 deploy 密码设置"
fi

# ✅ 方案 A: 允许 deploy 登录 + 受限 sudo (推荐)
# 理由:
# 1. GitHub Actions 需要灵活执行部署命令
# 2. 通过受限 sudo 控制权限,而非完全禁止登录
# 3. 不将 deploy 加入 docker 组,避免 root 等价权限
# 4. deploy 只能通过 SSH 密钥登录,不设置密码

log_info "配置 deploy 为可登录账户（仅 SSH 密钥认证）..."
# deploy 使用 bash shell（允许登录）
usermod -s /bin/bash deploy
# 锁定密码（只能通过 SSH 密钥登录，不能用密码）
passwd -l deploy
log_success "deploy 已配置为可 SSH 登录（仅密钥认证）"

# 配置 deploy 的受限 sudo 权限
setup_deploy_sudo_privileges

setup_user_bashrc "deploy"
```

**优势**:

- ✅ 可 SSH 登录（仅密钥认证，无密码）
- ✅ 受限 sudo 权限（docker/systemctl/rsync等）
- ✅ 不进入 docker 组（避免 root 等价权限）
- ✅ 所有操作有 sudo 审计日志
- ✅ CI/CD 配置简单，无需维护复杂白名单

#### 问题 3: 说明文档不准确

**旧文档**:

```bash
echo "  账户类型 1: yangshujie (运维账户)"
echo "    - sudo 权限 (系统管理)"
echo "    - docker 权限 (容器管理)"  # ← 不应该有

echo "  账户类型 2: deploy (CI/CD 账户)"
echo "    - 可登录 SSH"  # ← CI 不应该交互登录
echo "    - docker 权限 (部署容器)"  # ← 不应该有
echo "    - 生成 SSH 密钥对 (用于 GitHub Deploy Key)"  # ← 不需要
```

**修复后**:

```bash
echo "  账户类型 1: yangshujie (运维账户)"
echo "    - 可登录 SSH"
echo "    - sudo 权限 (系统管理)"
echo "    - ❌ 不进入 docker 组 (避免 root 等价权限)"
echo "    - 使用 'sudo docker' 操作容器"

echo "  账户类型 2: deploy (CI/CD 账户) - 安全加固"
echo "    - ❌ 禁止交互登录 (Shell: /usr/sbin/nologin)"
echo "    - ❌ 密码已锁定 (passwd -l)"
echo "    - ❌ 不进入 docker 组 (CI 不应有 root 等价权限)"
echo "    - ❌ 不生成 GitHub SSH 密钥 (由 GitHub Actions 管理)"
echo "    - 仅通过受限 SSH 执行白名单命令"
```

### 2. install-docker.sh

#### 问题: 自动将用户添加到 docker 组

**旧代码**:

```bash
# 目标用户列表
local users_to_add=()

# 添加 www 用户（如果存在）
if id -u www >/dev/null 2>&1; then
    users_to_add+=("www")  # ← 错误: www 不应该在 docker 组
fi

# 添加当前登录用户（非 root）
if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
    users_to_add+=("$SUDO_USER")  # ← 错误: 不应自动给 docker 组
fi
```

**修复后**:

```bash
# 目标用户列表
local users_to_add=()

# ❌ 安全加固: 不将 www 添加到 docker 组
# www 是业务进程账户,不应该有 docker 组权限 (docker 组 = root 等价权限)
# 业务容器通过 user: "${WWW_UID}:${WWW_GID}" 以 www 用户运行,无需 docker 组
# if id -u www >/dev/null 2>&1; then
#     users_to_add+=("www")
# fi

# ❌ 安全加固: 不自动将当前用户添加到 docker 组
# 运维人员应通过 sudo docker 操作容器,避免获得 root 等价权限
# if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
#     users_to_add+=("$SUDO_USER")
# fi

log_warn "安全策略: 不自动将用户添加到 docker 组"
log_info "运维人员请使用 'sudo docker' 命令操作容器"
log_info "理由: docker 组成员拥有 root 等价权限,违反最小权限原则"
```

**测试部分也同步修改**:

```bash
# 测试用户列表（仅测试 root，其他用户不在 docker 组）
local test_users=("root")

# ❌ 不测试 www 和其他用户的 docker 权限
# 原因: 按照安全策略,这些用户不应该在 docker 组中
# www: 仅作为容器内运行用户,不需要 docker 命令权限
# 运维人员: 应使用 sudo docker 而非直接 docker 命令

log_info "仅测试 root 用户的 Docker 权限"
log_info "其他用户应使用 'sudo docker' 命令"
```

## 🎯 使用指南

### yangshujie (运维人员)

#### Docker 操作

```bash
# ✅ 正确: 使用 sudo
sudo docker ps
sudo docker compose up -d
sudo docker exec -it mysql bash

# ❌ 错误: 直接使用 (会提示权限不足)
docker ps
# permission denied while trying to connect to the Docker daemon socket
```

#### 日常工作流

```bash
# SSH 登录
ssh yangshujie@server

# 进入工作目录
cd ~/workspace/infra

# 使用 Makefile (内部自动使用 sudo)
make mysql-start
make nginx-restart

# 手动操作容器
sudo docker ps -a
sudo docker logs mysql
```

#### Makefile 命令 (已集成 sudo)

所有 Makefile 命令内部已经使用 `sudo docker`，直接使用即可：

```bash
make mysql-start       # 内部: sudo docker compose up -d
make redis-stop        # 内部: sudo docker compose down
make nginx-logs        # 内部: sudo docker compose logs -f
```

### deploy (CI/CD 账号)

#### SSH 登录

```bash
# ✅ 正确: 使用 SSH 密钥登录
ssh -i ~/.ssh/deploy_key deploy@server
# 成功登录

# ❌ 错误: 使用密码登录
ssh deploy@server
# Permission denied (publickey)  # 密码已锁定，只能用密钥
```

#### deploy 的 Docker 操作

```bash
# ✅ 正确: 使用 sudo docker
sudo docker ps
sudo docker compose up -d
sudo docker exec -it myapp bash

# ❌ 错误: 直接使用 docker（没有 docker 组权限）
docker ps
# permission denied while trying to connect to the Docker daemon socket
```

#### 配置步骤

##### 步骤 1: 生成 SSH 密钥对（本地执行）

```bash
ssh-keygen -t ed25519 -C "deploy@github-actions" -f ~/.ssh/deploy_key
# 将公钥添加到服务器: ~/.ssh/deploy_key.pub
# 将私钥添加到 GitHub Secrets: DEPLOY_SSH_KEY
```

##### 步骤 2: 在服务器上添加公钥

```bash
# SSH 登录服务器（使用 yangshujie）
ssh yangshujie@server

# 添加 deploy 的 SSH 公钥
sudo mkdir -p /home/deploy/.ssh
sudo tee /home/deploy/.ssh/authorized_keys << 'EOF'
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... deploy@github-actions
EOF
sudo chown -R deploy:deploy /home/deploy/.ssh
sudo chmod 700 /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

##### 步骤 3: GitHub Actions 工作流

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
      - name: Deploy to server
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            # 使用 sudo 执行部署命令
            cd /srv/apps/myapp
            sudo docker compose pull
            sudo docker compose up -d
            
            # 或重启 systemd 服务
            sudo systemctl restart myapp.service
```

#### 允许的 sudo 命令

deploy 账户可以无密码执行以下命令：

- ✅ `sudo docker` / `sudo docker-compose`
- ✅ `sudo systemctl start|stop|restart|reload|status|enable|disable`
- ✅ `sudo rsync`
- ✅ `sudo chown` / `sudo chmod` / `sudo mkdir`

所有其他命令需要密码（但 deploy 密码已锁定，实际无法执行）。

**详细使用说明**: 参见 [GitHub Actions 部署指南](./github-actions-deploy.md)

### www (业务进程账号)

#### 用途

仅作为容器内运行用户，不需要任何 docker 命令权限。

#### Docker Compose 配置

```yaml
services:
  myapp:
    image: mycompany/myapp:latest
    user: "${WWW_UID}:${WWW_GID}"  # ← 以 www 用户运行
    env_file: /opt/infra/.env
    volumes:
      - /srv/apps/myapp:/app:rw
```

#### 验证

```bash
# 检查 www 用户不在 docker 组
groups www
# www : www

# 检查容器内运行用户
sudo docker exec myapp id
# uid=1002(www) gid=1002(www) groups=1002(www)
```

## 🔍 安全验证

### 验证用户组

```bash
# yangshujie: 只在 sudo 组，不在 docker 组
groups yangshujie
# yangshujie : yangshujie sudo

# deploy: 无任何特殊组
groups deploy
# deploy : deploy

# www: 无任何特殊组
groups www
# www : www
```

### 验证登录状态

```bash
# yangshujie: 可登录
su - yangshujie
# 成功

# deploy: 不可登录
su - deploy
# This account is currently not available.

# www: 不可登录
su - www
# This account is currently not available.
```

### 验证 docker 权限

```bash
# yangshujie: 需要 sudo
su - yangshujie
docker ps
# permission denied

sudo docker ps
# 成功

# deploy: 无 docker 权限
# (无法登录，无法测试)

# www: 无 docker 权限
# (无法登录，无法测试)
```

## 📊 权限对比表

| 账户 | 可登录 | sudo | docker 组 | Docker 操作方式 | 用途 |
|------|--------|------|-----------|----------------|------|
| **root** | ✅ | N/A | ✅ | `docker` | 紧急维护 |
| **yangshujie** | ✅ | ✅ 全部 | ❌ | `sudo docker` | 日常运维 |
| **deploy** | ✅ 仅密钥 | ✅ 白名单 | ❌ | `sudo docker` | CI/CD |
| **www** | ❌ | ❌ | ❌ | 容器内运行 | 业务进程 |

**说明**:

- **deploy 可登录**: ✅ 仅 SSH 密钥认证，密码已锁定
- **deploy sudo**: ✅ 受限白名单（docker/systemctl/rsync/chown/chmod/mkdir）
- **所有账户**: ❌ 不进入 docker 组，避免 root 等价权限

## 🚨 常见问题

### Q1: 为什么不让 yangshujie 进 docker 组？

**A**: docker 组成员可以直接操作 Docker socket (`/var/run/docker.sock`)，这等价于 root 权限：

```bash
# 任何 docker 组成员都可以这样获得 root shell
docker run -v /:/host -it alpine chroot /host bash
# 现在你就是 root，可以做任何事
```

通过 `sudo docker` 操作容器：

- 有审计日志 (`/var/log/auth.log`)
- 需要输入密码
- 可以通过 sudoers 细粒度控制权限

### Q2: deploy 可以登录，会不会不安全？

**A**: 不会，因为有多重安全措施：

1. **只能 SSH 密钥认证**: 密码已锁定，无法用密码登录
2. **私钥在 GitHub Secrets**: 不会泄露
3. **受限 sudo 白名单**: 只能执行必要的命令
4. **不在 docker 组**: 没有 root 等价权限
5. **审计日志**: 所有 sudo 操作都有日志 (`/var/log/auth.log`)

**对比 v2.1（禁止登录）的优势**:

- ✅ CI/CD 配置简单，不需要维护复杂的白名单脚本
- ✅ 仍然保持安全性（受限 sudo）
- ✅ 灵活性更好，可以自由组合命令

```yaml
# v2.2 简化的 GitHub Actions
- uses: appleboy/ssh-action@master
  with:
    username: deploy
    key: ${{ secrets.DEPLOY_SSH_KEY }}
    script: |
      cd /srv/apps/myapp
      sudo docker compose pull
      sudo docker compose up -d
```

### Q3: 现有服务器怎么迁移？

**A**:

1. **备份现有配置**:

   ```bash
   # 备份 yangshujie 的组
   id yangshujie > /tmp/yangshujie.backup
   
   # 备份 deploy 的配置
   id deploy > /tmp/deploy.backup
   getent passwd deploy > /tmp/deploy.passwd.backup
   ```

2. **移除 docker 组**:

   ```bash
   # 移除 yangshujie 的 docker 组
   sudo gpasswd -d yangshujie docker
   
   # 移除 deploy 的 docker 组
   sudo gpasswd -d deploy docker
   ```

3. **禁用 deploy 登录**:

   ```bash
   # 禁用 deploy 交互登录
   sudo usermod -s /usr/sbin/nologin deploy
   sudo passwd -l deploy
   ```

4. **更新 sudo 配置** (可选，细粒度控制):

   ```bash
   # /etc/sudoers.d/yangshujie
   yangshujie ALL=(ALL) /usr/bin/docker, /usr/bin/docker-compose
   ```

5. **测试验证**:

   ```bash
   # 测试 yangshujie 使用 sudo docker
   su - yangshujie
   sudo docker ps
   ```

### Q4: Makefile 命令还能用吗？

**A**: 能用！所有 Makefile 命令内部已经使用 `sudo docker compose`：

```makefile
# Makefile
mysql-start:
 sudo docker compose -f components/mysql/docker-compose.yml up -d
```

运维人员直接使用 `make` 命令即可：

```bash
make mysql-start
# 会提示输入 sudo 密码，然后正常执行
```

## 📝 迁移检查清单

- [ ] 备份所有用户的组和密码配置
- [ ] 移除 yangshujie 的 docker 组: `gpasswd -d yangshujie docker`
- [ ] 移除 deploy 的 docker 组: `gpasswd -d deploy docker`
- [ ] 禁用 deploy 登录: `usermod -s /usr/sbin/nologin deploy && passwd -l deploy`
- [ ] 验证 yangshujie 使用 `sudo docker` 正常
- [ ] 验证 Makefile 命令正常 (会提示输入 sudo 密码)
- [ ] 配置 deploy 的受限 SSH (authorized_keys command=)
- [ ] 测试 GitHub Actions 部署流程
- [ ] 删除 deploy 在服务器上的 SSH 密钥 (如果有)
- [ ] 更新团队文档和培训材料

## 🎓 安全最佳实践

1. **最小权限原则**: 用户只获得完成工作所需的最小权限
2. **职责分离**: 人用账号、CI 账号、服务账号严格分离
3. **审计追踪**: 使用 sudo 而非直接权限，保留操作日志
4. **受限访问**: CI 账号通过白名单命令而非完全 shell 访问
5. **定期审查**: 定期检查用户组和权限配置

## 📚 相关文档

- [用户系统重构总结](./user-system-refactoring.md)
- [www 用户使用指南](./www-user-guide.md)
- [容器用户策略说明](./container-user-strategy.md)

---

**版本**: v2.2 (平衡安全与灵活性)  
**更新时间**: 2025-10-25  
**变更类型**: deploy 账户策略调整 (允许 SSH 登录 + 受限 sudo)
