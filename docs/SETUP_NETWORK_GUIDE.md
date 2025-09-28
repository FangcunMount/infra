# Mihomo VPN 安装配置脚本使用文档

## 概述

`setup-network.sh` 是一个全自动化的 Mihomo (Clash.Meta) VPN 安装配置脚本，支持一键安装、配置和管理 VPN 服务。

## 功能特性

- ✅ **一键安装**：支持命令行参数传入订阅链接，完全自动化安装
- ✅ **智能路径检测**：自动识别项目目录结构，支持多种部署环境
- ✅ **完整配置**：自动处理 proxy-providers、规则文件、地理数据库
- ✅ **智能代理设置**：自动选择最优代理模式和节点
- ✅ **全面测试**：内置连接测试和故障诊断功能
- ✅ **多模式管理**：支持安装、测试、修复、状态查看等多种操作

## 系统要求

- **操作系统**：Ubuntu 18.04+ 
- **权限**：需要 root 权限
- **网络**：需要能够访问订阅链接和外网

## 快速开始

### 1. 准备项目文件

确保项目结构如下：
```
/root/workspace/infra/
├── scripts/
│   └── init-server/
│       └── setup-network.sh
└── static/
    ├── geoip.metadb
    ├── geosite.dat
    └── mihomo-linux-*
```

### 2. 一键安装

#### 方式一：直接传入订阅链接（推荐）
```bash
cd /root/workspace/infra
bash scripts/init-server/setup-network.sh "https://your-subscription-url"
```

#### 方式二：使用 --install 参数
```bash
cd /root/workspace/infra  
bash scripts/init-server/setup-network.sh --install "https://your-subscription-url"
```

#### 方式三：交互式安装
```bash
cd /root/workspace/infra
bash scripts/init-server/setup-network.sh
```

## 详细使用说明

### 命令格式

```bash
setup-network.sh [选项] [订阅链接]
```

### 选项说明

| 选项 | 描述 |
|------|------|
| `无参数` | 完整安装VPN（交互式输入订阅链接） |
| `--install` | 完整安装VPN |
| `--install <URL>` | 使用指定订阅链接安装VPN |
| `<URL>` | 直接使用订阅链接安装VPN |
| `--fix-proxy` | 修复代理设置 |
| `--test` | 测试VPN连接 |
| `--verify` | 验证和修复provider文件 |
| `--status` | 显示服务状态 |
| `--help, -h` | 显示帮助信息 |

### 使用示例

```bash
# 1. 完整自动化安装
bash scripts/init-server/setup-network.sh "https://example.com/subscription"

# 2. 查看服务状态
bash scripts/init-server/setup-network.sh --status

# 3. 测试连接
bash scripts/init-server/setup-network.sh --test

# 4. 修复代理设置
bash scripts/init-server/setup-network.sh --fix-proxy

# 5. 验证配置文件
bash scripts/init-server/setup-network.sh --verify

# 6. 显示帮助
bash scripts/init-server/setup-network.sh --help
```

## 安装流程详解

### 自动化安装流程

当使用订阅链接参数时，脚本将执行以下步骤：

1. **🔧 环境初始化**
   - 检测项目目录结构
   - 自动切换到正确目录
   - 显示路径检测信息

2. **✅ 系统环境检查**
   - 验证操作系统兼容性
   - 检查 root 权限
   - 验证静态资源文件

3. **📦 安装 mihomo 客户端**
   - 自动选择合适的二进制文件（amd64/arm64/armv7）
   - 安装到 `/usr/local/bin/mihomo`
   - 设置执行权限

4. **📋 订阅配置处理**
   - 验证订阅链接有效性
   - 下载订阅配置文件
   - 智能处理 proxy-providers 文件
   - 部署地理数据文件

5. **🚀 服务配置启动**
   - 创建 systemd 服务文件
   - 设置开机自启动
   - 配置端口监听（7890/7891/9090）

6. **🎯 智能代理设置**
   - 自动分析可用代理组
   - 选择最佳代理模式（优先自动选择）
   - 验证代理配置有效性

7. **🔍 验证和测试**
   - Provider 文件验证
   - 服务状态检查
   - 端口监听验证
   - 网站连通性测试

### 路径自动检测

脚本支持智能路径检测，按以下优先级查找资源：

1. `${REPO_ROOT}/static` - 标准项目结构
2. `${SCRIPT_DIR}/static` - 脚本同级目录
3. `$(pwd)/static` - 当前工作目录
4. `/root/workspace/infra/static` - 标准项目目录
5. `/root/static` - 传统位置

## 配置文件说明

### 主要文件位置

| 文件 | 路径 | 说明 |
|------|------|------|
| 主配置文件 | `/root/.config/clash/config.yaml` | Mihomo 主配置 |
| Provider文件 | `/root/.config/clash/*.yaml` | 代理节点提供商文件 |
| 服务文件 | `/etc/systemd/system/mihomo.service` | systemd 服务配置 |
| 二进制文件 | `/usr/local/bin/mihomo` | Mihomo 可执行文件 |
| 环境变量 | `/etc/profile.d/mihomo-proxy.sh` | 全局代理环境变量 |

### 端口配置

| 端口 | 协议 | 用途 |
|------|------|------|
| 7890 | HTTP/HTTPS | 混合代理端口 |
| 7891 | SOCKS5 | SOCKS5 代理端口 |
| 9090 | HTTP | 控制 API 和 Web 面板 |

## 管理操作

### 服务管理

```bash
# 查看服务状态
systemctl status mihomo

# 启动服务
systemctl start mihomo

# 停止服务
systemctl stop mihomo

# 重启服务
systemctl restart mihomo

# 查看日志
journalctl -u mihomo.service -f
```

### 代理环境变量

```bash
# 启用全局代理
source /etc/profile.d/mihomo-proxy.sh
proxy-on

# 禁用全局代理
proxy-off

# 查看代理状态
proxy-status
```

### Web 管理面板

访问控制面板进行高级配置：
- 本地访问：`http://127.0.0.1:9090/ui`
- 远程访问：`http://服务器IP:9090/ui`

## 故障排除

### 常见问题及解决方案

#### 1. 静态文件未找到
```bash
# 错误信息
[ERROR] 未找到 static 目录: /path/to/static

# 解决方案
# 确保在正确的项目目录下运行脚本
cd /root/workspace/infra
bash scripts/init-server/setup-network.sh "订阅链接"
```

#### 2. 代理未生效
```bash
# 运行代理修复
bash scripts/init-server/setup-network.sh --fix-proxy

# 手动测试代理
curl --proxy http://127.0.0.1:7890 http://httpbin.org/ip
```

#### 3. 服务启动失败
```bash
# 查看服务状态
systemctl status mihomo

# 查看详细日志
journalctl -u mihomo.service -n 50

# 重新安装
bash scripts/init-server/setup-network.sh --install "订阅链接"
```

#### 4. 订阅链接无法访问
```bash
# 测试链接连通性
curl -I "订阅链接"

# 检查网络连接
ping google.com

# 使用备用订阅链接重新安装
```

#### 5. 端口被占用
```bash
# 检查端口占用
netstat -tlnp | grep -E "(7890|7891|9090)"

# 停止冲突服务
systemctl stop 冲突服务名

# 重启 mihomo 服务
systemctl restart mihomo
```

### 诊断工具

脚本会自动创建诊断工具：
```bash
# 运行诊断脚本
/usr/local/bin/mihomo-diagnose

# 或使用脚本内置测试
bash scripts/init-server/setup-network.sh --test
```

## 卸载说明

如需完全卸载 VPN 服务，使用配套的卸载脚本：
```bash
bash uninstall-network.sh
```

卸载脚本会：
- 停止并删除 mihomo 服务
- 删除所有配置文件和二进制文件
- 清理环境变量和代理设置
- 恢复系统到初始状态

## 高级配置

### 自定义配置

如需自定义配置，可以：
1. 修改 `/root/.config/clash/config.yaml`
2. 重启服务：`systemctl restart mihomo`
3. 验证配置：`bash scripts/init-server/setup-network.sh --verify`

### 多订阅支持

脚本支持通过重新运行来切换不同的订阅：
```bash
# 切换到新订阅
bash scripts/init-server/setup-network.sh "新的订阅链接"
```

### 节点选择

通过 Web 面板可以：
- 手动选择特定节点
- 切换代理规则模式
- 查看节点延迟和状态
- 实时监控流量

## 实际使用示例

### 典型使用场景

#### 场景1：全新服务器安装
```bash
# 1. 准备项目文件
git clone <your-infra-repo> /root/workspace/infra
cd /root/workspace/infra

# 2. 一键安装 VPN
bash scripts/init-server/setup-network.sh "https://your-subscription-url"

# 3. 验证安装
bash scripts/init-server/setup-network.sh --status
```

#### 场景2：更换订阅链接
```bash
# 1. 切换到项目目录
cd /root/workspace/infra

# 2. 使用新订阅重新安装
bash scripts/init-server/setup-network.sh "https://new-subscription-url"

# 3. 测试连接
bash scripts/init-server/setup-network.sh --test
```

#### 场景3：故障修复
```bash
# 1. 检查状态
bash scripts/init-server/setup-network.sh --status

# 2. 修复代理
bash scripts/init-server/setup-network.sh --fix-proxy

# 3. 验证配置
bash scripts/init-server/setup-network.sh --verify

# 4. 测试连接
bash scripts/init-server/setup-network.sh --test
```

### 脚本输出解读

#### 成功安装的标志
```bash
[SUCCESS] 🎉 Mihomo VPN 安装配置完成！
[SUCCESS] ✅ 代理配置正常，VPN已激活
[SUCCESS] 🎉 代理连接完全正常，所有功能正常！
```

#### 需要关注的警告
```bash
[WARN] ⚠️ HTTP代理IP与直连相同 (当前使用直连节点)
# 含义：代理节点可能就在当前服务器，这是正常的

[WARN] ⚠️ 链接连通性测试失败，但将继续尝试下载
# 含义：网络可能有波动，但不影响安装
```

## 最佳实践

### 安全建议

1. **防火墙配置**：根据需要开放相应端口
2. **访问控制**：限制 Web 面板访问 IP
3. **定期更新**：定期更新订阅和配置
4. **监控日志**：定期检查服务日志

### 性能优化

1. **节点选择**：使用延迟最低的节点
2. **规则优化**：根据需求调整代理规则
3. **资源监控**：监控 CPU 和内存使用
4. **网络调优**：根据带宽调整并发数

### 维护建议

1. **定期测试**：定期运行连接测试
2. **配置备份**：备份重要配置文件
3. **日志清理**：定期清理过大的日志文件
4. **更新检查**：关注 Mihomo 版本更新

## 常用命令速查

```bash
# 🚀 安装相关
bash scripts/init-server/setup-network.sh "订阅链接"        # 一键安装
bash scripts/init-server/setup-network.sh --help          # 查看帮助

# 📊 状态管理
bash scripts/init-server/setup-network.sh --status        # 查看状态
bash scripts/init-server/setup-network.sh --test          # 测试连接

# 🔧 维护修复
bash scripts/init-server/setup-network.sh --fix-proxy     # 修复代理
bash scripts/init-server/setup-network.sh --verify        # 验证配置

# 🛠️ 系统服务
systemctl status mihomo                                   # 服务状态
systemctl restart mihomo                                  # 重启服务
journalctl -u mihomo.service -f                          # 查看日志

# 🌐 代理测试
curl --proxy http://127.0.0.1:7890 http://httpbin.org/ip  # 测试代理
curl --socks5 127.0.0.1:7891 http://httpbin.org/ip       # 测试SOCKS5
```

## 技术支持

如遇到问题，请按以下步骤排查：

1. **检查基础环境**
   ```bash
   bash scripts/init-server/setup-network.sh --status
   ```

2. **运行连接测试**
   ```bash
   bash scripts/init-server/setup-network.sh --test
   ```

3. **查看详细日志**
   ```bash
   journalctl -u mihomo.service -n 100
   ```

4. **尝试修复配置**
   ```bash
   bash scripts/init-server/setup-network.sh --fix-proxy
   ```

5. **重新安装（如必要）**
   ```bash
   bash scripts/init-server/setup-network.sh "订阅链接"
   ```

---

**注意**：此脚本专为 Ubuntu 系统设计，使用前请确保满足系统要求并具有相应权限。建议在测试环境中先行验证后再部署到生产环境。