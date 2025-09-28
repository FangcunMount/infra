# Docker VPN 快速使用指南

## 🚀 快速开始

### 1. 一键安装 Docker + VPN 配置

```bash
# 方法 1: 在线安装（推荐）
curl -sSL https://raw.githubusercontent.com/FangcunMount/infra/main/scripts/init-server/install-docker.sh | bash

# 方法 2: 手动下载运行
wget https://raw.githubusercontent.com/FangcunMount/infra/main/scripts/init-server/install-docker.sh
chmod +x install-docker.sh
sudo bash install-docker.sh
```

### 2. 单独配置 VPN（Docker 已安装）

```bash
bash install-docker.sh --configure-vpn-only
```

### 3. 测试 VPN 功能

```bash
bash install-docker.sh --test-vpn-only
```

## 📋 脚本命令选项

| 命令 | 功能 | 适用场景 |
|------|------|----------|
| `bash install-docker.sh` | 完整安装 | 全新服务器 |
| `bash install-docker.sh --configure-vpn-only` | 仅配置 VPN | Docker 已安装 |
| `bash install-docker.sh --test-vpn-only` | 仅测试 VPN | 验证功能 |
| `bash install-docker.sh --help` | 显示帮助 | 查看选项 |

## 🌐 VPN 代理使用方法

### 方法 1: 环境变量（推荐）

```bash
# 单个容器使用 VPN（推荐使用小写环境变量）
docker run --rm \
  -e http_proxy=http://172.18.0.1:7890 \
  -e https_proxy=http://172.18.0.1:7890 \
  alpine/curl http://ipinfo.io/ip

# 兼容性更好的方式（同时设置大小写）
docker run --rm \
  -e HTTP_PROXY=http://172.18.0.1:7890 \
  -e HTTPS_PROXY=http://172.18.0.1:7890 \
  -e http_proxy=http://172.18.0.1:7890 \
  -e https_proxy=http://172.18.0.1:7890 \
  alpine/curl http://ipinfo.io/ip

# 输出应该显示 VPN 出口 IP，而不是服务器真实 IP
```

### 方法 2: 显式代理参数

```bash
# 使用 curl 的 --proxy 参数
docker run --rm alpine/curl \
  --proxy http://172.18.0.1:7890 \
  http://ipinfo.io/ip
```

### 方法 3: Docker Compose

```yaml
version: '3.8'
services:
  myapp:
    image: myapp:latest
    environment:
      # 同时设置大小写环境变量确保兼容性
      - HTTP_PROXY=http://172.18.0.1:7890
      - HTTPS_PROXY=http://172.18.0.1:7890
      - http_proxy=http://172.18.0.1:7890
      - https_proxy=http://172.18.0.1:7890
      - NO_PROXY=localhost,127.0.0.1,::1
    ports:
      - "8080:80"
```

## 🧪 验证 VPN 功能

### 快速验证

```bash
# 1. 测试直接连接
DIRECT_IP=$(docker run --rm alpine/curl -s http://ipinfo.io/ip)
echo "直接连接 IP: $DIRECT_IP"

# 2. 测试代理连接（环境变量方式）
PROXY_IP_ENV=$(docker run --rm -e http_proxy=http://172.18.0.1:7890 alpine/curl -s http://ipinfo.io/ip)
echo "代理连接 IP (环境变量): $PROXY_IP_ENV"

# 3. 测试代理连接（显式参数方式）
PROXY_IP_PARAM=$(docker run --rm alpine/curl -s --proxy http://172.18.0.1:7890 http://ipinfo.io/ip)
echo "代理连接 IP (显式参数): $PROXY_IP_PARAM"

# 4. 比较结果
if [ "$PROXY_IP_ENV" != "$DIRECT_IP" ] && [ "$PROXY_IP_PARAM" != "$DIRECT_IP" ]; then
    echo "✅ VPN 代理工作正常！"
else
    echo "❌ VPN 代理未生效，请检查配置"
fi
```

### 自动化测试

```bash
# 运行完整测试
bash install-docker.sh --test-vpn-only
```

## 🔧 故障排除

### 1. VPN 服务检查

```bash
# 检查 Mihomo 服务状态
systemctl status mihomo

# 检查代理端口
netstat -tlnp | grep 7890
ss -tlnp | grep 7890
```

### 2. Docker 服务检查

```bash
# 检查 Docker 状态
systemctl status docker

# 查看 Docker 日志
journalctl -u docker.service -n 20
```

### 3. 网络连通性测试

```bash
# 测试容器到网关的连接
docker run --rm alpine ping -c 2 172.18.0.1

# 测试代理端口连接
docker run --rm alpine sh -c "nc -zv 172.18.0.1 7890"
```

### 4. 重新配置

```bash
# 如果 VPN 不工作，重新配置
bash install-docker.sh --configure-vpn-only
```

## 📁 配置文件位置

| 文件 | 用途 | 位置 |
|------|------|------|
| daemon.json | Docker 镜像源配置 | `/etc/docker/daemon.json` |
| http-proxy.conf | Docker 服务代理 | `/etc/systemd/system/docker.service.d/` |
| config.yaml | Mihomo VPN 配置 | `/root/.config/clash/config.yaml` |

## ❓ 常见问题

**Q: 容器还是显示服务器真实 IP？**
A: 需要明确设置代理环境变量，Docker 不会自动使用代理。

**Q: Docker 服务启动失败？**
A: 检查 daemon.json 语法，运行 `journalctl -u docker.service`。

**Q: 代理端口连接失败？**
A: 确认 VPN 服务正常运行，检查防火墙设置。

**Q: 如何让所有容器都使用 VPN？**
A: 在 Docker Compose 文件中全局设置环境变量，或修改 daemon.json。

## 🎯 最佳实践

1. **测试优先**: 安装后立即运行测试确保功能正常
2. **环境变量**: 优先使用环境变量方式，灵活性更高
3. **定期验证**: 定期运行测试脚本确保 VPN 功能正常
4. **日志监控**: 关注 Docker 和 VPN 服务日志异常

---

*最后更新: 2025-09-28*
*状态: ✅ 已完成*
