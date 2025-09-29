# 服务器组件 - 网关(Nginx)

> 🌐 部署 Nginx 反向代理网关和 SSL 终端

## 🎯 网关服务目标

- 部署 Nginx 高性能 Web 服务器
- 配置反向代理和负载均衡
- 设置 SSL/TLS 证书和 HTTPS
- 建立安全头和访问控制
- 配置日志记录和监控

## 🌐 网关架构设计

### 网关功能架构

```
🌍 Internet
    │
┌───▼────────────────────────────────────────┐
│            Nginx 网关层                    │
│  ┌─────────────────────────────────────────┐│
│  │         SSL 终端 (443)                 ││
│  │    • SSL 证书管理                      ││
│  │    • HTTP/2, HTTP/3 支持               ││
│  │    • 安全头设置                        ││
│  └─────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────┐│
│  │       反向代理 (80, 443)               ││
│  │    • 负载均衡                          ││
│  │    • 健康检查                          ││  
│  │    • 故障转移                          ││
│  └─────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────┐│
│  │         静态资源 (80)                  ││
│  │    • 静态文件服务                      ││
│  │    • 缓存控制                          ││
│  │    • 压缩优化                          ││
│  └─────────────────────────────────────────┘│
└────────────────────────────────────────────┘
    │
┌───▼────────────────────────────────────────┐
│          后端服务                          │
│  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Jenkins   │  │      业务应用       │  │
│  │   (8080)    │  │   (8001, 8002...)   │  │
│  └─────────────┘  └─────────────────────┘  │
└────────────────────────────────────────────┘
```

## 🚀 自动化部署

### 一键 Nginx 部署

```bash
# 使用 compose-manager 脚本部署网关服务
./scripts/deploy/compose-manager.sh infra up nginx

# 自动完成：
# ✅ 部署 Nginx 高性能配置
# ✅ 配置反向代理规则
# ✅ 设置 SSL 证书
# ✅ 应用安全配置
# ✅ 启用访问日志
```

## 🔧 手动配置步骤

### 步骤 1: 创建 Nginx 配置

```bash
# 创建 Nginx 配置目录结构
sudo mkdir -p /opt/infra/nginx/{conf,ssl,logs,html}
sudo chown -R 101:101 /opt/infra/nginx

# 主配置文件
sudo tee /opt/infra/nginx/conf/nginx.conf << 'EOF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log notice;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # 日志格式
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    # 性能优化
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    server_tokens off;

    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1000;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript 
               application/json application/javascript application/xml+rss 
               application/atom+xml image/svg+xml;

    # 安全头
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # 包含站点配置
    include /etc/nginx/conf.d/*.conf;
}
EOF

# 默认站点配置
sudo tee /opt/infra/nginx/conf/conf.d/default.conf << 'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    
    # 重定向到 HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2 default_server;
    listen [::]:443 ssl http2 default_server;
    server_name _;
    
    # SSL 配置
    ssl_certificate /etc/nginx/ssl/nginx-selfsigned.crt;
    ssl_certificate_key /etc/nginx/ssl/nginx-selfsigned.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    root /usr/share/nginx/html;
    index index.html index.htm;
    
    location / {
        try_files $uri $uri/ =404;
    }
    
    error_page 404 /404.html;
    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
    }
}
EOF

# Jenkins 代理配置
sudo tee /opt/infra/nginx/conf/conf.d/jenkins.conf << 'EOF'
upstream jenkins {
    server jenkins:8080 fail_timeout=0;
}

server {
    listen 443 ssl http2;
    server_name jenkins.your-domain.com;
    
    # SSL 配置
    ssl_certificate /etc/nginx/ssl/nginx-selfsigned.crt;
    ssl_certificate_key /etc/nginx/ssl/nginx-selfsigned.key;
    
    location / {
        proxy_pass http://jenkins;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Jenkins 特殊配置
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_set_header Connection "";
    }
}
EOF
```

### 步骤 2: 生成 SSL 证书

```bash
# 生成自签名证书（开发环境）
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /opt/infra/nginx/ssl/nginx-selfsigned.key \
    -out /opt/infra/nginx/ssl/nginx-selfsigned.crt \
    -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

# 设置证书权限
sudo chmod 600 /opt/infra/nginx/ssl/nginx-selfsigned.key
sudo chmod 644 /opt/infra/nginx/ssl/nginx-selfsigned.crt
```

### 步骤 3: 启动 Nginx 服务

```bash
# 启动 Nginx 容器
docker run -d \
  --name nginx \
  --network infra-frontend \
  --restart unless-stopped \
  -p 80:80 \
  -p 443:443 \
  -v /opt/infra/nginx/conf/nginx.conf:/etc/nginx/nginx.conf:ro \
  -v /opt/infra/nginx/conf/conf.d:/etc/nginx/conf.d:ro \
  -v /opt/infra/nginx/ssl:/etc/nginx/ssl:ro \
  -v /opt/infra/nginx/html:/usr/share/nginx/html:ro \
  -v /opt/infra/nginx/logs:/var/log/nginx \
  --health-cmd="curl -f http://localhost:80/ || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  nginx:alpine

# 连接到后端网络（访问 Jenkins）
docker network connect infra-backend nginx
```

## 📋 验证检查清单

### ✅ Nginx 服务验证

```bash
# 检查 Nginx 运行状态
curl -I http://localhost/ | grep -q "301" && echo "✅ HTTP 重定向正常" || echo "❌ HTTP 重定向失败"
curl -Ik https://localhost/ | grep -q "200 OK" && echo "✅ HTTPS 服务正常" || echo "❌ HTTPS 服务失败"

# 测试配置语法
docker exec nginx nginx -t && echo "✅ Nginx 配置语法正确" || echo "❌ Nginx 配置语法错误"

# 检查反向代理
curl -Ik https://localhost/jenkins/ | grep -q "Jenkins" && echo "✅ Jenkins 代理正常" || echo "❌ Jenkins 代理失败"
```

### ✅ SSL 证书验证

```bash
# 检查 SSL 证书
echo | openssl s_client -servername localhost -connect localhost:443 2>/dev/null | openssl x509 -noout -dates

# 测试 SSL 安全等级
curl -Ik https://localhost/ | grep -q "Strict-Transport-Security" && echo "✅ HSTS 头设置正确" || echo "❌ HSTS 头缺失"
```

## 🛡️ 安全配置优化

### 高级安全配置

```bash
# 创建高级安全配置
sudo tee -a /opt/infra/nginx/conf/conf.d/security.conf << 'EOF'
# 限制请求大小
client_max_body_size 10M;

# 防 DDoS
limit_req_zone $binary_remote_addr zone=login:10m rate=1r/s;
limit_conn_zone $binary_remote_addr zone=conn_limit_per_ip:10m;

# 隐藏 Nginx 版本
server_tokens off;

# 防止点击劫持
add_header X-Frame-Options "SAMEORIGIN" always;

# 内容类型嗅探保护
add_header X-Content-Type-Options "nosniff" always;

# XSS 保护
add_header X-XSS-Protection "1; mode=block" always;

# HSTS
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

# CSP 策略
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'" always;
EOF
```

## 🔍 监控和日志

### 日志分析脚本

```bash
# 创建访问日志分析脚本
sudo tee /usr/local/bin/nginx-log-analyzer << 'EOF'
#!/bin/bash
LOG_FILE="/opt/infra/nginx/logs/access.log"

echo "=== Nginx 访问统计 $(date) ==="

# 访问量统计
echo "总访问量: $(wc -l < $LOG_FILE)"

# IP 访问排行
echo "Top 10 访问 IP:"
awk '{print $1}' $LOG_FILE | sort | uniq -c | sort -nr | head -10

# 状态码统计
echo "HTTP 状态码分布:"
awk '{print $9}' $LOG_FILE | sort | uniq -c | sort -nr

# 访问路径排行
echo "Top 10 访问路径:"
awk '{print $7}' $LOG_FILE | sort | uniq -c | sort -nr | head -10

echo "=========================="
EOF

sudo chmod +x /usr/local/bin/nginx-log-analyzer
```

## 🔄 完成部署

恭喜！您已完成所有基础设施组件的部署：

✅ **网络&基础卷** - Docker 网络和数据持久化  
✅ **存储服务** - MySQL/Redis/MongoDB 数据库集群  
✅ **消息服务** - Kafka 消息队列系统  
✅ **CI/CD服务** - Jenkins 持续集成平台  
✅ **网关服务** - Nginx 反向代理和 SSL 终端  

### 🎯 最终验证

```bash
# 执行完整的基础设施验证
./scripts/deploy/compose-manager.sh infra status all
./scripts/deploy/compose-manager.sh infra test all

# 访问服务
echo "🌐 服务访问地址:"
echo "  • Nginx: https://localhost/"
echo "  • Jenkins: https://localhost/jenkins/"
echo "  • Kafka UI: http://localhost:8081 (开发环境)"
```

---

> 💡 **Nginx 运维提醒**: 定期更新 SSL 证书、监控访问日志、优化缓存策略、保持安全配置更新