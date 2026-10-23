"""Owned CI fault generator -> actual SYS index, no body export or business callback."""
import hashlib
import json
import os
import secrets
import time

from audit_transaction_limit import export, write_private
from provision_v2 import Admin


def safe_event(value):
    if value == {'event': 'ready', 'prepared': 1} and type(value['prepared']) is int:
        return value
    keys = {'event', 'prepared', 'unknown_checks', 'business_calls', 'final_confirmation_calls'}
    if (isinstance(value, dict) and set(value) == keys and value['event'] == 'closed'
            and all(type(value[k]) is int for k in keys-{'event'})
            and value['prepared'] == 1 and 0 < value['unknown_checks'] < 1024
            and value['business_calls'] == 0 and value['final_confirmation_calls'] == 0):
        return value
    return {'event': 'invalid_native_limit_fault_event'}


def create_native_limit(repo, directory, broker, project, grpc_port, ca, account, route,
                        run, native_runner, parameters, proof):
    if (not project.startswith('rocketmq-m2-') or directory.stat().st_mode & 0o077
            or route['message_type'] != 'TRANSACTION' or route['route_revision'] != 'm3-1'
            or route['owner'] not in ('iam.mysql', 'qs.mysql', 'qs.mongo', 'ai.mysql')):
        raise ValueError('owned isolated frozen transaction route required')
    source = repo/'scripts/rocketmq/probes/native-transaction-limit'
    env = dict(os.environ, GOWORK='off', GOFLAGS='-mod=readonly', GOTOOLCHAIN='local')
    module = json.loads(run(['go', 'list', '-m', '-json', 'github.com/apache/rocketmq-clients/golang/v5'], cwd=source, env=env).stdout)
    if module.get('Replace') or module.get('Version') != 'v5.1.4':
        raise RuntimeError('fixed raw fault driver required')
    binary = directory/'native-limit-fault'
    run(['go', 'build', '-race', '-trimpath', '-o', str(binary), '.'], cwd=source, env=env, timeout=300)
    binary.chmod(0o700)
    logs = directory/'native-limit-fault-logs'
    logs.mkdir(mode=0o700)
    env.update({'rocketmq.client.logRoot': str(logs), 'rocketmq.client.logLevel': 'error'})
    key = 'native-limit-'+secrets.token_hex(12)
    config = directory/'native-limit-fault-private.json'
    write_private(config, dict(Project=project, Endpoint=f'127.0.0.1:{grpc_port}', CAFile=str(ca),
        AccessKey=account['username'], SecretKey=account['password'], Topic=route['physical_topic'], Key=key))
    admin = Admin(broker)
    before = parameters(admin('getBrokerConfig'))
    proof.update(parameters_before=before, binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                 raw_fault_driver='5.1.4', business_sdk_acceptance_not_claimed=True)
    owned = {}
    path = directory/'native-limit-index-private.json'
    def supervise(native):
        owned['native'] = native
        proof['ready'] = safe_event(native.wait('ready', timeout=45))
        if proof['ready'].get('event') != 'ready':
            raise RuntimeError('owned fault half not prepared')
        deadline = time.monotonic()+110
        report = None
        while time.monotonic() < deadline:
            try:
                report = export(broker, project, key, path)
                break
            except RuntimeError:
                time.sleep(2)
        if report is None or len(report['records']) != 1 or path.stat().st_mode & 0o777 != 0o600:
            raise RuntimeError('actual bounded SYS native limit index absent')
        raw = path.read_bytes()
        if key.encode() in raw or b'private-native-limit-fault' in raw:
            raise RuntimeError('native limit index leaked private key/body')
        proof['index'] = dict(records=1, evidence_sha256=hashlib.sha256(raw).hexdigest(),
            read_only=report['read_only'], body_exported=report['body_exported'], mode='0600',
            topic=report['topic'], alert=report['alert'], owner_inferred_from_index=False)
        native.send('stop')
        proof['closed'] = safe_event(native.wait('closed', timeout=30))
        if proof['closed'].get('event') != 'closed':
            raise RuntimeError('fault generator lifecycle evidence incomplete')
    try:
        for key_, value in (('transactionTimeOut', '6000'), ('transactionCheckMax', '2')):
            admin('updateBrokerConfig', '-k', key_, '-v', value)
        proof['parameters_effective'] = parameters(admin('getBrokerConfig'))
        if proof['parameters_effective']['transactionCheckMax'] != 2 or proof['parameters_effective']['transactionTimeOut'] != 6000:
            raise RuntimeError('isolated native limit parameters not effective')
        result = native_runner([str(binary), str(config)], cwd=source, env=env, timeout=180, required=False,
            prefix='M3_NATIVE_LIMIT_FAULT ', supervise=supervise)
        if result.returncode:
            raise RuntimeError('owned native-limit fault process failed')
    finally:
        native = owned.get('native')
        if native is not None:
            native.drain()
            native.events[:] = [safe_event(value) for value in native.events]
        for key_ in ('transactionTimeOut', 'transactionCheckMax'):
            admin('updateBrokerConfig', '-k', key_, '-v', str(before[key_]))
        proof['parameters_restored'] = parameters(admin('getBrokerConfig'))
    if proof['parameters_restored'] != before:
        raise RuntimeError('owned native-limit fault parameters not restored')
    return path, proof['index']['evidence_sha256']
