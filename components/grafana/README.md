# Grafana 组件

本组件通过 provisioning 自动加载 QS 缓存治理看板，并依赖同网络中的 `prometheus` 数据源。

## 默认域名

- `grafana.fangcunmount.cn`

## 关键环境变量

- `GRAFANA_DOMAIN`
- `GRAFANA_ROOT_URL`
- `GRAFANA_ADMIN_USER`
- `GRAFANA_ADMIN_PASSWORD`
- `GRAFANA_MEMORY_LIMIT`
- `GRAFANA_CPUS`

## Nginx 接入

Grafana 的 Nginx 配置模板位于：

- `components/grafana/nginx/grafana.conf`

部署到运行目录示例：

```bash
bash scripts/03-nginx/nginx-app-manager.sh deploy grafana components/grafana/nginx/grafana.conf
```
