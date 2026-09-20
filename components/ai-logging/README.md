# AI diagnostic log pipeline (not deployed)

Pinned baseline: Loki 3.6.0, Alloy 1.11.2. Validate both binaries before release.
Storage profile runs on serverD; collector profile runs on serverA and serverD.
This is separate from the qs-ai business process and does not restart it.

Required deployment inputs: LOGS_BIND_IP (restricted serverD interface),
LOKI_WRITE_URL (HTTPS address with certificate SAN match), LOGS_SERVER_CERT_DIR,
LOGS_CLIENT_CERT_DIR. Certificate mounts contain only the named leaf chain, private
key and CA chain. Never mount the signing CA key. Sign independent logs/collector
certificates with infra's existing certificate workflow before activation.
The gateway accepts only authenticated pushes. Firewall restricts ingress to A/D.

Loki has no published host port. Join Grafana to `ai-logs` only after creating an
operations-only Grafana organization, then provision its Loki datasource with that
organization ID and `http://loki:3100`. Do not add this datasource to the default
organization. Anonymous access stays disabled. Query-only users get no gateway
credentials or Docker access.

The Docker socket remains privileged even when mounted read-only. Only the trusted
infra collector receives it. Container-name and schema allowlists limit ingestion;
they are not an authorization boundary around the Docker socket.

Deployment gates still required: verify binary configs; isolated ingestion/query;
malformed/legacy records excluded; certificate rejection; 30-minute outage replay;
container replacement; 14-day retention/compactor validation; measured 8 GiB budget
with 30% spare; Grafana access test; alert loading and actual notification evidence.
The volume does NOT implement an 8 GiB hard quota. Do not claim otherwise.

Useful query after activation:
`{service="qs-ai"} | json | request_id="<business UUID>"`
Follow returned session_id/run_id for execution; correlation_id for an RPC attempt.
Business IDs are JSON fields, not Loki labels. Audit evidence remains in MySQL.

Rollback: stop these profiles, retain named volumes and existing application logs.
Never use `down -v` as rollback. Existing business containers are unaffected.

Local evidence: Loki 3.6.0 `-verify-config=true`, Alloy 1.11.2 `validate`,
Compose configuration passed. An isolated non-root Loki started with a writable
scratch directory, accepted HTTP 204 on push and returned the expected event from
query_range. The temporary test container was removed. This does not establish
Alloy end-to-end ingestion, mTLS gateway readiness, Grafana access isolation or
production deployment. Named-volume initialization now assigns UID/GID 10001.

Additional isolated acceptance: Docker stdout -> Alloy Docker discovery -> schema
filter -> WAL -> Loki query passed. A non-JSON legacy sentinel was not ingested.
The experiment used a separate container allowlist and plaintext local test network;
production mTLS configuration was not weakened. Found and fixed the ordering bug
where schema must be promoted to a label before stage.match can filter it.

## 2026-09-20 acceptance blocker

Do not activate production profiles yet. A 30-minute gateway outage with an Alloy
restart failed the complete-sequence assertion. A 20-second reproduction received
sequences 0, 1, 6–13 but not 2–5, which were emitted before the collector restarted.
This is not evidence of durable restart replay. mTLS rejection and normal ingestion
passed; these do not establish restart durability.

Pinned Alloy v1.11.2 source (`internal/component/loki/write/write.go`) explicitly
leaves WAL replay as TODO. Merely enabling WAL is insufficient. Before deployment,
resolve recovery from retained Docker source logs or use a verified durable delivery
mechanism, then repeat the sequence test without relaxing its assertion. Docker log
retention must be measured against the recovery window; retained local logs are not
an unlimited archive. Do not silently trade this requirement for best-effort logs.

Reproduction (disposable local Docker network, no production credentials):

```sh
python3 scripts/tests/ai-log-pipeline.py --outage-seconds 20
# After recovery is fixed:
python3 scripts/tests/ai-log-pipeline.py --outage-seconds 1800
```

The script removes only its own named containers/network. It intentionally fails
when any fixture sequence is missing and prints diagnostic counts and isolated
container logs. Container replacement, retention deletion, Grafana organization
access and notifications remain pending.

Source: https://github.com/grafana/alloy/blob/v1.11.2/internal/component/loki/write/write.go

## Replacement collector preparation

User approved replacing Alloy while retaining Loki/Grafana and restart recovery
acceptance. Candidate: Vector 0.49.0 with file source acknowledgements and a 256 MiB
disk sink buffer. Docker API source alone also missed events emitted during
collector downtime and is not used in the production candidate.

The source template is NOT a deployable all-container configuration. Run
`scripts/prepare-ai-log-source.py` on each host to produce exact paths for approved
container names; it rejects unexpected log drivers and Docker roots. Mount the
rendered directory (not a single config file), and use `--watch-config`. The supplied
systemd timer refreshes the source list after replacements. It does not remove logs.
Keep source logs and buffer volumes during rollback and replacement; already
removed/rotated-away source data cannot be recovered. This is at-least-once
collection, not an audit ledger or exactly-once business persistence.

Short isolated file-source tests passed: 20-second gateway outage + graceful
collector restart (15 events), and SIGKILL + five-second stopped period (17 events),
with all emitted sequence numbers recovered. The 30-minute repeat remains pending.
Source allowlist tests: four passed. Vector binary config and Compose validation
passed. Production activation is still gated on remaining acceptance.

Production prerequisites prepared: Grafana organization `AI Operations` (id 2),
no datasource provisioned yet; independent serverA/serverD collector client
certificates and `ai-logs.svc` server certificate signed by the existing infra CA.
Only leaf keys/chains and CA public chain will be mounted/transferred.

Additional isolated replacement test passed: disk queue and file checkpoints survived
container removal/recreation plus source-file rotation; all 16 events recovered.
Production certificates have been staged; no collector has been activated.
