# M5发布后：一次真实业务验收回执

2026-11-01 12:31（北京时间）已完成用户指定合法填写会话的一次正常提交：答卷受理 → Assessment已评分 →标准报告落库并显示 → 一次正常深度解读 → AI持久响应及产物 → QS完成投影 → 四份双向业务ACK核对。此次通过仅覆盖这一份真实案例。首批M5生产发布仍以[发布回执](rocketmq-host-retirement-m5-production-release.md)为准；剩余五对象、历史51条责任和采集缺口均未宣布完成。

[结构化实际回执](../evidence/2026-11-01-host-retirement-real-canary.json)公开计数、来源和私有原件摘要，不包含受试者身份、答案、报告内容、令牌或真实请求ID。数据/恢复责任人均为shujie。

## 源码、冻结和操作边界

- 生产六实例仍为4620d11e2cffbc4b67b43965812cff3340f0be43，现库111/44。12:31最终实读A三实例、D三实例就绪，原ID/镜像/资产相同，零重启、无OOM；原六实例继续停止保留。
- 快照修复[QS #478](https://github.com/FangcunMount/qs-server/pull/478)已合并，精确main5fa0c1f51af2482b13a2c5a66c57a25edb4f7376的[CI41271612231](https://github.com/FangcunMount/qs-server/actions/runs/41271612231)、主线Code Quality、AI bridge、host failure audit、original MySQL root五工作流均success。原条件跳过保持原条件，未重跑为验收。
- 自动Production Deploy再次实读为disabled_manually；本轮没有应用重新部署、DDL、停业务、备份回放、历史重投、retired、删除凭证或缩减租约/重试预算。

## 实际执行与原始证明

1. 当前填写会话由用户指定并已填好，代理未改答案。初次窗口异常时客户端完整Network未发出提交，完整87对象基线无变化。用户恢复普通窗口后沿原填写会话/请求身份完成一次正常提交；未知结果先查原事实，没有第二份问卷或替代身份。
2. Mongo答卷与原answering_start、受试者、问卷/模型版本对应。现有answersheetgap.Scanner在有界主库快照内验证V2 native_atomic、原计划/执行/精确提交见证和wire，返回唯一assessment_present；MySQL对应唯一evaluated Assessment、一个Outcome和succeeded检查点。Outcome原引用/计划/执行/见证经SDK解析为Commit，原wire哈希一致。
3. 一个standard report_generation为generated，产物与查询目录均对应同一Outcome/Assessment；小程序标准报告正常显示。
4. 沿本次报告正常入口只请求一次深度解读。QS原command archive经当前canonical codec与SDK核对body/wire/指纹、原计划/引用/执行/见证，Commit；AI Inbox同一命令accepted，body hash一致。AI同一session/assessment/run绑定，模型调用新增一次response_received且原响应持久，artifact落库；QS完成投影到version4，小程序显示深度解读已生成。
5. AI准入回执和三个状态事件的四份原出站archive均由现有只读read_committed核验。四份event/body hash逐项匹配QS stored Inbox，QS ack_id逐项匹配AI持久STORED业务回执；不能将单独Broker ACK等同这些业务事实。

## 原计划关联及保留事实

填写入口与冻结attribution均为self_service，未带显式TaskID；现有[journey intake源码](https://github.com/FangcunMount/qs-server/blob/4620d11e2cffbc4b67b43965812cff3340f0be43/internal/apiserver/application/journey/assessmentintake/service.go#L403-L418)会按组织/受试者/量表匹配已开放任务。实读已关联一个原有任务，状态completed、version2，指向本次Assessment，因此Assessment记为plan。未创建新计划或手工改来源；此事实不证明任务入口、定时开放或提醒送达验收。

完整QS只读基线仍为87对象，64对象定义和全内容摘要相同；23对象随本次答卷/评分/报告/计划匹配、AI命令/四ACK及事务凭证变化。原重试、hold、提醒/调度记录均保留，其摘要未变化。三张表SHOW CREATE摘要变化经离线只替换AUTO_INCREMENT恢复值，即精确命中提交前原摘要，已证明是插入推进序号，不宣称原始摘要全部相同。

AI原39次模型调用、125份结果历史、57份Inbox均逐条与本轮前回执相同；新增分别为1/3/1。QS现为58条非retired命令，原缺51份archive/执行/见证集合摘要仍为76a5260d862fdbfb4759d56c41dbf1a58b1518ab788426eded212b1d2991d6cc；旧协议原文核对不能替代当前原生见证。业务仍运行，前后MySQL/Mongo读取不是跨库原子快照，也不是停写证明。

## 保护材料与剩余工作

实际提交、双向证明、失败诊断、完整差异、私有诊断源码及身份/字节绑定已追加归档，SHA256 `a07f9aeca2c6a308230051fddc06b838dfccb424f8c17e4d4855270bab837312`、602010字节；MacBook和ServerA两份回读/fsync一致，目录0700、文件0600，至少30天，未结责任延期，无自动清理。较早v1原件和原75MB历史dump的独立副本保留；v1本身不含本次后发生的真实验收。

本批F03单案例技术验收完成，F01当前基线和#478精确主线CI已补齐。继续按[后续批次](rocketmq-host-retirement-followthrough-20261101.md)推进：采集两处缺口根因、51条历史分类责任审查、AI/IAM/QS剩余五对象逐项解除依赖及各自保护/窗口审查、独立原生超限恢复矩阵。当前聚合指标完整性保护仍生效，不以日期过滤或retired改成假绿。一次案例不证明全模型/容量、真实设备兼容、提醒或授权矩阵；自动CD继续冻结。
