# Owned ordinary-message acceptance probe

Run only against the explicitly provisioned `infra.rocketmq.load.v1` topic and `infra-load` group. It never publishes business messages or creates resources. Do not run overlapping probes on this shared acceptance group.

`-payload-bytes` measures the decoded payload; the report separately records actual `wire_bytes` at the Broker. Default1024-byte payload encodes to a1573-byte legacy envelope. `-wire-bytes` can request an exact body size by JSON whitespace padding; it rejects envelopes that already exceed that size. Neither mode includes RPC/TLS/ACK overhead. Keep the chosen sizes in the evidence; a smaller payload cannot satisfy a larger-payload gate.

Credentials and CA are explicit private files. For example, from the module directory:

```sh
go run . -endpoint PRIVATE_HOST:8081 -credentials /private/load.json -ca /private/ca.crt -duration 60s -rate 300
```

Scheduling is bounded: unsent local-capacity drops, confirmed publications, unknown outcomes, unique receives, ACKs and duplicates are reported independently. A failed run remains failed even if its remaining messages are subsequently drained.

To reconcile a known failed run, use its exact `run_id`, original payload size and confirmed-minus-uniquely-received count:

```sh
go run . -endpoint PRIVATE_HOST:8081 -credentials /private/load.json -ca /private/ca.crt -duration 5m -reconcile-run load-0123456789abcdef01234567- -remaining 100
```

Reconciliation publishes nothing and reports a sorted message-ID-set digest. It ACKs older messages on this owned test route; never point it at a business route. Unknown publication outcomes require separate reconciliation, not subtraction from a successful count.

serverD cross-cloud throughput testing is deferred by user direction on2026-10-18. Retain the failed5Mbps result in the M1 execution ledger. Do not run another sustained cross-cloud test without a new need or change of deployment topology.
