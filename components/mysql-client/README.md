# Production public MySQL TLS

QS API, workers, IAM and AI use the organization Variables `MYSQL_PUBLIC_HOST`,
`MYSQL_PUBLIC_PORT`, `MYSQL_TLS_MODE=VERIFY_IDENTITY`, and `MYSQL_TLS_CA_REF`.
The CA reference is a full infra Git commit containing the official public RDS
CA PEM and its SHA256/source manifest. Database credentials remain repository Secrets.

`python3 scripts/mysql/ca.py install --ref <full-commit>` installs that exact CA
at `/data/infra/ssl/mysql/ca-chain.pem`; `verify` rejects drift, malformed/non-CA PEM and bundles without a currently
valid trust root. Official bundles may retain unrelated expired regional intermediates;
the Go/Python TLS handshake validates the actual negotiated chain and hostname. Each application mounts it read-only at
`/etc/qlume/mysql/ca-chain.pem`. Maintenance clients use the same pinned bytes.
Production never falls back to a private address, proxy, insecure TLS or plaintext.
Explicit `DISABLED` remains available for local and disposable test databases.

## Controlled rollout

Prepare baseline-derived images and private snapshots before enabling RDS SSL.
The cloud administrator must verify instance ownership and A/B/D egress allowlists,
then enable SSL for the public endpoint only. Do not enable global forced SSL.
Record the database server UUID/schema heads before and after; perform no business DDL.

AI uses `scripts/mysql/ai_cutover.py <prepared-release>` for preflight and the same
command with `--apply` for its locked native release/state transition. This path
checks the unchanged schema head, runs no Alembic upgrade and prunes no images.

The private `scripts/mysql/runtime.py` plan/apply/rollback tool takes one Go service at
a time under the existing deployment lock. It preserves container configuration,
credentials, networks and resource limits, and changes only the image, MySQL
binding, TLS parameters and CA mount. Plan files contain secrets: keep them owned by
root with mode 0600 inside a 0700 directory. Never attach them to Git or Actions artifacts.
An image ID (`sha256:...`) and full CA commit are mandatory. Apply rejects runtime
or plan drift. It retains the original container/image for rollback and disables
its restart policy only after the replacement is healthy. The original restart
policy is restored by rollback. No image/container pruning is performed.

Cut over AI, IAM (single running instance), API and individual worker replicas in
that order. Verify actual TLS session cipher/version, readiness, authorization
freshness and business behavior after each stage. Update the native frozen release
and Compose descriptors using the same allowlist, keeping private originals for
rollback. Automatic production releases remain paused.

Perform a real logical backup and an isolated restore rehearsal. Schema and role
maintenance run only preflight/status checks during this rollout. After all
clients pass and at least 30 minutes of healthy observation, stop the B proxy,
disable its restart policy and remove its default deployment/recreation entrypoints.
Do not retire the proxy or old address Secrets before this gate. Keep RDS SSL
enabled on rollback to avoid a second database restart.

## Verification

```sh
python3 scripts/mysql/test_ca.py
python3 scripts/mysql/test_runtime.py
python3 scripts/mysql/test_ai_cutover.py
```

This source change alone does not indicate that production cutover has completed.
