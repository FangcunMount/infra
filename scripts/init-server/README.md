# 🚀 服务器初始化脚本集合

新服务器标准三步初始化流程。

## 📋 快速开始

### 方法1：一键初始化（推荐）
```bash
sudo ./initialize-server.sh
```

### 方法2：分步执行
```bash
# 1. 用户和安全配置
sudo ./init-users.sh

# 2. 网络环境配置（无需Docker）
sudo ./setup-network.sh  

# 3. Docker环境安装（网络已就绪）
sudo ./install-docker.sh
```

## 🎯 执行流程优势

- ✅ **解决依赖问题** - 按正确顺序安装，避免网络和权限冲突
- ✅ **提升成功率** - 网络代理就绪后再安装Docker，避免拉取失败  
- ✅ **支持内网环境** - 自动检测并适配离线安装
- ✅ **完整验证** - 每步完成后自动验证功能

## 📁 脚本说明

| 脚本 | 功能 | 执行顺序 |
|------|------|----------|
| `initialize-server.sh` | 一键自动化初始化 | - |
| `init-users.sh` | 用户创建、SSH配置、安全加固 | ①  |
| `setup-network.sh` | mihomo代理、网络优化 | ② |
| `install-docker.sh` | Docker安装、服务配置 | ③ |
| `diagnose-network.sh` | 网络问题诊断工具 | 辅助 |

## 🔧 辅助工具

```bash
# 下载mihomo二进制文件（可选，内网环境预准备）
./download-mihomo-binaries.sh

# 网络问题诊断
sudo ./diagnose-network.sh

# Docker网络修复（如需要）
sudo ./fix-docker-network.sh
```

## 📚 详细文档

- `SERVER_INITIALIZATION_FLOW.md` - 完整流程说明
- `NEW_INSTALLATION_FLOW.md` - 重构详情
- `UBUNTU_OPTIMIZATION_REPORT.md` - 优化报告

## ⏱️ 预计时间

总计：10-23分钟
- 步骤1：2-5分钟
- 步骤2：3-8分钟  
- 步骤3：5-10分钟

执行完成后服务器将具备完整的用户、网络和容器环境！