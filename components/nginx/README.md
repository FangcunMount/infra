# Nginx 反向代理组件

## 📋 组件概述

提供生产级别的 Nginx 反向代理服务，支持 HTTPS、负载均衡、静态文件服务和安全防护。

## 🔧 配置文件

- **nginx.conf**: 主配置文件，包含全局设置和优化参数
- **conf.d/**: 虚拟主机配置目录
  - `default.conf`: 默认站点和健康检查
  - `apps.conf`: 应用路由配置
  - `apps/`: 单独应用配置文件
- **ssl/**: SSL 证书存储目录 (私钥不入库)

## 🌐 端口配置

- **HTTP**: `${NGINX_HTTP_PORT:-80}:80`
- **HTTPS**: `${NGINX_HTTPS_PORT:-443}:443`

## 📊 关键参数

- **Worker 进程**: `auto` (自动检测 CPU 核数)
- **连接数**: `4096` per worker
- **客户端上传限制**: `20MB`
- **Gzip 压缩**: 启用，压缩级别 6
- **缓冲区**: 优化的代理缓冲设置

## 🛡️ 安全特性

- **安全头**: HSTS, X-Frame-Options, X-Content-Type-Options
- **限流**: API 10req/s, 上传 2req/s
- **连接限制**: 每 IP 20 并发连接
- **隐藏文件保护**: 拒绝访问 `.` 开头文件

## 🚀 启动与管理

```bash
# 测试配置语法
docker exec nginx nginx -t

# 重载配置 (无需重启)
docker exec nginx nginx -s reload

# 查看状态页面  
curl http://localhost/nginx_status
```

## 📋 健康检查

- **HTTP**: `GET /health` → 200 OK
- **内部状态**: `GET /nginx_status` (仅内网)
- **容器检查**: `nginx -t` 每 30 秒

## 🔄 证书管理

详见 `ssl/README.md`，支持 Let's Encrypt 自动续期和手动证书管理。

## 📈 性能调优

- **文件描述符**: 100,000 ulimit
- **Keepalive**: 75s 超时，1000 请求复用
- **缓存**: 100MB 代理缓存，10MB 键空间
- **压缩**: 多种 MIME 类型支持

## 🔧 故障排除

```bash
# 查看错误日志
docker logs nginx

# 检查配置文件语法
make nginx-test

# 查看访问日志
tail -f /data/logs/nginx/access.log

# 检查端口监听
docker exec nginx netstat -tlnp
```

## 📝 变更记录

- 2024-09-26: 重构为组件化配置，支持跨节点代理
- 2024-09-25: 添加安全头和限流配置  
- 2024-09-24: 优化 SSL/TLS 配置和性能参数