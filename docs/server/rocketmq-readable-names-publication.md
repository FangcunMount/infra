# 可读候选镜像的固定发布

属于T11/T12准备，尚未发布稳定SDK或生产镜像。[唯一进度总表](rocketmq-readable-names-execution.md)。

独立`readable_publish_candidates.py`复用原M3/M4的TLS Registry运输与manifest/config digest回读，不改写旧发布器或冻结的旧证据。它不构建镜像、不启动应用、不做DDL或业务切换。

发布前逐项核验：原始计划摘要、现有固定ACR与五个仓库、全部精确源码与归档、固定v3路由摘要、成功的原构建workflow和实际八实例18项启动workflow。native报告必须原始摘要一致、八实例预算/身份/只读挂载/退出/无运行时DDL/完整清理全部通过；五份inventory与归档在任何Registry写入前复核，未选镜像或未经测试的归档不可混入。

RC计划可离线审阅，但执行路径在任何Registry写入前拒绝RC。稳定profile只能在真实发布后由源码固定其Go/Python版本、共同源码SHA和wheel摘要；还要回读两个轻量tag及官方非预发布Release，Python实际资产URL和GitHub digest须匹配。当前只有readable-rc1，故现阶段生产发布路径不能通过；没有预填未发布的hash。

五目标tag都先核对未占用；新tag使用`readable-candidate-<run>-<attempt>-<source>`，不覆盖M3/M4或稳定tag。网络/认证/标签查询失败直接保留失败；运输失败保留current_target及已发布精确对象，不能当作目标不存在或自动回滚。

读取或发布的receipt仅含源码/制品摘要和阶段，不含凭据/正文；运行报告0600，临时下载由owned目录清理。原运输实现不变，因此纯契约证明与其既有原生loopback运输证明分别记账；本轮尚无实际新Registry写入。

命令需要已审阅的计划与独立digest、私密authfile、只在GitHub-hosted隔离runner执行。生产部署仍要T11切换演练及T13冻结清单，镜像发布结果不授权恢复公众准入或删除旧资源。
