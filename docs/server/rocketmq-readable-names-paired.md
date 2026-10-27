# 可读路由 QS↔AI 成对故障验收

属于T11隔离准备，真实验收尚未通过；不代表生产切换、模型或system验收完成。[唯一总表](rocketmq-readable-names-execution.md)。

独立 `rocketmq-readable-paired.yml` 复用原五条成对宿主测试、两条真实故障测试和原40项报告检查；固定已发布 Go v0.6.0-rc.1、Python0.5.0rc1，显式启用readable-v1。原M3/M4默认版本、40项验收、首次wire、错误mTLS/正文、取消、消费者与协议关闭门禁保持。

使用两档：Python3.11/MySQL8.0.36、Python3.13/MySQL8.4；实际Go1.25.12、Broker5.5.1。只接受完整源码SHA与无replace/非editable的已发布SDK；真正的业务入口仍来自所冻结宿主源码。

- QS半消息后MQ断连、原业务根事务提交、原生产者SIGKILL；新实例暂停新写，读取原主库和writer epoch完成真实回查。
- AI半消息后Broker SIGKILL/原容器重启，确认不确定最终RPC；新宿主和Go消费者恢复首次消息、业务receipt/state/ACK。
- 继续核对模型调用为0、原executor/half/seal计数、首次wire、独立进程及完整清理；原五条基线不可用两条故障测试替代。

AI测试夹具只把包含naming_scheme的原route列表写为v3；旧列表仍写v2。此调整不修改生产代码、数据库或任何原消息。回执解析器默认仍要求原稳定版本；新入口同时绑定Go与Python可读预发布，不能只改一个版本便通过。

本地通过编译/静态检查和纯契约测试；pytest只收集7条，不冒充真实运行。镜像启动、完整旧新切换及生产业务验收另外记账。
