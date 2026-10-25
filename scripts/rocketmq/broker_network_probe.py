"""Owned missing-endpoint reproduction and guarded same-network repair."""
import json
import time
from broker_recovery_network import freeze,require_attached,reconnect_arguments,require_no_unplanned_restart,require


def roundtrip(fixture,broker):
    run=fixture.run;network_name=fixture.network
    def inspect():return json.loads(run(['docker','inspect',broker]).stdout)[0]
    def net():return json.loads(run(['docker','network','inspect',network_name]).stdout)[0]
    original=inspect();ns=fixture.project+'-nameserver-1'
    nameserver=json.loads(run(['docker','inspect',ns]).stdout)[0]
    expected=freeze(original,net(),nameserver['Id'])
    run(['docker','stop','--time','90',broker],timeout=150)
    run(['docker','network','disconnect',network_name,broker])
    try:require_attached(inspect(),net(),expected)
    except ValueError:pass
    else:raise ValueError('missing_network_did_not_block_start')
    # Deliberately bypass the guard only in this owned fixture to reproduce the incident.
    run(['docker','start',broker])
    deadline=time.monotonic()+25
    while time.monotonic()<deadline and inspect()['State']['Running']:time.sleep(1)
    failed=inspect();logs=run(['docker','logs',broker],required=False);raw=logs.stdout+logs.stderr
    require(not failed['State']['Running'] and failed['State']['ExitCode']==1
            and 'StackOverflowError' in raw and raw.count('MixAll.getLocalhostByNetworkInterface')>10,
            'actual_disconnected_mixall_recursion_not_reproduced')
    run(reconnect_arguments(failed,net(),expected))
    pending=inspect()['NetworkSettings']['Networks']
    fixture.report['pending_endpoint_readback']={k:{field:v.get(field) for field in
        ('NetworkID','Aliases','IPAddress')} for k,v in pending.items()}
    require_attached(inspect(),net(),expected)
    run(['docker','start',broker]);deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        current=inspect();require_attached(current,net(),expected);require_no_unplanned_restart(current)
        if current['State'].get('Health',{}).get('Status')=='healthy':break
        time.sleep(3)
    else:raise ValueError('reconnected_broker_health_timeout')
    current=inspect();require(current['Id']==original['Id'],'original_broker_replaced')
    after_ns=json.loads(run(['docker','inspect',ns]).stdout)[0]
    require(after_ns['Id']==nameserver['Id'] and after_ns['State']['StartedAt']==nameserver['State']['StartedAt'],
            'nameserver_restarted_or_replaced')
    return dict(missing_endpoint_blocks_admission=True,actual_disconnected_mixall_stack_overflow_reproduced=True,
        same_original_network_and_container_repaired=True,reconnected_broker_healthy_without_automatic_restart=True)
