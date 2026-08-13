# 独立 K6 压测机初始化

## 结论

推荐从 Mac 上的 `infra` 仓库直接初始化临时 Linux 压测机。远端机器不需要预先 clone `infra`：

```bash
cd /Users/yangshujie/workspace/infra

make perf-runner-init-remote \
  PERF_RUNNER_HOST=root@203.0.113.10 \
  PERF_RUNNER_SSH_IDENTITY_FILE=/absolute/path/to/private-key
```

命令完成后，远端会具备与 `qs-server` 压测工具链匹配的 Go、k6、系统工具、代码目录和结果目录，并已经执行 `make perf-verify`。该命令只准备压测机，**不会自动发起公网压测**。

## 适用边界

压测机是独立的流量发生器，不是 `serverA`～`serverD` 的第五个生产节点：

- 不安装 Docker；
- 不加入 Tailscale 或生产 Swarm；
- 不部署 MongoDB、NSQ、Prometheus 等服务；
- 不接收或打印 token、DSN 等凭据；
- 只通过生产公开 HTTPS 入口发起请求，通过已授权观测入口采集证据。

建议使用专用的 Linux 实例。脚本支持 `x86_64/amd64` 和 `aarch64/arm64`，以及使用 `apt`、`dnf` 或 `yum` 的发行版。低于 `4C/8GiB` 或可用磁盘低于 `10GiB` 时只告警，不中断初始化；这类机器适合 smoke，不应直接作为正式 admission 结论来源。

## 初始化内容

| 类别 | 内容 |
|---|---|
| 压测工具 | `k6 v1.5.0` |
| 构建工具 | `Go 1.25.12`、`make`、`git`、`jq`、`curl` |
| 网络诊断 | `mtr`、`dig`、`sar` |
| 安全校验 | Go 官方下载元数据 SHA256、k6 release checksums |
| 系统设置 | 压测用户 `nofile=65535`，重新登录后生效 |
| 代码 | `/opt/qs-perf/qs-server` |
| 工具 | `/opt/qs-perf/bin/perfctl` |
| 结果 | `/opt/qs-perf/runs` |
| 私密文件目录 | `/opt/qs-perf/secrets`，权限 `0700` |

默认会 clone `qs-server` 的 `main` 分支，并执行：

```bash
make perf-verify
```

这只证明压测工具链在压测机上可执行，不代表 token、生产端点或正式压力门禁已经通过。

## 常用命令

### 1. 从 Mac 初始化远端机器

```bash
make perf-runner-init-remote \
  PERF_RUNNER_HOST=root@203.0.113.10 \
  PERF_RUNNER_SSH_IDENTITY_FILE=/absolute/path/to/private-key
```

如果 SSH 用户不是 root，需要该用户具备免密 `sudo`。首次连接默认使用 `StrictHostKeyChecking=accept-new`；完成云控制台指纹核对后，可强制只接受已记录的主机密钥：

```bash
make perf-runner-init-remote \
  PERF_RUNNER_HOST=ecs-user@203.0.113.10 \
  PERF_RUNNER_STRICT_HOST_KEY_CHECKING=yes
```

### 2. 在压测机本地初始化

如果 `infra` 已经位于远端机器，也可以执行：

```bash
make perf-runner-init
```

### 3. 重复校验

```bash
make perf-runner-check-remote PERF_RUNNER_HOST=root@203.0.113.10
```

校验范围包括工具版本、CPU/内存/磁盘、`qs-server` checkout、`perfctl`，以及以下默认公网就绪地址：

- `https://collect.fangcunmount.cn/readyz`
- `https://qs.fangcunmount.cn/readyz`

可按实际部署覆盖：

```bash
make perf-runner-check-remote \
  PERF_RUNNER_HOST=root@203.0.113.10 \
  PERF_READY_URLS="https://collect.example.com/readyz https://qs.example.com/readyz"
```

### 4. 固定代码分支或 tag

正式压测应使用与已部署版本相匹配的分支或 tag：

```bash
make perf-runner-init-remote \
  PERF_RUNNER_HOST=root@203.0.113.10 \
  PERF_QS_SERVER_REF=release-20260814
```

重复初始化默认保留已有 checkout。只有显式设置 `PERF_UPDATE_REPO=true` 时，脚本才会更新一个干净的 checkout；检测到未提交修改时仍会停止更新并保留现场。

## 初始化后的压测流程

先登录压测机，使新的 `nofile` 限制生效：

```bash
ssh root@203.0.113.10
source /etc/profile.d/qs-perf.sh
cd /opt/qs-perf/qs-server
make perf-init
```

然后通过安全通道写入 `tmp/perf` 所需 token/config。不要把 token 放入 shell 历史、Make 参数、Git 或初始化日志。观测 URL 和 `PERF_ISOLATED_ENV=true` 可写入 `/opt/qs-perf/secrets/perf.env`，并保持文件权限 `0600`。

凭据准备完成后依次执行：

```bash
make perf-preflight
make perf-run PLAN=quick
make perf-run PLAN=baseline
```

只有 `perf-preflight`、真实样本、阈值、流量隔离和相关服务端观测证据都成立，才能接受压测结果。初始化成功本身不等于生产压测成功。

## 结果取回与销毁

压测结束后，先把完整运行目录取回 Mac：

```bash
rsync -av \
  root@203.0.113.10:/opt/qs-perf/runs/ \
  /Users/yangshujie/workspace/golang/src/github.com/fangcun-mount/qs-server/tmp/perf/remote-runs/
```

至少确认结构化报告、原生 K6 输出、观测快照和 testee IDs 均已取回，再执行压测数据清理并释放临时云实例。`infra` 中的初始化命令不会自动删除远端结果或销毁云资源。

## 可选开关

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `PERF_WORKSPACE_ROOT` | `/opt/qs-perf` | 远端工作根目录 |
| `PERF_GO_VERSION` | `1.25.12` | Go 固定版本 |
| `PERF_K6_VERSION` | `v1.5.0` | k6 固定版本 |
| `PERF_QS_SERVER_REF` | `main` | clone 的分支或 tag |
| `PERF_UPDATE_REPO` | `false` | 更新已有且干净的 checkout |
| `PERF_RUN_VERIFY` | `true` | 初始化时执行 `make perf-verify` |
| `PERF_SKIP_REPO` | `false` | 只安装系统工具，不准备代码 |
| `PERF_SKIP_NETWORK_CHECK` | `false` | 跳过公网就绪探针，不建议正式使用 |

## 失败处理

- Go/k6 SHA256 不匹配：立即停止，不安装下载文件；
- `make perf-verify` 失败：机器不视为准备完成；
- 公网就绪探针失败：先处理 DNS、TLS、安全组或出口网络，不开始压测；
- 已有 Go 版本不同：原 `/usr/local/go` 会移动到带时间戳的备份目录，不直接删除；
- 已有 `qs-server` checkout 有本地修改：保留修改，不自动覆盖。
