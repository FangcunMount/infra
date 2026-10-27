# 可读资源镜像的固定 SDK 校验

此工具支持 T11/T12 的镜像准备；尚未构建、发布或部署新镜像，进度见[执行总表](rocketmq-readable-names-execution.md)。

`final_image_candidate.py --sdk-profile readable-rc1` 明确选择已发布的 Go `v0.6.0-rc.1` / Python `0.5.0rc1`，SDK源码固定为`5c2e3cd155e67c0f766e93bf95238b16fc219b5f`。Go运行二进制必须包含精确版本和module sum且没有replace；Python源lock必须指向精确公开wheel URL及SHA256，镜像内安装版本、客户端5.1.2和应用源码标识仍须吻合。

默认`m3-stable`继续执行原M3/M4的Go0.5.0/Python0.4.0校验；二者不能相互替代。可读候选使用独立`readable-final-image-inventory/v1`报告，明确`stable_release=false`，不能交给旧M4发布验收器充当稳定版证明。稳定SDK发布后，必须依据正式tag、重新下载制品及校验receipt增加独立固定profile；当前没有浮动或未发布的稳定profile。

所有Docker操作仍由既有GitHub-hosted Linux guard限制，不在MacBook执行。该校验仅证明镜像依赖与来源，不替代八实例启动、配置/预算、真实业务、故障或生产验收；独立构建入口已提供，只在workflow_dispatch时构建五个镜像，不自动发布registry或部署；尚未发起构建。启动验收及发布器接入仍待完成。
