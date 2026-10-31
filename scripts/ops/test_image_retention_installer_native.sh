#!/usr/bin/env bash
# Only ephemeral, networkless test containers; no host mounts or production access.
set -Eeuo pipefail
image=${1:?reviewed isolated installer fixture image required}
for selector in DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH; do unset "$selector"; done
for host in serverA serverB serverD; do
  case "$host" in
    serverA) service=qs-ai; wrong=serverD ;;
    serverB) service=qs-operating-system; wrong=serverA ;;
    serverD) service=qs-worker; wrong=serverA ;;
  esac
  docker --host=unix:///var/run/docker.sock run --rm -i --network=none --hostname "$host" \
    --label qlume.retention-installer-test=true --entrypoint /bin/bash "$image" -s -- "$host" "$service" "$wrong" <<'NATIVE'
set -Eeuo pipefail
host=$1; service=$2; wrong=$3
lock=/var/lib/fangcun-image-retention/deploy.lock
before=$(stat -c %i "$lock")
bash /work/install.sh "$host" deploy /work/image-retention.py
test ! -e /usr/local/libexec/fangcun/image-retention.py
bash /work/install.sh "$host" deploy /work/image-retention.py --apply
test "$(stat -c %i "$lock")" = "$before"
test "$(stat -c %u:%a /usr/local/libexec/fangcun/image-retention.py)" = 0:755
sudo -u deploy sudo -n -l -- /usr/bin/python3 -I /usr/local/libexec/fangcun/image-retention.py --service "$service" --image-ref sha256:18a39e862a82bfb9b503a3dd93639688bc45016caa2c7f1bf9081953b4523fa0
if sudo -u deploy sudo -n -l -- /usr/bin/python3 -c 'print(1)'; then exit 91; fi
bash /work/install.sh "$host" deploy /work/image-retention.py --apply
test "$(stat -c %i "$lock")" = "$before"
cp /work/image-retention.py /work/wrong.py
echo changed >> /work/wrong.py
if bash /work/install.sh "$host" deploy /work/wrong.py --apply; then exit 92; fi
if bash /work/install.sh "$wrong" deploy /work/image-retention.py --apply; then exit 93; fi
echo "PASS $host preview/install/idempotence/inode/exact-policy/generic-python-denial/hash/host"
NATIVE
done
