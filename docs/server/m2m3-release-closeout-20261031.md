# M2/M3 发布收口（2026-10-31）

这是宿主工程退役计划的 M2/M3 发布记录；不能与此前 infra 同名阶段混用完成计数。
应用冻结镜像已经上线；**不代表 M2 全量业务观测及发布清理已验收**。

## 本轮确认

- [三节点快照](https://github.com/FangcunMount/qs-server/actions/runs/41150432808)：北京时间 08:25 左右，IAM、QS API、两份 Collection、三份 Worker、AI、后台共九个业务容器仍绑定原冻结版本。后台按 Docker healthy 检查；八个服务副本另有显式 ready 证明。
- [监控回读](https://github.com/FangcunMount/infra/actions/runs/41151331507)：北京时间 08:39，七类抓取目标全部 up；四个事务 owner 均 available/fresh=1、admission_protected=0。两个 Grafana 面板 API 200 且模型与冻结配置相符，旧 Outbox 面板 404。AI 业务 ACK 等待为真实样本 0；QS 业务观测仍不可用，缺失样本不能按 0 展示。
- [历史事实只读审计](https://github.com/FangcunMount/qs-server/actions/runs/41150741066)：57 条未退役命令中，51 条缺少原 archive/execution/witness；全部 51 条的准入回执与已存 Inbox 正文及哈希匹配（47 accepted、4 rejected）。29 条有工作流投影，23 条有终态投影及对应版本事件；22 条有评测状态。这些计数会按不同命令引用同一业务聚合，**不是互不重叠的业务完成数量**，也不能代替原事务凭证。
- 历史集合摘要：`76a5260d862fdbfb4759d56c41dbf1a58b1518ab788426eded212b1d2991d6cc`。摘要在只读进程内按命令 ID 排序并散列证据字段，不导出身份和正文。
- 清理根因：原 Worker 镜像清单包含 `仓库@sha256:…` 别名，旧解析器误判，修复选择器通过相同清单且保护全部容器镜像；IAM 的主机校验仍为旧 serverB，已修为 serverA。显式保护 ID 必须在 bootstrap 到期后继续保留。
- 四宿主统一核对 root 所有、父目录不可改写且与发布包相同的固定清理器，调用 `/usr/bin/python3 -I`。ServerA/D 尚未安装；ServerB 是不同版本。安装与生产清理仍待验。

[结构化证据](evidence/m2m3-closeout-20261031.json) 保留实际服务 SHA/digest、观测结果与证据分类。

## 历史验证

既往 M3-C 的 14 项真实 RocketMQ 重投、Broker/Worker 重启、真实 Redis 和业务幂等验收记录沿用此前结果。本轮清理控制器修复没有重跑这整套验收，没有执行生产 Broker 故障或业务重投；本轮 PR CI 的实际结果另记。

## 固定清理器的管理员安装

源码修复：IAM #172、QS #470、AI #245、后台 #79。先取得各最终提交的 CI，再安装可信副本及限定命令，最后验证实际清理；不能把本地绿或应用 healthy 当作清理通过。

1. 使用 QS 提交 `4f45c1b26edd73773a6f702a58d6efb377c4af25` 的 `scripts/cd/image-retention.py`。期望 SHA256：`53ec1f1e093aca37ad671a50d37203b87757f2daea7f78d03e96df7c51474324`。
2. 由服务器管理员审核并执行本提交的 [安装工具](../../scripts/ops/install-image-retention.sh)。先预览，再应用；`DEPLOY_ACCOUNT` 是该节点现有 Actions SSH 登录用户，不是数据库用户：

   ```bash
   bash install-image-retention.sh serverA DEPLOY_ACCOUNT ./image-retention.py
   sudo bash install-image-retention.sh serverA DEPLOY_ACCOUNT ./image-retention.py --apply
   ```

   ServerB、ServerD 分别改为 `serverB`、`serverD`。工具验证真实主机、脚本复制后的摘要、父目录和原锁 inode，验证 sudoers 语法；保留原固定脚本副本。仅添加各节点服务的固定 Python 命令，不授予 `/tmp/*`、`python -c` 或通用 Python 权限；已有不同的同名 sudoers 片段会拒绝覆盖，须管理员单独核对。安装工具默认不写入，不启动容器、不执行清理、不读写业务数据库。
3. 回读安装文件摘要、权限和精确命令授权。按当前运行 SHA 和真实兼容回退 ID 做只读 preview；检查所有容器引用和回退资产都在 keep 内。禁止使用猜测的旧镜像或单纯按构建时间挑选回退。
4. 相同主机锁下执行审核过的清理，再验证审计状态、所有容器身份/健康、当前镜像与兼容回退仍存在。候选为空时可以记录真实 0 删除，不能虚构回收空间。

## 隔离验证与未完成边界

- 四仓各 21 项清理器单测；既有锁测试；AI 70 项部署定向测试、Ruff、文档门禁。
- [真实 Docker 对照](../../scripts/ops/test_image_retention_native.py) 只使用本次打标签的隔离资产，无网络、数据库或卷。preview 不写入；apply 仅移除两条自有旧标签，保留运行/停止容器、未知仓库别名和显式回退 ID。classic 本地引擎拒绝导入 digest RepoTags 的失败保留；该格式另用实际生产只读清单复验，没有把它计入本机原生复现通过。
- [安装验证](../../scripts/ops/test_image_retention_installer_native.sh) 在三个无网络隔离主机配置中使用真实 visudo 验证预览、安装、幂等、原锁 inode、限定命令允许、通用 Python 拒绝、错误哈希和主机拒绝。复用既有 Readable production window contracts CI，不引入大型测试框架。
- 最终 PR/main CI、节点安装和实际生产清理未完成前，不能标为清理验收通过。
- 不改业务数据库，不补造 archive/witness，不删除或退役这 51 条业务历史，不重放。下一步先核对原发布备份及历史责任处置来源；若需要数据库更改，须另行给出绑定集合摘要、保留与回退方式的具体方案并取得明确授权。
- M4/M5 不在此记录的完成范围内。
