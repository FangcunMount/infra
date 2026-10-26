# M4 最终镜像与八实例验收候选

当前C08最终候选已冻结并发布ACR、在云主机离线预置；尚未替换生产应用或完成system回归。候选由[固定清单](../../components/rocketmq/m4-final-image-candidates.json)绑定三库源码、已成功的三次构建run、同一builder提交和稳定SDK；五类镜像均已构建，其中三个QS镜像使用测试关闭检查修正后的源码重建，首次QS阶段镜像不作为最终候选。

[独立最终重建workflow](../../.github/workflows/m4-final-image-rebuild.yml)回读实际成功构建、逐目标下载精确源码对应的metadata与archive，再执行原八实例配置证明。原C06固定source/build默认值及历史receipt不被改写；最终模式必须显式传入清单，不能把旧C06结果冒充清理后的验证。

IAM旧 `m3-messaging` 切换CLI已退役。新的**仅GitHub隔离环境**initializer在空的具名fixture数据库中调用原迁移到45，显式写入原fixture的 `iam.mysql` binding并选择transaction；要求原binding为空、原protocol唯一、写入后没有witness。它不进入镜像、不供生产使用、不迁移旧任务或恢复旧CLI。默认schema40的历史fixture仍保持原合同，只有显式 `IAM_IMAGE_FIXTURE_MODE=m4-final` 才进入当前初始化。

候选八实例仍使用原UID/GID、CPU/内存、4owner预算、三worker各48并发、21份合成文件的27处只读挂载；真实启动后应零运行期DDL、完整关闭/清理。该证明只使用临时数据库和独立网络，不连接生产、导入真实业务数据或调用在线模型。

C08后续门禁：完整源CI与合并、候选实际重建和失败恢复步骤、重新核对生产身份/材料/资源、固定root工具安装及普通部署用户拒绝验证、受控八实例部署、合法system最小业务回归和发布索引。任何一步未通过均不打勾；不恢复自动CD、不改schema/owner/epoch、不删除保留资产、不回退NSQ或重做原未知模型请求。现有全量备份仍不能覆盖首个新runtime之后的业务事实。

## 固定归档发布

[本次发布计划](evidence/rocketmq-m4-image-publication-plan-20261027-v2.json)固定三次成功构建run、最终18项启动报告原始摘要、五份inventory/归档/config ID和稳定SDK；三库源码分别为IAM4609d454、QS1f38f583、AIb00cf3a2。独立`m4_publish_candidates.py`在任何Registry写入前回读成功run、完整报告及全部归档，再复用原TLS传输和不可变manifest/config核验。所有目标tag先检查未占用，不覆盖M3/稳定tag；传输失败保留current_target未知状态，不把失败当成不存在。

实际执行从IAM既有`production`环境读取原ACR Secrets，检查显式审核main SHA及生产CD暂停；infra不新增/复制凭据。它只发布原归档，既不重新build，也不部署。旧`publish_candidates.py`默认仍执行原M3 C1合同，仅为新profile显式借用归档校验的reviewed_builder参数。真实拥有的回环Registry传输检查继续在GitHub runner运行，本机不启动Docker。

最终依赖审计另行移除了AI的NSQ extra与无调用CI服务，原stage f83472c7归档不发布。新AI b00cf3a2构建40362760742，后续48789cdf仅改测试/CI/closure，全部Docker COPY/构建输入逐项相同；14项完整CI及两档各5668用例通过后源码已合并。最终[18项八实例证明](evidence/rocketmq-m4-c08-final-eight-instance-native-20261027.json)由40365407657执行，还在实际镜像内验证了pynsq/tornado不存在和当前导入有效；3项Go codec、零DDL/全部退出清理通过。首次夹具错误及错误旧profile不计通过，均保留于[审计](evidence/rocketmq-m4-c08-final-audit-20261027.json)。发布必须使用v2计划，并将IAM workflow固定到承载该计划的已合并infra源码；旧阶段计划禁止用于最终生产候选。


## 最终发布与主机候选冻结（2026-10-27）

[IAM正式发布run40371739428](https://github.com/FangcunMount/iam/actions/runs/40371739428)已在main工作流d22910071e8e5d21fb411b7c0856c18d8d2aefc6上完成；infra传输源码dd65adabc3de65d863b52d64e5f85d9e5a47bc32随PR338合并。五项通过、零失败/跳过，不重新构建、不启动应用。[原始ACR回执](evidence/rocketmq-m4-c08-acr-publication-20261027.json)的摘要为7537dd4d313085a7313a373cb0f82a501b5483fd110bb9935384b5318cd44145。

两主机ACR读取鉴权拒绝，未复制或下放CI推送凭据；经既有Mac mini SSH上传固定原归档并离线预置。云端Docker实际engine ID可能与CI engine ID、归档config和ACR manifest不同，不能只比较这些ID。实际保存后的完整config SHA、全部rootfs diff IDs、关键配置与验收归档一致；冻结的Compose直接使用实际不可变engine ID，发布索引单独关联ACR manifest。全部5镜像/原归档、配置/环境、21材料/27挂载和正式API预检见[候选冻结receipt](evidence/rocketmq-m4-c08-final-freeze-20261027.json)。

新的运行目录为`/opt/fangcun-m4/releases/m4-c08-20261027-v1`，均为不活动候选包。原八实例、原活动配置/指针、原锁及业务事实保持；仅准备新的未来API材料binding，并完成network=none离线预检。C08-02完成不等于C08-03执行包、C08-04部署/system验收或C08-05发布收尾完成。[生产清单](rocketmq-m4-production-release.md)仍未开启维护。
