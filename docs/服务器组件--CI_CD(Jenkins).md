# 服务器组件 - CI/CD(Jenkins)

> 🔧 部署 Jenkins 持续集成和持续部署平台

## 🎯 CI/CD 服务目标

- 部署 Jenkins LTS 持续集成平台
- 配置 Docker-in-Docker 构建环境
- 设置 Pipeline as Code
- 集成代码仓库和部署流程
- 建立构建监控和通知

## 🚀 自动化部署

### 一键 Jenkins 部署

```bash
# 使用 compose-manager 脚本部署 CI/CD 服务
./scripts/deploy/compose-manager.sh infra up cicd

# 自动完成：
# ✅ 部署 Jenkins LTS 版本
# ✅ 配置 Docker-in-Docker
# ✅ 安装必要插件
# ✅ 设置数据持久化
# ✅ 配置安全设置
```

## 🔧 手动配置步骤

### 部署 Jenkins 服务

```bash
# 创建 Jenkins 配置目录
sudo mkdir -p /opt/infra/jenkins/{data,logs}
sudo chown -R 1000:1000 /opt/infra/jenkins

# 启动 Jenkins 容器
docker run -d \
  --name jenkins \
  --network infra-backend \
  --restart unless-stopped \
  -p 8080:8080 \
  -p 50000:50000 \
  -v infra_jenkins_data:/var/jenkins_home \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /opt/infra/jenkins/logs:/var/log/jenkins \
  -e JENKINS_OPTS="--httpPort=8080 --prefix=/jenkins" \
  --health-cmd="curl -f http://localhost:8080/login || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  jenkins/jenkins:lts

# 获取初始管理员密码
docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

### Jenkins 初始化配置

```bash
# 安装推荐插件列表
PLUGINS="
  pipeline-stage-view
  docker-pipeline
  git
  github
  gitlab-plugin
  nodejs
  maven-plugin
  gradle
  build-timeout
  timestamper
  ws-cleanup
  ant
  workflow-aggregator
  pipeline-npm
  ssh-slaves
  matrix-auth
  pam-auth
  ldap
  email-ext
  mailer
"

# 通过 CLI 安装插件
for plugin in $PLUGINS; do
  docker exec jenkins jenkins-cli install-plugin $plugin
done

# 重启 Jenkins
docker restart jenkins
```

## 📋 验证检查清单

### ✅ Jenkins 服务验证

```bash
# 检查 Jenkins 运行状态
curl -I http://localhost:8080/login | grep -q "200 OK" && echo "✅ Jenkins Web界面正常" || echo "❌ Jenkins Web界面异常"

# 检查 Docker 集成
docker exec jenkins docker --version >/dev/null 2>&1 && echo "✅ Jenkins Docker集成正常" || echo "❌ Jenkins Docker集成失败"

# 访问 Jenkins
echo "🌐 Jenkins 访问地址: http://localhost:8080"
echo "👤 默认用户: admin"
echo "🔑 初始密码: $(docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword 2>/dev/null || echo '请查看容器日志')"
```

## 🛠️ Jenkins Pipeline 示例

### 基础 Pipeline 配置

```groovy
pipeline {
    agent any
    
    environment {
        DOCKER_REGISTRY = 'your-registry.com'
        APP_NAME = 'your-app'
    }
    
    stages {
        stage('Checkout') {
            steps {
                git branch: 'main', url: 'https://github.com/your-repo.git'
            }
        }
        
        stage('Build') {
            steps {
                script {
                    def image = docker.build("${DOCKER_REGISTRY}/${APP_NAME}:${BUILD_NUMBER}")
                }
            }
        }
        
        stage('Test') {
            steps {
                sh 'docker run --rm ${DOCKER_REGISTRY}/${APP_NAME}:${BUILD_NUMBER} npm test'
            }
        }
        
        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                sh '''
                    docker-compose -f docker-compose.yml pull
                    docker-compose -f docker-compose.yml up -d
                '''
            }
        }
    }
    
    post {
        always {
            cleanWs()
        }
        success {
            echo 'Pipeline succeeded!'
        }
        failure {
            echo 'Pipeline failed!'
        }
    }
}
```

## 🔄 下一步

CI/CD 服务部署完成后，最后部署：

1. [🌐 网关服务](服务器组件--网关(Nginx).md) - 部署 Nginx 反向代理网关

---

> 💡 **Jenkins 运维提醒**: 定期备份 Jenkins 配置和作业、更新插件版本、监控构建队列和资源使用