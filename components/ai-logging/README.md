# AI diagnostic logging

Production candidate: Vector 0.49.0 file checkpoints + disk sink buffer, mTLS push
only gateway (nginx 1.27.5), Loki 3.6.0, existing Grafana 11.1.4 ops organization.
This is infrastructure outside the single qs-ai business process.

## Collection and recovery

`scripts/prepare-ai-log-source.py` renders exact Docker json-file paths for `qs-ai`,
`qs-apiserver` and `qs-worker-runtime-N`. It rejects unexpected drivers, identities
and Docker roots. Never deploy the wildcard source template directly. Mount the
rendered config DIRECTORY and enable Vector `--watch-config`; the systemd timer
refreshes approved container IDs every 15 seconds, including retained stopped
containers. No Docker socket is mounted into Vector. Log files are read-only.

Only schema_version=1 qs-ai/qs-apiserver events pass filtering. Business IDs stay in
JSON, never labels. The original event timestamp is retained. The 256 MiB disk
buffer blocks ingestion when full, without blocking the application stdout path.
Keep source files and buffer volumes during rollback/replacement. Removed or
rotated-away unread source data cannot be recovered. This is at-least-once
collection, not an audit ledger or an exactly-once business guarantee.

Alloy's original config is retained solely to reproduce its failed restart test.
Alloy 1.11.2 WAL did not replay pending entries after restart; Vector Docker API
source also missed events produced during downtime. Neither is a deployment option.
Source: https://github.com/grafana/alloy/blob/v1.11.2/internal/component/loki/write/write.go

## Storage and access

Loki has no host port and stays on private `ai-logs`; only Grafana and the push
proxy join it. Gateway port 18443 binds the serverD Tailscale interface, requires a
trusted client certificate, and accepts only POST /loki/api/v1/push. No query API
is exposed. Only leaf keys/chains and CA PUBLIC chain are staged/mounted; no CA key.
Independent serverA/serverD collector certificates and ai-logs.svc server cert have
been issued by infra's existing CA workflow.

Grafana `AI Operations` org id 2 has been created with one administrator. Datasource
uid `ai-logs` and dashboard uid `ai-operational-logs` belong only to this organization;
never provision into default org 1. Anonymous access stays disabled.

Loki retains 336 hours; production compactor deletion delay is 2 hours. The 8 GiB
storage budget is a planning budget, NOT a filesystem quota. Capacity and free space
must continue to be observed; this change does not establish a peak-volume SLA.

## Deploy and rollback

Release files live in /opt/ai-logging/releases/<revision>, with `current` symlink.
Runtime inputs live in /data/infra/ai-logging/runtime.env (not Git): LOGS_BIND_IP,
LOGS_GATEWAY_IP, LOGS_SERVER_CERT_DIR, LOGS_CLIENT_CERT_DIR,
LOGS_RENDERED_CONFIG_DIR, LOKI_ENDPOINT=https://ai-logs.svc:18443.
Use `components/ai-logging/docker-compose.yml` with this --env-file; storage profile
on D, collector profile on A and D. Always run exact-source rendering before start.
Install the systemd service/timer only after paths are established.

Grafana's initial private-network connection does not require a restart. For
subsequent serverD deployment, combine the base Compose file with
`deploy/serverD/docker-compose.ai-logging.yml`. Normal make targets use --env-file:
set COMPOSE_FILE=docker-compose.yml:docker-compose.ai-logging.yml in the PRIVATE
serverD env. Explicit -f invocations must include the override too.

Rollback: stop collector timers and these Compose profiles, restore previous release
and config. Keep all log/buffer volumes. Never use down -v. Business containers and
business data are untouched. Preserve the Grafana/Prometheus prior configuration
before adding provisioning/rules.

## Acceptance evidence

Passed in isolated Docker networks with disposable credentials:
- mTLS rejects missing client cert; authorized push/query succeeds.
- 20-second outage + restart: 15/15 unique sequence IDs recovered.
- SIGKILL + five-second stopped period: 17/17 recovered.
- Collector replacement + source rotation: 16/16 recovered with persistent storage.
- Non-JSON sentinel exclusion and original timestamp preservation passed separately.
- Exact source allowlist/path/driver validation: four unit tests passed.
- Vector binary config, Compose and three Prometheus rule trigger tests passed.
- Grafana ops admin can read datasource; ordinary user (including forged org header)
  and anonymous cannot.
- 14-day retention: old and current fixtures initially queryable; after enabling
  336h retention with accelerated compactor timing, old chunks physically removed,
  15-day fixture gone, current fixture retained. Production timing is not accelerated.

30-minute outage/restart repeat is still running. Production activation and real
cross-service troubleshooting acceptance remain pending. External notification has
no configured channel (user confirmed); rules/visibility are in scope, external
notification delivery is explicitly deferred, not reported as passed.

Reproducible commands:

```sh
python3 scripts/tests/test_ai_log_sources.py
python3 scripts/tests/ai-log-pipeline.py --outage-seconds 20 --crash
python3 scripts/tests/ai-log-pipeline.py --outage-seconds 20 --replace
python3 scripts/tests/ai-log-pipeline.py --outage-seconds 1800
python3 scripts/tests/ai-log-retention.py
python3 scripts/tests/ai-log-grafana-access.py
```
