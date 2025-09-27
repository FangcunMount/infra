# 网络环境配置流程更新

## 🎯 新的执行流程

为了解决 Docker 镜像拉取的网络依赖问题，我们重新设计了安装流程：

### 1️⃣ 第一阶段：网络环境配置（无需 Docker）
```bash
# 直接安装 mihomo 网络环境（使用二进制版本）
sudo ./setup-network.sh
```

**特点：**
- ✅ **无 Docker 依赖** - 使用 mihomo 二进制文件
- ✅ **内网友好** - 支持本地静态文件
- ✅ **快速启动** - 避免镜像拉取问题
- ✅ **systemd 集成** - 专用系统服务

### 2️⃣ 第二阶段：Docker 环境配置（网络就绪后）
```bash
# 网络环境准备好后安装 Docker
sudo ./install-docker.sh
```

**优势：**
- ✅ **网络代理可用** - mihomo 提供网络加速
- ✅ **镜像拉取顺畅** - 通过代理访问 Docker Hub
- ✅ **避免循环依赖** - 先网络后 Docker

## 📋 详细操作步骤

### 准备阶段（可选）
如果需要在内网环境使用，可提前下载二进制文件：

```bash
# 下载多架构二进制文件到 static 目录
./download-mihomo-binaries.sh
```

这会下载：
- `static/mihomo-linux-amd64` - x86_64 架构
- `static/mihomo-linux-arm64` - ARM64 架构  
- `static/mihomo-linux-armv7` - ARMv7 架构

### 执行安装

#### 1. 网络环境配置
```bash
sudo ./setup-network.sh
```

**脚本会自动：**
- 检查系统环境（仅 Ubuntu）
- 安装 mihomo 二进制文件
- 创建配置目录
- 处理地理数据文件（优先使用本地）
- 配置 VPN 订阅
- 创建 systemd 服务
- 启动网络代理服务
- 配置全局代理环境
- 创建管理脚本

#### 2. 验证网络环境
```bash
# 检查服务状态
systemctl status mihomo

# 检查代理端口
curl -I --proxy http://localhost:7890 https://www.google.com

# 使用管理脚本
mihomo-control status
```

#### 3. 安装 Docker（现在网络已就绪）
```bash
sudo ./install-docker.sh
```

现在 Docker 安装应该会很顺利，因为：
- 网络代理已配置
- 可以访问 Docker 官方源
- 镜像拉取不会超时

## 🔧 管理命令

安装完成后，可使用以下命令管理 mihomo：

```bash
# 服务管理
systemctl start|stop|restart|status mihomo

# 或使用便捷脚本
mihomo-control start|stop|restart|status|logs

# 更新订阅
mihomo-control update <订阅URL>

# 编辑配置
mihomo-control config
```

## 🎯 关键改进

### 架构优化
- **去除 Docker 依赖** - 网络配置阶段不需要 Docker
- **二进制直接安装** - 更轻量，启动更快
- **系统用户隔离** - 创建专用 mihomo 用户
- **安全加固** - systemd 安全配置

### 文件结构
```
/opt/mihomo/
├── config/
│   ├── config.yaml          # 主配置文件
│   └── update-subscription.sh  # 订阅更新脚本
└── data/
    ├── GeoSite.dat          # 地理位置数据
    └── GeoIP.metadb         # IP 地理数据

/usr/local/bin/
└── mihomo                   # 主程序二进制

/usr/local/bin/
└── mihomo-control           # 管理脚本

/etc/systemd/system/
└── mihomo.service           # 系统服务
```

## 🚀 优势总结

1. **解决循环依赖** - 网络环境不依赖 Docker
2. **提升安装成功率** - 避免网络问题导致的失败
3. **简化维护** - 原生 systemd 服务管理
4. **性能优化** - 二进制直接运行，无容器开销
5. **安全增强** - 专用用户和权限隔离

## 📝 注意事项

- 仅支持 Ubuntu 系统
- 需要 root 权限执行
- 推荐先配置网络环境，再安装其他服务
- 静态文件可提前准备，支持完全离线安装

这个新流程彻底解决了之前遇到的 Docker 网络问题！