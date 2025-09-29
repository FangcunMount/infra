# 🚀 基础设施安装部署计划

## 📋 **执行前提条件**

### **1. 服务器环境要求**
- ✅ 服务器已经安装 Docker 和 Docker Compose
- ✅ 已经运行 `init-users.sh` 创建了 www 用户
- ✅ www 用户具有 sudo 权限
- ❗ **需要确保**: www 用户已加入 docker 组

### **2. 权限配置检查**
```bash
# 1. 连接到服务器并切换到 www 用户
ssh root@47.94.204.124
su - www

# 2. 检查 docker 权限（如果失败，需要先配置）
docker ps

# 3. 如果上面命令失败，需要配置 docker 权限
exit  # 切回 root
usermod -aG docker www
su - www  # 重新切换到 www 用户
```

## 🎯 **第一阶段：环境准备**

### **步骤 1.1：代码部署**
```bash
# 在 www 用户下执行
cd /home/www
git clone https://github.com/FangcunMount/infra.git
cd infra

# 或者如果已有代码，更新到最新
cd /home/www/infra
git pull origin main
```

### **步骤 1.2：权限检查**
```bash
# 检查当前用户和权限
whoami                    # 应该显示: www
groups                    # 应该包含: docker sudo
docker --version          # 检查 Docker 版本
docker-compose --version  # 检查 Docker Compose 版本
```

### **步骤 1.3：环境变量配置**
```bash
# 检查环境配置文件
ls -la compose/env/dev/.env
ls -la compose/env/prod/.env

# 如果文件不存在，需要创建
# 开发环境配置已经准备好，生产环境可能需要调整
```

## 🏗️ **第二阶段：基础设施初始化**

### **步骤 2.1：网络和卷初始化**
```bash
cd /home/www/infra

# 使用 Makefile 进行初始化（推荐）
make init-infra

# 或者直接使用脚本
./scripts/init-components/init-infrastructure.sh create
```

**预期结果:**
- ✅ 创建 `infra-frontend` 网络
- ✅ 创建 `infra-backend` 网络  
- ✅ 创建所有必要的数据卷

### **步骤 2.2：验证基础设施**
```bash
# 检查网络创建情况
docker network ls | grep infra

# 检查卷创建情况
docker volume ls | grep infra

# 使用 make 命令检查状态
make status
```

## 📦 **第三阶段：存储服务安装**

### **步骤 3.1：安装存储服务组件**
```bash
# 方法一：使用 make 安装所有存储服务（推荐）
make install-mysql
make install-redis  
make install-mongo

# 方法二：使用脚本逐个安装
./scripts/init-components/install-components.sh mysql
./scripts/init-components/install-components.sh redis
./scripts/init-components/install-components.sh mongo
```

### **步骤 3.2：启动存储服务**
```bash
# 启动存储服务
make up-storage

# 或者分别启动
docker-compose -f compose/infra/docker-compose.storage.yml up -d
```

### **步骤 3.3：验证存储服务**
```bash
# 检查容器状态
make ps

# 检查服务健康状态
make health

# 检查日志
make logs SERVICE=mysql
make logs SERVICE=redis
make logs SERVICE=mongo
```

## 🌐 **第四阶段：网关服务安装**

### **步骤 4.1：安装 Nginx**
```bash
make install-nginx
```

### **步骤 4.2：启动 Nginx**
```bash
make up-nginx
```

### **步骤 4.3：验证 Nginx**
```bash
# 检查 Nginx 容器状态
docker ps | grep nginx

# 检查 Nginx 日志
make logs SERVICE=nginx

# 测试 Nginx 访问
curl -I http://localhost
```

## 🔧 **第五阶段：完整性验证**

### **步骤 5.1：全面状态检查**
```bash
# 使用 make 检查所有状态
make status

# 检查所有容器
make ps

# 检查网络连接
docker network inspect infra-frontend
docker network inspect infra-backend
```

### **步骤 5.2：服务连通性测试**
```bash
# 测试 MySQL 连接
docker exec -it mysql mysql -u www -p -e "SELECT 1"

# 测试 Redis 连接  
docker exec -it redis redis-cli ping

# 测试 MongoDB 连接
docker exec -it mongo mongosh --eval "db.adminCommand('ping')"
```

### **步骤 5.3：日志路径验证**
```bash
# 检查统一日志路径
ls -la /data/log/mysql/
ls -la /data/log/redis/
ls -la /data/log/mongo/
ls -la /data/log/nginx/
```

## ⚡ **快速执行脚本**

如果一切环境正常，可以使用快速执行脚本：

```bash
#!/bin/bash
# 快速部署脚本
cd /home/www/infra

# 1. 初始化基础设施
make init-infra

# 2. 安装存储服务
make install-mysql install-redis install-mongo

# 3. 安装网关服务  
make install-nginx

# 4. 启动所有服务
make up-storage
make up-nginx

# 5. 检查状态
make status
make ps
```

## 🚨 **常见问题处理**

### **权限问题**
```bash
# Docker 权限不足
sudo usermod -aG docker www
# 重新登录 www 用户

# 文件权限问题
sudo chown -R www:www /home/www/infra
```

### **端口冲突**
```bash
# 检查端口占用
netstat -tulpn | grep :80
netstat -tulpn | grep :3306
```

### **服务启动失败**
```bash
# 查看详细错误日志
make logs SERVICE=服务名

# 检查容器状态
docker ps -a
```

## 📊 **部署检查清单**

- [ ] **环境准备**
  - [ ] www 用户创建完成
  - [ ] Docker 权限配置完成
  - [ ] 代码仓库克隆完成

- [ ] **基础设施**
  - [ ] 网络创建成功 (infra-frontend, infra-backend)
  - [ ] 数据卷创建成功
  - [ ] 基础设施状态检查通过

- [ ] **存储服务**
  - [ ] MySQL 安装并启动成功
  - [ ] Redis 安装并启动成功
  - [ ] MongoDB 安装并启动成功
  - [ ] 统一日志路径配置正确

- [ ] **网关服务**
  - [ ] Nginx 安装并启动成功
  - [ ] 网关访问测试通过

- [ ] **完整性验证**
  - [ ] 所有容器运行正常
  - [ ] 服务连通性测试通过
  - [ ] 日志输出正常

---

**准备执行了吗？请按照以上步骤顺序执行，有任何问题随时告诉我！** 🚀