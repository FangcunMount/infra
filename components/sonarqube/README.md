# SonarQube 组件

本组件部署在 Mac mini Docker Desktop，由 `make macmini-sonarqube-up` 启动，包含 SonarQube Community Edition 与 PostgreSQL。

当前镜像均原生支持 Apple Silicon：

- `sonarqube:26.7.0.124771-community`: `linux/arm64`
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

全新部署请为 `SONAR_DB_PASSWORD` 生成独立强密码：

```bash
openssl rand -base64 32
```

启动时 `sonarqube-init` 会在 Docker Desktop Linux VM 内设置 Elasticsearch 所需的 `vm.max_map_count` 和 `fs.file-max`，无需修改 macOS 的 `sysctl`。

## 全新部署

在 Mac mini 的 infra 仓库执行：

```bash
make macmini-sonarqube-up
make macmini-sonarqube-status
```

等待状态为 `healthy` 后，在 Mac mini 验证：

```bash
curl -fsS http://127.0.0.1:9000/api/system/status
```

预期返回 `"status":"UP"`。

## Nginx 接入

SonarQube 的 Nginx 配置模板位于：

- `components/sonarqube/nginx/sonarqube.conf`

确认 Mac mini API 已 `UP`，并在 serverA 验证 `curl http://100.126.200.55:9000/api/system/status` 可访问后，部署：

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
