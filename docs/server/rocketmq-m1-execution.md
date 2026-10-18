# RocketMQ M1 execution ledger

## Approved scope

Docker Compose on serverD, maintained by infra. RocketMQ 5.5.1 Single Master with synchronous flush, NameServer 384MiB and Broker+Proxy 1280MiB. Preserve the original three workers and concurrency48; free host memory must remain at least512MiB. No new serverA, IAM relocation, DB/Redis relocation, transaction messages or Outbox retirement.

M1 now includes normal-message SDK integration, fixed releases (Go v0.4.0-rocketmq.1; Python0.3.0a1), IAM/QS/AI adoption, coordinated production deployment and NSQ pause with all data preserved. M2 adds transactions; M3 adopts suitable transactions and retires eligible publisher Outboxes and finally NSQ.

Prepare and verify before downtime. During maintenance gate ingress/Relay, drain effective NSQ subscriptions, preserve disconnected history, stop QS chain and NSQ, deploy RocketMQ, preprovision trusted route bindings and ACLs, start consumers before publishers, verify business paths, then restore. After first RocketMQ publish, rollback requires reconciliation and cannot blindly switch providers. Preserve immutable body/identity, host DB transaction, receipt distinction and frozen/unknown AI recovery boundaries.

## Current progress

- Five clean source checkouts isolated into codex/rocketmq-m1 worktrees.
- serverD baseline refreshed:4CPU/3719MiB, available2132MiB, disk28GiB free;3workers andNSQ still running.
- No production service pause, deployment, CD setting change or queue mutation performed.
- Official5.5.1 distribution SHA512 verified; PGP verification is a required Docker build step.
- Go adapter implementation in progress; no release/host adoption acceptance claimed.

## Required evidence before cutover

- Infra: signed/digest pinned image, effective JVM flags, persistence, ACL positive/negative tests, private network access, metrics from old mini.
- SDK: make check, Python lint/types/unit tests, required real Broker + DB/fault proofs, installed-wheel proof, four Go/Python producer-consumer pairs.
- Hosts: provider-aware configuration/preflight/audit, fixed dependency artifacts, CD gates, exact source/image revisions, outbox/receipt/idempotency regressions.
- Performance:1KiB300msg/s10min publish p95<=500ms/p99<=2s; three workers at original concurrency48 under representative mixed load30min; no unaccounted Unknown/loss/duplicate effect.
- Runtime: IAM version/cache, submission/worker, AI command/result/receipt, readiness;24h postrestore without OOM/restarts/persistent backlog/unassigned failures.

## Implementation checkpoint (2026-10-18)

Five worktrees: /Users/yangshujie/.codex/worktrees/rocketmq-m1/{infra,sdk,iam,qs-server,qs-ai}. SDK draft PR32 is published; source Go/Python adapters and lifecycle/settlement/route/failure tests exist. SDK make check and hosted MySQL/MongoDB/NSQ/Redis integrations plus Python3.11/3.13 source/installed-wheel matrices passed for the first revision; final patches require CI revalidation.

A disposable old-mini Compose stack proved Go/Python interoperability, ACL allow/deny, explicit synchronous flush, and a confirmed message surviving Broker SIGKILL. The revised infra image uses Java as PID1 without upstream8GiB/15GiB defaults. Real SIGTERM exited143 in21.13s without OOM. These are isolated test results, not serverD capacity/deployment or business acceptance.

IAM has explicit provider/file options, ordinary publisher/policy subscription wiring, a pre-claim publication gate and additive migration41 for provider-aware failure audit. Existing NSQ audit is preserved. QS has ordinary publisher/subscriber/worker/authz and AI-event wiring plus candidate frozen binding support. AI has provider/file bindings, common publisher/received contracts and a pre-scan publication gate. Targeted tests passed; source uses temporary local SDK dependency overrides until fixed release artifacts exist. No host changes are released.

Infra owns Docker build/configuration/provisioning, required real-Broker CI and verified image export. Code and evidence preparation continues. Production CD gates, business services, queues and databases are unchanged at this checkpoint. No formal SDK release, serverD RocketMQ deployment, NSQ pause or business cutover has occurred.
