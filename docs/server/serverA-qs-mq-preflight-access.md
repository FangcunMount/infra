# P. 代码分析报告：ServerA QS MQ 预检授权修复

2026-10-30 已安装 `fangcun-qs-mq-preflight-3b8a931` 窄规则。
当前 CD 命令形态已通过管理员及 deploy 的 `sudo -l` 查询；14 项越界查询均被拒绝。
本轮未执行 MQ root 工具，未恢复或触发 QS CD。旧规则、16 个既有受保护文件和
9 个容器均保持原样。[现场证据](evidence/servera-qs-mq-access-20261030.json)。

## 分析目标与范围

审查并修复 QS API 固定发布 `3b8a931e2451e38602e8b26bc623bf8d37a69878`
的预检授权。范围限于管理员权限审查、sudoers 安装和只读匹配查询。
本轮不执行材料冻结、迁移、业务重投、Broker 测试、工作流恢复或发布。

## 入口与调用路径

[失败 CD](https://github.com/FangcunMount/qs-server/actions/runs/41080952961)
在 API 离线材料预检阶段失败，Collection/Worker 跳过。
`remote-deploy.sh` 当前通过 `$SUDO python3 <固定工具>` 传入新镜像、
`/tmp/qs-deploy-apiserver-<PID>/configs/apiserver.prod.yaml` 和 UID/GID 2000；
调用不含 `-I`，不能由旧参数的规则覆盖。

## 当前职责与依赖

`/etc/sudoers.d/fangcun-m4-api-freeze` 保留旧 image ID、旧配置路径及 `-I` 的回退授权。
新增规则源位于
[`deploy/serverA/sudoers/fangcun-qs-mq-preflight-3b8a931`](../../deploy/serverA/sudoers/fangcun-qs-mq-preflight-3b8a931)。
工具只依赖 Python 标准库和 Docker；获准执行后会运行无网络的离线预检容器、
冻结发布材料，因此授权查询成功不代表工具已执行或业务发布已完成。

ServerA sudo 为 `1.9.15p5`，现场 sudoers 手册确认 `>=1.9.10` 支持 POSIX 参数正则。
解释器路径固定，仅参数采用 `^...$`；唯一可变部分是 PID `[0-9]{1,7}`。
现场 `pid_max=4194304`，其余路径、参数顺序、镜像、UID/GID 均固定。

## 行为 / 契约 / 不变量边界

工具 SHA256：`ce8b2112bd2669efa14ae34880a6f6462e38d629a4a17ff9673936b70b359bb3`。
工具为 root:root、0555、非软链接，全部父目录均由 root 控制且不可被组或其他用户写入。
固定镜像标签为 `ghcr.io/fangcunmount/qs-apiserver:3b8a931e2451e38602e8b26bc623bf8d37a69878`；
现场本地 image ID 为 `sha256:821cfa3613e12d6ab39c469c45c9d959e1184a8277efb61070c9fcfc369df47d`，
revision label 与发布源码一致。这是安装时的绑定核验，镜像标签本身不具有不可变性；
后续重试仍须按既有镜像摘要验证流程核对，不能重标记或替换该标签对应内容。

本规则兼容当前无 `-I` 调用：已审查当前 sudo 的 Python 环境过滤、解释器与导入目录所有权，
并对该命令单独强制 `env_reset`、root HOME、`CWD=/`、`NOSETENV` 和 `PYTHON*` 清理。
这不会将无 `-I` 的解释器变为 Python isolated mode；环境信任边界仍依赖上述受保护目录和 sudo 配置。
不得改为通用 Python、任意工具或镜像、无界临时路径通配符。

## 测试与可观测性现状

[权限查询 run](https://github.com/FangcunMount/qs-server/actions/runs/41081630294)
的制品 12990560938 已解压审查，ZIP SHA256 与交接值一致。
查询只输出配置 UID/GID 是否为 2000 的布尔值，未暴露凭据。

新文件先经 `visudo -cf` 校验，再由 root 以忽略的点文件暂存，以不覆盖的原子链接发布，
随后通过全量 `visudo -c` 和实际 sudo 权限查询。
PID 为 `1`、`12345`、`4194304` 的当前形态均匹配；通用 Python、错误工具/镜像、
额外 `-I`、额外选项、错误 UID/GID、路径穿越和超长 PID 等 14 项均被拒绝。
所有反向检查均为列表查询，不执行被查询命令。

本地权限测试共 13 项通过，含原有安装回滚测试及新增 4 项参数/环境契约测试。
原用户初始化测试保持独立；此发布专属规则不由 `serverA-access-apply` 自动安装。

## 分析指标与判定

| 指标 | 判定与证据 |
| --- | --- |
| 入口路径 | 绿：固定发布源码、现有 sudoers、制品与现场查询相互印证 |
| 授权边界 | 绿：固定命令、锚定参数正则、14 项反向查询拒绝 |
| 环境信任 | 黄：兼容当前无 `-I` 调用，依赖受保护 Python 路径和命令级环境限制 |
| 授权故障闭环 | 绿：当前形态可以匹配，旧规则保持有效 |
| 发布验收 | 黄：尚未执行 root 工具或重新发布，留给发布维护方复核 |

## 主要风险点

不得为修复本问题重跑 `server-init-users`，也不得修改原 `fangcun-m4-api-freeze` 回退规则。
临时配置路径的正则只限制命令形态，不能证明路径存在、文件内容正确或工具业务预检一定通过。
本次没有改动 `/opt/infra` 现场 checkout，也没有更改 GitHub 变量或 secrets。

## 初步发现或假设

根因已确认：旧授权同时固定 `-I`、旧镜像和旧配置路径，与当前 CD 的三个变化均不匹配。
新增命令级环境限制后，当前调用可被窄规则覆盖，无需先更改本次固定镜像的部署源码。

## 下一步建议

发布维护方先只读复核，再自行恢复 QS 工作流并重试同一固定镜像。
本轮结束时 `cd.yml` 经 Actions API 回读仍为 `disabled_manually`。
后续若改为强制 `-I`，应先适配并验证消费者调用，再另行变更精确授权。

撤销本次授权时，管理员只删除 `/etc/sudoers.d/fangcun-qs-mq-preflight-3b8a931`
并执行 `visudo -c`；旧回退规则仍保留。管理员审查和安装记录保存在
`/root/infra-servera-qs-mq-access-20261030`，不含可在聊天或仓库公开的凭据内容。
