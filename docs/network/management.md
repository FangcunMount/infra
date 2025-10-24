# 网络管理指南

## 概述

本指南说明如何管理基础设施网络和业务应用网络,包括Docker网络、Swarm集群和VPN配置。

## 网络架构原则

### 单向依赖设计

```text
业务应用 ──→ 基础设施网络 (infra-network)
   ✓              ✓
 主动连接        被动提供服务
```

**核心原则**:

- **基础设施组件** (MySQL, Redis, MongoDB, Nginx, NSQ等)
  - ✅ 只连接 `infra-network`
  - ❌ 不连接任何业务网络
  - 作用: 被动等待业务应用访问

- **业务应用**
  - ✅ 连接自己的业务网络 (如 `miniblog-network`)
  - ✅ 同时连接 `infra-network` 访问基础设施
  - 作用: 主动连接所需资源

**为什么这样设计?**

1. **解耦**: 基础设施与业务应用解耦,互不影响
2. **简化**: 新增业务不需要修改基础设施配置
3. **灵活**: 业务可以选择性地连接需要的服务
4. **维护性**: 基础设施配置保持稳定,易于维护

## 网络类型

| 网络名称 | 类型 | 子网 | 用途 |
|---------|------|------|------|
| `infra-network` | overlay | 172.20.0.0/16 | 基础设施共享网络 |
| `<app>-network` | bridge/overlay | 172.21+.0.0/16 | 业务应用专用网络 |

## 基础设施网络管理

### 初始化网络

```bash
# 完整初始化 (网络 + 卷)
make init

# 仅初始化网络
make network-init

# 自定义配置
INFRA_BACKEND_SUBNET=172.20.0.0/16 make network-init
INFRA_NETWORK_MTU=1450 make network-init
```

### 查看网络状态

```bash
# 网络状态概览
make network-status

# 列出所有网络
make network-list

# 查看网络详情
make network-inspect NAME=infra-network

# 诊断网络问题
make network-diagnose
```

### 重置网络

```bash
# 删除并重建网络
make network-reset

# 完整重置 (包括卷)
make reset
```

## 业务网络管理

### 创建业务网络

```bash
# 创建 bridge 网络 (单机)
make app-network-create NAME=miniblog-network

# 创建 overlay 网络 (分布式)
make app-network-create NAME=app-net DRIVER=overlay

# 自定义子网
make app-network-create NAME=app-net SUBNET=172.21.0.0/16
```

### 管理业务网络

```bash
# 列出所有网络
make app-network-list

# 查看网络详情
make app-network-inspect NAME=miniblog-network

# 删除网络
make app-network-delete NAME=miniblog-network

# 批量清理未使用的网络
docker network prune
```

### 业务应用配置示例

#### 正确的配置方式 ✅

```yaml
# miniblog/docker-compose.yml
version: '3.8'

services:
  miniblog-app:
    image: miniblog:latest
    networks:
      - miniblog-network   # 自己的业务网络
      - infra-network      # 连接基础设施
    environment:
      # 通过服务名访问基础设施
      - MYSQL_HOST=mysql
      - REDIS_HOST=redis
      - MONGO_HOST=mongo

networks:
  miniblog-network:
    external: true         # 使用外部创建的网络
  infra-network:
    external: true         # 连接基础设施网络
```

#### 错误的配置方式 ❌

```yaml
# ❌ 不要在基础设施组件中配置业务网络
# components/mysql/docker-compose.yml
services:
  mysql:
    networks:
      - infra-network
      - miniblog-network  # ❌ 错误!
      - blog-network      # ❌ 每增加业务都要改
```

## Docker Swarm 管理

### 初始化 Swarm 集群

#### 在管理节点 (ServerA) 初始化

```bash
# 初始化 Swarm
make swarm-init

# 或手动指定IP
docker swarm init --advertise-addr 121.43.138.102
```

#### 在工作节点 (ServerB) 加入

```bash
# 1. 在管理节点获取加入令牌
docker swarm join-token worker

# 2. 在工作节点执行返回的命令
docker swarm join --token SWMTKN-xxx 121.43.138.102:2377

# 或使用Makefile (需要手动输入token)
make swarm-join
```

### 管理 Swarm 节点

```bash
# 查看节点列表
docker node ls

# 查看节点详情
docker node inspect <node-id>

# 更新节点标签
docker node update --label-add role=worker node-b

# 节点维护模式
docker node update --availability drain node-b   # 停止调度
docker node update --availability active node-b  # 恢复调度
```

### 离开 Swarm

```bash
# 在工作节点离开集群
docker swarm leave

# 在管理节点强制离开
docker swarm leave --force

# 或使用 Makefile
make swarm-leave
```

## VPN 管理

### Mihomo VPN (推荐)

#### 安装 Mihomo

```bash
# 自动安装
make vpn-install

# 手动安装
cd /path/to/infra
./scripts/network/vpn-manager.sh install
```

#### 配置 VPN

```bash
# 编辑配置文件
vim /etc/mihomo/config.yaml
```

基本配置示例:

```yaml
# /etc/mihomo/config.yaml
port: 7890
socks-port: 7891
allow-lan: false
mode: rule
log-level: info

proxies:
  - name: "my-proxy"
    type: ss/vmess/trojan
    server: your-server.com
    port: 443
    # ... 其他配置

proxy-groups:
  - name: "PROXY"
    type: select
    proxies:
      - "my-proxy"

rules:
  - DOMAIN-SUFFIX,google.com,PROXY
  - DOMAIN-SUFFIX,github.com,PROXY
  - MATCH,DIRECT
```

#### 管理 VPN 服务

```bash
# 启动 VPN
make vpn-start

# 停止 VPN
make vpn-stop

# 重启 VPN
make vpn-restart

# 查看状态
make vpn-status

# 查看日志
make vpn-logs
```

#### 测试 VPN

```bash
# 测试连接
make vpn-test

# 或手动测试
curl --proxy http://127.0.0.1:7890 https://www.google.com
```

### OpenVPN (备选方案)

如果需要使用OpenVPN:

```bash
# 安装 OpenVPN
sudo apt-get install openvpn

# 连接 VPN
sudo openvpn --config /path/to/config.ovpn

# 后台运行
sudo openvpn --config /path/to/config.ovpn --daemon
```

## 网络诊断

### 基础连通性检查

```bash
# 在容器内测试
docker exec <container> ping mysql
docker exec <container> ping nsqd
docker exec <container> curl http://redis:6379

# 测试DNS解析
docker exec <container> nslookup mysql
docker exec <container> nslookup nsqd
```

### 跨主机通信检查

```bash
# 检查 Swarm 节点通信
docker node ls

# 检查防火墙端口
nc -zv <target_ip> 2377  # Swarm 管理
nc -zv <target_ip> 7946  # 节点通信
nc -zv <target_ip> 4789  # VXLAN

# 测试 Overlay 网络
docker run --rm --network infra-network alpine ping mysql
```

### 性能测试

```bash
# 测试延迟
docker exec <container> ping -c 10 mysql

# 测试带宽 (使用 iperf3)
# 在服务端
docker run --rm --network infra-network -p 5201:5201 networkstatic/iperf3 -s

# 在客户端
docker run --rm --network infra-network networkstatic/iperf3 -c <server_ip>
```

### 网络统计

```bash
# 查看容器网络统计
docker stats

# 查看网络流量
docker network inspect infra-network

# 查看连接数
netstat -an | grep ESTABLISHED | wc -l
```

## 常见问题排查

### 问题1: 网络无法创建

**症状**: `Error response from daemon: network ... already exists`

**解决**:

```bash
# 查看现有网络
docker network ls

# 删除冲突网络
docker network rm <network_name>

# 重新创建
make network-init
```

### 问题2: 服务无法通信

**症状**: 容器之间无法ping通或访问

**排查步骤**:

```bash
# 1. 检查容器是否在同一网络
docker inspect <container> | grep -A 10 Networks

# 2. 检查网络状态
make network-status

# 3. 测试DNS解析
docker exec <container> nslookup <service_name>

# 4. 检查防火墙
sudo ufw status

# 5. 查看日志
docker logs <container>
```

### 问题3: Swarm 节点无法加入

**症状**: `Error response from daemon: rpc error`

**解决**:

```bash
# 1. 检查防火墙端口
sudo ufw allow 2377/tcp
sudo ufw allow 7946/tcp
sudo ufw allow 7946/udp
sudo ufw allow 4789/udp

# 2. 检查管理节点IP
docker swarm init --advertise-addr <correct_ip>

# 3. 重新生成令牌
docker swarm join-token worker

# 4. 清理旧配置
rm -rf /var/lib/docker/swarm
docker swarm leave --force
```

### 问题4: VPN 无法连接

**症状**: VPN启动失败或无法访问外网

**排查步骤**:

```bash
# 1. 检查服务状态
systemctl status mihomo

# 2. 查看日志
journalctl -u mihomo -f

# 3. 测试配置
mihomo -t -f /etc/mihomo/config.yaml

# 4. 检查端口占用
netstat -tlnp | grep 7890

# 5. 重启服务
make vpn-restart
```

### 问题5: 跨主机通信延迟高

**症状**: 跨服务器访问慢

**优化方案**:

```bash
# 1. 调整 MTU
INFRA_NETWORK_MTU=1450 make network-reset

# 2. 禁用加密 (内网环境)
# 编辑 docker-compose.yml
networks:
  infra-network:
    driver: overlay
    driver_opts:
      encrypted: "false"  # 禁用加密

# 3. 检查物理网络
ping <target_ip>
traceroute <target_ip>
```

## 安全配置

### 防火墙规则

#### ServerA (管理节点)

```bash
# 基础端口
sudo ufw allow 22/tcp                    # SSH
sudo ufw allow 80/tcp                    # HTTP
sudo ufw allow 443/tcp                   # HTTPS

# Swarm 端口
sudo ufw allow 2377/tcp                  # Swarm 管理
sudo ufw allow 7946/tcp                  # 节点通信
sudo ufw allow 7946/udp
sudo ufw allow 4789/udp                  # VXLAN

# 限制数据库访问
sudo ufw allow from <trusted_ip> to any port 3306   # MySQL
sudo ufw allow from <trusted_ip> to any port 6379   # Redis
sudo ufw allow from <trusted_ip> to any port 27017  # MongoDB

# 启用防火墙
sudo ufw enable
```

#### ServerB (工作节点)

```bash
# 基础端口
sudo ufw allow 22/tcp                    # SSH

# Swarm 端口
sudo ufw allow 7946/tcp                  # 节点通信
sudo ufw allow 7946/udp
sudo ufw allow 4789/udp                  # VXLAN

# NSQ 端口 (仅限内网)
# 不对外开放,只通过 Overlay 网络访问

# 启用防火墙
sudo ufw enable
```

### 网络加密

#### 启用 Overlay 加密

```bash
# 创建加密网络
docker network create \
  --driver overlay \
  --opt encrypted=true \
  infra-network
```

**注意**: 加密会增加5-10%的CPU开销

### SSH 安全加固

```bash
# 编辑 SSH 配置
sudo vim /etc/ssh/sshd_config

# 推荐配置
Port 2222                              # 更改默认端口
PermitRootLogin no                     # 禁止root登录
PasswordAuthentication no              # 禁用密码登录
PubkeyAuthentication yes               # 启用密钥认证
AllowUsers deploy                      # 只允许特定用户

# 重启 SSH
sudo systemctl restart sshd
```

## 网络优化

### MTU 优化

```bash
# 测试最佳 MTU
ping -M do -s 1472 <target_ip>

# 调整 MTU
INFRA_NETWORK_MTU=1450 make network-init
```

### 连接池配置

在应用中配置合理的数据库连接池:

```python
# Python 示例
SQLALCHEMY_POOL_SIZE = 10
SQLALCHEMY_POOL_RECYCLE = 3600
SQLALCHEMY_MAX_OVERFLOW = 20
```

### DNS 缓存

```bash
# 在应用容器中配置 DNS 缓存
dns:
  - 8.8.8.8
  - 114.114.114.114
dns_options:
  - "ndots:2"
  - "timeout:2"
  - "attempts:3"
```

## 监控和告警

### 网络监控指标

关键指标:

```yaml
网络延迟: ping time < 5ms
丢包率: packet loss < 0.1%
带宽使用: bandwidth usage < 80%
连接数: active connections
错误率: network errors < 1%
```

### 监控命令

```bash
# 实时监控
make network-monitor

# 查看统计
docker stats --no-stream

# 检查连接
netstat -antp | grep ESTABLISHED

# 查看网络接口
ifconfig
ip addr show
```

## 备份和恢复

### 网络配置备份

```bash
# 导出网络配置
docker network inspect infra-network > network-backup.json

# 导出 Swarm 配置
docker swarm ca > swarm-ca-backup.pem
```

### 恢复步骤

```bash
# 1. 重建网络
docker network create \
  --driver overlay \
  --subnet 172.20.0.0/16 \
  --gateway 172.20.0.1 \
  infra-network

# 2. 重新初始化 Swarm
docker swarm init --advertise-addr <ip>

# 3. 重新部署服务
make up
```

## 扩展阅读

### 相关文档

- [网络架构](./architecture.md) - 详细网络架构设计
- [Swarm部署指南](./swarm.md) - Docker Swarm集群部署
- [服务器架构](../server/architecture.md) - 服务器分布架构

### 官方文档

- [Docker网络](https://docs.docker.com/network/)
- [Docker Swarm](https://docs.docker.com/engine/swarm/)
- [Overlay网络](https://docs.docker.com/network/overlay/)

---

**更新时间**: 2025-01-24  
**文档版本**: v1.0
