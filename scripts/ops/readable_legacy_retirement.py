"""Explicit v1 catalog retirement review, separate from the typed v2 planner.

Pure review only. Production must independently collect and recheck each named
object under the original locks. No prefix discovery or MQ execution is offered.
"""
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'rocketmq'))
from nsq_drain_evidence import stamp
from readable_retirement import COUNTERS, SHA, SUBJECT, pop_retry_companions, require, resources
from readable_transition import digest
from routes import validate


def permissions(manifest, account):
    topics = {row['topic']: row['physical_topic'] for row in manifest['routes']}
    subscriptions = {(row['topic'], row.get('subscription')): row
                     for row in manifest['routes'] if row.get('consumer_group')}
    result = {}
    for topic in account.get('publish', []):
        result.setdefault('Topic:' + topics[topic], set()).update(('Pub', 'Get'))
    for logical, subscription in account.get('subscriptions', []):
        route = subscriptions[(logical, subscription)]
        result.setdefault('Topic:' + route['physical_topic'], set()).update(('Sub', 'Get'))
        result.setdefault('Group:' + route['consumer_group'], set()).update(('Sub', 'Get'))
    return result


def review(previous, current, subjects, selected, evidence, now):
    require(previous.get('version') == 1 and current.get('version') == 3,
            'explicit canonical v1 catalog and active v3 required')
    validate(previous); validate(current)
    require(isinstance(subjects, dict) and set(subjects) == set(previous['accounts'])
            and all(isinstance(x, str) and SUBJECT.fullmatch(x) for x in subjects.values())
            and len(set(subjects.values())) == len(subjects), 'exact legacy subjects required')
    old, active = resources(previous), resources(current)
    require(isinstance(selected, list) and selected
            and all(isinstance(x, str) for x in selected)
            and len(set(selected)) == len(selected) and set(selected) <= old
            and not set(selected) & active, 'individually named legacy objects only')
    require(evidence.get('schema') == 'readable-retirement-observations/v1'
            and evidence.get('previous_manifest_sha256') == digest(previous)
            and evidence.get('active_manifest_sha256') == digest(current), 'frozen catalogs differ')
    require(now.tzinfo is not None
            and 0 <= (now - stamp(evidence.get('captured_at'))).total_seconds() <= 15,
            'fresh legacy observation required')
    broker, nameserver, cluster = (evidence.get(k) for k in ('broker', 'nameserver', 'cluster'))
    require(evidence.get('broker_version') == '5.5.1'
            and isinstance(broker, str) and re.fullmatch(r'[A-Za-z0-9_.-]+:[0-9]{1,5}', broker)
            and isinstance(nameserver, str) and re.fullmatch(r'[A-Za-z0-9_.-]+:[0-9]{1,5}', nameserver)
            and isinstance(cluster, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', cluster)
            and evidence.get('cluster_masters') == [broker], 'exact pinned single Broker required')
    require(all(evidence.get(k) is True for k in
                ('old_runtimes_stopped', 'new_business_accepted', 'history_mapping_preserved')),
            'runtime, business and retained history proof required')
    names = evidence.get('broker_topic_names')
    require(isinstance(names, list) and 0 < len(names) <= 10000
            and all(isinstance(x, str) and x and len(x.encode()) <= 255 for x in names)
            and len(set(names)) == len(names), 'complete current Broker Topic names required')
    for resource in selected:
        if resource.startswith('Topic:'):
            topic = resource.removeprefix('Topic:')
            require(topic in names and not pop_retry_companions(topic, names),
                    'missing Topic or protected POP companion')
    observations = evidence.get('resources')
    require(isinstance(observations, dict) and set(observations) == set(selected),
            'one exact legacy observation per object required')
    for row in observations.values():
        require(isinstance(row, dict) and set(row) == set(COUNTERS) | {'export_sha256'}
                and all(type(row[k]) is int and row[k] == 0 for k in COUNTERS)
                and isinstance(row['export_sha256'], str) and SHA.fullmatch(row['export_sha256']),
                'unresolved legacy responsibility or missing export')
    commands = []
    for role in sorted(subjects):
        grants = permissions(previous, previous['accounts'][role])
        for resource in sorted(set(selected) & set(grants)):
            commands.append(['deleteAcl', '-b', broker, '-s', 'User:' + subjects[role], '-r', resource])
    for resource in sorted(selected):
        kind, name = resource.split(':', 1)
        if kind == 'Group':
            commands.append(['deleteSubGroup', '-b', broker, '-g', name, '-r', 'true'])
    for resource in sorted(selected):
        kind, name = resource.split(':', 1)
        if kind == 'Topic':
            commands.append(['deleteTopic', '-n', nameserver, '-c', cluster, '-t', name])
    return dict(schema='readable-legacy-v1-retirement-review/v1', selected=sorted(selected),
                retained=sorted(old - set(selected)), commands=commands,
                previous_manifest_sha256=digest(previous), active_manifest_sha256=digest(current),
                observations_sha256=digest(evidence), read_only=True, execution_authorized=False,
                compatibility_with_typed_v2_not_assumed=True)
