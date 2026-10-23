#!/usr/bin/env python3
"""Read-only keyed DLQ index export for one explicit canonical v2 subscription.

No bodies, replay, consumer offsets, resource provisioning or database selection.
A shared group lists candidate owners; its index does not prove one owner.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from audit_transaction_limit import write_private
from routes import validate_v2

MAX_RECORDS = 64


def select_route(manifest, route_id):
    try:
        if not isinstance(manifest,dict):
            raise ValueError('canonical v2 manifest required')
        validate_v2(manifest)
    except (ValueError,TypeError,KeyError,AttributeError):
        raise ValueError('canonical v2 manifest required') from None
    routes = [r for r in manifest['routes'] if r['id'] == route_id]
    if len(routes) != 1 or not routes[0].get('consumer_group'):
        raise ValueError('one explicit subscribed v2 route required')
    group = routes[0]['consumer_group']
    if not re.fullmatch(r'rmq2_g_[0-9a-f]{32}', group):
        raise ValueError('canonical v2 group required')
    owners = sorted({r['owner'] for r in manifest['routes'] if r.get('consumer_group') == group})
    return dict(topic='%DLQ%'+group, route_id=route_id,
                candidate_owners=owners, owner_scope_ambiguous=len(owners)>1)


def parse_index(output, key, topic):
    if (not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', key)
            or not re.fullmatch(r'%DLQ%rmq2_g_[0-9a-f]{32}', topic)):
        raise ValueError('explicit bounded key and v2 native DLQ topic required')
    if len(output.encode()) > 1048576:
        raise RuntimeError('bounded private index response required')
    records, seen, header = [], set(), False
    for line in output.splitlines():
        fields = line.split()
        if fields == ['#Message','ID','#QID','#Offset','#IndexKey']:
            header = True
            continue
        if len(fields) != 4 or not re.fullmatch(r'[0-9A-Fa-f]{32,64}', fields[0]):
            continue
        index = fields[3].split('@')
        if (not header or len(index) != 6 or index[1:4] != [topic,'K',key]
                or index[4] != fields[0]
                or not all(value.isascii() and value.isdecimal()
                           for value in (fields[1],fields[2],index[0],index[5]))
                or any(int(value) > 2**63-1 for value in (fields[1],fields[2],index[0],index[5]))
                or fields[0] in seen or len(records) >= MAX_RECORDS):
            raise RuntimeError('unexpected pinned native index response')
        seen.add(fields[0])
        records.append(dict(broker_message_id=fields[0],queue_id=int(fields[1]),
            queue_offset=int(fields[2]),index_hour=int(index[0]),commitlog_offset=int(index[5])))
    if not header:
        raise RuntimeError('authoritative native index header absent')
    return dict(topic=topic,key_sha256=hashlib.sha256(key.encode()).hexdigest(),records=records,
        raw_admin_sha256=hashlib.sha256(output.encode()).hexdigest(),read_only=True,
        body_exported=False,truncated_possible=len(records)==MAX_RECORDS,
        query_scope='one_key_one_group_not_global_inventory',
        alert='native_dead_letter_records' if records else None,
        severity='critical' if records else None)


def export(container, project, manifest_file, route_id, key, output):
    with manifest_file.open('rb') as stream:
        raw = stream.read(1048577)
    if len(raw) > 1048576:
        raise ValueError('bounded manifest required')
    selection = select_route(json.loads(raw),route_id)
    parse_index('#Message ID #QID #Offset #IndexKey',key,selection['topic'])
    if any(not re.fullmatch(r'[a-z0-9-]{1,80}', value) for value in (container,project)):
        raise ValueError('explicit Compose identity required')

    def run(arguments):
        try:
            result = subprocess.run(arguments,capture_output=True,text=True,timeout=45)
        except (subprocess.TimeoutExpired,OSError):
            raise RuntimeError('private read-only index unavailable') from None
        if (result.returncode or len(result.stdout.encode()) > 1048576
                or len(result.stderr.encode()) > 1048576
                or 'Exception' in result.stdout+result.stderr
                or 'command failed' in result.stdout+result.stderr):
            raise RuntimeError('private read-only index unavailable')
        return result.stdout

    label = run(['docker','inspect','--format',
        '{{index .Config.Labels "com.docker.compose.project"}}',container]).strip()
    if label != project:
        raise RuntimeError('Compose project mismatch')
    raw_index = run(['docker','exec',container,'java','-Xms32m','-Xmx128m',
        '-XX:MaxDirectMemorySize=32m','-cp','/opt/rocketmq/conf:/opt/rocketmq/lib/*',
        'org.apache.rocketmq.tools.command.MQAdminStartup','queryMsgByKey',
        '-n','nameserver:9876','-t',selection['topic'],'-k',key,'-m',str(MAX_RECORDS)])
    report = parse_index(raw_index,key,selection['topic'])
    report.update(selection,manifest_sha256=hashlib.sha256(raw).hexdigest(),index_format_version='rocketmq-5.5.1-queryMsgByKey')
    write_private(output,report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('container','project','route','key'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    try:
        report = export(args.container,args.project,args.manifest,args.route,args.key,args.output)
    except (RuntimeError,ValueError,OSError,KeyError,TypeError):
        print(json.dumps(dict(status='unavailable',read_only=True,body_exported=False)))
        return 1
    print(json.dumps(dict(records=len(report['records']),read_only=True,body_exported=False,
        truncated_possible=report['truncated_possible'],owner_scope_ambiguous=report['owner_scope_ambiguous'],
        alert=report['alert'],severity=report['severity'])))
    return 2 if report['records'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
