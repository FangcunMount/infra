"""Transport-only ACL/type probe in a private loopback fixture, never a host SDK proof."""
import argparse
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import secrets

import grpc

from rocketmq.grpc_protocol import Code, QueryRouteRequest, TransactionResolution
from rocketmq.v5.client import ClientConfiguration, Credentials
from rocketmq.v5.consumer import SimpleConsumer
from rocketmq.v5.exception import ClientException
from rocketmq.v5.model import FilterExpression, Message
from rocketmq.v5.producer import Producer, TransactionChecker
from rocketmq.v5.util import MessagingResultChecker

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


def start(client, topic, *, wait_settings=True):
    client.startup()
    client._retrieve_topic_route_data(topic)
    if wait_settings and not client._init_settings_event.wait(timeout=5):
        raise RuntimeError('pinned Broker settings not received')


def check_denied(operation, codes):
    try:
        operation()
    except ClientException as error:
        if error.code not in codes:
            raise RuntimeError('negative probe failed for an unexpected Broker status') from None
        return error.code
    raise RuntimeError('Broker accepted a forbidden operation')


def check_route(client, topic):
    # The 5.1.2 route cache logs and discards the original Broker exception.
    # Verify its actual signed response before invoking that cache so a generic
    # connection/route error can never be counted as a permission rejection.
    req = QueryRouteRequest()
    req.topic.name = topic
    req.topic.resource_namespace = client.client_configuration.namespace
    req.endpoints.CopyFrom(client.client_configuration.rpc_endpoints.endpoints)
    response = client.rpc_client.query_topic_route_async(
        client.client_configuration.rpc_endpoints,req,metadata=client.sign(),timeout=5).result(timeout=7)
    MessagingResultChecker.check(response.status)
    if response.status.code != Code.OK or not response.message_queues:
        raise RuntimeError('authoritative Broker route absent')


def close(client):
    if client.is_running:
        client.shutdown()
    else:
        # A denied pre-start route still created an instance-owned RPC channel.
        # The upstream shutdown short-circuits when not running; close it here.
        client.rpc_client.stop()


def run(config, cases, *, tls_only=False):
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
    if tls_only:
        return
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
                    check_route(producer, physical)
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
            close(producer)
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
                check_route(consumer, physical)
                # An unauthorized Group may reject telemetry settings. Require
                # the actual receive RPC denial instead of counting that timeout.
                start(consumer, physical, wait_settings=allowed)
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
                close(consumer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--tls-only', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    # The pinned raw client has no log-root option. Replace its process-local
    # handler before reading credentials or starting any client operation.
    logger = logging.getLogger('rocketmq-python-client')
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.addHandler(logging.FileHandler(args.config.parent/'m3-raw-client.log'))
    cases, failed = {}, 0
    try:
        run(json.loads(args.config.read_text()), cases, tls_only=args.tls_only)
    except Exception:
        failed = 1
    print(MARKER + json.dumps(dict(client='5.1.2',passed=len(cases),failed=failed,
        skipped=0,cases=cases,scope='isolated_transport_acl_and_broker_type_only')),flush=True)
    return failed


if __name__ == '__main__':
    raise SystemExit(main())
