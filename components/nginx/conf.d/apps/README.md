# 应用配置目录

此目录用于存放应用项目的 Nginx 配置文件。

## 工作原理

1. infra 项目将此目录挂载到 nginx 容器的 `/etc/nginx/conf.d/apps/`
2. 应用项目通过部署脚本将配置文件复制到此目录
3. 复制完成后重载 nginx 配置

## 使用示例

```bash
# 方法1：使用 infra 提供的管理工具（推荐，自动生成配置）
cd /path/to/infra
make app-deploy APP=iam DOMAIN=iam.fangcunmount.cn PORT=8080 SSL=yes
make app-deploy APP=qs DOMAIN=qs.fangcunmount.cn PORT=8081
make app-deploy APP=collect DOMAIN=collect.fangcunmount.cn PORT=8082
make app-deploy APP=operating DOMAIN=operating.fangcunmount.cn PORT=8083
make app-deploy APP=blog DOMAIN=blog.yangshujie.com PORT=8084 SSL=yes

# 方法2：在应用项目的部署脚本中部署现有配置文件
cp ./nginx/blog.conf /data/apps/nginx-configs/blog.conf
bash /path/to/infra/scripts/03-nginx/nginx-app-manager.sh reload
```

## 文件命名规范

- 使用应用名称作为文件名：`blog.conf`, `api.conf`, `admin.conf`
- 避免域名作为文件名，因为域名可能变化
- 一个应用一个配置文件
