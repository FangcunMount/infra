# 用户权限安全加固说明 (v2.1)

## 🔒 安全问题与修复

### 问题概述

之前的 v2.0 版本存在严重的安全/职责边界问题：

1. **yangshujie 和 deploy 都被加入 docker 组** → docker 组 = root 等价权限
2. **deploy 被设置为可登录用户** → CI 账号不应该有交互式 shell
3. **deploy 在服务器上生成 SSH 密钥** → CI 不需要在服务器上出站到 GitHub
4. **install-docker.sh 考虑把 www 加入 docker 组** → 违反"www 仅作为服务进程所有者"的边界

### 核心原则

```text
✅ yangshujie (人用) → sudo 权限，不进 docker 组
✅ deploy (CI 用) → 禁止交互登录，不进 docker 组，受限 SSH
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

#### 问题 2: deploy 被加入 docker 组并可登录

**旧代码**:

```bash
create_user "deploy"
set_user_password "deploy"
add_docker_privilege "deploy"  # ← 错误: CI 不应有 docker 组权限
create_ssh_keys "deploy"      # ← 错误: CI 不需要在服务器上生成 GitHub 密钥
setup_user_bashrc "deploy"
```

**修复后**:

```bash
create_user "deploy"
if [[ "$NON_INTERACTIVE" != true ]]; then
    set_user_password "deploy"
else
    log_warn "非交互模式: 跳过 deploy 密码设置"
fi

# ❌ 安全加固: deploy 不进入 docker 组,不在服务器上生成 GitHub SSH 密钥
# 理由:
# 1. docker 组 = root 等价权限,不应给 CI 账号
# 2. deploy 的 SSH 密钥应由 GitHub Actions 管理,不在服务器上生成
# 3. deploy 应通过受限 SSH 执行白名单命令,而非直接操作 Docker
# add_docker_privilege "deploy"
# create_ssh_keys "deploy"

# 禁止 deploy 交互登录 (CI 账号不应该有交互式 shell)
log_info "禁止 deploy 交互登录..."
usermod -s /usr/sbin/nologin deploy
passwd -l deploy  # 锁定密码
log_success "deploy 已设置为不可交互登录"

setup_user_bashrc "deploy"
```

**影响**:

- deploy 无法通过 SSH 交互式登录
- deploy 无密码（已锁定）
- deploy 仅能通过受限 SSH 执行白名单命令（需配合 authorized_keys 的 command= 限制）

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

#### 禁止行为

```bash
# ❌ 错误: 无法交互登录
ssh deploy@server
# This account is currently not available.

# ❌ 错误: 无法直接使用 docker
su - deploy
docker ps
# deploy: shell: /usr/sbin/nologin
```

#### 正确使用方式

deploy 账号**仅供 GitHub Actions 使用**，通过受限 SSH 执行白名单命令。

**配置受限 SSH** (在服务器上执行):

```bash
# 使用自动化脚本配置受限 SSH
sudo ./scripts/server/setup-deploy-ssh.sh "$(cat ~/.ssh/deploy_key.pub)"

# 脚本会自动创建:
# 1. /usr/local/bin/deployctl          - 白名单命令入口
# 2. /home/deploy/.ssh/authorized_keys - 强制命令 + 禁用能力
# 3. /etc/sudoers.d/deploy-cicd        - 最小 sudo 白名单
# 4. /var/log/deployctl.log            - 命令执行日志
```

**GitHub Actions 配置示例**:

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
            # 所有命令都会通过 deployctl 白名单过滤
            docker compose -f /srv/apps/myapp/docker-compose.yml up -d
            systemctl restart myapp.service
```

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
| **yangshujie** | ✅ | ✅ | ❌ | `sudo docker` | 日常运维 |
| **deploy** | ❌ | ❌ | ❌ | 受限 SSH | CI/CD |
| **www** | ❌ | ❌ | ❌ | 容器内运行 | 业务进程 |

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

### Q2: deploy 不能登录，GitHub Actions 怎么用？

**A**: GitHub Actions 通过 SSH 密钥认证，不需要交互式登录：

```yaml
# GitHub Actions 使用 SSH 密钥连接，不需要 shell
- uses: appleboy/ssh-action@master
  with:
    username: deploy
    key: ${{ secrets.DEPLOY_SSH_KEY }}
    script: |
      # 通过 authorized_keys 的 command= 限制执行的命令
```

配合 `authorized_keys` 的 `command=` 选项，可以限制 deploy 只能执行白名单命令。

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

**版本**: v2.1 (安全加固版)  
**更新时间**: 2025-10-24  
**变更类型**: 安全修复 (Breaking Change)
