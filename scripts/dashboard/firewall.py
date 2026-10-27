"""Own only Dashboard's two published destinations in DOCKER-USER."""
import ipaddress
import json
import subprocess
import argparse

CHAIN='INFRA-MQ-DASH'


def install(bind_ip, network, web_source='100.74.123.45'):
    address=ipaddress.IPv4Address(bind_ip)
    if address not in ipaddress.ip_network('100.64.0.0/10'):
        raise ValueError('Tailscale bind required')
    if ipaddress.IPv4Address(web_source) not in ipaddress.ip_network('100.64.0.0/10'):
        raise ValueError('Tailscale ingress source required')
    value=json.loads(subprocess.check_output(['docker','network','inspect',network]))[0]
    if value['Driver']!='bridge' or len(value['IPAM']['Config'])!=1:
        raise ValueError('single owned Broker bridge required')
    bridge=value.get('Options',{}).get('com.docker.network.bridge.name') or 'br-'+value['Id'][:12]
    subnet=str(ipaddress.ip_network(value['IPAM']['Config'][0]['Subnet']))
    def run(*args,required=True):
        return subprocess.run(['iptables','--wait','10',*args],capture_output=True,check=required)
    if not bridge.replace('-','').isalnum():
        raise ValueError('invalid bridge name')
    # Atomic replacement of this chain only, including on Docker restart.
    rules=['*filter', ':'+CHAIN+' - [0:0]', '-F '+CHAIN,
        f'-A {CHAIN} -p tcp -i lo -s {bind_ip}/32 -j ACCEPT',
        f'-A {CHAIN} -p tcp -m conntrack --ctorigdstport 18082 -i tailscale0 -s {web_source}/32 -j ACCEPT',
        f'-A {CHAIN} -p tcp -m conntrack --ctorigdstport 10911 -i {bridge} -s {subnet} -j ACCEPT',
        f'-A {CHAIN} -p tcp -j REJECT --reject-with tcp-reset', 'COMMIT', '']
    result=subprocess.run(['iptables-restore','--wait','10','--noflush'],
        input='\n'.join(rules).encode(),capture_output=True)
    if result.returncode:
        # Only this fixed, credential-free ruleset reaches iptables-restore.
        raise RuntimeError('scoped_rules_rejected: '+result.stderr.decode()[-1000:])
    for port in ('18082','10911'):
        rule=['-p','tcp','-m','conntrack','--ctorigdst',bind_ip,'--ctorigdstport',port,'-j',CHAIN]
        if run('-C','DOCKER-USER',*rule,required=False).returncode:
            run('-I','DOCKER-USER','1',*rule)
        # Docker's userland proxy can receive host-bound traffic through INPUT
        # without crossing DOCKER-USER. Protect that path as well as DNAT.
        local=['-p','tcp','-d',bind_ip,'--dport',port,'-j',CHAIN]
        if run('-C','INPUT',*local,required=False).returncode:
            run('-I','INPUT','1',*local)
    return dict(private_bind=bind_ip,web_ingress_source=web_source,ui_servera_only=True,rpc_broker_bridge_only=True,
        trusted_host_self_check=True,dnat_and_userland_proxy_protected=True,
        existing_firewall_chains_preserved=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind-ip',required=True)
    parser.add_argument('--network',default='rocketmq_rocketmq')
    parser.add_argument('--web-source',default='100.74.123.45')
    args=parser.parse_args()
    print(json.dumps(install(args.bind_ip,args.network,args.web_source)))
