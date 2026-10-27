"""Add one native RPC mapping using the original Compose definition and image.

The caller owns admission timing, deployment lock and durable execution journal.
No store restore is performed. A recovery uses the same image and current store.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time


def run(args, *, timeout=60, required=True):
    result=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if required and result.returncode:raise RuntimeError('native_broker_command_failed')
    return result


def inspect(name):
    return json.loads(run(['docker','inspect',name]).stdout)[0]


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def critical(row):
    host=row['HostConfig'];config=row['Config']
    return dict(image=row['Image'],config={k:config.get(k) for k in
        ['Entrypoint','Cmd','User','WorkingDir','Hostname','Healthcheck','StopTimeout']},
        environment=dict(value.split('=',1) for value in config.get('Env',[])),
        resources={k:host.get(k) for k in ['Memory','NanoCpus','CpuShares','CpuPeriod','CpuQuota',
            'CpusetCpus','PidsLimit','ShmSize','IpcMode','Privileged','ReadonlyRootfs','Init',
            'RestartPolicy','LogConfig','SecurityOpt','CapAdd','CapDrop','Ulimits','ExtraHosts','Sysctls']},
        mounts=sorted((m['Type'],m['Source'],m['Destination'],m['RW'],m.get('Propagation','')) for m in row['Mounts']),
        networks={name:sorted(value.get('Aliases') or []) for name,value in row['NetworkSettings']['Networks'].items()},
        custom_labels={k:v for k,v in config.get('Labels',{}).items() if not k.startswith('com.docker.compose.')})


def ports(row):
    return {key:sorted((v['HostIp'],v['HostPort']) for v in values)
        for key,values in row['HostConfig']['PortBindings'].items()}


def override(path, before, bind_ip):
    if '10911/tcp' in ports(before):raise RuntimeError('native_port_already_present')
    value=dict(services=dict(broker=dict(hostname=before['Config']['Hostname'],
        ports=[dict(target=10911,published='10911',host_ip=bind_ip,protocol='tcp')])) )
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream,indent=2)
    return value


def healthy(name, timeout=150):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=inspect(name)
        if value['State']['Running'] and value['State'].get('Health',{}).get('Status')=='healthy':
            return value
        time.sleep(2)
    raise RuntimeError('native_broker_not_healthy')


def cold_backup(before, directory):
    if inspect(before['Name'].lstrip('/'))['State']['Running']:
        raise RuntimeError('cold_backup_requires_stopped_broker')
    sources={Path(m['Destination']).name:Path(m['Source']) for m in before['Mounts']
        if m['Destination'] in ['/etc/rocketmq','/home/rocketmq/store','/home/rocketmq/auth']}
    if set(sources)!={'rocketmq','store','auth'}:raise RuntimeError('exact_cold_backup_sources_required')
    archive=Path(directory)/'broker-before-native.tar'
    fd=os.open(archive,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'wb') as stream:
        with tarfile.open(fileobj=stream,mode='w') as target:
            for name,path in sorted(sources.items()):target.add(path,arcname=name)
        stream.flush();os.fsync(stream.fileno())
    with tarfile.open(archive) as source:
        members=source.getmembers()
        if not any(m.name.startswith('store/') for m in members):raise RuntimeError('empty_cold_backup')
        if any(m.issym() or m.islnk() for m in members):raise RuntimeError('unexpected_backup_link')
    return dict(path=str(archive),bytes=archive.stat().st_size,sha256=digest(archive),
        files=sum(m.isfile() for m in members),store_restored=False)


def add_native_port(before, original_compose, overlay, backup_directory, bind_ip, checkpoint):
    name=before['Name'].lstrip('/')
    if inspect(name)['Id']!=before['Id']:raise RuntimeError('broker_identity_changed')
    checkpoint('broker_stop_issued')
    run(['docker','stop','--time','90',name],timeout=110)
    checkpoint('broker_stopped')
    backup=cold_backup(before,backup_directory)
    checkpoint('cold_backup_verified',backup=backup)
    command=[*original_compose,'-f',str(overlay)]
    # The marker precedes the first start. After this point current store wins;
    # never replace it with the cold backup after accepted messages may exist.
    checkpoint('native_start_issued')
    run(command+['up','-d','--no-deps','--pull','never','broker'],timeout=100)
    after=healthy(name)
    old,new=critical(before),critical(after)
    if old!=new:
        raise RuntimeError('unapproved_broker_runtime_drift:'+','.join(key for key in old if old[key]!=new[key]))
    expected={**ports(before),'10911/tcp':[(bind_ip,'10911')]}
    if ports(after)!=expected:raise RuntimeError('unapproved_broker_port_drift')
    if after['Id']==before['Id']:raise RuntimeError('broker_not_recreated')
    checkpoint('native_broker_healthy',broker_id=after['Id'])
    return after,backup
