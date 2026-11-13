#!/usr/bin/env bash
# Runs on a dedicated GitHub-hosted Linux runner. The expiry uses real systemd.
set -euo pipefail

profile="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../deploy/serverA/monitoring-pilot" && pwd -P)"
work=$(mktemp -d)
project=qlume-servera-monitoring-pilot
expire="$project-expire"
refresh="$project-refresh"
compose=(docker compose -f "$work/compose.yml" -f "$work/offline.override.yml")
network="$project-ci-network"
volume="$project-ci-data"

cleanup() {
    systemctl stop "$expire.timer" "$expire.service" "$refresh.service" || :
    "${compose[@]}" down || :
    docker volume rm "$volume" || :
    docker network rm "$network" || :
    rm -rf -- "$work"
}
trap cleanup EXIT

cp "$profile"/{pilot.sh,compose.yml,prometheus.yml} "$work/"
install -d -m 755 "$work/targets"
printf '[]\n' | tee "$work"/targets/{serverA,serverD}.json >/dev/null
# Discovery authorization is verified separately with the real OpenSSH fixture.
printf 'raise SystemExit(0)\n' > "$work/discover.py"
cat > "$work/offline.override.yml" <<YAML
services:
  prometheus:
    volumes:
      - type: bind
        source: $work/targets
        target: /etc/prometheus/targets
        read_only: true
        bind:
          create_host_path: false
networks:
  backend:
    name: $network
volumes:
  data:
    name: $volume
YAML

docker network create --internal "$network"
docker volume create "$volume"
image=$("${compose[@]}" config --images)
docker image inspect "$image" >/dev/null

stop_utc=$(date -u --date='+35 seconds' '+%Y-%m-%d %H:%M:%S UTC')
/bin/bash "$work/pilot.sh" start "$stop_utc" offline
container=$("${compose[@]}" ps --quiet prometheus)
[[ -n "$container" ]]
[[ "$(docker inspect --format '{{.State.Status}}' "$container")" == running ]]
systemctl is-active --quiet "$expire.timer"
systemctl is-active --quiet "$refresh.service"
poll_until=$((SECONDS + 80))
while [[ "$(docker inspect --format '{{.State.Status}}' "$container")" != exited ]]; do
    [[ "$SECONDS" -lt "$poll_until" ]] || exit 1
    sleep 1
done
[[ "$(docker inspect --format '{{.State.Status}}' "$container")" == exited ]]
[[ "$(docker inspect --format '{{.State.ExitCode}}' "$container")" == 0 ]]
finished=$(docker inspect --format '{{.State.FinishedAt}}' "$container")
deadline_epoch=$(date --date="$stop_utc" +%s)
finished_epoch=$(date --date="$finished" +%s)
[[ "$finished_epoch" -ge "$deadline_epoch" && "$finished_epoch" -le "$((deadline_epoch + 25))" ]]
if systemctl is-active --quiet "$refresh.service"; then
    exit 1
fi
docker volume inspect "$volume" >/dev/null
/bin/bash "$work/pilot.sh" stop offline
docker volume inspect "$volume" >/dev/null
printf 'systemd expiry stopped container %s at %s (signed deadline %s) and retained %s\n' \
    "$container" "$finished" "$stop_utc" "$volume"
