"""Production-shaped owned-fixture configuration; never discovers credentials."""
import copy
import re

from image_start_fixture import require


def rocketmq(*, owners=(), instance='qs-apiserver-1', credential='qs'):
    value = dict(endpoint='broker:8081', credentials_file='/fixture/' + credential + '-credentials.json',
                 ca_file='/fixture/mq-ca.crt', routes_file='/fixture/routes.json',
                 instance_id=instance, publish_enabled=False, transactions={})
    for owner in owners:
        require(owner in ('qs.mysql', 'qs.mongo'), 'explicit_qs_owner_required')
        value['transactions'][owner] = dict(store_id='isolated-' + owner.replace('.', '-') + '-primary',
            writer_epoch='m3-1', route_revision='m3-1',
            credentials_file='/fixture/' + ('mongo' if owner == 'qs.mongo' else 'qs') + '-credentials.json')
    return value


def iam_options(base, certificate, *, sync):
    c = copy.deepcopy(base)
    c.update(enabled=True, **{'grpc-enabled': True, 'jwks-enabled': True})
    c['grpc']['address'] = 'iam-apiserver:9090'
    c['grpc']['tls'].update(enabled=True, **{'ca-file': '/fixture/service-ca.crt',
        'cert-file': '/fixture/' + certificate + '.crt', 'key-file': '/fixture/' + certificate + '.key'})
    # Exercise the real IAM service. HTTP is confined to the internal owned
    # network; gRPC continues to use the original mTLS identity/ACL contract.
    c['jwks'].update(url='http://iam-apiserver:9080/.well-known/jwks.json', **{'grpc-endpoint': 'iam-apiserver:9090'})
    if sync:
        c['authz-sync'].update(enabled=True, provider='rocketmq', **{'ephemeral-nsq': False,
            'rocketmq': rocketmq(), 'channel-prefix': 'qs-authz-sync'})
    return c


def configuration(base, component, database, password, delegated_key):
    require(component in ('api', 'collection', 'worker'), 'explicit_component_required')
    require(re.fullmatch(r'qs_m3_image_[a-z0-9_]{1,36}', database), 'owned_database_required')
    require(re.fullmatch('[0-9a-f]{64}', delegated_key), 'owned_delegated_key_required')
    c = copy.deepcopy(base)
    if c.get('cache', {}).get('policy_file'):
        policy = c['cache']['policy_file']
        require(re.fullmatch(r'cache/[a-z-]+\.prod\.yaml', policy), 'original_owned_policy_path_required')
        # The main file moves to /fixture; keep the exact policy already shipped
        # in the original image rather than resolving relative to that mount.
        c['cache']['policy_file'] = '/app/configs/' + policy
    c['insecure'] = {'bind-address': '0.0.0.0', 'bind-port': 8080}
    if 'secure' in c: c['secure']['bind-port'] = 0
    c['redis'].update(host='redis', port=6379, username='', password='')
    # Only database endpoints/identities change. Preserve all pool, worker,
    # retry, scheduler, backpressure and consumer budgets in the source config.
    if component != 'collection':
        c['mysql'].update(host='mysql:3306', username='qs_runtime', password=password,
                          database=database, **{'tls-mode': 'DISABLED'})
        c['mongodb'].update(host='mongo:27017', username='', password='', database=database,
                            url='mongodb://mongo:27017/' + database + '?replicaSet=image-proof')
        c['messaging'].update(provider='rocketmq', rocketmq=rocketmq(
            owners=('qs.mysql', 'qs.mongo') if component == 'api' else (),
            credential='qs' if component == 'api' else 'worker'))
    if component in ('api', 'collection'):
        identity = 'qs-apiserver' if component == 'api' else 'qs-collection-server'
        c['iam'] = iam_options(c['iam'], identity, sync=component == 'api')
        c['delegated-subject']['current-key'] = delegated_key
    if component == 'api':
        c['migration'].update(enabled=False, autoseed=False, database=database)
        c['grpc'].update(**{'tls-cert-file': '/fixture/qs-apiserver.crt',
            'tls-key-file': '/fixture/qs-apiserver.key'})
        c['grpc']['mtls']['ca-file'] = '/fixture/service-ca.crt'
        c['grpc']['acl']['config-file'] = '/app/configs/grpc-acl.prod.yaml'
        c['ai_workflow']['management'].update(address='ai:50061', ca_file='/fixture/service-ca.crt',
            cert_file='/fixture/qs-apiserver.crt', key_file='/fixture/qs-apiserver.key')
        c['ai_workflow']['messaging'] = dict(enabled=True, provider='rocketmq',
            rocketmq=rocketmq(owners=('qs.mysql',)),
            signing_key_file='/fixture/qs-sign-private.json',
            decrypt_key_files={'qs-recipient': '/fixture/qs-recipient-private.json'},
            ai_signer_files={'ai-sign': '/fixture/ai-sign-public.json'},
            ai_recipient_key_file='/fixture/ai-decrypt-public.json')
    elif component == 'collection':
        c['grpc_client'].update(endpoint='qs-apiserver:9090', **{'tls-ca-file': '/fixture/service-ca.crt',
            'tls-cert-file': '/fixture/qs-collection-server.crt', 'tls-key-file': '/fixture/qs-collection-server.key'})
    else:
        c['grpc'].update(**{'tls-ca-file': '/fixture/service-ca.crt', 'tls-cert-file': '/fixture/qs-worker.crt',
            'tls-key-file': '/fixture/qs-worker.key'})
    return c
