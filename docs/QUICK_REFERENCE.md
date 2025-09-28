# Setup Network 快速参考

## 一键安装命令

```bash
cd /root/workspace/infra
bash scripts/init-server/setup-network.sh "https://your-subscription-url"
```

## 常用命令

```bash
# 📊 状态查看
bash scripts/init-server/setup-network.sh --status

# 🔧 修复代理
bash scripts/init-server/setup-network.sh --fix-proxy

# 🧪 连接测试
bash scripts/init-server/setup-network.sh --test

# ✅ 配置验证
bash scripts/init-server/setup-network.sh --verify

# ❓ 查看帮助
bash scripts/init-server/setup-network.sh --help
```

## 服务管理

```bash
# 查看状态
systemctl status mihomo

# 重启服务
systemctl restart mihomo

# 查看日志
journalctl -u mihomo.service -f
```

## 端口信息

- **HTTP/HTTPS 代理**: 7890
- **SOCKS5 代理**: 7891  
- **Web 管理面板**: 9090

## 快速测试

```bash
# 测试代理连接
curl --proxy http://127.0.0.1:7890 http://httpbin.org/ip

# 测试网站访问
curl --proxy http://127.0.0.1:7890 -I http://google.com
```

## 常见问题

### 代理不工作
```bash
bash scripts/init-server/setup-network.sh --fix-proxy
```

### 服务异常
```bash
systemctl restart mihomo
bash scripts/init-server/setup-network.sh --test
```

### 重新安装
```bash
bash scripts/init-server/setup-network.sh "新订阅链接"
```

---

📖 完整文档请查看: [SETUP_NETWORK_GUIDE.md](./SETUP_NETWORK_GUIDE.md)