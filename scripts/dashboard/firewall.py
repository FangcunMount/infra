"""Own only Dashboard's two published destinations in DOCKER-USER."""
import ipaddress
import json
import subprocess

CHAIN='INFRA-MQ-DASH'


def install(bind_ip, network):
    address=ipaddress.IPv4Address(bind_ip)
    if address not in ipaddress.ip_network('100.64.0.0/10'):
        raise ValueError('Tailscale bind required')
    value=json.loads(subprocess.check_output(['docker','network','inspect',network]))[0]
    if value['Driver']!='bridge' or len(value['IPAM']['Config'])!=1:
        raise ValueError('single owned Broker bridge required')
    bridge=value.get('Options',{}).get('com.docker.network.bridge.name') or 'br-'+value['Id'][:12]
    subnet=str(ipaddress.ip_network(value['IPAM']['Config'][0]['Subnet']))
    def run(*args,required=True):
        return subprocess.run(['iptables','--wait','10',*args],capture_output=True,check=required)
    if run('-S',CHAIN,required=False).returncode:
        run('-N',CHAIN)
    # Only our chain is replaced; existing RocketMQ/worker rules are untouched.
    run('-F',CHAIN)
    run('-A',CHAIN,'-p','tcp','-m','conntrack','--ctorigdstport','18082',
        '-i','tailscale0','-s','100.64.0.0/10','-j','ACCEPT')
    run('-A',CHAIN,'-p','tcp','-m','conntrack','--ctorigdstport','10911',
        '-i',bridge,'-s',subnet,'-j','ACCEPT')
    run('-A',CHAIN,'-j','REJECT','--reject-with','tcp-reset')
    for port in ('18082','10911'):
        rule=['-p','tcp','-m','conntrack','--ctorigdst',bind_ip,'--ctorigdstport',port,'-j',CHAIN]
        if run('-C','DOCKER-USER',*rule,required=False).returncode:
            run('-I','DOCKER-USER','1',*rule)
    return dict(private_bind=bind_ip,ui_tailscale_only=True,rpc_broker_bridge_only=True,
        existing_firewall_chains_preserved=True)
