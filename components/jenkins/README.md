# Jenkins 组件

Jenkins 是一个开源的持续集成/持续部署 (CI/CD) 平台。

## 服务端口

- **Web 界面**: 8080
- **Agent 通信端口**: 50000

## 默认访问

- URL: http://localhost:8080
- 用户名: admin
- 密码: 在 .env 文件中查看 `JENKINS_ADMIN_PASSWORD`

## 功能特性

- **Configuration as Code (CasC)**: 通过 YAML 配置文件自动配置 Jenkins
- **插件预安装**: 预装常用插件，包括 Docker、Git、Pipeline 等
- **Docker 集成**: 内置 Docker 支持，可直接使用宿主机 Docker
- **流水线支持**: 完整的 Pipeline 功能，支持声明式和脚本式语法
- **多种 SCM 支持**: Git、GitHub、GitLab、SVN 等

## 目录结构

```
/data/jenkins/
├── jenkins_home/          # Jenkins 主目录（映射到容器内 /var/jenkins_home）
├── casc_configs/         # Configuration as Code 配置
└── logs/                 # 日志文件
```

## 配置文件

- `override.yml`: Docker Compose 服务定义
- `jenkins.yaml`: Configuration as Code 配置
- `plugins.txt`: 预安装插件列表

## 使用说明

### 初始化

首次启动时，Jenkins 会自动：
1. 安装 `plugins.txt` 中定义的所有插件
2. 应用 `jenkins.yaml` 中的配置
3. 创建管理员用户
4. 设置基本的安全和授权策略

### 创建第一个流水线

1. 访问 http://localhost:8080
2. 使用管理员账户登录
3. 进入 "CI-CD" 文件夹
4. 查看预置的示例流水线
5. 根据需要修改或创建新的流水线

### Docker 集成使用

Jenkins 容器已经挂载了宿主机的 Docker socket，可以直接在流水线中使用 Docker 命令：

```groovy
pipeline {
    agent any
    stages {
        stage('Build') {
            steps {
                script {
                    sh 'docker build -t myapp:latest .'
                }
            }
        }
    }
}
```

### 配置管理

所有配置都通过 Configuration as Code 管理，修改配置：

1. 编辑 `jenkins.yaml` 文件
2. 重启 Jenkins 容器
3. 配置会自动应用

## 安全注意事项

- 默认禁用匿名访问
- 建议修改默认密码
- 生产环境中应配置 HTTPS
- 定期更新插件和 Jenkins 版本

## 故障排除

### 启动失败
检查日志：
```bash
docker-compose logs jenkins
```

### 插件安装失败
查看 Jenkins 日志：
```bash
# 使用 docker compose 命令
docker compose exec jenkins cat /var/jenkins_home/logs/jenkins.log

# 或使用传统命令
docker-compose exec jenkins cat /var/jenkins_home/logs/jenkins.log
```

### 配置不生效

确认 CasC 配置语法：

```bash
# 进入容器检查配置
docker compose exec jenkins /bin/bash

# 或使用传统命令
docker-compose exec jenkins /bin/bash
```

## 扩展功能

### 添加新插件

在 `plugins.txt` 中添加插件，然后重新构建容器。

### 自定义配置

修改 `jenkins.yaml` 文件，添加所需配置。

### 集成外部服务

通过 CasC 配置集成 Git、Docker Registry、通知服务等。