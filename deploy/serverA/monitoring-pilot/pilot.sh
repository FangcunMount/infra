#!/usr/bin/env bash
set -euo pipefail

directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
script="$directory/pilot.sh"
expire=qlume-servera-monitoring-pilot-expire
refresh=qlume-servera-monitoring-pilot-refresh
discovery=/etc/infra-monitoring-pilot/discovery.json
operation=${1:?usage: pilot.sh start STOP_UTC [offline], stop [offline], or withdraw [offline]}
shift

if [[ "$operation" == start ]]; then
    stop_utc=${1:?set the signed UTC stop time}
    shift
fi

compose=(docker compose -f "$directory/compose.yml")
withdraw=(/bin/bash "$script" withdraw)
if [[ ${1-} == offline ]]; then
    compose+=(-f "$directory/offline.override.yml")
    withdraw+=(offline)
    shift
fi
if [[ $# != 0 ]]; then
    printf 'unexpected pilot argument\n' >&2
    exit 2
fi

case "$operation" in
    refresh)
        umask 022
        while :; do
            python3 -B "$directory/discover.py" --config "$discovery" || :
            sleep 15
        done
        ;;
    start|stop|withdraw) ;;
    *) exit 2 ;;
esac

# Start and both withdrawal paths act on the same Compose project.
exec 9>/run/lock/qlume-servera-monitoring-pilot.lock
flock -x 9

stop_pilot() {
    local containers id state refresh_state refresh_stopped=true
    if ! timeout --kill-after=2s 15s systemctl stop "$refresh.service"; then
        refresh_state=$(timeout --kill-after=2s 5s systemctl show --property=LoadState --value "$refresh.service") || refresh_state=unknown
        [[ "$refresh_state" == not-found ]] || refresh_stopped=false
    fi
    timeout --kill-after=2s 25s "${compose[@]}" stop -t 15 prometheus || return 1
    containers=$(timeout --kill-after=2s 5s "${compose[@]}" ps --all --quiet prometheus) || return 1
    if [[ -n "$containers" ]]; then
        while IFS= read -r id; do
            state=$(timeout --kill-after=2s 5s docker inspect --format '{{.State.Status}}' "$id") || return 1
            [[ "$state" == exited || "$state" == created ]] || return 1
        done <<< "$containers"
    fi
    [[ "$refresh_stopped" == true ]]
}

case "$operation" in
    stop)
        stop_pilot
        systemctl stop "$expire.timer"
        ;;
    withdraw)
        stop_pilot
        ;;
    start)
        umask 022
        stop_epoch=$(date --date="$stop_utc" +%s)
        [[ "$stop_epoch" -gt "$(date +%s)" ]] || exit 1
        if systemctl is-active --quiet "$expire.timer" || systemctl is-active --quiet "$refresh.service"; then
            printf 'pilot units are already active\n' >&2
            exit 1
        fi
        python3 -B "$directory/discover.py" --config "$discovery"
        systemd-run --unit="$expire" --on-calendar="$stop_utc" --timer-property=AccuracySec=1s \
            "${withdraw[@]}"

        rollback_start() {
            local result=$?
            if [[ "$result" != 0 ]]; then
                if ! stop_pilot; then
                    printf 'pilot stop could not be verified; inspect the expiry unit and container\n' >&2
                fi
            fi
        }
        trap rollback_start EXIT
        trap 'exit 129' HUP
        trap 'exit 130' INT
        trap 'exit 143' TERM

        timeout --kill-after=2s 5s systemctl is-active --quiet "$expire.timer"
        timeout --kill-after=2s 5s systemctl list-timers "$expire.timer"
        remaining=$((stop_epoch - $(date +%s)))
        [[ "$remaining" -gt 0 ]] || exit 1
        if [[ "$remaining" -gt 30 ]]; then
            remaining=30
        fi
        timeout --kill-after=2s "${remaining}s" "${compose[@]}" up -d --no-build --pull never prometheus
        remaining=$((stop_epoch - $(date +%s)))
        [[ "$remaining" -gt 0 ]] || exit 1
        timeout --kill-after=2s 10s systemd-run --unit="$refresh" --property=RuntimeMaxSec="${remaining}s" \
            /bin/bash "$script" refresh
        [[ "$stop_epoch" -gt "$(date +%s)" ]] || exit 1
        ;;
esac
