# Production Env Notes

`compose/env/prod/*.env` contains machine-specific values and is ignored by Git.
Keep the following network values consistent after each node joins Tailscale:

```env
INFRA_NETWORK_ENCRYPTED=false

# Replace with `tailscale ip -4` from each server.
NODE_A_IP=<serverA-ts-ip>
NODE_B_IP=<serverB-ts-ip>
NODE_C_IP=<serverC-ts-ip>
NODE_D_IP=<serverD-ts-ip>
```

Per-node conventions:

```env
# serverA.env
TAILSCALE_HOSTNAME=serverA

# serverB.env
TAILSCALE_HOSTNAME=serverB

# serverC.env
TAILSCALE_HOSTNAME=serverC

# serverD.env
TAILSCALE_HOSTNAME=serverD
NSQD_BROADCAST_ADDRESS=${NODE_D_IP}
```

Swarm must use the same Tailscale IP for both `advertise-addr` and `data-path-addr`.
Do not use public IPs or Mihomo proxy egress IPs for Swarm node addresses.
