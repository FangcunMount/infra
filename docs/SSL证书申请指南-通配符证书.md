# SSL 通配符证书申请指南

## 📋 概述

本指南说明如何使用阿里云 DNS API 申请 Let's Encrypt 通配符 SSL 证书，一个证书覆盖主域名和所有子域名。

## 🎯 通配符证书优势

### ✅ 覆盖范围广
```
一个证书覆盖：
✅ yangshujie.com
✅ www.yangshujie.com
✅ api.yangshujie.com
✅ admin.yangshujie.com
✅ *.yangshujie.com (所有子域名)
```

### ✅ 无需停止服务
- 使用 DNS 验证，无需占用 80/443 端口
- 申请和续期过程中 Nginx 可正常运行
- 零停机时间

### ✅ 自动续期
- Let's Encrypt 证书 90 天有效期
- 自动续期，无需手动操作
- DNS 验证方式续期也不影响服务

---

## 🚀 快速开始

### 步骤 1：配置阿里云 DNS API 凭证

#### 1.1 获取 AccessKey

1. 登录阿里云控制台：https://ram.console.aliyun.com/users
2. 创建 RAM 用户（推荐）或使用主账号
3. 授予权限：`AliyunDNSFullAccess`
4. 创建 AccessKey，记录：
   - AccessKey ID: `LTAI5t...`
   - AccessKey Secret: `xxx...`

#### 1.2 在服务器上配置凭证

**方式 1：使用交互式命令（推荐）**
```bash
make ssl-setup-aliyun
# 按提示输入 AccessKey ID 和 Secret
```

**方式 2：手动创建凭证文件**
```bash
# 创建凭证目录
mkdir -p ~/.secrets

# 创建凭证文件
cat > ~/.secrets/aliyun.ini << EOF
dns_aliyun_access_key = LTAI5t...（你的 AccessKey ID）
dns_aliyun_access_key_secret = xxx...（你的 AccessKey Secret）
EOF

# 设置安全权限
chmod 600 ~/.secrets/aliyun.ini
```

### 步骤 2：申请通配符证书

```bash
# 方式 1：使用 Makefile（推荐）
make ssl-wildcard DOMAIN=yangshujie.com EMAIL=yshujie@163.com

# 方式 2：直接使用脚本
scripts/tools/ssl-manager.sh wildcard yangshujie.com yshujie@163.com
```

### 步骤 3：验证证书

```bash
# 列出所有证书
make ssl-list

# 查看证书详情
openssl x509 -in /data/ssl/certs/yangshujie.com.crt -text -noout | grep -A2 "Subject Alternative Name"
# 应该显示: DNS:yangshujie.com, DNS:*.yangshujie.com
```

---

## 📝 完整使用说明

### 证书管理命令

#### 1. 申请通配符证书
```bash
# 申请主域名 + 通配符证书
make ssl-wildcard DOMAIN=yangshujie.com EMAIL=yshujie@163.com

# 证书覆盖范围：
# - yangshujie.com
# - *.yangshujie.com (所有子域名)
```

#### 2. 申请单域名证书
```bash
# 仅申请单个域名的证书（HTTP 验证，需要停止 Nginx）
make ssl-obtain DOMAIN=www.yangshujie.com EMAIL=yshujie@163.com
```

#### 3. 续期证书
```bash
# 续期所有证书（自动检测过期时间）
make ssl-renew

# 证书在到期前 30 天内会被续期
```

#### 4. 列出所有证书
```bash
make ssl-list

# 输出示例：
# 🔒 yangshujie.com
#    到期时间: Jan 22 12:00:00 2026 GMT
#    证书文件: /data/ssl/certs/yangshujie.com.crt
#    私钥文件: /data/ssl/private/yangshujie.com.key
```

#### 5. 删除证书
```bash
make ssl-remove DOMAIN=yangshujie.com
```

---

## 🔧 证书自动续期配置

### 设置自动续期任务

```bash
# 方式 1：使用脚本自动配置
scripts/tools/ssl-manager.sh setup-auto

# 方式 2：手动配置 crontab
# 每周一凌晨 2:00 检查并续期证书
echo "0 2 * * 1 /opt/infra/scripts/tools/ssl-manager.sh renew" | crontab -
```

### 验证自动续期配置

```bash
# 查看 crontab 任务
crontab -l | grep ssl

# 手动测试续期（dry-run）
certbot renew --dry-run
```

---

## 🌐 Nginx 配置示例

### 生成 SSL 配置模板

```bash
# 生成配置文件
scripts/tools/ssl-manager.sh config yangshujie.com > /data/apps/nginx-configs/yangshujie-ssl.conf

# 或者手动创建
cat > /data/apps/nginx-configs/yangshujie-ssl.conf << 'EOF'
server {
    listen 443 ssl http2;
    server_name yangshujie.com www.yangshujie.com;
    
    # SSL 证书配置
    ssl_certificate /data/ssl/certs/yangshujie.com.crt;
    ssl_certificate_key /data/ssl/private/yangshujie.com.key;
    
    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=31536000" always;
    
    # 应用配置
    location / {
        proxy_pass http://your-backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name yangshujie.com www.yangshujie.com;
    return 301 https://$server_name$request_uri;
}
EOF
```

### 重载 Nginx 配置

```bash
# 测试配置
docker exec nginx nginx -t

# 重载配置
docker exec nginx nginx -s reload

# 或者重启 Nginx
make restart-nginx
```

---

## 💰 费用说明

### 完全免费 ✅

| 项目 | 费用 | 说明 |
|------|------|------|
| 阿里云 DNS 解析 | **免费** | 基础版足够使用 |
| DNS API 调用 | **免费** | 20 次/秒限制（证书申请仅需 2-3 次） |
| Let's Encrypt | **免费** | 通配符证书、90 天有效期 |
| certbot 工具 | **免费** | 开源软件 |
| **总计** | **¥0** | 完全免费 |

---

## ⚠️ 注意事项

### 1. 域名必须在阿里云 DNS 解析
- 如果域名在其他服务商（如 Cloudflare、腾讯云），需要先迁移到阿里云
- 或者为该服务商安装对应的 certbot DNS 插件

### 2. AccessKey 安全
```bash
# 凭证文件权限必须是 600
chmod 600 ~/.secrets/aliyun.ini

# 建议使用 RAM 子账号，仅授予 DNS 相关权限
# 权限：AliyunDNSFullAccess
```

### 3. 证书有效期
- Let's Encrypt 证书有效期：90 天
- 建议在到期前 30 天续期
- 配置自动续期任务，避免证书过期

### 4. 续期频率限制
- 每个域名每周最多申请 50 个证书
- 正常续期不会触发限制

---

## 🔍 故障排查

### 问题 1：阿里云凭证文件不存在

**错误信息：**
```
❌ 阿里云凭证文件不存在: ~/.secrets/aliyun.ini
```

**解决方案：**
```bash
# 运行交互式配置
make ssl-setup-aliyun

# 或手动创建凭证文件（见上文）
```

### 问题 2：DNS 验证失败

**错误信息：**
```
Timeout during connect (likely firewall problem)
```

**解决方案：**
```bash
# 检查域名是否在阿里云 DNS 解析
# 检查 AccessKey 权限是否正确（AliyunDNSFullAccess）
# 等待几分钟后重试（DNS 传播需要时间）
```

### 问题 3：certbot-dns-aliyun 插件未安装

**错误信息：**
```
ModuleNotFoundError: No module named 'certbot_dns_aliyun'
```

**解决方案：**
```bash
# 安装插件
sudo pip3 install certbot-dns-aliyun

# 或使用系统包管理器
sudo yum install python3-certbot-dns-aliyun  # CentOS
sudo apt install python3-certbot-dns-aliyun  # Ubuntu
```

### 问题 4：证书续期失败

**检查日志：**
```bash
# 查看 certbot 日志
sudo tail -f /var/log/letsencrypt/letsencrypt.log

# 手动测试续期
certbot renew --dry-run
```

---

## 📚 相关资源

- **Let's Encrypt 文档**: https://letsencrypt.org/docs/
- **Certbot 文档**: https://certbot.eff.org/docs/
- **阿里云 RAM 控制台**: https://ram.console.aliyun.com/
- **阿里云 DNS 控制台**: https://dns.console.aliyun.com/

---

## 📞 获取帮助

```bash
# 查看脚本帮助
scripts/tools/ssl-manager.sh help

# 查看 Makefile 帮助
make help | grep ssl
```

---

**更新时间**: 2025-10-24
**维护者**: Infrastructure Team
