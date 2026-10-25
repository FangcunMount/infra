# M3 T35 生产NSQ退役具名执行清单

用户已豁免T34的48h等待并要求继续执行；仍保留当前运行/未决责任复核和全部数据保护。本清单落实原M3 T35及已有生产/类似操作授权，不是新一次业务provider切换，也不执行M4物理清理。

## 固定范围

- 唯一主机serverD，原Docker socket与原部署锁；精确容器nsqd、nsqlookupd、nsqadmin，均为nsqio/nsq:v1.3.0、Compose project serverd。
- 原nsqd已停机，不为了验收重新启动；只将三容器restart策略改no并停止仍运行的两个辅助服务。保留三个容器ID、镜像、挂载、配置、数据和冷备份。
- 保留`/data/infra/nsq/data`、三个`/data/infra/nsq/*.conf`及原NSQ保护副本。原冻结离线授权缓存副本继续作为历史取证，不重新投递。
- `/opt/infra/deploy/serverD/docker-compose.yml`仅新增三个NSQ服务的手动profile与restart=no；原extends/env/network不变。通用components/nsq及Mac mini开发NSQ不修改。
- `/data/infra/messaging-provider`记录rocketmq，原Makefile仅为nsq-start/nsq-recreate/serverD-up添加现有guard，保留其余字节；通用compose-manager对up/restart的nsq/all在任何基础设施副作用前执行该guard。保留旧文件、权限和摘要；原已不存在的guard脚本从合并源码安装。
- 先通过7项边界测试、实际Compose渲染/默认不启动证明、源码CI和合并，再安装源码及执行生产操作。真实Compose证明仅运行于隔离CI。

## 执行前核验

1. T33合法业务验收、原离线迁移/四owner绑定、NSQ排空与保留缓存清单、未来计划交接及首次启动屏障均有原证据。
2. 当前8应用/4owner/10 targets/公网就绪通过；Broker无未决/冲突/保护告警。只读核对当前精确witness和业务receipt，不发新模型请求。
3. 核对生产NSQ容器身份、源码原摘要、原部署锁、数据树摘要、备份副本；核对systemd/cron/rc.local中有无自动拉起NSQ的责任。
4. 在全部八个应用的真实网络namespace及serverD宿主，核对无到NSQ端口的活动已建立连接。失败则先排查责任，不删除数据或强行宣布退出。

## 执行与回读

持有原serverD部署锁，备份并按精确原摘要替换已合并受验文件；安装rocketmq marker。Docker只对三个具名容器执行update restart=no与stop，不rm/down/prune、不改业务或Broker。回读三个容器停止、restart=no、ID/镜像/挂载未变；数据树/配置摘要一致、备份仍在，NSQ端口无listener/活动连接，原其他容器ID/开始时间/重启数不变。

重新验证8实例/4owner/10 targets、协议无未决异常、公网就绪及serverD内存。生产启动guard须实际拒绝旧NSQ入口；Compose未启用手动profile时不选NSQ，通用开发组件保持原行为。记录T35回执后打勾；T36核对生产发布索引、合并及具名M4移交。自动生产CD保持暂停，不通过修改provider变量恢复历史部署模板。

失败后仅检查现状并前向修复；不得自动重启NSQ、翻转provider、补发旧事件或覆盖当前数据库。数据/历史清理、旧代码/手工安装入口的完整移除与CD重新启用另属M4/后续具名发布。
