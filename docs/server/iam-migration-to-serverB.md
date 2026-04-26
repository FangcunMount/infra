# IAM 迁移到 serverB 指导手册

## 目的

这份手册解决一件事：

把 `IAM` 从旧落点迁移到 `serverB`，同时保持：

- 公网入口仍由 `serverA/nginx` 统一承接
- 公网 HTTPS 证书仍只放在 `serverA`
- `IAM` 与 `qs-collection-server` 同机，`NSQ` 在 `serverD`
- 如果启用 `gRPC mTLS`，明确哪些证书需要迁、哪些不需要迁

## 当前目标拓扑

- `serverA 2C2G`：`nginx + qs-apiserver`
- `serverB 2C2G`：`qs-collection-server + IAM`
- `serverC 4C4G`：`mongodb`
- `serverD 2C4G`：`qs-worker + operating + nsq`

四台机器共同加入 `infra-network`，`serverA` 仍是唯一公网入口。

## 核心结论

### 1. 公网 SSL 证书不跟着 IAM 迁移

原因：

- `nginx` 在 `serverA` 上监听 `80/443`，[components/nginx/docker-compose.yml](/Users/yangshujie/workspace/infra/components/nginx/docker-compose.yml:4)
- `nginx` 直接挂载 `serverA` 宿主机的 `/data/ssl`，[components/nginx/docker-compose.yml](/Users/yangshujie/workspace/infra/components/nginx/docker-compose.yml:14)
- 应用 Nginx 配置模板也是在 `serverA/nginx` 上加载 `/data/ssl/certs/*` 与 `/data/ssl/private/*`，[scripts/03-nginx/nginx-app-manager.sh](/Users/yangshujie/workspace/infra/scripts/03-nginx/nginx-app-manager.sh:59)

所以迁移后链路应保持为：

`客户端 -> serverA/nginx (HTTPS) -> serverB/IAM (HTTP or internal gRPC over infra-network)`

### 2. 如果 IAM 启用了 gRPC mTLS，相关证书要迁到 serverB

这和公网 HTTPS 证书是两套东西。

参考现有 mTLS 约定：[docs/grpc-mtls.md](/Users/yangshujie/workspace/infra/docs/grpc-mtls.md:1)

对 `IAM` 来说：

- 如果 `IAM` 是 gRPC 服务端，`serverB` 需要持有：
  - 服务端证书
  - 服务端私钥
  - CA 链
- 如果 `qs` 或其他服务调用 `IAM` gRPC，它们各自所在节点还需要持有：
  - 客户端证书
  - 客户端私钥
  - CA 链

## 迁移边界

### infra 仓库负责

- `infra-network` 已经支持四节点跨云 overlay
- `serverA` 上的 `nginx`
- Nginx 应用路由配置
- gRPC mTLS 证书脚本与分发口径

### IAM 业务仓库负责

- `IAM` 容器部署位置切到 `serverB`
- IAM 自身资源配额
- IAM 的 MySQL / Redis / Mongo / gRPC 依赖配置
- IAM 的健康检查与回滚

## 迁移前检查

### A. 基础网络

确认：

- `serverA/serverB/serverC/serverD` 都已加入 Swarm
- `infra-network` 已存在
- `serverA` 和 `serverB` 上容器都能加入 `infra-network`

建议检查：

```bash
docker node ls
docker network inspect infra-network
```

### B. 公网入口

确认：

- `serverA` 上 `nginx` 正常运行
- `iam.fangcunmount.cn` 仍然解析到 `serverA`
- `serverA` 宿主机 `/data/ssl` 中证书有效

### C. IAM 依赖

确认 IAM 在 `serverB` 上可访问：

- 云 MySQL
- 云 Redis
- `mongo:27017`（如果 IAM 业务依赖 Mongo）
- `nsqlookupd:4161` / `nsqd:4150`（如果 IAM 依赖 NSQ）

## 推荐迁移步骤

### 第一步：先保证 IAM 能在 serverB 本机启动

不要先改公网流量。

先在 `IAM` 业务仓库里完成：

- 部署目标机器切换到 `serverB`
- 容器接入 `infra-network`
- 环境变量切到新的依赖地址

推荐最少核对：

- `MYSQL_HOST` 指向云 MySQL
- `REDIS_HOST` 指向云 Redis
- 需要 Mongo 时，`MONGO_HOST=mongo`
- 需要 NSQ 时，`NSQLOOKUPD_HOST=nsqlookupd`、`NSQD_HOST=nsqd`

### 第二步：确认 serverA 的 nginx 可以通过 overlay 找到 IAM

`nginx-app-manager` 生成的 upstream 默认是：

```nginx
upstream iam_backend {
    server iam:8080;
}
```

参考：[scripts/03-nginx/nginx-app-manager.sh](/Users/yangshujie/workspace/infra/scripts/03-nginx/nginx-app-manager.sh:55)

所以这里有一个关键前提：

- `IAM` 在 Docker 网络里的可解析名字必须是 `iam`

如果你实际容器名/服务名不是 `iam`，有两种做法：

1. 让 IAM 容器在 `infra-network` 里暴露成 `iam`
2. 不用自动模板，改成手写 Nginx 配置，upstream 指向真实容器名

### 第三步：在 serverA 上部署 IAM 的 Nginx 路由

如果 IAM 的 overlay 名称就是 `iam`，可以直接：

```bash
make app-deploy APP=iam DOMAIN=iam.fangcunmount.cn PORT=8080 SSL=yes
make nginx-test
make nginx-reload
```

参考：[components/nginx/conf.d/README.md](/Users/yangshujie/workspace/infra/components/nginx/conf.d/README.md:16)

这一步只会改：

- `serverA` 上 `/data/apps/nginx-configs`
- `serverA` 上 `nginx` 的路由

不会改证书位置。证书仍在 `serverA:/data/ssl`。

### 第四步：验证 Forwarded Headers 口径

当前模板会传：

- `Host`
- `X-Real-IP`
- `X-Forwarded-For`
- `X-Forwarded-Proto`

参考：[scripts/03-nginx/nginx-app-manager.sh](/Users/yangshujie/workspace/infra/scripts/03-nginx/nginx-app-manager.sh:66)

所以 IAM 迁移后要确认：

- 是否信任 `X-Forwarded-Proto=https`
- 是否按 `Host` 生成外链 / 回调地址
- Cookie 的 `Secure` / `SameSite` 行为是否仍正确

如果 IAM 自己会生成登录跳转地址、回调地址、邮件链接，这一步必须做回归。

### 第五步：切流前做内网验证

建议先在 `serverA` 上验证：

```bash
docker exec nginx wget -qO- http://iam:8080/health
```

如果 IAM 不是这个健康路径，就换成实际健康接口。

通过后再从外部验证：

```bash
curl -I https://iam.fangcunmount.cn
```

### 第六步：切流后做业务回归

至少回归：

- 登录
- 刷新 token
- 登出
- 用户资料读写
- 依赖 IAM 的业务系统回调
- 如果开启 gRPC，回归一次调用链

## gRPC mTLS 迁移口径

## 不启用 gRPC mTLS

如果当前 IAM 只有 HTTP / gRPC 明文内网流量：

- 不需要迁任何 mTLS 证书
- 只需要确保 `serverA -> serverB/IAM` 的网络可达

## 启用 gRPC mTLS

如果 IAM 在 `serverB` 上承载 gRPC 服务端：

### serverB 必须具备

- `/data/infra/ssl/grpc/server/iam-apiserver.crt`
- `/data/infra/ssl/grpc/server/iam-apiserver.key`
- `/data/infra/ssl/grpc/ca/ca-chain.crt`

参考示例：[docs/grpc-mtls.md](/Users/yangshujie/workspace/infra/docs/grpc-mtls.md:106)

### IAM 的调用方必须具备

例如 `qs` 调 `IAM`：

- 客户端证书
- 客户端私钥
- CA 链

参考示例：[docs/grpc-mtls.md](/Users/yangshujie/workspace/infra/docs/grpc-mtls.md:125)

### 推荐做法

1. 先在一台管理机生成证书：

```bash
make grpc-ca
make grpc-server NAME=iam-apiserver OU=IAM ALT_DNS=iam-apiserver.internal.example.com
```

2. 把服务端证书分发到 `serverB`
3. 把客户端证书分发到实际调用 IAM 的节点
4. 修改 IAM 和调用方的挂载路径
5. 再开启 mTLS 强校验

注意：

- `serverA` 不因为公网 HTTPS 而需要持有这套 `iam-apiserver` 服务端私钥
- `serverA` 只有在它本机服务要“作为 gRPC 客户端调用 IAM”时，才需要对应客户端证书

## 回滚方案

如果迁移后出问题，回滚顺序建议：

1. 保留 `serverB` 上的新 IAM 实例不删
2. 把 `serverA/nginx` upstream 指回旧 IAM 落点
3. `nginx-test` + `nginx-reload`
4. 外部验证恢复
5. 再排查 `serverB` 上的新实例问题

不要在第一时间删掉新实例或删除证书，先恢复入口流量最重要。

## 最终检查清单

- `IAM` 已部署在 `serverB`
- `IAM` 已接入 `infra-network`
- `serverA/nginx` 能解析并访问 `iam:8080`
- `iam.fangcunmount.cn` 仍解析到 `serverA`
- 公网证书仍只在 `serverA:/data/ssl`
- 如果启用 gRPC mTLS：
  - `serverB` 有 `IAM` 服务端证书
  - 调用方节点有客户端证书
  - CA 链已同步
- 登录、回调、Cookie、gRPC 调用都已回归

## 相关文档

- [服务器架构设计](./architecture.md)
- [网络架构](../network/architecture.md)
- [gRPC mTLS 证书管理指引](../grpc-mtls.md)
- [SSL 通配符证书申请指南](./ssl-guide.md)
