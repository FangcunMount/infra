# M3 实际运行 profile 与再次部署保护

**当前交付状态（2026-10-25）：M3按用户修订范围闭环，35项验证完成＋T34用户豁免；未宣称48h通过。NSQ生产服务已正式停用且不自动重启，自动业务CD仍暂停。实际版本/配置/验收/保留范围及后续计划见[最终发布索引](rocketmq-m3-production-release.md)。下文候选和当时“当前”状态作为有日期历史保留，以总表/最终索引为准。**

2026-10-25 T33已通过。下表是本轮实际生产配置；原140成员静态包、错误启动和被替代的配置保留为历史，不能按旧目录名推断再次部署目标。镜像、资源、并发及writer epoch维持冻结候选；自动生产CD仍暂停，恢复须经T36核验。

| 目标 | 实际目录 | 消息职责 |
| --- | --- | --- |
| serverA IAM | `/opt/fangcun-m3/releases/m3-20261025-v2/docker/acceptance` | iam.mysql、IAM授权订阅 |
| serverA API | `/opt/fangcun-m3/releases/m3-20261025-v3/servera-migrated/authz-sync` | qs.mysql/qs.mongo、IAM授权订阅 |
| serverA collection两副本 | `/opt/fangcun-m3/releases/m3-20261025-v2/qs-collection/acceptance` | 原冻结职责 |
| serverA AI | `/opt/fangcun-m3/releases/m3-20261025-v2/qs-ai/acceptance` | ai.mysql、AI订阅 |
| serverD 三worker | `/opt/fangcun-m3/releases/m3-20261025-v2/qs-worker/sealed` | 消费专用；目录名sealed不代表消费者被关闭 |

## 配置条件

- 三worker的`messaging.provider=rocketmq`、`messaging.rocketmq.publish_enabled=false`，不启动事务owner。三个消费者保持原768MiB/1CPU/并发48，不能为适配拆分Topic放大并发。旧v2 worker acceptance中publish_enabled=true被宿主正确拒绝，已被上表消费专用配置替代。
- API的`iam.authz-sync.rocketmq.instance_id=qs-apiserver-1`，派生逻辑订阅必须为`qs-authz-sync-apiserver-qs-apiserver-1`，精确对应冻结manifest中的TRANSACTION/iam.mysql物理Topic/group。旧qs-authz-sync-1实例值不再是可部署候选；不通过临时创建新group或重置offset修复。
- 四owner、数据库绑定、route revision、writer epoch和首次wire沿冻结协议；未重新加密/补发原业务事件。

再次部署时先在宿主配置解码、所有env覆盖完成后导出0600的最终JSON，使用infra源码的只读guard；不要打印配置或把密文原文件当作有效配置JSON：

```sh
python3 scripts/ops/m3_runtime_profile.py --role worker \
  --effective-config /run/m3/worker-effective.private.json \
  --routes /run/m3/routes.private.json
python3 scripts/ops/m3_runtime_profile.py --role apiserver \
  --effective-config /run/m3/api-effective.private.json \
  --routes /run/m3/routes.private.json
```

这两个命令只输出校验摘要，不安装资源、打开准入或启动应用。它是独立CLI，当前没有自动接管三库所有CD；T36须审核再次部署入口与最终配置引用后才能恢复自动CD。四份实际配置校验已证明修正worker/API通过、旧错误配置被拒绝；9个边界测试及6个防火墙测试在两个OS全部通过。

## serverD 持久规则

运维PR295合并后，`/opt/infra-rocketmq/current`已原子指向`/opt/infra-rocketmq/releases/m3-firewall-f144da7956e5`。新release从原73384d115bc1734e6589fb18064777e0f3dfcf0c复制，仅替换已审查的firewall.sh；其他28个文件摘要不变。原release、原部署锁和Broker锁的inode/权限保留。

原systemd单元仍执行current下的manage.sh；后续启动使用持久规则。规则只允许既有专用qs-network派生bridge访问serverD私网8081，不放开5557或任意bridge。非预期网络driver/ID/options/成员会在替换owned chain前失败。应用前后INFRA-ROCKETMQ规则文本一致，没有重置全局策略、修改其他链或重启Broker/应用。

[观察与运维收口回执](evidence/rocketmq-m3-observation-start-20261025.json)记录12项CI、10份真实依赖报告451/0/0及清理、真实48h起点。历史数据、NSQ卷与备份继续保留；M4负责物理和代码清理。
