# M4 最终镜像与八实例验收候选

当前仅准备 C08 隔离验收，尚未部署生产或完成 system 回归。候选由[固定清单](../../components/rocketmq/m4-final-image-candidates.json)绑定三库源码、已成功的两个构建run、同一builder提交和稳定SDK；五类镜像均已构建，其中三个QS镜像使用测试关闭检查修正后的源码重建，首次QS阶段镜像不作为最终候选。

[独立最终重建workflow](../../.github/workflows/m4-final-image-rebuild.yml)回读实际成功构建、逐目标下载精确源码对应的metadata与archive，再执行原八实例配置证明。原C06固定source/build默认值及历史receipt不被改写；最终模式必须显式传入清单，不能把旧C06结果冒充清理后的验证。

IAM旧 `m3-messaging` 切换CLI已退役。新的**仅GitHub隔离环境**initializer在空的具名fixture数据库中调用原迁移到45，显式写入原fixture的 `iam.mysql` binding并选择transaction；要求原binding为空、原protocol唯一、写入后没有witness。它不进入镜像、不供生产使用、不迁移旧任务或恢复旧CLI。默认schema40的历史fixture仍保持原合同，只有显式 `IAM_IMAGE_FIXTURE_MODE=m4-final` 才进入当前初始化。

候选八实例仍使用原UID/GID、CPU/内存、4owner预算、三worker各48并发、21份合成文件的27处只读挂载；真实启动后应零运行期DDL、完整关闭/清理。该证明只使用临时数据库和独立网络，不连接生产、导入真实业务数据或调用在线模型。

C08后续门禁：完整源CI与合并、候选实际重建和失败恢复步骤、重新核对生产身份/材料/资源、固定root工具安装及普通部署用户拒绝验证、受控八实例部署、合法system最小业务回归和发布索引。任何一步未通过均不打勾；不恢复自动CD、不改schema/owner/epoch、不删除保留资产、不回退NSQ或重做原未知模型请求。现有全量备份仍不能覆盖首个新runtime之后的业务事实。

## 固定归档发布

[本次发布计划](evidence/rocketmq-m4-image-publication-plan-20261027.json)固定两个成功构建run、最终18项启动报告原始摘要、五份inventory/归档/config ID和稳定SDK；三库源码分别为IAM4609d454、QS1f38f583、AIf83472c7。独立`m4_publish_candidates.py`在任何Registry写入前回读成功run、完整报告及全部归档，再复用原TLS传输和不可变manifest/config核验。所有目标tag先检查未占用，不覆盖M3/稳定tag；传输失败保留current_target未知状态，不把失败当成不存在。

实际执行从IAM既有`production`环境读取原ACR Secrets，检查显式审核main SHA及生产CD暂停；infra不新增/复制凭据。它只发布原归档，既不重新build，也不部署。旧`publish_candidates.py`默认仍执行原M3 C1合同，仅为新profile显式借用归档校验的reviewed_builder参数。真实拥有的回环Registry传输检查继续在GitHub runner运行，本机不启动Docker。
