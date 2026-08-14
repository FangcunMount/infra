#!/usr/bin/env bash
set -Eeuo pipefail

network_name="${INFRA_NETWORK_NAME:-infra-network}"
expected_underlay_mtu="${INFRA_NETWORK_MTU:-1280}"
overlay_overhead="${INFRA_OVERLAY_OVERHEAD:-50}"
verify_container="${MTU_VERIFY_CONTAINER:-}"
verify_target="${MTU_VERIFY_TARGET:-}"
expected_endpoint_mtu=$((expected_underlay_mtu - overlay_overhead))

fail() {
  printf '[ERROR] %s\n' "$*" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail 'docker command is required'
command -v ip >/dev/null 2>&1 || fail 'ip command is required'
command -v nsenter >/dev/null 2>&1 || fail 'nsenter command is required'

docker network inspect "$network_name" >/dev/null 2>&1 ||
  fail "network $network_name is not visible on this node"

driver_mtu="$(docker network inspect "$network_name" \
  --format '{{ index .Options "com.docker.network.driver.mtu" }}')"
if [[ "$driver_mtu" != "$expected_underlay_mtu" ]]; then
  fail "network $network_name driver MTU=$driver_mtu, expected $expected_underlay_mtu; recreate the overlay network before continuing"
fi

tailscale_mtu="$(ip -o link show tailscale0 2>/dev/null |
  awk '{for (i=1; i<=NF; i++) if ($i == "mtu") {print $(i+1); exit}}')"
[[ -n "$tailscale_mtu" ]] || fail 'tailscale0 MTU is unavailable'
if (( expected_underlay_mtu > tailscale_mtu )); then
  fail "configured MTU=$expected_underlay_mtu exceeds tailscale0 MTU=$tailscale_mtu"
fi

printf '[OK] network=%s driver_mtu=%s tailscale_mtu=%s expected_endpoint_mtu=%s\n' \
  "$network_name" "$driver_mtu" "$tailscale_mtu" "$expected_endpoint_mtu"

containers=()
if [[ -n "$verify_container" ]]; then
  containers+=("$verify_container")
else
  while IFS= read -r container; do
    [[ -n "$container" ]] && containers+=("$container")
  done < <(docker ps --filter "network=$network_name" --format '{{.Names}}' | sort)
fi

(( ${#containers[@]} > 0 )) || fail "no running container attached to $network_name"

probe_pid=""
probe_container=""
for container in "${containers[@]}"; do
  pid="$(docker inspect --format '{{.State.Pid}}' "$container" 2>/dev/null)" ||
    fail "cannot inspect container $container"
  (( pid > 0 )) || fail "container $container is not running"

  endpoint_ip="$(docker inspect \
    --format "{{with index .NetworkSettings.Networks \"$network_name\"}}{{.IPAddress}}{{end}}" \
    "$container")"
  [[ -n "$endpoint_ip" ]] || fail "container $container is not attached to $network_name"

  endpoint_mtu="$(nsenter -t "$pid" -n ip -o addr show |
    awk -v ip="$endpoint_ip" '$0 ~ ("inet " ip "/") {for (i=1; i<=NF; i++) if ($i == "mtu") {print $(i+1); exit}}')"
  if [[ -z "$endpoint_mtu" ]]; then
    endpoint_if="$(nsenter -t "$pid" -n ip -o addr show |
      awk -v ip="$endpoint_ip" '$0 ~ ("inet " ip "/") {sub(/:$/, "", $2); print $2; exit}')"
    endpoint_mtu="$(nsenter -t "$pid" -n ip -o link show "$endpoint_if" |
      awk '{for (i=1; i<=NF; i++) if ($i == "mtu") {print $(i+1); exit}}')"
  fi
  [[ -n "$endpoint_mtu" ]] || fail "cannot resolve endpoint MTU for $container ($endpoint_ip)"
  if (( endpoint_mtu > expected_endpoint_mtu )); then
    fail "container $container endpoint MTU=$endpoint_mtu exceeds safe MTU=$expected_endpoint_mtu"
  fi
  printf '[OK] container=%s ip=%s endpoint_mtu=%s\n' "$container" "$endpoint_ip" "$endpoint_mtu"
  if [[ -z "$probe_pid" ]]; then
    probe_pid="$pid"
    probe_container="$container"
  fi
done

if [[ -n "$verify_target" ]]; then
  command -v tracepath >/dev/null 2>&1 || fail 'tracepath command is required when MTU_VERIFY_TARGET is set'

  target_ip=""
  if [[ "$verify_target" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    target_ip="$verify_target"
  else
    while IFS= read -r target_container; do
      endpoint="$(docker inspect \
        --format "{{with index .NetworkSettings.Networks \"$network_name\"}}{{.IPAddress}}|{{range .Aliases}}{{.}} {{end}}{{end}}" \
        "$target_container")"
      endpoint_ip="${endpoint%%|*}"
      endpoint_aliases="${endpoint#*|}"
      for endpoint_alias in $endpoint_aliases; do
        if [[ "$endpoint_alias" == "$verify_target" ]]; then
          target_ip="$endpoint_ip"
          break 2
        fi
      done
    done < <(docker ps --filter "network=$network_name" --format '{{.Names}}' | sort)
  fi

  if [[ -z "$target_ip" ]]; then
    target_ip="$(docker exec "$probe_container" getent ahostsv4 "$verify_target" 2>/dev/null |
      awk 'NR == 1 {print $1}' || true)"
  fi
  if [[ -z "$target_ip" ]]; then
    target_ip="$(nsenter -t "$probe_pid" -n getent ahostsv4 "$verify_target" 2>/dev/null |
      awk 'NR == 1 {print $1}' || true)"
  fi
  [[ -n "$target_ip" ]] || fail "cannot resolve MTU_VERIFY_TARGET=$verify_target"
  observed_pmtu="$(nsenter -t "$probe_pid" -n tracepath -n -m 4 "$target_ip" 2>/dev/null |
    awk '/pmtu/ {for (i=1; i<=NF; i++) if ($i == "pmtu") value=$(i+1)} END {print value}')"
  [[ -n "$observed_pmtu" ]] || fail "cannot observe PMTU to $verify_target ($target_ip)"
  if (( observed_pmtu > expected_endpoint_mtu )); then
    fail "PMTU to $verify_target is $observed_pmtu, expected <= $expected_endpoint_mtu"
  fi
  printf '[OK] target=%s ip=%s pmtu=%s\n' "$verify_target" "$target_ip" "$observed_pmtu"
fi
