# P. 代码分析报告：ServerA 账户与 CI/CD 权限维护

2026-10-30 已修复材料验证的 sudoers 缺口：`deploy` 现在可免密执行
`iam`、`qs-api`、`ai` 三项 `m4-readable-20261028-v1` 验证。
新增规则只包含三个固定命令；原有账户、密码、SSH 和其他 sudoers 文件保持原样。
现场复验见 [脱敏证据](evidence/servera-access-20261030.json)。
原 CI 的三个 `verified=false / command_not_permitted` 已在
[只读复验 run 41045469900](https://github.com/FangcunMount/qs-server/actions/runs/41045469900)
的 SVRA 产物中全部变为 `verified=true`，角色、revision 和回执摘要与现场复验一致。
本次未发布业务服务或执行数据库变更。

同日后续完成 [QS MQ 离线预检授权修复](serverA-qs-mq-preflight-access.md)：
新增固定发布 `3b8a931…` 的独立窄规则，兼容当前无 `-I` 调用。
该次只校验 sudo 匹配，未执行 MQ 工具；发布工作流保持暂停。

## 分析目标与范围

维护腾讯云新 ServerA 的人工管理、CI/CD、运行时身份，以及材料验证授权。
范围包括账户和组、sudoers、固定材料工具、仓库初始化入口和实际 CI 调用。
本页的账户信息是现场快照；后续以 `serverA-access-audit` 输出为准。

## 入口与调用路径

`qs-server Read-only release snapshot -> SVRA_USERNAME -> SSH deploy@serverA -> sudo
/usr/bin/python3 -I <digest>.py --verify-installed -> 固定角色/版本的材料回执`。

[问题 run 41044118988](https://github.com/FangcunMount/qs-server/actions/runs/41044118988)
的 snapshot job 虽然成功，但服务器 sudo 日志记录三次 `deploy : command not allowed`。
该 job 的成功断言只检查顶层 `read_only` 和 `containers`，不能证明每个材料验证成功。
本次以实际 deploy 执行结果、回执和 sudoers 拒绝检查作为授权验收。

## 当前职责与依赖

| 身份 | 现场 UID:GID | 登录与提权 | 维护方式 |
| --- | --- | --- | --- |
| root | 0:0 | 紧急管理；已设置密码 | 保留当前状态，不由本入口改密 |
| ubuntu | 1000:1001 | 当前人工 SSH 管理员，具有 sudo，云初始化提供免密授权 | 通过现有管理员通道维护 |
| deploy | 1002:2001 | `/bin/bash`，仅 deploy 组；当前已设置密码 | CI SSH 登录；sudoers 授权，不加入 sudo/docker 组 |
| www | 2000:2000 | 密码锁定、`/usr/sbin/nologin`，仅 www 组 | 宿主运行时 UID/GID；AI 容器内部身份另由其发布配置维护 |
| yangshujie | 不存在 | 新机未创建该人工账户 | 不以批量初始化隐式补建 |

`ubuntu` 还保留云镜像原有辅助组，详见证据；这些组本次未调整。
`P` 表示已设置密码，不能据此推断 SSH 是否允许密码认证。
公钥和密码内容留在服务器和 GitHub Secrets；仓库只记录非敏感身份、命令和摘要。

现有 sudoers 文件的所有权归属：

| 文件 | 职责 | 本次处理 |
| --- | --- | --- |
| `90-cloud-init-users` | 云镜像人工管理员 | 保留 |
| `deploy-cicd` | 原有 Docker、部署文件、诊断和服务操作 | 保留 |
| `fangcun-m4-material-verify` | 旧 `m4-c06-20261026-v1` 三角色验证 | 保留，供已有流程使用 |
| `fangcun-m4-api-freeze` | 既有精确 API 冻结命令 | 保留 |
| `fangcun-m4-readable-material-verify` | 当前 readable revision 三角色验证 | 新增，由本仓库维护 |

既有 Docker、chown 等授权仍具有较高系统权限；三个精确新规则的范围不代表
整个 deploy 账户已实现严格的最小权限隔离。基础白名单收紧应单独梳理实际发布调用。

## 行为 / 契约 / 不变量边界

受管文件源：[`deploy/serverA/sudoers/fangcun-m4-readable-material-verify`](../../deploy/serverA/sudoers/fangcun-m4-readable-material-verify)。
三个规则固定解释器 `/usr/bin/python3`、`-I`、工具路径、参数顺序、host、role 和 revision。
工具 SHA256 为 `36f3046ed453dfbf8beae684269c94d1a6db0abaa23de51e09d41e462c6a3d5c`。
工具须 root:root、0555、普通单链接文件，父目录须 root 所有且不可被组或其他用户写入。
sudoers 文件须 root:root、0440。

仅允许 `--verify-installed --host serverA --expect-role ROLE --expect-revision
m4-readable-20261028-v1`，ROLE 为 `iam`、`qs-api`、`ai`。不接受命令/路径通配符、
通用 Python、上传脚本、其他 revision、其他 host、额外 `--plan` 或 `--apply`。

`scripts/00-server/servera-access.py` 默认审计，只有 `--apply` 才安装规则。
它拒绝错误主机、deploy 身份/特权组漂移、www 身份漂移、工具摘要漂移、
未通过的材料校验，以及已存在但内容/元数据不符的受管规则。
安装采用 root 私有锁、临时文件、visudo 校验、不覆盖的原子发布；
整体 sudoers 或真实命令复验失败时移除本次新增文件。
它不创建账户、不改 UID/GID、不锁密码、不写 SSH 配置、不操作服务或材料。

## 测试与可观测性现状

本地新增 9 项权限边界测试，既有用户初始化 9 项测试均通过；
新规则已通过服务器 `visudo` 语法和整体验证。
现场三个角色均以 `runuser -u deploy -- sudo -n -- <精确命令>` 实际执行，
验证 `verified/read_only=true/activated=false`、身份和回执 SHA256。
另以 `sudo -n -l -- <命令>` 检查 8 类越界授权，均被拒绝；拒绝检查不执行越界命令。

首次应用只新增一个 sudoers 文件，15 个原有受保护文件内容与权限比对通过。
幂等复验包含新增文件共 16 个文件，比对通过；重复 apply 返回 `changed=false`。
9 个容器的状态、image、restart count 和规范化挂载比对通过；
首次安装窗口内无容器 create/start/stop/die/restart/destroy/update/pause/unpause 事件。
Docker 挂载列表顺序不稳定，比对时须先按挂载目标排序。

## 分析指标与判定

| 指标 | 判定 | 证据 / 标准 |
| --- | --- | --- |
| 入口路径清晰度 | 绿 | CI 源码、服务器拒绝日志和 deploy 身份相互印证 |
| 行为边界清晰度 | 绿 | 新增三个完整固定命令；8 类反向检查拒绝 |
| 测试保护 | 绿 | 语法、异常回滚、幂等和现场实际执行均覆盖 |
| 故障闭环 | 绿 | 旧 revision 规则拒绝新参数；新规则安装后实际执行通过 |
| 可观测性 | 黄 | 原 snapshot 的顶层成功断言未覆盖材料验证状态 |

## 主要风险点

通用 `make server-init-users` 会锁定 deploy 密码、调整组并覆盖 `deploy-cicd`；
模板还包含现场白名单未允许的通用 `rm *`。它是批量初始化入口，不能作为
新 A 的日常权限修复工具。`make init-user` 则只用于新增独立账户，遇到已有账户拒绝。

新 A `/opt/infra` 现场 checkout 有独立提交，本次没有 pull/reset 或替换它；
此次使用管理员 root 私有目录 `/root/infra-servera-access-20261030` 应用已审查的源码。
使用以下 Make 入口前，应确认所用 checkout 已包含本变更。

## 初步发现或假设

已确认根因是材料 revision 更新后，受限 sudoers 仍停留在旧参数。
迁移后人工账户和 deploy 密码状态也与通用初始化说明存在差异；
本次将这些现状单独登记，未将它们推断为认证故障或擅自重置。

## 下一步建议与日常操作

在目标 ServerA 上，由现有管理员从包含本变更的 infra checkout 执行：

```bash
make serverA-access-audit  # 缺失返回 1，拒绝/漂移返回 2，验证成功返回 0
make serverA-access-apply # 显式安装；重复执行不改已有规则
```

新增材料 revision 应先审查并安装固定工具和材料，再通过 PR 更新精确策略及校验常量，
验证全部正反向命令，最后复验消费者 CI。不要将 revision 放宽为通配符。
收紧已有基础部署权限、调整人工账户或登录方式，以及强化消费者 snapshot 断言，
应各自沿真实调用链另行维护。

如需撤销本次授权，仅由管理员执行以下命令，旧规则仍保留：

```bash
sudo rm -- /etc/sudoers.d/fangcun-m4-readable-material-verify
sudo visudo -c
```

撤销后 readable revision 的三个命令将重新失去授权，消费者 CI 将再次报告此缺口。
