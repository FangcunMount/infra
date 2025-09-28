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

## 📁 核心脚本

| 脚本 | 功能 | 执行顺序 |
|------|------|----------|
| `initialize-server.sh` | 一键自动化初始化 | - |
| `init-users.sh` | 用户创建、SSH配置、安全加固 | ①  |
| `setup-network.sh` | Mihomo VPN 代理、网络优化 | ② |
| `install-docker.sh` | **Docker统一安装配置** | ③ |

## 🐳 Docker 统一功能

新版 `install-docker.sh` 整合了所有 Docker 相关功能：

- ✅ **Docker Engine 安装** - 完整的Docker CE安装流程
- ✅ **用户权限配置** - 自动配置docker组权限并测试  
- ✅ **VPN网络集成** - 自动检测VPN并配置代理模式
- ✅ **Docker Compose** - 安装并测试Docker Compose插件
- ✅ **完整性验证** - 用户权限、基本功能、网络连接全面测试
- ✅ **Docker Hub认证** - 可选的Docker Hub登录配置

## 🔧 VPN 管理工具

```bash
# VPN 状态管理和测试
./docker-vpn-manager.sh status      # 查看 VPN 状态  
./docker-vpn-manager.sh enable      # 启用 VPN 模式
./docker-vpn-manager.sh disable     # 禁用 VPN 模式
./docker-vpn-manager.sh test        # 测试网络连接
./docker-vpn-manager.sh docker-test # Docker VPN 专项测试
./docker-vpn-manager.sh proxies     # 查看所有代理组状态
./docker-vpn-manager.sh switch      # 切换漏网之鱼代理选择

# 网络服务管理
./test-docker-users.sh

# 下载 Mihomo 二进制文件（可选，内网环境预准备）
./download-mihomo-binaries.sh

# 卸载网络环境
./uninstall-network.sh
```

## 🎉 新特性

- ✅ **自动 VPN 配置** - Docker 安装时自动配置 VPN 代理模式
- ✅ **智能代理切换** - 自动配置"漏网之鱼"代理组，确保容器使用 VPN
- ✅ **完整测试套件** - 提供全面的网络和 Docker VPN 测试
- ✅ **便捷管理工具** - `vpn` 命令提供一站式 VPN 管理

## 📚 详细文档

- `README-config-fix.md` - 配置修复功能说明
- `README-repeatable.md` - 可重复执行改造说明

## ⏱️ 预计时间

总计：10-23分钟

- 步骤1：2-5分钟
- 步骤2：3-8分钟  
- 步骤3：5-10分钟

执行完成后服务器将具备完整的用户、网络和容器环境！
