# 可读资源镜像的固定 SDK 校验

此工具支持 T11/T12 的镜像准备；尚未构建、发布或部署新镜像，进度见[执行总表](rocketmq-readable-names-execution.md)。

`final_image_candidate.py --sdk-profile readable-rc1` 明确选择已发布的 Go `v0.6.0-rc.1` / Python `0.5.0rc1`，SDK源码固定为`5c2e3cd155e67c0f766e93bf95238b16fc219b5f`。Go运行二进制必须包含精确版本和module sum且没有replace；Python源lock必须指向精确公开wheel URL及SHA256，镜像内安装版本、客户端5.1.2和应用源码标识仍须吻合。

默认`m3-stable`继续执行原M3/M4的Go0.5.0/Python0.4.0校验；二者不能相互替代。可读候选使用独立`readable-final-image-inventory/v1`报告，明确`stable_release=false`，不能交给旧M4发布验收器充当稳定版证明。稳定SDK发布后，必须依据正式tag、重新下载制品及校验receipt增加独立固定profile；当前没有浮动或未发布的稳定profile。

所有Docker操作仍由既有GitHub-hosted Linux guard限制，不在MacBook执行。该校验仅证明镜像依赖与来源，不替代八实例启动、配置/预算、真实业务、故障或生产验收；独立构建入口已提供，只在workflow_dispatch时构建五个镜像，不自动发布registry或部署；尚未发起构建。启动验收及发布器接入仍待完成。

`readable_image_candidates.py`提供独立候选清单与只读归档验证。五个镜像须来自同一协调构建，绑定三库源码、builder SHA、Go UID/GID、v3路由文件原字节摘要，以及每个inventory/归档/config摘要与大小。读取归档时验证实际config及非root用户，不解压、不加载或启动镜像。旧M4 inventory、旧SDK、replace、错误源码、缺清理或不完整证明均拒绝。当前只提供构建与来源校验，八实例启动/切换/故障及registry发布仍未接入，不能作为上线证明。

## 八实例启动入口

`five_image_start.py --readable-candidate <已提交的清单>` 使用独立的 readable 报告与严格归档校验。全部五个归档、源码、发布 SDK、原始非 root 身份和配套工具在首次 Docker load 前校验；不接受旧 M3/M4 清单或旧启动/切换 receipt。继承原生产配置生成器、21 份只读版本材料和八个原进程的资源/并发，检查四 owner 在暂停准入时仍保持 Checker、三轮原 worker 重启与八进程完整关闭；启动期间不执行 DDL。

`.github/workflows/rocketmq-readable-startup.yml` 的 PR 入口只运行契约。手动真实启动必须指定仓库内已审核并提交的 `components/rocketmq/readable-image-candidates-*.json`，下载其唯一成功协调构建的五份原始归档，检查构建 workflow 身份，再运行真实启动。

该入口尚未执行；没有实际镜像清单、没有启动或生产结果。启动报告不能标记旧新切换、业务或 system 验收通过，T11 的切换/故障和 T12 的正式版本仍有独立门禁。旧 M3/M4 默认 SDK、报告及历史候选保持原门禁。
