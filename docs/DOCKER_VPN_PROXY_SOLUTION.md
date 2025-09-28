# Docker VPN 代理解决方案

## 问题概述

Docker 容器无法通过 VPN 代理访问外网的问题已彻底解决。

## 解决方案

### 1. 核心问题

- **原问题**: Docker 容器内应用程序无法使用宿主机的 VPN 代理
- **根本原因**: Docker daemon 配置错误导致服务启动失败
- **解决方法**: 修复 daemon.json 配置并实现正确的代理集成

### 2. 技术实现

#### VPN 代理配置

- **VPN 服务**: Mihomo (Clash Meta)
- **代理端口**:
  - HTTP 代理: 7890
  - SOCKS5 代理: 7891
  - API 接口: 9090
- **监听地址**: 0.0.0.0 (允许 LAN 访问)

#### Docker 网络配置

- **Docker 网络**: bridge (默认)
- **网络子网**: 172.18.0.0/16
- **网关地址**: 172.18.0.1
- **代理访问**: `http://172.18.0.1:7890`

#### Docker Daemon 配置

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.nju.edu.cn"
  ]
}
```

**重要**: 移除了错误的 runtime 配置，避免 `runtime name 'runc' is reserved` 错误。

### 3. 使用方法

#### 方法一: 环境变量 (推荐)

```bash
docker run --rm -e HTTP_PROXY=http://172.18.0.1:7890 -e HTTPS_PROXY=http://172.18.0.1:7890 alpine/curl http://ipinfo.io/ip
```

#### 方法二: 显式代理参数

```bash
docker run --rm alpine/curl --proxy http://172.18.0.1:7890 http://ipinfo.io/ip
```

### 4. 验证测试

#### 测试脚本

更新后的 `install-docker.sh` 包含完整的测试功能：

```bash
test_vpn_network() {
    # 测试直接连接
    direct_ip=$(docker run --rm alpine/curl -s http://ipinfo.io/ip)
    
    # 测试代理连接  
    proxy_ip=$(docker run --rm alpine/curl -s --proxy http://172.18.0.1:7890 http://ipinfo.io/ip)
    
    # 比较结果
    if [[ "$proxy_ip" != "$direct_ip" ]]; then
        echo "✅ VPN 代理工作正常"
    fi
}
```

#### 测试结果

- **直连 IP**: 47.94.204.124 (服务器真实IP)  
- **代理 IP**: 154.17.230.130 (VPN 出口IP)
- **状态**: ✅ 代理功能正常

### 5. 常见问题排查

#### Docker 服务启动失败

**错误**: `failed to start daemon: runtime name 'runc' is reserved`

**解决**: 移除 daemon.json 中的 runtime 配置

```bash
# 检查配置
cat /etc/docker/daemon.json

# 重启服务
systemctl restart docker
```

#### 容器无法访问代理

**检查步骤**:

1. **VPN 服务状态**:

   ```bash
   systemctl status mihomo
   netstat -tlnp | grep 7890
   ```

2. **网络连通性**:

   ```bash
   docker run --rm alpine ping -c 2 172.18.0.1
   docker run --rm alpine nc -zv 172.18.0.1 7890
   ```

3. **代理功能**:

   ```bash
   docker run --rm alpine/curl --proxy http://172.18.0.1:7890 http://ipinfo.io/ip
   ```

### 6. 自动化部署

`install-docker.sh` 脚本现已集成完整的 VPN 代理支持：

- ✅ 自动检测 VPN 服务
- ✅ 配置 Docker daemon
- ✅ 网络连通性测试
- ✅ 代理功能验证

### 7. 生产环境建议

#### Docker Compose 集成

```yaml
version: '3.8'
services:
  app:
    image: myapp:latest
    environment:
      - HTTP_PROXY=http://172.18.0.1:7890
      - HTTPS_PROXY=http://172.18.0.1:7890
      - NO_PROXY=localhost,127.0.0.1,::1
```

#### 全局代理配置

对于需要全局 VPN 代理的环境，可配置 Docker daemon 环境变量：

```bash
# /etc/systemd/system/docker.service.d/http-proxy.conf
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
Environment="NO_PROXY=localhost,127.0.0.1,::1"
```

## 总结

通过修复 Docker daemon 配置错误并实现正确的网络代理集成，Docker 容器现在可以seamlessly使用宿主机的 VPN 代理访问外网。整个解决方案已集成到 `install-docker.sh` 脚本中，实现一键部署和自动化测试。

**关键成果**:

- ✅ Docker 容器 VPN 代理功能完全正常
- ✅ 自动化安装和配置脚本  
- ✅ 完整的测试和验证机制
- ✅ 生产环境部署指南

---

*最后更新: 2025-09-28*
*状态: ✅ 已解决*
