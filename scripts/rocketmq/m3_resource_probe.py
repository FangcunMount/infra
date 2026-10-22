"""Transport-only ACL/type probe in a private loopback fixture, never a host SDK proof."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import secrets

import grpc

from rocketmq.grpc_protocol import Code, TransactionResolution
from rocketmq.v5.client import ClientConfiguration, Credentials
from rocketmq.v5.consumer import SimpleConsumer
from rocketmq.v5.exception import ClientException
from rocketmq.v5.model import FilterExpression, Message
from rocketmq.v5.producer import Producer, TransactionChecker

MARKER = 'M3_RESOURCE_RECEIPT '


class FixtureRollback(TransactionChecker):
    def check(self, message):
        # These are synthetic transport probes with no local business transaction.
        return TransactionResolution.ROLLBACK


class BrokerTypeProbe(Producer):
    def reset_setting(self, settings):
        super().reset_setting(settings)
        # Test-only instance bypass: require the real Broker to reject wrong types,
        # rather than counting the pinned driver's pre-send type validation.
        self._Producer__validate_message_type = False


def start(client, topic):
    client.startup()
    client._retrieve_topic_route_data(topic)
    if not client._init_settings_event.wait(timeout=5):
        raise RuntimeError('pinned Broker settings not received')


def check_denied(operation, codes):
    try:
        operation()
    except ClientException as error:
        if error.code not in codes:
            raise RuntimeError('negative probe failed for an unexpected Broker status') from None
        return error.code
    raise RuntimeError('Broker accepted a forbidden operation')


def run(config, cases):
    if importlib.metadata.version('rocketmq-python-client') != '5.1.2':
        raise RuntimeError('fixed Python client required')
    if not config['endpoint'].startswith('127.0.0.1:'):
        raise RuntimeError('owned loopback endpoint required')
    def handshake(ca=None, *, name=None, plaintext=False, expected=True):
        channel = (grpc.insecure_channel(config['endpoint']) if plaintext else
            grpc.secure_channel(config['endpoint'], grpc.ssl_channel_credentials(
                root_certificates=Path(ca or config['ca']).read_bytes()),
                options=[('grpc.ssl_target_name_override',name)] if name else None))
        try:
            try:
                grpc.channel_ready_future(channel).result(timeout=3)
            except grpc.FutureTimeoutError:
                if expected:
                    raise RuntimeError('verified TLS control unavailable') from None
            else:
                if not expected:
                    raise RuntimeError('untrusted or plaintext TLS probe was accepted')
        finally:
            channel.close()
    handshake()
    cases['tls/verified_ca_and_san'] = 'allowed'
    handshake(config['wrong_ca'],expected=False)
    cases['tls/wrong_ca'] = 'rejected'
    handshake(name='wrong-server-name.invalid',expected=False)
    cases['tls/wrong_san'] = 'rejected'
    handshake(plaintext=True,expected=False)
    cases['tls/plaintext'] = 'rejected'
    handshake()
    cases['tls/verified_control_after_negatives'] = 'allowed'
    manifest = config['manifest']
    routes = {r['id']:r for r in manifest['routes']}
    topics = {r['physical_topic']:r for r in routes.values()}
    for role, grants in manifest['accounts'].items():
        account = config['accounts'][role]
        client_config = ClientConfiguration(config['endpoint'], Credentials(
            account['username'], account['password']), request_timeout=5)
        allowed = {routes[i]['physical_topic'] for i in grants['publish']}
        producer = BrokerTypeProbe(client_config, topics=allowed,
            checker=FixtureRollback(), tls_enable=True)
        try:
            start(producer, sorted(allowed)[0])
            for physical, route in sorted(topics.items()):
                def send(kind=route['message_type']):
                    transaction = producer.begin_transaction() if kind == 'TRANSACTION' else None
                    message = Message()
                    message.topic, message.body = physical, b'isolated-m3-transport-proof'
                    message.keys = 'm3-resource-' + secrets.token_hex(8)
                    receipt = producer.send(message, transaction)
                    if not receipt or not receipt.message_id:
                        raise RuntimeError('real Broker receipt absent')
                    if transaction:
                        if not receipt.transaction_id:
                            raise RuntimeError('half transaction receipt absent')
                        transaction.rollback()
                identity = role + '/publish/' + route['id']
                if physical in allowed:
                    send()
                    cases[identity] = 'allowed'
                    wrong = 'NORMAL' if route['message_type'] == 'TRANSACTION' else 'TRANSACTION'
                    code = check_denied(lambda:send(wrong), {Code.MESSAGE_PROPERTY_CONFLICT_WITH_TYPE})
                    cases[role + '/type/' + route['id']] = code
                else:
                    cases[identity] = check_denied(send, {Code.FORBIDDEN})
        finally:
            producer.shutdown()
        permissions = config['permissions'][role]
        for route in routes.values():
            if not route['consumer_group']:
                continue
            physical, group = route['physical_topic'], route['consumer_group']
            allowed = ('Sub' in permissions.get('Topic:'+physical, [])
                       and 'Sub' in permissions.get('Group:'+group, []))
            consumer = SimpleConsumer(client_config, group,
                subscription={physical:FilterExpression()}, await_duration=1, tls_enable=True)
            def receive():
                start(consumer, physical)
                for message in consumer.receive(16, 15):
                    consumer.ack(message)
            try:
                identity = role + '/subscribe/' + route['id']
                if allowed:
                    receive()
                    cases[identity] = 'allowed'
                else:
                    cases[identity] = check_denied(receive, {Code.FORBIDDEN})
            finally:
                consumer.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    cases, failed = {}, 0
    try:
        run(json.loads(args.config.read_text()), cases)
    except Exception:
        failed = 1
    print(MARKER + json.dumps(dict(client='5.1.2',passed=len(cases),failed=failed,
        skipped=0,cases=cases,scope='isolated_transport_acl_and_broker_type_only')),flush=True)
    return failed


if __name__ == '__main__':
    raise SystemExit(main())
