# 静态资源文件目录

此目录存放预下载的静态资源文件，用于内网环境部署。

## 文件列表

### 地理数据文件
- `GeoSite.dat` - 域名分流规则数据库
- `GeoIP.metadb` - IP地址地理位置数据库

### 下载方式

```bash
# 下载 GeoSite.dat
curl -L -o static/GeoSite.dat \
  "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geosite.dat"

# 下载 GeoIP.metadb
curl -L -o static/GeoIP.metadb \
  "https://github.com/MetaCubeX/meta-rules-dat/releases/download/latest/geoip.metadb"
```

### 使用说明

当这些文件存在时，`setup-network.sh` 脚本会：
1. 优先使用本地静态文件
2. 跳过网络下载步骤
3. 适用于内网和外网环境

### 文件更新

建议定期更新这些文件以获得最新的分流规则：

```bash
# 更新脚本（可以定期执行）
./scripts/update-static-files.sh
```