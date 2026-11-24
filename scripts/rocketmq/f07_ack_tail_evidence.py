"""Bind the disposable hosted Broker's ACK-tail events to its physical store."""
import base64
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

from final_image_candidate import ci_guard

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ops'))
from readable_pop_record import TOPIC, decode_system_record, unique

STORE = '/home/rocketmq/store'
FIRST_FILE = '00000000000000000000'
EVENT = re.compile(
    r'F07_ACK_TAIL event=verified queue=([0-7]) ck_offset=(\d+) '
    r'ack_offset=(\d+) ack_log=(\d+) prior_commit=(\d+)'
)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def match_ack(checkpoint, ack, kind):
    identity = tuple(checkpoint[k] for k in ('t', 'c', 'q', 'so', 'pt', 'bn'))
    if identity != tuple(ack[k] for k in ('t', 'c', 'q', 'so', 'pt', 'bn')):
        raise ValueError('fixture_ack_checkpoint_identity_mismatch')
    start, count = checkpoint['so'], checkpoint['n']
    differences = checkpoint.get('d') or list(range(count))
    covered = ack['aol'] if kind == 'bAck' else [ack['ao']]
    if not (type(start) is int and isinstance(differences, list) and len(differences) == count
            and all(type(value) is int and value >= 0 for value in differences)
            and len(set(differences)) == count and isinstance(covered, list) and covered
            and len(set(covered)) == len(covered)
            and all(type(value) is int and value - start in differences for value in covered)):
        raise ValueError('fixture_ack_checkpoint_coverage_mismatch')
    return digest(json.dumps(identity, separators=(',', ':')).encode())


def collect(run, broker, project, image, routes, env):
    ci_guard(env)
    if not re.fullmatch(r'rocketmq-m2-[0-9a-f]{12}', project) or broker != project + '-broker-1':
        raise ValueError('owned_ack_tail_project_required')

    def identity():
        item, = json.loads(run(['docker', 'inspect', broker], timeout=5).stdout)
        labels = item['Config']['Labels']
        if (labels.get('com.docker.compose.project') != project
                or labels.get('com.docker.compose.service') != 'broker'
                or item['Image'] != image or not item['State']['Running']
                or not re.fullmatch('[0-9a-f]{64}', item['Id'])):
            raise ValueError('owned_ack_tail_identity_required')
        return dict(id=item['Id'], image=item['Image'], started_at=item['State']['StartedAt'])

    before = identity()
    log = run(['docker', 'logs', '--tail', '4000', before['id']], timeout=8)
    lines = (log.stdout + log.stderr).splitlines()
    events = set()
    for line in lines:
        if 'F07_ACK_TAIL event=verified' not in line:
            continue
        match = EVENT.fullmatch(line)
        if match is None:
            raise ValueError('fixture_ack_tail_event_malformed')
        events.add(tuple(map(int, match.groups())))
    if not 0 < len(events) <= 64:
        raise ValueError('bounded_fixture_ack_tail_events_required')

    capture_deadline = time.monotonic() + 60

    def read(path, offset, size):
        remaining = capture_deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('fixture_ack_tail_capture_timeout')
        result = run(['docker', 'exec', before['id'], 'sh', '-ec',
                      'dd if="$1" iflag=skip_bytes,count_bytes skip="$2" count="$3" status=none | base64',
                      'f07-ack-tail', path, str(offset), str(size)], timeout=min(4, remaining))
        raw = base64.b64decode(''.join(result.stdout.split()), validate=True)
        if len(raw) != size:
            raise ValueError('fixture_ack_tail_storage_short_read')
        return raw

    def record(queue, offset):
        if not 0 <= offset < 1024:
            raise ValueError('fixture_ack_tail_queue_offset_outside_first_segment')
        index = f'{STORE}/consumequeue/{TOPIC}/{queue}/{FIRST_FILE}'
        entry = read(index, offset * 20, 20)
        physical, size, _ = struct.unpack('>qiq', entry)
        if not (0 <= physical < 134217728 and 91 <= size <= 32768 and physical + size <= 134217728):
            raise ValueError('fixture_ack_tail_commitlog_outside_first_segment')
        raw = read(f'{STORE}/commitlog/{FIRST_FILE}', physical, size)
        if read(index, offset * 20, 20) != entry:
            raise ValueError('fixture_ack_tail_consumequeue_changed')
        summary, document = decode_system_record(raw, queue=queue, queue_offset=offset, physical_offset=physical)
        summary['consumequeue_entry_sha256'] = digest(entry)
        return summary, document

    records = []
    seen = set()
    for queue, ck_offset, ack_offset, ack_log, prior_commit in sorted(events):
        if not ck_offset <= prior_commit < ack_offset:
            raise ValueError('fixture_ack_tail_event_bounds_mismatch')
        position = (queue, ack_offset)
        if position in seen:
            raise ValueError('fixture_ack_tail_conflicting_event')
        seen.add(position)
        ck, checkpoint = record(queue, ck_offset)
        ack, ack_doc = record(queue, ack_offset)
        if (ck['kind'] != 'ck' or ack['kind'] not in ('ack', 'bAck') or ack['physical_offset'] != ack_log
                or (checkpoint.get('t'), checkpoint.get('c')) not in routes):
            raise ValueError('fixture_ack_tail_physical_record_mismatch')
        records.append(dict(queue=queue, checkpoint=ck, ack=ack, prior_commit=prior_commit,
                            checkpoint_identity_sha256=match_ack(checkpoint, ack_doc, ack['kind'])))

    required = {}
    for row in records:
        key = str(row['queue'])
        required[key] = max(required.get(key, -1), row['ack']['queue_offset'])
    deadline = time.monotonic() + 20
    while True:
        offsets = run(['docker', 'exec', before['id'], 'head', '-c', '262145',
                       STORE + '/config/consumerOffset.json'], timeout=5).stdout
        if len(offsets.encode()) > 262144:
            raise ValueError('fixture_ack_tail_persisted_offsets_too_large')
        normalized = re.sub(r'(?m)^(\s*)([0-7])(\s*:)', r'\1"\2"\3', offsets)
        document = json.loads(normalized, object_pairs_hook=unique)
        cursor = document['offsetTable'].get(TOPIC + '@CID_RMQ_SYS_REVIVE_GROUP', {})
        if all(type(cursor.get(q)) is int and cursor[q] >= target for q, target in required.items()):
            break
        if time.monotonic() >= deadline:
            raise ValueError('fixture_ack_tail_persisted_offset_not_reached')
        time.sleep(.5)
    if before != identity():
        raise ValueError('fixture_ack_tail_broker_changed')
    return dict(broker=before, records=records, persisted_revive={q: cursor[q] for q in required},
                persisted_offsets_sha256=digest(offsets.encode()), read_only=True, production_access=False)
