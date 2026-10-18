# RocketMQ M1 execution ledger

## Scope and current status (2026-10-18)

RocketMQ is deployed on serverD and managed by infra. Business services still use NSQ; no production database migration or business provider cutover has occurred. M1 remains in progress.

M1 includes ordinary-message SDK support, fixed Go/Python releases, IAM/QS/AI adoption, coordinated production deployment and pausing NSQ while preserving its data. M2 adds transaction messages; M3 adopts suitable transactions and retires eligible publisher Outboxes and eventually NSQ. Host transactions, receipts, idempotency and frozen/unknown AI recovery remain authoritative.

The user confirmed serverD has 5 Mbps public bandwidth. On 2026-10-18 the user directed us to stop additional cross-cloud throughput testing because the services will soon move into the same cloud. Preserve the failed cross-cloud result below; defer that capacity gate until co-location, without claiming it passed. Continue deployment and business acceptance preparation. Do not change bandwidth or worker limits.

## Deployed infrastructure

- serverD: 4 CPU / 3719 MiB, no swap. Original three workers retain concurrency48 and their resource limits.
- Docker RocketMQ5.5.1 Single Master, synchronous flush. NameServer384MiB/.25CPU; Broker+Proxy1280MiB/1.5CPU with bounded JVM heap/direct memory.
- Runtime release `/opt/infra-rocketmq/releases/73384d115bc1734e6589fb18064777e0f3dfcf0c`; `/opt/infra-rocketmq/current` points to it. `infra-rocketmq.service` is enabled and active.
- Tested CI image config digest `sha256:5cd5b00c2b6bd3b3a47ea15cd1d1df3ff3d3acaa3f958fa182fe00f426feb9be`; Docker29/containerd manifest identity `sha256:6387937671866c6ca6c973b8e5df649ce101463e95f4e300c5455b2975bf3353`. Archive manifest/config/layer identities are verified without rewriting the CI receipt.
- gRPC TLS only on `100.118.164.39:8081`; Broker metrics on `100.118.164.39:5557`. Scoped Docker forwarding permits the declared Tailscale sources. Public access was checked from serverA and timed out.
- Ten NORMAL topics and explicit groups provisioned from `components/rocketmq/serverd-routes.json`; separate least-privilege credentials per application. No credentials or keys belong in Git.
- Old M2/8GB Mac mini Prometheus directly scrapes serverD: `up{job="rocketmq"}=1`. No persistent serverD collection agent.
- NSQ and original three workers remain running. No queue data, volume or historical disconnected subscription was deleted.

## Fixed source artifacts

| Repository | Merged source | Status |
| --- | --- | --- |
| reliable-messaging | `18c0c38b5869b60eac5ce238c15d5e5c4048eeea` | Go `v0.4.0-rocketmq.1`, Python `python/v0.3.0a1` published; main CI and installed-wheel tests passed |
| infra | `eea2ca7ae4dd8f3f4759ee3b9d45d37a260f613b` | PR16/17 merged; serverD runtime above is an earlier fixed release from PR17 |
| IAM | `f5788a56dc5437fc033f93760d55181fb847c01d` | PR127 merged; main CI passed; image built, production deploy skipped by pause gate |
| qs-server | `669cee2d3b2b777cf431f05e470f6bab4a6138f0` | PR402 merged; PR CI passed; main CI requires resolution before candidate promotion |
| qs-ai | `c288eb94c09a8ac930f0ae6b03d62a09147b72fb` | PR156 merged after all14 checks passed; main CI pending |

Python release wheel SHA256: `b980312490a5c013ed82542478580c2bf3a72d02a299d7629bc1e81ed11e08e1`. Host adoption uses fixed published artifacts, without local SDK replacements.

IAM/QS production deploy pause gates remain true. AI `AUTO_DEPLOY_ENABLED` was changed from true to false for coordinated deployment. Future IAM/QS deployment variables explicitly select RocketMQ with publishers disabled; this has not changed running containers.

## Runtime evidence and capacity boundary

On real serverD, all four Go/Python producer-consumer pairs passed, as did allowed/denied ACL probes. The isolated build acceptance also proved confirmed-message persistence after Broker SIGKILL and bounded graceful SIGTERM. These do not establish business acceptance.

| Probe | Result |
| --- | --- |
| Cross-cloud smoke,100 messages | All confirmed and uniquely ACKed; p95 14.64ms / p99 16.11ms |
| Cross-cloud300/s10min,1024 decoded payload bytes /1573 Broker body bytes | **Failed**:180000 scheduled,176884 confirmed,3116 locally dropped before send; p95 179.84ms / p99 242.30ms;0 unknown/rejected/invalid/duplicates |
| Failed-run reconciliation |144990 initially ACKed +31894 subsequently reconciled =176884 confirmed; no unaccounted confirmed messages |
| serverD-local300/s60s,same1024 payload /1573 body |18000/18000 confirmed and uniquely ACKed;0 dropped/unknown/rejected/invalid/duplicates; p95 5.69ms / p99 10.83ms |
|660-second host observation across failed cross-cloud run |133 samples; minimum MemAvailable1265.23MiB; original six container identities/restart counts unchanged; no OOM |

Failed cross-cloud run: `load-6f60f4d6655e6151d214c19c-`. Reconciled remainder ID-set SHA256 `f196c37a194d42b429040d1aa3769de1e8c61dfd448b524c901f12831415389e`. Local comparison run: `load-58211f5f1dfdaa3f8b7b8565-`.

The measured Broker egress approached the purchased5Mbps limit; the local comparison supports a network bottleneck diagnosis. It is not a same-cloud sustained-capacity proof. No additional cross-cloud300/s run is scheduled after the user's direction.

## Remaining delivery gates

1. Finish main CI and prepare exact candidate image digests, rollback assets, private credentials/CA/routes and immutable deployment tooling.
2. Prepare actual database protection/recovery evidence for IAM41 and QS104/40. Retain the existing offline approval and paired-database protocol; synthetic test approvals are not production evidence. Neither migration has run in production.
3. Freeze approved QS ingress/message writes, gate Relay before claims, reconcile effective NSQ subscriptions and preserve disconnected history. Stop only the approved chain and NSQ, preserving all data and disabling NSQ automatic restart.
4. Start consumers before publishers; validate runtime SHA/provider/readiness, IAM policy/cache, submission/workers and AI command/result/receipt using the system account. No blind provider flip after first business RocketMQ publication.
5. Complete representative business mixed-load validation with all three original workers and24h postrestore observation. Preserve the deferred cross-cloud gate and repeat capacity validation after cloud co-location.

The current healthy Broker, SDK releases and green source checks do not mean the business cutover or M1 is complete.
