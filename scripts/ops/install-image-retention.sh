#!/usr/bin/env bash
# Administrator entrypoint. Default: preview. Does not start apps or run cleanup.
set -Eeuo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
expected=53ec1f1e093aca37ad671a50d37203b87757f2daea7f78d03e96df7c51474324
host=${1:?host required: serverA/serverB/serverD}
deploy_account=${2:?existing deployment account required}
source_helper=${3:?reviewed image-retention.py required}
mode=${4:---preview}
[[ $# -le 4 && "$mode" =~ ^--(preview|apply)$ ]]
[[ "$deploy_account" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]
case "$host" in
  serverA) services=(iam qs-apiserver qs-collection-server qs-ai) ;;
  serverB) services=(qs-operating-system) ;;
  serverD) services=(qs-worker) ;;
  *) echo 'Unexpected host' >&2; exit 1 ;;
esac
[[ -f "$source_helper" && ! -L "$source_helper" ]]
[[ $(sha256sum "$source_helper" | cut -d ' ' -f1) == "$expected" ]]
helper=/usr/local/libexec/fangcun/image-retention.py
rules() {
  for service in "${services[@]}"; do
    printf '%s ALL=(root) NOPASSWD: /usr/bin/python3 -I %s --service %s --image-ref *\n' "$deploy_account" "$helper" "$service"
  done
}
if [[ "$mode" == --preview ]]; then
  printf 'PREVIEW ONLY: host=%s helper_sha256=%s; no installation, cleanup, app or DB operation\n' "$host" "$expected"
  rules
  exit 0
fi
[[ $(id -u) == 0 && $(hostname -s) == "$host" && $(id -u "$deploy_account") != 0 ]]
visudo -c >/dev/null
lock=/var/lib/fangcun-image-retention/deploy.lock
[[ ! -L "$lock" && $(readlink -f "$lock") == "$lock" && -f "$lock" ]]
[[ $(stat -c '%u:%a' "$(dirname "$lock")") == 0:755 && $(stat -c '%u:%a' "$lock") == 0:666 ]]
identity=$(stat -c '%d:%i' "$lock")
exec 9<"$lock"
flock -w 60 9
[[ $(stat -Lc '%d:%i' /proc/self/fd/9) == "$identity" && $(stat -c '%d:%i' "$lock") == "$identity" ]]
for directory in / /usr /usr/local /usr/local/libexec /usr/local/libexec/fangcun /etc /etc/sudoers.d; do
  if [[ -e "$directory" || -L "$directory" ]]; then
    [[ -d "$directory" && ! -L "$directory" && $(stat -c '%u' "$directory") == 0 ]]
    [[ -z $(find "$directory" -maxdepth 0 -perm /022 -print) ]]
  fi
done
install -d -o root -g root -m 0755 "$(dirname "$helper")"
temporary_helper=$(mktemp "$(dirname "$helper")/.retention.XXXXXX")
temporary_rules=$(mktemp /etc/sudoers.d/.qlume-retention.XXXXXX)
trap 'rm -f -- "$temporary_helper" "$temporary_rules"' EXIT
# Verify the copied root-owned bytes before publishing or making them readable.
install -o root -g root -m 0600 "$source_helper" "$temporary_helper"
[[ $(sha256sum "$temporary_helper" | cut -d ' ' -f1) == "$expected" ]]
rules > "$temporary_rules"
chmod 0440 "$temporary_rules"
visudo -c -f "$temporary_rules" >/dev/null
if [[ -e /etc/sudoers.d/qlume-image-retention || -L /etc/sudoers.d/qlume-image-retention ]]; then
  [[ ! -L /etc/sudoers.d/qlume-image-retention ]]
  cmp -s "$temporary_rules" /etc/sudoers.d/qlume-image-retention
fi
if [[ -e "$helper" || -L "$helper" ]]; then
  [[ -f "$helper" && ! -L "$helper" && $(stat -c '%u' "$helper") == 0 ]]
  old_sha=$(sha256sum "$helper" | cut -d ' ' -f1)
  install -o root -g root -m 0600 "$helper" "${helper%.py}.previous.$old_sha.py"
fi
chmod 0755 "$temporary_helper"
mv -T "$temporary_helper" "$helper"
mv -T "$temporary_rules" /etc/sudoers.d/qlume-image-retention
visudo -c >/dev/null
[[ $(stat -c '%d:%i' "$lock") == "$identity" ]]
printf 'Installed reviewed helper %s on %s; original lock inode retained. Cleanup NOT executed.\n' "$expected" "$host"
