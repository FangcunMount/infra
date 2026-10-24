# M3 稳定 SDK 与最终候选门禁

唯一进度见[M3总表](rocketmq-m3-execution.md)。T25按2026-10-24批准的首发范围完成；本页维护T26–T29的发布边界，不授权生产。高级手工恢复工具移至独立后续台账，未完成不算通过。

## T26 当前协议候选评审

Go tx.4/Python a4固定SDK源码04757bd3，SDK main 03c62b4仅新增发布文档；8个关键API/状态/生命周期/schema文件逐字节一致，[候选摘要](evidence/rocketmq-m3-protocol-review-candidate-20261024.json)保留源码SHA和文件摘要。此评审不修改codec、schema、wire、客户端或业务职责。

| 契约 | 冻结内容 | 验证责任 |
| --- | --- | --- |
| 独立发送 | Reserve/Execute与普通Publisher分开；完整冻结计划、幂等赢家、一次执行资格 | M2、T03–T20已有真实原根与发布依赖证据；当前成对门禁重新绑定实际版本 |
| 原事务 | 原根Bind/guard、业务与全部witness共同提交；Checker只读精确证据，缺失/矛盾/DB故障为Unknown | T23/T24真实四owner故障与保护，最终当前依赖回归 |
| 三阶段 | Half/Local/Final独立，LocalCommitted+FinalUnknown合法；取消/超时不证明回滚 | SDK API/状态测试及宿主原提交回复故障 |
| 重试 | Retry/Replan仅由宿主明确授权；不因投递或回查故障重做模型/业务 | T13/T18，原根授权与真实invocation证据 |
| 生命周期 | 显式Start、StopAdmission、Close/Wait；超时保留真实在途；不关闭宿主DB/loop | T22/T23/T24及既有SDK有界测试 |
| 责任 | 生产者最终一致不等于消费者业务完成；消费幂等/Inbox/receipt及业务调度继续 | QS↔AI实际默认消费者和原根成对闭环 |
| 超限 | 原主库持久封新写、保留Checker/读取/审计，无自动解保护；未验收CLI不进首发包 | 已批准首发范围，实际镜像/执行包排除由T29核验 |

IAM035f94e5、QS83147d8e、AI05d2db71的main tree与各自已通过源码CI的候选完全相同（8/28/12成功，QS条件API同步N/A另列）。成对夹具仍写死旧tx.2/a2/a3，需要更新到当前真实tx.4/a4：验证固定Go模块Sum/GoModSum、Python下载wheel hash/uv.lock和receipt实际版本，不允许replace/editable或伪造版本。AI本批仅修改测试夹具；没有业务变更。完整当前成对CI尚待通过，T26未打勾。

## T27–T29 执行边界

T26门禁通过后，Go拟发v0.5.0、Python拟发0.4.0/tag python/v0.4.0（2026-10-24核验尚未占用，发布前再核验）。版本准备只改版本/构建断言/锁和文档，不搭载新协议功能。两个tag固定同一已合并源码SHA，绑定源码/真实存储/故障验收、wheel/sdist摘要与receipt；不覆盖既有tag或资产，不新增PyPI。

发布后重新下载Go模块和Python资产、核对摘要并独立安装。三库随后锁定稳定依赖，实际当前门禁重新执行；source通过不等于制品已安装。T29才冻结最终镜像、配置、资源、恢复工具与执行清单，验证启动前恢复、首次启动屏障和30分钟切换演练。T30还须105独立完成核验和具名生产批准；T33须合法system登录，48小时观察在生产切换后。
