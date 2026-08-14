# 独立 K6 压测机初始化

## 结论

推荐从 Mac 上的 `infra` 仓库直接初始化临时 Linux 压测机。远端机器不需要预先 clone `infra`：

```bash
cd /Users/yangshujie/workspace/infra

make perf-runner-init-remote \
  PERF_RUNNER_HOST=root@203.0.113.10 \
  PERF_RUNNER_SSH_IDENTITY_FILE=/absolute/path/to/private-key
```

命令带上三份压测材料后，远端会具备与 `qs-server` 压测工具链匹配的 Go、Node.js、k6、系统工具、代码与结果目录；随后自动刷新两组 IAM token 并执行 `perf-preflight`。该命令会做认证与只读预检，**不会自动发起公网压测**。

## 适用边界

压测机是独立的流量发生器，不是 `serverA`～`serverD` 的第五个生产节点：

- 不安装 Docker；
- 不加入 Tailscale 或生产 Swarm；
- 不部署 MongoDB、NSQ、Prometheus 等服务；
- 只接收三份明确的压测材料，不接收数据库 DSN；短期 token 在远端生成且不会打印；
- 只通过生产公开 HTTPS 入口发起请求，通过已授权观测入口采集证据。

建议使用专用的 Linux 实例。脚本支持 `x86_64/amd64` 和 `aarch64/arm64`，以及使用 `apt`、`dnf` 或 `yum` 的发行版。低于 `4C/8GiB` 或可用磁盘低于 `10GiB` 时只告警，不中断初始化；这类机器适合 smoke，不应直接作为正式 admission 结论来源。

## 初始化内容

| 类别 | 内容 |
|---|---|
| 压测工具 | `k6 v1.5.0` |
| 构建与预检 | `Go 1.25.12`、`Node.js`、`make`、`git`、`jq`、`curl` |
| 网络诊断 | `mtr`、`dig`、`sar` |
| 结果传输 | `rsync` |
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

### 0. 日常一键同步

首次使用时创建只保存在本机的同步配置：

```bash
cp scripts/00-server/perf-runner-sync.mk.example .perf-runner-sync.mk
chmod 0600 .perf-runner-sync.mk
```

填写压测机、SSH key、qs-server 与三份压测材料的绝对路径。之后源码或 K6 工具链有更新时只需：

```bash
make perf-runner-sync
```

该入口复用下方完整初始化流程：上传本地 Git tracked 源码快照、构建 `perfctl`、执行 `perf-verify`、同步三份材料、刷新 token 并运行 `perf-preflight`。它不会自动执行 `perf-run`，因此同步成功不等于已经开始压测。`.perf-runner-sync.mk` 已被 Git 忽略，不得在其中保存 IAM 密码、token 或数据库凭据。

### 1. 从 Mac 初始化远端机器

```bash
make perf-runner-init-remote \
  PERF_RUNNER_HOST=root@39.102.210.142 \
  PERF_RUNNER_SSH_IDENTITY_FILE=~/.ssh/id_ed25519_personal \
  PERF_QS_SERVER_SOURCE_DIR=/Users/yangshujie/workspace/golang/src/github.com/fangcun-mount/qs-server \
  PERF_GO_PROXY=https://goproxy.cn,direct \
  PERF_GO_SUMDB=sum.golang.google.cn \
  PERF_RUNNER_ENV_FILE=/Users/yangshujie/workspace/golang/src/github.com/fangcun-mount/qs-server/tmp/perf/perf.env \
  PERF_RUNNER_IAM_USERS_FILE=/Users/yangshujie/workspace/golang/src/github.com/fangcun-mount/qs-server/tmp/perf/iam-users.json \
  PERF_RUNNER_CONFIG_FILE=/Users/yangshujie/workspace/golang/src/github.com/fangcun-mount/qs-server/tmp/perf/qs-perf.config.json
```

阿里云到 GitHub 和 `proxy.golang.org` 的连接不稳定时，推荐使用上面的本地源码模式和仅作用于构建命令的 Go 镜像，无需在压测机安装系统代理。源码会从 Git tracked 文件生成快照（包含 tracked 修改，排除 untracked、`.env*` 和 secrets），再通过 SSH 上传并校验 SHA256。未设置 `PERF_QS_SERVER_SOURCE_DIR` 时才会从 GitHub clone。`GOSUMDB` 仍然启用，只切换到 Google 面向中国大陆的校验镜像。

传入三份压测材料后，初始化成功才会继续同步。脚本不会打印文件内容：`perf.env` 安装到 `/opt/qs-perf/secrets/perf.env`，两个 JSON 安装到 `/opt/qs-perf/qs-server/tmp/perf/`；目录权限为 `0700`，文件权限为 `0600`。三份文件必须一起提供。同步完成后会生成 `tokens.json` 与 `apiserver-tokens.json`，并运行完整 `perf-preflight`；任何认证、配置或业务探针失败都会让初始化命令失败。

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

### 5. 刷新环境、IAM 用户和 K6 配置

token 或压测配置更新后，不必重新安装压测机：

```bash
make perf-runner-sync-config-remote \
  PERF_RUNNER_HOST=root@39.102.210.142 \
  PERF_RUNNER_SSH_IDENTITY_FILE=~/.ssh/id_ed25519_personal \
  PERF_RUNNER_ENV_FILE=/Users/yangshujie/workspace/golang/src/github.com/fangcun-mount/qs-server/tmp/perf/perf.env \
  PERF_RUNNER_IAM_USERS_FILE=/Users/yangshujie/workspace/golang/src/github.com/fangcun-mount/qs-server/tmp/perf/iam-users.json \
  PERF_RUNNER_CONFIG_FILE=/Users/yangshujie/workspace/golang/src/github.com/fangcun-mount/qs-server/tmp/perf/qs-perf.config.json
```

`perf.env` 可由 [`scripts/00-server/perf-runner.env.example`](../../scripts/00-server/perf-runner.env.example) 复制。只接受压测观测、恢复门和 IAM 非敏感调优变量；值按字面量规范化，不执行 shell 展开。共享 NSQD 应设置 `PERF_NSQ_TOPICS`，避免 `cb.failed.*` 等无关 topic 污染恢复证据。`PERF_ISOLATED_ENV=true` 只是操作者对受控窗口的声明，不能替代 `origin="other"` 增量为 0 的实际证据。

默认同步后自动刷新 token 并运行 `perf-preflight`。仅在排障时需要只写文件，可显式设置 `PERF_RUNNER_AUTO_PREPARE=false`；正式压测前仍必须重新执行默认准备流程。

同步前，本机三份文件也必须为私有权限：

```bash
chmod 0600 tmp/perf/perf.env tmp/perf/iam-users.json tmp/perf/qs-perf.config.json
```

## 初始化后的压测流程

完成初始化或单独同步后，重新登录压测机使新的 `nofile` 限制生效。此时不需要再导出变量、复制配置或手工生成 token，直接执行：

```bash
ssh root@203.0.113.10
source /etc/profile.d/qs-perf.sh
/opt/qs-perf/bin/perf-run PLAN=quick
/opt/qs-perf/bin/perf-run PLAN=baseline
```

`perf-run` 每次都会重新获取短期 token、运行一次 `perf-preflight`，再把完整运行目录写到 `/opt/qs-perf/runs`。三份材料已由同步脚本写入固定路径；不要把 token、IAM 密码或文件内容放入 shell 历史、Make 参数、Git 或初始化日志。

若只想刷新 token 和预检、不产生压力，可执行：

```bash
/opt/qs-perf/bin/perf-prepare
```

高级排障仍可使用 `/opt/qs-perf/bin/perf-with-env <command>`；它只为当前子进程加载 `/opt/qs-perf/secrets/perf.env`，不会把变量写入系统全局 profile。

不需要向压测机传递 MySQL/MongoDB/Redis DSN。它们只用于可选的深度快照，公开 Prometheus、readyz 与 NSQD 证据已经覆盖正式门禁；避免把生产数据库凭据扩大到临时压测机。

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
| `PERF_RUNNER_SYNC_CONFIG` | `.perf-runner-sync.mk` | `make perf-runner-sync` 使用的本机私有 Make 配置 |
| `PERF_GO_VERSION` | `1.25.12` | Go 固定版本 |
| `PERF_K6_VERSION` | `v1.5.0` | k6 固定版本 |
| `PERF_QS_SERVER_REF` | `main` | clone 的分支或 tag |
| `PERF_QS_SERVER_SOURCE_DIR` | 空 | Mac 上 qs-server 的绝对路径；设置后上传安全过滤的源码快照，不访问 GitHub |
| `PERF_GO_PROXY` | 空 | 可选 GOPROXY，仅注入远端 Go 构建与验证命令 |
| `PERF_GO_SUMDB` | 空 | 可选 GOSUMDB；不建议关闭模块校验 |
| `PERF_RUNNER_ENV_FILE` | 空 | 本机 `perf.env` 绝对路径；与下面两份 JSON 一起同步 |
| `PERF_RUNNER_IAM_USERS_FILE` | 空 | 本机 `iam-users.json` 绝对路径 |
| `PERF_RUNNER_CONFIG_FILE` | 空 | 本机 `qs-perf.config.json` 绝对路径 |
| `PERF_RUNNER_AUTO_PREPARE` | `true` | 同步后自动刷新 token 并运行 `perf-preflight` |
| `PERF_UPDATE_REPO` | `false` | 更新已有且干净的 checkout |
| `PERF_RUN_VERIFY` | `true` | 初始化时执行 `make perf-verify` |
| `PERF_SKIP_REPO` | `false` | 只安装系统工具，不准备代码 |
| `PERF_SKIP_NETWORK_CHECK` | `false` | 跳过公网就绪探针，不建议正式使用 |
| `PERF_DOWNLOAD_ATTEMPTS` | `5` | Go/k6 下载总尝试次数，覆盖连接中断等全部 curl 错误 |
| `PERF_DOWNLOAD_RETRY_DELAY_SECONDS` | `3` | 下载失败后的重试间隔秒数 |

## 失败处理

- Go/k6 SHA256 不匹配：立即停止，不安装下载文件；
- Go/k6 下载中断：清理不完整文件并自动重试；重复执行初始化命令会跳过已安装的正确版本；
- qs-server clone 中断：先重试 clone；只有新 checkout 校验完整后，才把原残缺目录移动到带时间戳的备份；
- 本地源码上传或 SHA256 校验失败：停止替换远端代码；原 checkout 保持不变；
- `make perf-verify` 失败：机器不视为准备完成；
- 公网就绪探针失败：先处理 DNS、TLS、安全组或出口网络，不开始压测；
- 已有 Go 版本不同：原 `/usr/local/go` 会移动到带时间戳的备份目录，不直接删除；
- 已有 `qs-server` checkout 有本地修改：保留修改，不自动覆盖。
