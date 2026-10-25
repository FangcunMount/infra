#!/usr/bin/env bash
# Restrict only serverD's two Docker-published RocketMQ ports. No policy reset.
set -euo pipefail
[[ $(id -u) = 0 ]] || { echo 'Root is required for the Docker forwarding filter.' >&2; exit 1; }
command -v iptables >/dev/null
command -v iptables-restore >/dev/null
iptables -w 10 -S DOCKER-USER >/dev/null
chain=INFRA-ROCKETMQ
bind_ip=100.118.164.39
# The local worker network is a separate ingress from Tailscale. Derive its
# bridge only from the existing dedicated network; never trust an arbitrary
# interface, source CIDR or a newly attached non-worker container.
worker_bridge=$(python3 - <<'PY_BRIDGE'
import json
import re
import subprocess
import sys

p = subprocess.run(['docker', '--host', 'unix:///var/run/docker.sock',
                    'network', 'inspect', 'qs-network'],
                   capture_output=True, text=True, timeout=15)
if p.returncode:
    if 'qs-network' in p.stderr and ('not found' in p.stderr.lower() or 'no such network' in p.stderr.lower()):
        print('')  # Broker-only installation remains restricted to Tailscale.
        raise SystemExit(0)
    raise SystemExit('Worker network discovery unavailable; original filter retained')
rows = json.loads(p.stdout)
if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
    raise SystemExit('One reviewed worker network required')
n = rows[0]
if (n.get('Name') != 'qs-network' or n.get('Driver') != 'bridge' or n.get('Options')
        or not isinstance(n.get('Id'), str) or not re.fullmatch('[0-9a-f]{64}', n['Id'])
        or not isinstance(n.get('Containers'), dict)):
    raise SystemExit('Unexpected worker network identity; original filter retained')
for endpoint in n['Containers'].values():
    if not isinstance(endpoint, dict) or not re.fullmatch('qs-worker-runtime-[123]', endpoint.get('Name', '')):
        raise SystemExit('Non-worker member on dedicated bridge; original filter retained')
print('br-' + n['Id'][:12])
PY_BRIDGE
)
worker_rule=''
if [[ -n "$worker_bridge" ]]; then
  worker_rule="-A INFRA-ROCKETMQ -i $worker_bridge -p tcp -m conntrack --ctdir ORIGINAL --ctorigdst $bind_ip --ctorigdstport 8081 -m comment --comment infra-m3-local-qs-worker -j RETURN"
fi
iptables -w 10 -S "$chain" >/dev/null 2>&1 || iptables -w 10 -N "$chain"
# Atomic replacement of our owned chain; existing Docker/Swarm rules remain.
iptables-restore -w 10 --noflush <<RULES
*filter
:INFRA-ROCKETMQ - [0:0]
-F INFRA-ROCKETMQ
$worker_rule
-A INFRA-ROCKETMQ -m conntrack --ctorigdstport 8081 -s 100.85.122.124 -j RETURN
-A INFRA-ROCKETMQ -m conntrack --ctorigdstport 8081 -s 100.74.123.45 -j RETURN
-A INFRA-ROCKETMQ -m conntrack --ctorigdstport 8081 -s 100.91.31.24 -j RETURN
-A INFRA-ROCKETMQ -m conntrack --ctorigdstport 8081 -s 100.126.200.55 -j RETURN
-A INFRA-ROCKETMQ -s 100.118.164.39 -j RETURN
-A INFRA-ROCKETMQ -m conntrack --ctorigdstport 5557 -s 100.126.200.55 -j RETURN
-A INFRA-ROCKETMQ -p tcp -j REJECT --reject-with tcp-reset
COMMIT
RULES
for port in 8081 5557; do
  rule=(-p tcp -m conntrack --ctdir ORIGINAL --ctorigdst "$bind_ip" --ctorigdstport "$port" -j "$chain")
  iptables -w 10 -C DOCKER-USER "${rule[@]}" 2>/dev/null || iptables -w 10 -I DOCKER-USER 1 "${rule[@]}"
done
echo 'RocketMQ forwarding filter installed for gRPC8081 and metrics5557 only.'
