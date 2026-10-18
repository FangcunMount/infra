#!/usr/bin/env bash
# Restrict only serverD's two Docker-published RocketMQ ports. No policy reset.
set -euo pipefail
[[ $(id -u) = 0 ]] || { echo 'Root is required for the Docker forwarding filter.' >&2; exit 1; }
command -v iptables >/dev/null
command -v iptables-restore >/dev/null
iptables -w 10 -S DOCKER-USER >/dev/null
chain=INFRA-ROCKETMQ
bind_ip=100.118.164.39
iptables -w 10 -S "$chain" >/dev/null 2>&1 || iptables -w 10 -N "$chain"
# Atomic replacement of our owned chain; existing Docker/Swarm rules remain.
iptables-restore -w 10 --noflush <<'RULES'
*filter
:INFRA-ROCKETMQ - [0:0]
-F INFRA-ROCKETMQ
-A INFRA-ROCKETMQ -m conntrack --ctorigdstport 8081 -s 100.85.122.124 -j RETURN
-A INFRA-ROCKETMQ -m conntrack --ctorigdstport 8081 -s 100.91.31.24 -j RETURN
-A INFRA-ROCKETMQ -m conntrack --ctorigdstport 8081 -s 100.126.200.55 -j RETURN
-A INFRA-ROCKETMQ -s 100.118.164.39 -j RETURN
-A INFRA-ROCKETMQ -m conntrack --ctorigdstport 5557 -s 100.126.200.55 -j RETURN
-A INFRA-ROCKETMQ -j REJECT --reject-with tcp-reset
COMMIT
RULES
for port in 8081 5557; do
  rule=(-p tcp -m conntrack --ctdir ORIGINAL --ctorigdst "$bind_ip" --ctorigdstport "$port" -j "$chain")
  iptables -w 10 -C DOCKER-USER "${rule[@]}" 2>/dev/null || iptables -w 10 -I DOCKER-USER 1 "${rule[@]}"
done
echo 'RocketMQ forwarding filter installed for gRPC8081 and metrics5557 only.'
