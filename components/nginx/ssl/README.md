# SSL 证书目录

## 📁 目录说明

此目录存放 SSL/TLS 证书文件，**不应将私钥文件提交到版本控制系统**。

## 🔐 证书文件命名规范

```
ssl/
├── README.md                    # 本文件  
├── example.com/                 # 按域名分目录
│   ├── fullchain.pem           # 完整证书链
│   ├── privkey.pem             # 私钥文件 (**不入库**)
│   └── cert.pem                # 证书文件
├── *.local/                     # 本地开发证书
└── wildcard/                    # 通配符证书
    ├── fullchain.pem
    └── privkey.pem
```

## 🛡️ 安全要点

1. **私钥文件权限**: `chmod 600 *.pem`
2. **目录权限**: `chmod 755 ssl/`
3. **不入库**: 所有 `.key`、`.pem` 私钥文件已在 `.gitignore` 中排除
4. **定期更新**: Let's Encrypt 证书 90 天有效期，建议 60 天更新

## 🚀 Let's Encrypt 自动化示例

```bash
# 使用 certbot 获取证书
certbot certonly --webroot \
  -w /var/www/html \
  -d example.com \
  -d www.example.com

# 复制到 nginx 目录
cp /etc/letsencrypt/live/example.com/fullchain.pem ./ssl/example.com/
cp /etc/letsencrypt/live/example.com/privkey.pem ./ssl/example.com/

# 重载 nginx 配置
docker exec nginx nginx -s reload
```

## 📋 证书续期脚本

```bash
#!/bin/bash
# renew-certs.sh

certbot renew --quiet
if [ $? -eq 0 ]; then
    cp /etc/letsencrypt/live/*/fullchain.pem ./ssl/
    cp /etc/letsencrypt/live/*/privkey.pem ./ssl/
    docker exec nginx nginx -s reload
    echo "$(date): 证书续期成功"
fi
```

## 🔧 Nginx 配置示例

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;
    
    ssl_certificate     /etc/nginx/ssl/example.com/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/example.com/privkey.pem;
    
    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    # 安全头
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;
    
    # 应用代理配置...
}
```

## ⚠️ 重要提醒

- 生产环境证书文件权限必须严格控制
- 定期检查证书过期时间: `openssl x509 -in cert.pem -noout -dates`
- 备份证书文件到安全的离线存储
- 使用 SOPS 或 Vault 等工具管理敏感配置