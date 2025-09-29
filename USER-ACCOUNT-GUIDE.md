# 基础设施脚本执行账号选择指南

## 🤔 **问题分析: 使用哪个账号运行脚本？**

### **当前脚本的权限需求分析**

#### **需要特权操作的场景**
```bash
# 1. 创建系统目录 (/data/infra/*)
sudo mkdir -p /data/infra/{mysql,redis,mongo,kafka,jenkins,nginx,logs}

# 2. 设置目录权限
sudo chown -R user:docker /data/infra
sudo chmod -R 755 /data/infra  

# 3. Docker 操作 (需要 docker 组权限)
docker network create infra-frontend
docker volume create infra_mysql_data
```

---

## 🎯 **推荐方案: 使用 `admin` 用户 (非 root)**

### **✅ 为什么推荐 `admin` 用户？**

#### **1. 安全最佳实践**
```bash
# admin 用户配置
- 属于 wheel 组 (sudo 权限)  
- 属于 docker 组 (Docker 操作权限)
- 非 root 用户 (降低风险)
- SSH 密钥认证 (更安全)
```

#### **2. 权限适配性**
- ✅ **Docker 操作**: 通过 `docker` 组成员身份直接访问
- ✅ **系统目录**: 通过 `sudo` 提升权限创建 `/data` 目录  
- ✅ **文件权限**: 可以设置合理的用户所有权
- ✅ **安全隔离**: 避免直接使用 root 的安全风险

#### **3. 脚本兼容性**
```bash
# 当前脚本设计已经支持
INFRA_USER="${INFRA_USER:-$USER}"      # 自动使用当前用户
INFRA_GROUP="${INFRA_GROUP:-docker}"   # 默认使用 docker 组

# 权限操作使用 sudo
sudo mkdir -p "${INFRA_DATA_ROOT}"
sudo chown -R "${INFRA_USER}:${INFRA_GROUP}" "${INFRA_DATA_ROOT}"
```

---

## ⚠️ **不推荐直接使用 root**

### **❌ 使用 root 的问题**

#### **1. 安全风险**
- 🔴 **权限过大**: root 拥有系统完全控制权
- 🔴 **误操作风险**: 一个错误可能破坏整个系统
- 🔴 **审计困难**: 难以追踪具体的操作来源

#### **2. 文件所有权问题**
```bash
# 如果用 root 运行脚本
/data/infra/mysql/data -> root:root (777)
/data/infra/redis/data -> root:root (777)

# 问题：
- Docker 容器可能无法正确访问
- 其他用户无法管理这些文件
- 权限过于宽松 (安全风险)
```

#### **3. Docker 最佳实践违背**
Docker 官方建议：避免在容器中使用 root，也避免宿主机 root 直接管理 Docker。

---

## ❌ **不推荐使用 www 用户**

### **www 用户的限制**

#### **1. 权限不足**
```bash
# www 用户通常配置
- 无 sudo 权限
- 不属于 docker 组  
- 受限的系统访问权限
```

#### **2. 用途不匹配**
```bash
# www 用户的设计用途
- Web 服务进程运行
- 处理 HTTP 请求  
- 文件服务 (nginx/apache)

# 不适合：
- 系统基础设施管理
- Docker 容器编排
- 系统目录创建
```

---

## 🚀 **推荐的用户配置方案**

### **方案1: 使用现有 admin 用户** ⭐️ **推荐**

```bash
# 1. 确认 admin 用户配置
sudo usermod -a -G docker admin        # 加入 docker 组
sudo usermod -a -G wheel admin         # 加入 wheel 组 (sudo 权限)

# 2. 切换到 admin 用户运行脚本
su - admin
cd /path/to/infra

# 3. 运行基础设施脚本
make init-infra                        # 初始化网络和卷
make up-storage                        # 启动存储服务
```

### **方案2: 创建专用部署用户** 🔄 **可选**

```bash
# 1. 创建 deploy 用户 (如果不存在)
sudo useradd -m -g deploy -G docker,wheel -s /bin/bash deploy
sudo passwd deploy

# 2. 配置 sudo 权限
echo "deploy ALL=(ALL) NOPASSWD: /bin/mkdir, /bin/chown, /bin/chmod" | sudo tee /etc/sudoers.d/deploy

# 3. 使用 deploy 用户运行
su - deploy
```

### **方案3: 当前用户 + Docker 组** ✅ **适用于开发**

```bash
# 1. 将当前用户加入 docker 组
sudo usermod -a -G docker $USER

# 2. 重新登录或刷新组权限
newgrp docker

# 3. 直接运行脚本 (当前已支持)
make init-infra
make up-storage
```

---

## 📋 **不同场景的账号选择**

### **开发环境** 🧪
```bash
推荐: 当前开发用户 (已配置 docker 组)
原因: 
- 权限适中，便于调试
- 文件所有权清晰  
- 开发效率高
```

### **测试环境** 🔧  
```bash
推荐: admin 用户
原因:
- 模拟生产环境权限模型
- 完整的系统管理权限
- 安全性和功能性平衡
```

### **生产环境** 🏭
```bash
推荐: 专用 deploy 用户
原因:  
- 最小权限原则
- 审计和追踪友好
- 符合企业安全标准
配置: 受限 sudo + docker 组 + SSH 密钥认证
```

---

## 🔧 **当前脚本的用户配置**

### **自动适配机制**
```bash
# scripts/init-components/init-infrastructure.sh 中的配置
INFRA_USER="${INFRA_USER:-$USER}"      # 默认使用当前用户
INFRA_GROUP="${INFRA_GROUP:-docker}"   # 默认使用 docker 组

# 可以通过环境变量覆盖
export INFRA_USER=admin
export INFRA_GROUP=docker
make init-infra
```

### **权限检查机制**
```bash
# 脚本会自动检查
- Docker 是否运行
- 用户是否有 Docker 访问权限  
- 必要时提示权限不足
```

---

## 🎉 **最终推荐**

### **开发/测试环境**
```bash
使用账号: admin 或当前开发用户 (配置 docker 组)
执行方式: 
su - admin  
make init-infra
make up-storage
```

### **生产环境**  
```bash
使用账号: 专用 deploy 用户
配置要求:
- sudo 权限 (仅限必要命令)
- docker 组成员  
- SSH 密钥认证
- 审计日志记录
```

### **避免使用**
- ❌ **root 用户**: 权限过大，安全风险高
- ❌ **www 用户**: 权限不足，用途不匹配
- ❌ **随意用户**: 可能缺少必要权限

**最佳实践：使用具有适当权限的非特权用户，通过 sudo 和 docker 组来获得必要的系统访问能力。** 🛡️

---

*配置指南更新时间: 2025-09-29*  
*适用场景: 开发/测试/生产环境*  
*安全等级: 生产级标准*