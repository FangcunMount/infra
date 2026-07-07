# SonarQube 组件

本组件部署在 `serverD`，由 `make serverD-sonarqube-up` 或 `make serverD-up` 启动，包含 SonarQube Community Edition 与 PostgreSQL。

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
- `SONAR_WEB_JAVAOPTS`
- `SONAR_CE_JAVAOPTS`

## 宿主机前置条件

部署前在 `serverD` 设置内核参数：

```bash
sudo tee /etc/sysctl.d/99-sonarqube.conf <<'EOF'
vm.max_map_count=524288
fs.file-max=131072
EOF
sudo sysctl --system
```

## Nginx 接入

SonarQube 的 Nginx 配置模板位于：

- `components/sonarqube/nginx/sonarqube.conf`

在 `serverA` 部署示例：

```bash
make sonarqube-nginx-deploy
```

部署后请在 SonarQube 后台将 Server base URL 设置为 `SONAR_ROOT_URL`。

## 默认账号

- 用户名：`admin`
- 密码：`admin`（首次登录强制修改）
