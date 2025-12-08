# gRPC mTLS 证书管理指引

场景：gRPC 服务需要 mTLS，现有脚本在应用代码中生成 CA 和服务端/客户端证书。建议把生成器放到 infra，证书落到统一的数据目录，但不把任何私钥提交到 Git。

## 基本原则

- 仅版本化脚本与说明；任何 `.key/.crt/.pem` 仍被 `.gitignore` 屏蔽。
- 默认输出目录：`CERT_DIR=${INFRA_DATA_ROOT:-/data/infra}/ssl/grpc`，与现有数据根保持一致，可通过环境变量覆盖。
- 开发/测试可使用自签 CA；生产请使用内网 PKI 或云 KMS/HSM 颁发的证书，并通过密钥管理/配置中心分发。

## 目录与生成

- 生成脚本：`scripts/04-ssl/grpc-mtls.sh`
- 生成结果（默认）：
  - `.../ssl/grpc/ca/{root-ca.*,intermediate-ca.*,ca-chain.crt}`
  - `.../ssl/grpc/server/{iam-grpc.key,iam-grpc.crt,iam-grpc-fullchain.crt}`
  - `.../ssl/grpc/clients/*.key|*.crt`

### 常用命令（开发/测试）

#### 方式一：使用 Make 命令（推荐）

```bash
# 1. 生成 CA 证书（Root CA + Intermediate CA）
make grpc-ca

# 2. 为服务生成证书（需要先有 CA）
make grpc-server NAME=iam-grpc                                    # 使用默认 OU
make grpc-server NAME=user-api OU=User                            # 指定 OU
make grpc-server NAME=order-api OU=Order ALT_DNS=order.internal.example.com  # 完整参数

# 3. 一键生成所有证书（CA + 默认服务端 + 客户端）
make grpc-generate-all

# 4. 验证证书
make grpc-verify

# 5. 查看证书信息
make grpc-info

# 6. 清理证书
make grpc-clean
```

#### 方式二：直接使用脚本

```bash
# 分步生成
bash scripts/04-ssl/grpc-mtls.sh generate-ca
bash scripts/04-ssl/grpc-mtls.sh generate-server iam-grpc IAM iam-grpc.internal.example.com

# 一键生成所有
bash scripts/04-ssl/grpc-mtls.sh generate

# 强制重新生成
bash scripts/04-ssl/grpc-mtls.sh force

# 验证/查看/清理
bash scripts/04-ssl/grpc-mtls.sh verify
bash scripts/04-ssl/grpc-mtls.sh info
bash scripts/04-ssl/grpc-mtls.sh clean

# 更换输出目录
CERT_DIR=/data/ssl/iam-contracts/grpc bash scripts/04-ssl/grpc-mtls.sh generate
```

## 使用场景示例

### 场景一：初始化基础设施

```bash
# 1. 生成 CA（只需执行一次）
make grpc-ca

# 2. 为各个服务生成证书
make grpc-server NAME=iam-grpc OU=IAM ALT_DNS=iam-grpc.internal.example.com
make grpc-server NAME=user-api OU=User ALT_DNS=user-api.internal.example.com
make grpc-server NAME=order-api OU=Order

# 3. 验证证书
make grpc-verify
```

### 场景二：快速开发测试

```bash
# 一键生成所有证书（包括默认的 iam-grpc、qs、admin、ops）
make grpc-generate-all

# 查看生成的证书信息
make grpc-info
```

### 场景三：添加新服务

```bash
# 为新服务生成证书（前提：CA 已存在）
make grpc-server NAME=payment-api OU=Payment ALT_DNS=payment-api.internal.example.com

# 验证新证书
make grpc-verify
```

## Docker Compose 挂载示例

### 服务端配置（iam-grpc）

```yaml
services:
  iam-grpc:
    image: your-grpc-image
    volumes:
      # 服务端证书（带完整链）
      - /data/infra/ssl/grpc/server/iam-grpc-fullchain.crt:/certs/server.crt:ro
      - /data/infra/ssl/grpc/server/iam-grpc.key:/certs/server.key:ro
      # CA 证书链（用于验证客户端）
      - /data/infra/ssl/grpc/ca/ca-chain.crt:/certs/ca-chain.crt:ro
    environment:
      - GRPC_SSL_CERT_FILE=/certs/server.crt
      - GRPC_SSL_KEY_FILE=/certs/server.key
      - GRPC_SSL_CA_FILE=/certs/ca-chain.crt
      - GRPC_SSL_REQUIRE_CLIENT_CERT=true  # 启用 mTLS
```

### 客户端配置（qs 调用 iam-grpc）

```yaml
services:
  qs-api:
    image: your-qs-image
    volumes:
      # 客户端证书
      - /data/infra/ssl/grpc/clients/qs.crt:/certs/client.crt:ro
      - /data/infra/ssl/grpc/clients/qs.key:/certs/client.key:ro
      # CA 证书链（用于验证服务端）
      - /data/infra/ssl/grpc/ca/ca-chain.crt:/certs/ca-chain.crt:ro
    environment:
      - GRPC_CLIENT_CERT_FILE=/certs/client.crt
      - GRPC_CLIENT_KEY_FILE=/certs/client.key
      - GRPC_CLIENT_CA_FILE=/certs/ca-chain.crt
      - IAM_GRPC_ENDPOINT=iam-grpc:50051
```

## 证书管理

### 证书有效期

- **Root CA**: 10 年（3650 天）
- **Intermediate CA**: 5 年（1825 天）
- **服务端/客户端证书**: 1 年（365 天）

### 证书续期

```bash
# 服务端证书到期续期（保留 CA）
make grpc-server NAME=iam-grpc OU=IAM ALT_DNS=iam-grpc.internal.example.com

# CA 到期需要重新生成所有证书
make grpc-clean
make grpc-generate-all
```

### 查看证书到期时间

```bash
# 查看所有证书信息（包括有效期）
make grpc-info

# 或使用 openssl 命令
openssl x509 -in /data/infra/ssl/grpc/server/iam-grpc.crt -noout -dates
```

## 生产环境建议

### 安全最佳实践

- ✅ **不提交私钥**：任何 `.key` 文件应被 `.gitignore` 屏蔽
- ✅ **限制权限**：`chmod 600` 私钥文件，`chmod 644` 证书文件
- ✅ **定期轮换**：建议每 3-6 个月轮换服务端/客户端证书
- ✅ **备份 CA**：Root CA 和 Intermediate CA 私钥需要安全备份
- ⚠️ **仅内网使用**：自签名证书不适用于公网服务

### 证书分发策略

#### 开发/测试环境

```bash
# 直接在服务器上生成
make grpc-ca
make grpc-server NAME=iam-grpc
```

#### 生产环境

**方案一：集中式管理**

- 在一台管理机上生成所有证书
- 通过 Ansible/SCP 安全分发到各服务器
- 私钥仅分发给需要的服务

**方案二：密钥管理服务**

- 结合 HashiCorp Vault、云 KMS/HSM 或证书管理服务
- 通过配置中心或密钥注入方式动态下发
- 自动化续期和分发流程

**方案三：服务网格**

- 使用 Istio、Linkerd 等服务网格自动管理 mTLS
- 证书由控制平面统一颁发和轮换

### 与现有 SSL 证书的区别

| 特性 | `ssl-manager.sh` (Let's Encrypt) | `grpc-mtls.sh` (自签名) |
|------|----------------------------------|------------------------|
| 用途 | 公网 HTTPS (Nginx/API Gateway) | 内网 gRPC mTLS |
| 签发方式 | 公共 CA 申请 | 自签名 CA |
| 信任链 | 浏览器默认信任 | 仅内部信任 |
| 验证方式 | 单向（服务端） | 双向（mTLS） |
| 续期方式 | 自动（Let's Encrypt） | 手动或脚本 |
| 成本 | 免费但有限制 | 完全免费 |

### 监控与告警

建议在监控系统中添加证书到期告警：

```bash
# 检查证书距离到期的天数
openssl x509 -in /data/infra/ssl/grpc/server/iam-grpc.crt -noout -checkend $((30*86400))
```

提前 30 天告警，预留充足的续期时间。
