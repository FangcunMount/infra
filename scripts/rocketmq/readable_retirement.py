"""Offline, individually named retirement review. Never contacts or mutates MQ.

The observations must come from the frozen production read-only collectors.
This evaluator cannot authenticate those observations or authorize execution;
the maintenance executor must re-read them under its existing deployment lock.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import re

from audit_transaction_limit import write_private
from nsq_drain_evidence import load, stamp
from readable_transition import digest, validate_transition
from routes import permissions_v2

COUNTERS = (
    'active_writers', 'active_consumers', 'backlog', 'in_flight',
    'invisible_retries', 'unresolved_transactions', 'broker_bound_plans',
    'pending_receipts', 'unresolved_dead_letters', 'native_limit_responsibilities',
)
SHA = re.compile(r'[0-9a-f]{64}')
SUBJECT = re.compile(r'[A-Za-z0-9_.-]{1,80}')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def resources(manifest):
    return ({'Topic:' + r['physical_topic'] for r in manifest['routes']}
            | {'Group:' + r['consumer_group'] for r in manifest['routes'] if r.get('consumer_group')})


def plan_retirement(previous, current, subjects, selected, evidence, now):
    validate_transition(previous, current)
    require(isinstance(subjects, dict) and set(subjects) == set(previous['accounts']),
            'exact existing account roles required')
    require(all(isinstance(v, str) and SUBJECT.fullmatch(v) for v in subjects.values())
            and len(set(subjects.values())) == len(subjects), 'distinct named subjects required')
    old, active = resources(previous), resources(current)
    require(isinstance(selected, list) and selected and all(isinstance(v, str) for v in selected)
            and len(set(selected)) == len(selected) and set(selected) <= old
            and not set(selected) & active, 'only distinct explicitly selected old resources allowed')
    require(evidence.get('schema') == 'readable-retirement-observations/v1'
            and evidence.get('previous_manifest_sha256') == digest(previous)
            and evidence.get('active_manifest_sha256') == digest(current), 'frozen manifests differ')
    observed = stamp(evidence.get('captured_at'))
    require(now.tzinfo is not None and 0 <= (now - observed).total_seconds() <= 15,
            'fresh observation required')
    require(evidence.get('broker_version') == '5.5.1', 'pinned Broker required')
    cluster, broker, nameserver = (evidence.get(k) for k in ('cluster', 'broker', 'nameserver'))
    require(isinstance(cluster, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', cluster)
            and isinstance(broker, str) and re.fullmatch(r'[A-Za-z0-9_.-]+:[0-9]{1,5}', broker)
            and isinstance(nameserver, str) and re.fullmatch(r'[A-Za-z0-9_.-]+:[0-9]{1,5}', nameserver),
            'explicit single Broker and NameServer required')
    require(evidence.get('cluster_masters') == [broker], 'frozen single Broker membership required')
    require(evidence.get('old_runtimes_stopped') is True
            and evidence.get('new_business_accepted') is True
            and evidence.get('history_mapping_preserved') is True,
            'runtime, business acceptance and historical evidence prerequisites required')
    observations = evidence.get('resources')
    require(isinstance(observations, dict) and set(observations) == set(selected),
            'one complete observation for every selected object required')
    for row in observations.values():
        require(isinstance(row, dict) and set(row) == set(COUNTERS) | {'export_sha256'},
                'complete responsibility counters and export digest required')
        require(all(type(row[k]) is int and row[k] == 0 for k in COUNTERS),
                'selected resource retains responsibility')
        require(isinstance(row['export_sha256'], str) and SHA.fullmatch(row['export_sha256']),
                'configuration, ACL and progress export required')
    # Only exact old grants. Never remove a subject or an entire ACL.
    commands = []
    for role in sorted(subjects):
        grants = permissions_v2(previous, previous['accounts'][role])
        for resource in sorted(set(selected) & grants.keys()):
            commands.append(['deleteAcl', '-b', broker, '-s', 'User:' + subjects[role], '-r', resource])
    for resource in sorted(selected):
        kind, name = resource.split(':', 1)
        if kind == 'Group':
            # The cluster branch also deletes retry/DLQ Topics in 5.5.1.
            commands.append(['deleteSubGroup', '-b', broker, '-g', name, '-r', 'true'])
    for resource in sorted(selected):
        kind, name = resource.split(':', 1)
        if kind == 'Topic':
            # deleteTopic has no -b option and must update NameServer as well.
            commands.append(['deleteTopic', '-n', nameserver, '-c', cluster, '-t', name])
    return dict(schema='readable-retirement-review/v1', previous_manifest_sha256=digest(previous),
                active_manifest_sha256=digest(current), observations_sha256=digest(evidence),
                selected=sorted(selected), retained=sorted(old - set(selected)), commands=commands,
                read_only=True, execution_authorized=False,
                live_confirmation_required=['same cluster membership', 'same complete responsibility observations',
                                            'same ACL and metadata exports', 'existing deployment locks'],
                protected=['system and transaction internal Topics', 'retry and DLQ Topics',
                           'historical database evidence', 'unselected resources'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('previous', 'current', 'subjects', 'selected', 'observations', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    previous, current, subjects, selected, evidence = (
        load(getattr(args, key))[0] for key in ('previous', 'current', 'subjects', 'selected', 'observations'))
    result = plan_retirement(previous, current, subjects, selected, evidence, dt.datetime.now(dt.timezone.utc))
    write_private(args.output, result)
    print(json.dumps(dict(selected=len(result['selected']), retained=len(result['retained']),
                          read_only=True, execution_authorized=False)))


if __name__ == '__main__':
    main()
