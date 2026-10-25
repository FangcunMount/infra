"""Read-before-write guards for reconnecting one original Compose endpoint.

Returns a reviewed command; never connects or starts a production container.
"""
import hashlib
import json


def require(value,reason):
    if not value:raise ValueError(reason)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def freeze(container,network,nameserver_id):
    return dict(broker_id=container['Id'],image=container['Image'],name=container['Name'],
        config_sha256=fingerprint(container['Config']),host_config_sha256=fingerprint(container['HostConfig']),
        network_id=network['Id'],network_name=network['Name'],
        network_sha256=fingerprint({k:network.get(k) for k in
            ('Id','Name','Driver','Scope','Internal','EnableIPv6','IPAM','Labels','Options')}),
        nameserver_id=nameserver_id)


def require_identity(container,network,expected):
    require(freeze(container,network,expected['nameserver_id'])==expected,'frozen_broker_or_network_changed')
    require(network['Driver']=='bridge' and network['Scope']=='local'
        and network['Labels'].get('com.docker.compose.network')=='rocketmq'
        and container['Config']['Labels'].get('com.docker.compose.project')
            ==network['Labels'].get('com.docker.compose.project')
        and container['Config']['Labels'].get('com.docker.compose.service')=='broker'
        and container['HostConfig']['NetworkMode']==network['Name']
        and expected['nameserver_id'] in network['Containers'],'original_compose_bridge_required')


def reconnect_arguments(container,network,expected):
    require_identity(container,network,expected)
    require(not container['State']['Running'] and container['State']['Status']=='exited',
            'stopped_original_broker_required')
    require(not container['NetworkSettings']['Networks'],'only_missing_endpoint_repair_allowed')
    return ['docker','--host','unix:///var/run/docker.sock','network','connect',
            '--alias','broker','--alias',container['Name'].lstrip('/'),network['Id'],container['Id']]


def require_attached(container,network,expected):
    require_identity(container,network,expected)
    actual=container['NetworkSettings']['Networks']
    if container['State']['Running']:
        require(set(actual)=={network['Name']} and actual[network['Name']]['NetworkID']==network['Id']
                and actual[network['Name']].get('IPAddress')
                and container['Id'] in network['Containers'],'exact_live_original_endpoint_required')
        endpoint=actual[network['Name']]
    else:
        # Docker stores a requested endpoint before starting its sandbox. When
        # connected by ID, the pending key can be that ID and NetworkID empty.
        require(len(actual)==1 and next(iter(actual)) in (network['Name'],network['Id']),
                'exact_original_endpoint_required_before_start')
        endpoint=next(iter(actual.values()))
        require(endpoint.get('NetworkID','') in ('',network['Id']),'pending_network_id_conflicts')
    require({'broker',container['Name'].lstrip('/')}<=set(endpoint.get('Aliases') or []),
            'original_broker_service_aliases_required')


def require_no_unplanned_restart(container):
    # A manual start/restart resets Docker's automatic-restart counter to zero.
    # Any automatic restart is failure, even when State.Running remains true.
    require(container['State']['Running'] and not container['State']['Restarting']
            and not container['State']['OOMKilled'] and container['RestartCount']==0,
            'unplanned_restart_or_exit_detected')
