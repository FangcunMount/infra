#!/usr/bin/env python3
"""Read-only native TX limit index export. Exports index metadata only; never exports message bodies.

Use an explicitly identified infra Compose project. Never changes Broker config,
ACL, evidence or messages. The caller decides admission/recovery separately.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

TOPIC = 'TRANS_CHECK_MAX_TIME_TOPIC'


def parse_index(output, key):
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', key):
        raise ValueError('bounded index key required')
    records = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 4 or not re.fullmatch(r'[0-9A-Fa-f]{32,64}', fields[0]):
            continue
        if not fields[1].isdigit() or not fields[2].isdigit():
            continue
        index = fields[3].split('@')
        if (len(index) != 6 or index[1:4] != [TOPIC, 'K', key]
                or index[4] != fields[0] or not index[0].isdigit() or not index[5].isdigit()):
            raise RuntimeError('unexpected pinned native limit index format')
        records.append({'broker_message_id':fields[0], 'queue_id':int(fields[1]),
                        'queue_offset':int(fields[2]),'commitlog_offset':int(index[5]),
                        'index_hour':int(index[0])})
    return {'topic':TOPIC,'key_sha256':hashlib.sha256(key.encode()).hexdigest(),
            'records':records,'raw_admin_sha256':hashlib.sha256(output.encode()).hexdigest(),
            'read_only':True,'body_exported':False,
            'truncated_possible':len(records)==64,
            'alert':'native_transaction_check_limit_reached' if records else None,
            'severity':'critical' if records else None}


def write_private(path, report):
    # Atomic create, no symlink following and no replacement of existing audit.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')


def export(container, project, key, output):
    parse_index("", key)
    if not re.fullmatch(r'[a-z0-9-]{1,80}', container) or not re.fullmatch(r'[a-z0-9-]{1,80}', project):
        raise ValueError('explicit Compose identity required')
    def run(arguments):
        try:
            result = subprocess.run(arguments, capture_output=True, text=True, timeout=45)
        except (subprocess.TimeoutExpired, OSError):
            raise RuntimeError('private read-only audit unavailable') from None
        if result.returncode:
            raise RuntimeError('private read-only audit failed')
        return result.stdout
    label = run(['docker','inspect','--format',
                 '{{index .Config.Labels "com.docker.compose.project"}}',container]).strip()
    if label != project:
        raise RuntimeError('Compose project mismatch')
    # QueryMsgByKeySubCommand 5.5.1 prints only the index table; not queryMsgById.
    raw = run(['docker','exec',container,'java','-Xms32m','-Xmx128m',
               '-XX:MaxDirectMemorySize=32m','-cp','/opt/rocketmq/conf:/opt/rocketmq/lib/*',
               'org.apache.rocketmq.tools.command.MQAdminStartup','queryMsgByKey',
               '-n','nameserver:9876','-t',TOPIC,'-k',key,'-m','64'])
    report = parse_index(raw,key)
    if not report['records']:
        raise RuntimeError('native transaction limit index evidence absent')
    write_private(output,report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('container','project','key'):
        parser.add_argument('--'+field,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    report = export(args.container,args.project,args.key,args.output)
    print(json.dumps({'records':len(report['records']),'read_only':True,'body_exported':False,
            'truncated_possible':len(records)==64,
            'alert':'native_transaction_check_limit_reached' if records else None,
            'severity':'critical' if records else None}))


if __name__ == '__main__':
    main()
