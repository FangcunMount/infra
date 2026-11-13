#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
work=$(mktemp -d)
engine=
cleanup() {
    if [[ -n $engine ]]; then
        docker rm -fv "$engine" >/dev/null
    fi
    rm -rf "$work"
}
trap cleanup EXIT

candidate=$(docker compose -f "$root/deploy/serverA/monitoring/compose.yml" config --format json |
    jq -er '.services["query-bridge"].image')
python3 "$root/scripts/monitoring/export-query-bridge-oci.py" "$candidate" "$work/query-bridge.tar" > "$work/expected.json"
# SHA-256 of the decompressed tar sealed on MacBook and ServerA.
printf '%s  %s\n' 6cc514a24ea07faa4b0a8a140312d4a19124d0f25b229ae3c0deeb11cee78cbc "$work/query-bridge.tar" |
    sha256sum --check --strict

# ServerA uses amd64 Engine 29.1.3 with containerd's overlayfs snapshotter.
engine=$(docker run -d --privileged --network none --entrypoint dockerd \
    docker.io/library/docker@sha256:64d6ee47ea821c986467199baa162f5ac8cde3f57b719f18e23f3ed7a7444131 \
    --host=unix:///var/run/docker.sock --bridge=none --iptables=false --ip6tables=false \
    --ip-forward=false --ip-masq=false)
for attempt in {1..30}; do
    if docker exec "$engine" docker info --format '{{json .}}' > "$work/engine.json" 2>/dev/null; then
        break
    fi
    if [[ $attempt == 30 ]]; then
        docker logs "$engine" >&2
        exit 1
    fi
    sleep 1
done
jq -e '.ServerVersion=="29.1.3" and .Architecture=="x86_64" and .Driver=="overlayfs" and
    any(.DriverStatus[]; .==["driver-type","io.containerd.snapshotter.v1"])' "$work/engine.json"
test -z "$(docker exec "$engine" docker image ls --quiet)"
docker exec -i "$engine" docker image load --platform linux/amd64 < "$work/query-bridge.tar"
docker exec "$engine" docker image inspect "$candidate" > "$work/actual.json"
jq -e --slurpfile expected "$work/expected.json" '
    $expected[0] as $wanted | .[0] |
    .Id==$wanted.manifest and .Descriptor.digest==$wanted.manifest and
    .Os=="linux" and .Architecture=="amd64" and .RootFS.Layers==$wanted.layers and
    any(.RepoTags[]; .==($wanted.tag | sub("^docker.io/library/"; ""))) and
    any(.RepoDigests[]; .==("nginx@" + $wanted.manifest))
' "$work/actual.json"
docker exec "$engine" docker run --rm --pull never --network none --read-only --entrypoint nginx "$candidate" -v
