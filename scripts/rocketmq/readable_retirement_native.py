"""Deletion semantics proof for selected empty CI resources only.

This is deliberately not a production retirement executor. It requires the
owned loopback fixture, complete successful native resource acceptance, exact
old/new ACL union, one Broker and an old Topic whose actual offsets are zero.
"""
import hashlib
import re
import secrets
import subprocess
import time

from provision_v2 import Admin, preflight
from readable_transition import digest, validate_transition


def command(admin, operation, *args, success=None):
    raw = admin.docker('java', '-Xms32m', '-Xmx128m', '-XX:MaxDirectMemorySize=32m', '-cp',
        '/opt/rocketmq/conf:/opt/rocketmq/lib/*', 'org.apache.rocketmq.tools.command.MQAdminStartup',
        operation, *args).stdout
    if 'Exception' in raw or 'command failed' in raw or (success and success not in raw):
        raise RuntimeError('owned retirement command incomplete')
    return raw


def empty_topic(output):
    header = False
    rows = []
    for line in output.splitlines():
        if line.startswith('#Broker Name'):
            header = True
        elif header and line.strip() and not line.startswith('Topic Put TPS:'):
            parts = line.split()
            if len(parts) < 4 or not all(re.fullmatch(r'[0-9]+', n) for n in parts[1:4]):
                raise RuntimeError('unrecognized owned Topic offset snapshot')
            rows.append(parts)
    if len(rows) != 1 or rows[0][1:4] != ['0', '0', '0']:
        raise RuntimeError('owned old Topic is not proven empty')


def single_cluster(output):
    header = False
    rows = []
    for line in output.splitlines():
        if line.startswith('#Cluster Name'):
            header = True
        elif header and line.strip():
            rows.append(line.split())
    if (len(rows) != 1 or rows[0][:4] !=
            ['FangcunMount', 'serverd-rocketmq', '0', '127.0.0.1:10911']):
        raise RuntimeError('owned single Broker membership differs')


def retry_v2_parameter(raw):
    rows = re.findall(r'^\s*enableRetryTopicV2\s*=\s*(true|false)\s*$', raw, re.MULTILINE)
    if len(rows) != 1:
        raise RuntimeError('one authoritative POP retry setting required')
    return rows[0] == 'true'


def generate_owned_pop_v2(container, project, invoke):
    # Internal v2 retry creation is disabled by the pinned Broker default. Enable
    # only inside this verified disposable project, retain until revive creates
    # its resource, then restore the effective original setting before deletion.
    import os
    from final_image_candidate import ci_guard
    ci_guard(os.environ)
    if not re.fullmatch(r'rocketmq-m2-[0-9a-f]{12}', project):
        raise RuntimeError('owned isolated POP control project required')
    identity = subprocess.run(['docker', 'inspect', '--format',
        '{{index .Config.Labels "com.docker.compose.project"}}', container],
        capture_output=True, text=True, timeout=15)
    if identity.returncode or identity.stdout.strip() != project:
        raise RuntimeError('owned isolated POP control Broker differs')
    admin = Admin(container)
    before = retry_v2_parameter(admin('getBrokerConfig'))
    snapshot = '/tmp/readable-pop-control-' + secrets.token_hex(6)
    admin.docker('mkdir', '-m', '700', snapshot)
    try:
        if not before:
            command(admin, 'updateBrokerConfig', '-b', '127.0.0.1:10911',
                '-k', 'enableRetryTopicV2', '-v', 'true', success='update broker config success, ')
        if not retry_v2_parameter(admin('getBrokerConfig')):
            raise RuntimeError('owned POP v2 control setting not effective')
        row = invoke()
        deadline = time.monotonic() + 90
        while row['retry_topic'] not in admin.metadata(snapshot)['topicConfigTable']:
            if time.monotonic() >= deadline:
                raise RuntimeError('actual POP v2 retry was not created by Broker revive')
            time.sleep(1)
    finally:
        try:
            if not before:
                command(admin, 'updateBrokerConfig', '-b', '127.0.0.1:10911',
                    '-k', 'enableRetryTopicV2', '-v', 'false', success='update broker config success, ')
            if retry_v2_parameter(admin('getBrokerConfig')) != before:
                raise RuntimeError('owned original POP v2 setting not restored')
        finally:
            for name in ('topic.json', 'subscriptionGroup.json'):
                admin.docker('rm', '-f', '--', snapshot + '/' + name, required=False)
            admin.docker('rmdir', snapshot, required=False)
    return row, dict(before=before, during=True, after=before, restored=True, production=False)


def run_owned_retirement(container, project, previous, current, accounts, receipt, *, pop_v2_sentinel=None):
    validate_transition(previous, current)
    if (not re.fullmatch(r'rocketmq-m2-[0-9a-f]{12}', project)
            or receipt.get('failed') != 0 or receipt.get('skipped') != 0
            or receipt.get('passed') != 130):
        raise RuntimeError('complete owned native resource acceptance required')
    admin = Admin(container)
    # The Docker label is authoritative; no production project is accepted.
    identity = subprocess.run(['docker', 'inspect', '--format',
        '{{index .Config.Labels "com.docker.compose.project"}}', container],
        capture_output=True, text=True, timeout=15)
    if identity.returncode or identity.stdout.strip() != project:
        raise RuntimeError('owned isolated Broker identity differs')
    snapshot = '/tmp/readable-retirement-' + secrets.token_hex(6)
    admin.docker('mkdir', '-m', '700', snapshot)
    try:
        metadata = admin.metadata(snapshot)
        users = admin.users()
        acls = {a['username']: admin.acl(a['username']) for a in accounts.values()}
        if preflight(current, accounts, metadata, users, acls, previous=previous) != ([], [], [], []):
            raise RuntimeError('complete exact owned old/new resource union required')
        membership = command(admin, 'clusterList', '-n', 'nameserver:9876')
        single_cluster(membership)
        topic = previous['routes'][0]['physical_topic']
        group = next(r['consumer_group'] for r in previous['routes'] if r.get('consumer_group'))
        offsets = command(admin, 'topicStatus', '-n', 'nameserver:9876', '-t', topic)
        empty_topic(offsets)
        # Classic/v1 empty sentinels plus a real unselected v2 retry responsibility
        # make accidental cleanup observable inside this isolated project only.
        unselected_topic = next(r['physical_topic'] for r in previous['routes'] if r['physical_topic'] != topic)
        from pop_retry_sentinel import receipt as sentinel_receipt, MARKER
        import json
        sentinel_route = next(r for r in current['routes'] if r['topic'] == 'qs.survey.lifecycle'
                              and r['message_type'] == 'NORMAL' and r.get('subscription') == 'qs-worker')
        sentinel_receipt(MARKER + json.dumps(pop_v2_sentinel), sentinel_route)
        pop_v2_topic = pop_v2_sentinel['retry_topic']
        # '+' is reserved to internal POP creation and rejected by updateTopic.
        # Require the actual revive path from a real unacked delivery instead.
        deadline = time.monotonic() + 90
        while pop_v2_topic not in metadata['topicConfigTable']:
            if time.monotonic() >= deadline:
                raise RuntimeError('actual POP v2 retry was not created by Broker revive')
            time.sleep(1)
            metadata = admin.metadata(snapshot)
        sentinels = ['%RETRY%' + group, '%DLQ%' + group,
                     '%RETRY%' + group + '_' + unselected_topic]
        if any(name in metadata['topicConfigTable'] for name in sentinels):
            raise RuntimeError('owned sentinel already exists')
        for name in sentinels:
            admin('updateTopic', '-t', name, '-r', '1', '-w', '1', '-p', '6',
                  '-a', '+message.type=NORMAL', mutation=True)
        before = admin.metadata(snapshot)
        for role, account in sorted(accounts.items()):
            for resource in ('Topic:' + topic, 'Group:' + group):
                if resource in acls[account['username']]:
                    admin('deleteAcl', '-s', 'User:' + account['username'], '-r', resource, mutation=True)
        admin('deleteSubGroup', '-g', group, '-r', 'true', mutation=True)
        from readable_retirement import pop_retry_companions
        live = admin.metadata(snapshot)
        if pop_retry_companions(topic, live['topicConfigTable']):
            raise RuntimeError('owned selected Topic has protected POP retry companions')
        single_cluster(command(admin, 'clusterList', '-n', 'nameserver:9876'))
        raw = command(admin, 'deleteTopic', '-n', 'nameserver:9876', '-c', 'FangcunMount', '-t', topic,
                      success=f'delete topic [{topic}] from NameServer success.')
        if f'delete topic [{topic}] from cluster [FangcunMount] success.' not in raw:
            raise RuntimeError('owned Broker Topic deletion not confirmed')
        after = admin.metadata(snapshot)
        expected = {key: dict(value) for key, value in before.items()}
        del expected['topicConfigTable'][topic]
        del expected['subscriptionGroupTable'][group]
        if after != expected:
            raise RuntimeError('owned retirement changed an unselected resource')
        listed = command(admin, 'topicList', '-n', 'nameserver:9876').splitlines()
        if topic in {line.strip() for line in listed}:
            raise RuntimeError('owned Topic retained NameServer route')
        for account in accounts.values():
            expected_acl = dict(acls[account['username']])
            expected_acl.pop('Topic:' + topic, None)
            expected_acl.pop('Group:' + group, None)
            if admin.acl(account['username']) != expected_acl:
                raise RuntimeError('owned retirement changed an unselected permission')
        return dict(passed=4, failed=0, skipped=0, cases=dict(
            named_old_acl_only=True, named_group_preserves_retry_dlq=True,
            named_topic_removed_from_broker_and_nameserver=True, all_other_resources_preserved=True),
            selected_topic=topic, selected_group=group, retained_sentinels=sentinels + [pop_v2_topic],
            pop_v2_generation=pop_v2_sentinel,
            membership_sha256=hashlib.sha256(membership.encode()).hexdigest(),
            offsets_sha256=hashlib.sha256(offsets.encode()).hexdigest(),
            before_metadata_sha256=digest(before), after_metadata_sha256=digest(after),
            scope='selected empty owned CI resources only; unselected actual POP v2 responsibility retained; no production authorization')
    finally:
        for name in ('topic.json', 'subscriptionGroup.json'):
            admin.docker('rm', '-f', '--', snapshot + '/' + name, required=False)
        admin.docker('rmdir', snapshot, required=False)
