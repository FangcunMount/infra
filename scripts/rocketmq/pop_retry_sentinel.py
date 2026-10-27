"""Create one real POP-v2 retry in the owned resource fixture, never production.

The existing NORMAL input and exact application grants are reused. One synthetic
transport delivery is intentionally left unacked, then all local clients close.
Broker revive creates its own retry resource; no admin validation is bypassed.
"""
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets

from final_image_candidate import ci_guard

MARKER = 'READABLE_POP_SENTINEL '
FIELDS = {'schema', 'topic', 'group', 'retry_topic', 'body_sha256', 'received', 'ack_calls', 'clients_closed'}


def route_and_roles(config):
    from routes import validate
    manifest = config['manifest']
    validate(manifest)
    if manifest['version'] != 3:
        raise ValueError('owned_readable_sentinel_manifest_required')
    routes = [r for r in manifest['routes'] if r['topic'] == 'qs.survey.lifecycle'
              and r['message_type'] == 'NORMAL' and r.get('subscription') == 'qs-worker']
    if len(routes) != 1:
        raise ValueError('one_owned_normal_sentinel_input_required')
    route = routes[0]
    def role_for(key):
        roles = [name for name, grants in manifest['accounts'].items() if route['id'] in grants[key]]
        if not roles:
            raise ValueError('existing_exact_sentinel_grants_required')
        return sorted(roles)[0]
    return route, role_for('publish'), role_for('subscriptions')


def receipt(raw, route):
    lines = [s.removeprefix(MARKER) for s in raw.splitlines() if s.startswith(MARKER)]
    if len(lines) != 1 or len(lines[0]) > 4096:
        raise ValueError('one_bounded_actual_pop_sentinel_receipt_required')
    row = json.loads(lines[0])
    if (not isinstance(row, dict) or set(row) != FIELDS
            or row['schema'] != 'owned-actual-pop-v2-sentinel/v1'
            or row['topic'] != route['physical_topic'] or row['group'] != route['consumer_group']
            or row['retry_topic'] != '%RETRY%' + row['group'] + '+' + row['topic']
            or not isinstance(row['body_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', row['body_sha256'])
            or type(row['received']) is not int or row['received'] != 1
            or type(row['ack_calls']) is not int or row['ack_calls'] != 0
            or row['clients_closed'] is not True):
        raise ValueError('actual_unacked_closed_pop_sentinel_required')
    return row


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--project', required=True)
    args = parser.parse_args()
    ci_guard(os.environ)
    if not re.fullmatch('rocketmq-m2-[0-9a-f]{12}', args.project):
        raise ValueError('owned_pop_sentinel_project_required')
    if args.config.stat().st_mode & 0o077:
        raise ValueError('private_owned_pop_sentinel_configuration_required')
    os.umask(0o077)
    from m3_resource_probe import start, close
    from rocketmq.v5.client import ClientConfiguration, Credentials
    from rocketmq.v5.producer import Producer
    from rocketmq.v5.consumer import SimpleConsumer
    from rocketmq.v5.model import FilterExpression, Message
    logger = logging.getLogger('rocketmq-python-client')
    for handler in list(logger.handlers):
        logger.removeHandler(handler); handler.close()
    logger.addHandler(logging.FileHandler(args.config.parent / 'pop-sentinel-private.log'))
    config = json.loads(args.config.read_bytes())
    if not re.fullmatch('127[.]0[.]0[.]1:[0-9]{1,5}', config['endpoint']):
        raise ValueError('owned_pop_sentinel_loopback_required')
    route, publisher, subscriber = route_and_roles(config)
    def connection(role):
        value = config['accounts'][role]
        return ClientConfiguration(config['endpoint'], Credentials(value['username'], value['password']), request_timeout=5)
    consumer = SimpleConsumer(connection(subscriber), route['consumer_group'],
        subscription={route['physical_topic']: FilterExpression()}, await_duration=1, tls_enable=True)
    producer = Producer(connection(publisher), topics={route['physical_topic']}, tls_enable=True)
    token = secrets.token_bytes(32)
    received = 0
    try:
        start(consumer, route['physical_topic']); start(producer, route['physical_topic'])
        message = Message(); message.topic = route['physical_topic']; message.body = token
        sent = producer.send(message)
        if not sent or not sent.message_id:
            raise RuntimeError('actual_pop_sentinel_send_receipt_required')
        import time
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            for delivery in consumer.receive(1, 15):
                if delivery.body != token:
                    raise RuntimeError('unexpected_owned_sentinel_delivery')
                received += 1
                break
            if received:
                break
        if received != 1:
            raise RuntimeError('actual_held_pop_sentinel_required')
        # Deliberately no ACK: this owned positive control leaves the Broker to
        # materialize its retry, which remains protected through unrelated deletes.
    finally:
        try:
            close(consumer)
        finally:
            close(producer)
    print(MARKER + json.dumps(dict(schema='owned-actual-pop-v2-sentinel/v1', topic=route['physical_topic'],
        group=route['consumer_group'], retry_topic='%RETRY%' + route['consumer_group'] + '+' + route['physical_topic'],
        body_sha256=hashlib.sha256(token).hexdigest(), received=received, ack_calls=0, clients_closed=True)))


if __name__ == '__main__':
    main()
