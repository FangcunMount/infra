# ServerA 独立采集试验候选

本目录供隔离验证和生产试验审查。正式监控继续由现有 Mac mini 项目负责。

ServerA 在宿主机运行现有固定 inventory helper，读取本机监控容器。ServerD 的 inventory 通过严格主机密钥校验的受限 SSH 获取。发现程序每轮独立发布两份 file SD，来源失败时保留最近有效文件，超过 120 秒清空该来源。Prometheus 挂载发现目录和配置为只读，直接从 overlay 读取八个应用指标，从 ServerD Tailnet 端口读取 Broker，保留现有 job、instance、component 和 host 标签。副本数量及地址由现役 inventory 决定。

生产试验前需要签收以下项目。

- 核对 ServerA 到 ServerD 的 TCP 和现有主机指纹，具名审批试验账户对固定 inventory helper 的访问。若采用新增公钥，按现场来源 IP、固定命令、`restrict` 和 UTC `expiry-time` 审批。按公钥指纹绑定授权行及撤回责任人。Mac mini 原发现入口继续使用原凭证。
- 固定 ServerA 上的试验身份、镜像摘要、独立卷、只读配置和可访问 overlay 及 Broker 的网络。采集进程使用独立容器，发现 helper 在宿主侧执行。限制试验查询到已批准的只读入口。
- 从临时实例验收十个具名目标和四个事务 owner。沿用原集中采集 481 点、35 秒新鲜度和即时端点口径，保存两小时查询及前后容器身份。另核对副本地址变化和单源过期。
- 记录试验结束时限。到期或失败时停止试验进程，按清单处理专用授权及试验文件，保留原件和历史监控。接管正式查询、告警、历史存储或数据保留另行审查。

## 具名试验步骤

以下命令供完成授权和工件签收后的 ServerA 窗口使用。先在签收单记录操作 ID、操作人和审查人、UTC 起止、停止期限、SSH 来源授权和撤回责任人。记录当前生产容器及 overlay 身份、两份 Collection 地址、发布冻结以及 Mac mini 两小时查询结果。

1. 将本目录的 Compose 和 Prometheus 配置放到本次签收的固定目录 `/opt/infra-monitoring-pilot`，同目录安装签收的 `scripts/monitoring/discover.py`。宿主文件和私有配置由 root 持有。以 `discovery.example.json` 为基线填入经批准的凭证路径和 ServerD 主机公钥。试验 SSH 仅读取该私钥和固定主机公钥，每次连接重新认证。目标目录 `/var/lib/infra-monitoring-pilot/targets` 允许试验容器读取，仅宿主发现程序可写。核对审批的固定 helper 仍为 root 持有，实际 SSH 仅运行该 helper。
2. 预先确认 amd64 镜像摘要与 Compose 相符，核对同名试验容器和定时器均为空。若走离线导入，用签收包中的脚本读回归档摘要及镜像，并将 `offline.override.yml` 放在同一目录。以下命令均使用 `compose.yml` 和签收的 `offline.override.yml`。已有原仓库摘要的路径可省去覆盖文件及对应的 `-f` 参数。根据授权创建独立试验卷 `qlume-servera-monitoring-pilot-data`，或签收同一试验复验使用的原卷。先用同一组参数执行 `config`，核对没有宿主端口、数据卷及只读挂载、外部 overlay 身份。首次执行发现并核对两份 file SD 的实际身份和目标地址，再开始试验。
3. 由获批管理员在 root 终端启动。将 `PILOT_STOP_UTC` 设置为签收的绝对停止时间，使用 `YYYY-MM-DD HH:MM:SS UTC`。停止定时器先于采集器启用，启动后读取其触发时间。窗口预留启动、两小时连续采集和撤回时间。SSH 授权以同一停止时间为上限，在 `authorized_keys` 中用 `expiry-time="YYYYMMDDHHMMSSZ"` 表示。

```sh
(
set -eu
umask 022
cd /opt/infra-monitoring-pilot
test -n "${PILOT_STOP_UTC:?set the signed UTC stop time}"
stop_epoch=$(/usr/bin/date --date="$PILOT_STOP_UTC" +%s)
test "$stop_epoch" -gt "$(/usr/bin/date +%s)"
/usr/bin/python3 -B discover.py --config /etc/infra-monitoring-pilot/discovery.json
systemd-run --unit=qlume-servera-monitoring-pilot-expire \
  --on-calendar="$PILOT_STOP_UTC" --timer-property=AccuracySec=1s \
  /bin/bash -c 'systemctl stop qlume-servera-monitoring-pilot-refresh.service || :; exec /usr/bin/docker compose -f /opt/infra-monitoring-pilot/compose.yml -f /opt/infra-monitoring-pilot/offline.override.yml stop -t 15 prometheus'
systemctl is-active --quiet qlume-servera-monitoring-pilot-expire.timer
systemctl list-timers qlume-servera-monitoring-pilot-expire.timer
test "$stop_epoch" -gt "$(/usr/bin/date +%s)"
docker compose -f compose.yml -f offline.override.yml up -d --no-build --pull never prometheus
remaining=$((stop_epoch - $(/usr/bin/date +%s)))
if [ "$remaining" -le 0 ]; then
  docker compose -f compose.yml -f offline.override.yml stop -t 15 prometheus
  exit 1
fi
if ! systemd-run --unit=qlume-servera-monitoring-pilot-refresh \
  --property=RuntimeMaxSec="${remaining}s" \
  /bin/bash -c 'umask 022; while :; do /usr/bin/python3 -B /opt/infra-monitoring-pilot/discover.py --config /etc/infra-monitoring-pilot/discovery.json; sleep 15; done'; then
  docker compose -f compose.yml -f offline.override.yml stop -t 15 prometheus
  exit 1
fi
)
```

4. 从试验容器 loopback 读取就绪和即时目标。Prometheus 2.54.1 的宿主端口和容器 overlay 地址均没有查询监听。使用既有审查脚本 `m5_window_central_observe.py` 的 `observe` 入口在试验容器网络命名空间读原口径，留存完整 JSON、身份快照及摘要。脚本采用 #432 的 `de9722a2fd79cadc86d9054fb393fbef0736ba21`，其 SHA-256 为 `f15b9022eba3b1fb78dfbe0b5543f8013797c27006f638cc731c6c462ced5274`。将 `COLLECTION_1`、`COLLECTION_2` 设为本窗口实读的具名地址，`W00_VERIFIER` 设为已校验脚本的绝对路径。

```sh
(
set -eu
container="$(docker compose -f compose.yml -f offline.override.yml ps -q prometheus)"
test -n "$container"
docker exec "$container" wget -qO- http://127.0.0.1:9090/-/ready
pid="$(docker inspect --format '{{.State.Pid}}' "$container")"
test "$pid" -gt 0
nsenter -t "$pid" -n /usr/bin/python3 - "$W00_VERIFIER" "$COLLECTION_1" "$COLLECTION_2" <<'PY'
import json
import runpy
import sys
import time

verifier = runpy.run_path(sys.argv[1])
step = verifier["STEP"]
report = verifier["observe"](
    verifier["api"]("http://127.0.0.1:9090"),
    verifier["expected_targets"](sys.argv[2:]),
    int(time.time()) // step * step,
)
print(json.dumps({**report, "transport": "servera-pilot-loopback"}, allow_nan=False, sort_keys=True))
raise SystemExit(0 if report["passed"] else 1)
PY
)
```

5. 到期或中止时，先停止 `qlume-servera-monitoring-pilot-refresh.service`，再从同一目录执行 `docker compose -f compose.yml -f offline.override.yml stop -t 15 prometheus`。用 `docker inspect` 实读试验容器为 `exited` 后停止 `qlume-servera-monitoring-pilot-expire.timer`。保留试验卷和原件。按指纹撤回签收单绑定的试验授权行，实读原 Mac mini 授权行及原查询路径，复验发布冻结。
