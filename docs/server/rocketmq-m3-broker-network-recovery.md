# serverD 原 Docker 网络连接恢复与一次受控重试

状态：**待追加具名生产批准，未执行网络变更或第二次人工启动**。本清单补充已批准的[原恢复清单](rocketmq-m3-broker-recovery.md)，仅增加恢复原有Docker endpoint及一次受控重试；业务切换仍不在范围内。目标与配置摘要、既有network ID/IPAM/labels、NameServer身份、原失败状态和执行代码摘要见[固定v2计划](evidence/rocketmq-m3-broker-network-recovery-plan-20261025.json)。

## 原失败事实与已完成保护

- 用户已批准infra269；完整`store/auth/三配置`冷备份覆盖68文件、逻辑1,733,424,782B，归档58,455,997B，逐文件内容/属主/权限验证通过。Mac mini副本重新计算SHA-256与源一致，目录0700/文件0600，保留至少30天且未结责任延长、不自动删除。
- 首次人工启动后，Broker因本机地址解析递归退出1，原`unless-stopped`策略自动拉起11次。已触发原失败路径、仅停止该Broker；未到原用户校验或`updateUser`阶段，三配置摘要保持原样，密码未更换。
- 只读复核证明，原容器在本次操作之前`NetworkSettings.Networks`即为空，而`HostConfig.NetworkMode=rocketmq_rocketmq`；NameServer仍连接同一既有bridge且健康。启动前漏将空网络作为阻断条件，运行期又仅检查Running而未及时拒绝Restarting/自动重启计数，两个门禁均须补齐。
- 私有日志明确包含StackOverflowError及MixAll两个方法递归。固定5.5.1[源码](https://github.com/apache/rocketmq/blob/rocketmq-all-5.5.1/common/src/main/java/org/apache/rocketmq/common/MixAll.java)在无法解析本机且没有非loopback网卡时，其本机地址和网卡fallback相互调用。断网为当前直接故障原因；何时及为何原endpoint丢失尚未确认，不归因于此次Tailscale重新认证。
- 失败后全部冷备份源文件的字节和元数据仍与原清单一致，其它容器的CID/image/配置/启动时间/状态/重启计数保持；原备份可以在再次核验后复用。[首轮实际执行回执](evidence/rocketmq-m3-broker-recovery-attempt-20261025.json)保留失败，不改签成功。

## 唯一新增的生产变更

将**原停机容器**接回**原已存在的Compose bridge**，保持原镜像、配置、资源、数据卷、端口和重启策略，不创建或重配网络、不操作Tailscale或手工防火墙：

```sh
docker --host unix:///var/run/docker.sock network connect \
  --alias broker --alias rocketmq-broker-1 \
  edffac725f5015491bef78c66f31d0a4757f15c1d909f2e1bc1e1c5df492d90d \
  ce02d3e209b1f17dbf9b7544b3629f363fa45e5a80e3766b77295f038e86ccce
```

network为`rocketmq_rocketmq`、bridge/local、172.22.0.0/16，既有NameServer为172.22.0.2。完整属性及指纹冻结在计划中，绝不临时选择其它网络或分配固定容器IP。新IP由原bridge按现有IPAM分配，宿主私网8081/5557绑定不变。

## 追加执行步骤与门禁

1. 沿原Mac mini个人SSH入口和原部署互斥锁，再读停机原CID/image、当前exit1/自动重启计数11、配置/属主/模式/inode、完整Config/HostConfig指纹、原network指纹、NameServer CID/启动时间及健康、三个worker。任何漂移停止重新冻结。
2. 逐文件复核原冷备份源和原manifest、归档SHA；在Mac mini重新计算既有副本SHA并记新的读回回执。只在全范围字节/元数据完全一致时复用；不一致则停止，先按原范围做新的完整冷备份并核对副本，不使用陈旧备份启动。
3. 新root0700操作目录只保存本次阶段、代码指纹和私有凭据；不覆盖v1失败原件或备份。网络connect仅调用一次，必须对原停机容器和原bridge；已有错误网络、其它网络或未知endpoint一律拒绝。回复未知只读核验，不循环connect。
4. 启动前校验已准备的原endpoint及`broker/rocketmq-broker-1` aliases。Docker在停机状态可能仅保留准备信息，NetworkID/IP尚空；这与运行期的真实endpoint分别校验。**没有endpoint禁止启动**；运行后必须为原network ID、真实非loopback IPv4、原CID在该网络的活动endpoint。
5. 仅增加一次人工启动。健康等待最长180秒；**首次Restarting、自动重启计数非零、退出或OOM立即进入失败停止**，不能仅凭Running=true继续等待。保持原重启策略，不关闭自动重启来隐藏故障。
6. 健康后继续原已批准的管理员更换流程：新鲜原凭据精确校验，真实`updateUser -p`明确成功，三原inode写入/fsync且非管理员字段/权限不变，然后一次计划内重启。回复未知不继续或盲重试。分别用全新客户端验证新成功→旧明确CODE16→新成功、默认tools和持久Super/Enable；原CID/image/配置元数据/资源/端口保持。
7. 回读实际事务参数、48小时保留、Topic/group/ACL语义不变、可用内存≥512MiB和无额外重启；确认NameServer及其它全部容器保持。Mac mini必须在最终计划重启后重新抓取到Broker和三个worker均up，再记录成功。M3应用、Topic/ACL/schema/provider及业务准入仍不切换。

## 验证与失败边界

[隔离真实验证](evidence/rocketmq-m3-broker-network-validation-20261025.json)40157748699为**12/0/0**：确实断开原fixture网络并复现MixAll栈溢出，再接回同一bridge/原CID，验证健康、无自动重启并完成原密码更换全链。4项新增纯契约及合计353纯测试通过。首轮隔离验证在接回后的停机prepared endpoint校验失败，已区分prepared/live后复验；原失败保留。infra272其余源码CI/合并待完成，全部通过并合并后才允许执行。

本次新增connect和第二次人工启动超出infra269原清单的一次启动/失败即停边界，因此需要追加具名确认。CI和测试成功均不代替生产批准。

失败只停止原Broker，保留已接回的原endpoint、当前凭据、完整备份与阶段；不自动断开恢复的连接，不再启动，不恢复旧密码、Auth DB或store，不停止NSQ/worker或扩大网络/权限。新事实提交不明时只读确认并具名处理。M3仍28/36，T29内部4/5。
