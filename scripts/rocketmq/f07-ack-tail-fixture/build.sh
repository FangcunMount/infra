#!/usr/bin/env bash
set -euo pipefail

fixture=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
work=$(mktemp -d)
container=
cleanup() {
    if [[ -n "$container" ]]; then
        docker rm "$container" >/dev/null
    fi
    rm -rf -- "$work"
}
trap cleanup EXIT
cd "$work"

stock=rocketmq-readable:5.5.1
container=$(docker create --network none "$stock")
mkdir lib classes overlay checks
docker cp "$container:/opt/rocketmq/lib/." lib/
shasum -a 256 -c <<'HASH'
21b53ce3b4c5d749f869456310462c8f1ea2b505dc54eb2d510febc78969aba1  lib/rocketmq-broker-5.5.1.jar
ead65691c56eb843517ee156a160585ff14801cd5b720d3f37b4e992706d872a  lib/rocketmq-store-5.5.1.jar
HASH

source_base=https://raw.githubusercontent.com/apache/rocketmq/efa1be59d6fc747ad220f036c86030f05f0419f9
curl -fsSL --retry 3 --max-time 30 "$source_base/broker/src/main/java/org/apache/rocketmq/broker/processor/PopReviveService.java" -o PopReviveService.java
curl -fsSL --retry 3 --max-time 30 "$source_base/store/src/main/java/org/apache/rocketmq/store/timer/TimerMessageStore.java" -o TimerMessageStore.java
shasum -a 256 -c <<'HASH'
b45f3684c01e89e094cea9694e55e14aebe6b67f5e3cc34e754d2f071c424dbb  PopReviveService.java
2a675da4edc9d26323561883eb21a8168c7d0c0cb4ce7dca16684842cc13ae7d  TimerMessageStore.java
HASH
patch -f -F 0 -p1 < "$fixture/pop-revive.patch"
patch -f -F 0 -p1 < "$fixture/timer-recovery.patch"
shasum -a 256 -c <<'HASH'
28f10855534e60accca8ef0dc775d05dca2aa5949444407595290954275849ef  PopReviveService.java
414bad09be629e6f0f1498aceabc010a287ba0d7c3708b302e5cb5351e2dd882  TimerMessageStore.java
HASH

javac --release 8 -cp 'lib/*' -d classes PopReviveService.java TimerMessageStore.java
javac --release 8 -cp 'classes:lib/*' -d checks "$fixture/RetryIndexRegression.java"
java -cp 'checks:classes:lib/*' org.apache.rocketmq.broker.processor.RetryIndexRegression
cp lib/rocketmq-{broker,store}-5.5.1.jar overlay/
jar uf overlay/rocketmq-broker-5.5.1.jar -C classes org/apache/rocketmq/broker/processor
jar uf overlay/rocketmq-store-5.5.1.jar -C classes org/apache/rocketmq/store/timer
shasum -a 256 overlay/*.jar

docker build --pull=false --tag rocketmq-readable:f07-ack-tail --file - overlay <<'DOCKERFILE'
FROM rocketmq-readable:5.5.1
COPY rocketmq-broker-5.5.1.jar rocketmq-store-5.5.1.jar /opt/rocketmq/lib/
ENV JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS} -Dfangcun.standaloneReviveAppendCandidate=true -Dfangcun.standaloneTimerRecoveryCandidate=true"
DOCKERFILE
docker image inspect rocketmq-readable:f07-ack-tail --format '{{.Id}}'
