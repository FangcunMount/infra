# SonarQube 组件

本组件部署在 Mac mini Docker Desktop，由 `make macmini-sonarqube-up` 启动，包含 SonarQube Community Edition 与 PostgreSQL。

当前镜像均原生支持 Apple Silicon：

- `sonarqube:26.1.0.118079-community`: `linux/arm64`
- `postgres:16-alpine`: `linux/arm64`

## 默认域名

- `sonar.fangcunmount.cn`

## 关键环境变量

- `SONAR_DB_USER`
- `SONAR_DB_PASSWORD`
- `SONAR_DB_NAME`
- `SONAR_DOMAIN`
- `SONAR_ROOT_URL`
- `SONAR_DB_MEMORY_LIMIT`
- `SONAR_DB_CPUS`
- `SONAR_MEMORY_LIMIT`
- `SONAR_CPUS`

JVM 堆参数固定在 `components/sonarqube/docker-compose.yml`：Web/CE 为 `-Xmx384m -Xms256m`，Search 为 `-Xmx512m -Xms512m`。

## Mac mini 前置条件

1. Docker Desktop 至少分配 4 GB 内存，建议 6 GB。
2. 复制并填写环境变量：

```bash
cp compose/env/prod/mac-mini.env.example compose/env/prod/mac-mini.env
```

`SONAR_DB_PASSWORD` 必须与迁移前 serverD 的实际值一致。

启动时 `sonarqube-init` 会在 Docker Desktop Linux VM 内设置 Elasticsearch 所需的 `vm.max_map_count` 和 `fs.file-max`，无需修改 macOS 的 `sysctl`。

## 从 serverD 迁移

在 Mac mini 的 infra 仓库执行：

```bash
SOURCE_SSH=deploy@82.157.204.239 make sonarqube-migrate-to-macmini
```

若 `deploy` 用户不能免密执行 Docker，可使用有 Docker 权限的 SSH 用户，或给迁移所需 Docker 命令配置临时 `NOPASSWD`。

迁移流程：

1. 停止 serverD 的 SonarQube 应用，保留 PostgreSQL 运行。
2. 使用 `pg_dump` 生成一致性备份。
3. 在 Mac mini 启动 ARM64 PostgreSQL 并恢复。
4. 启动 SonarQube，等待 API 状态 `UP`。
5. 在 serverA 部署新的 Nginx 配置，将上游切到 `100.126.200.55:9000`。

迁移不会删除 serverD 的数据库容器或卷。确认稳定运行一周后再人工清理。

SonarQube 的 Elasticsearch 索引卷不迁移，目标实例会根据 PostgreSQL 自动重建；自定义插件需单独核对并重新安装。

## Nginx 接入

SonarQube 的 Nginx 配置模板位于：

- `components/sonarqube/nginx/sonarqube.conf`

迁移完成并确认 Mac mini API 已 `UP` 后，在 `serverA` 部署：

```bash
make sonarqube-nginx-deploy
```

部署后请在 SonarQube 后台将 Server base URL 设置为 `SONAR_ROOT_URL`。

## 升级

1. 在 `components/sonarqube/docker-compose.yml` 修改 `image` 版本。
2. 在 Mac mini 拉取代码后执行：

```bash
make sonarqube-upgrade
# 或
make macmini-sonarqube-upgrade
```

仅备份数据库：

```bash
make sonarqube-backup
```

跳过备份（已手动备份时）：

```bash
SKIP_BACKUP=1 make sonarqube-upgrade
```

升级完成后访问 `${SONAR_ROOT_URL}/setup` 完成数据库迁移。

## 默认账号

- 用户名：`admin`
- 密码：`admin`（首次登录强制修改）
