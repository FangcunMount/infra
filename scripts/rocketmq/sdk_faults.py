"""Real packet boundaries against ONLY ci-transactions' owned dependencies.

The process proxy observes original witness commit or real Broker response, then
closes TCP. No exception injection stands in for the service-side fact.
"""
import json

from sdk_acceptance import assert_absent


def run_faults(start, proxy_start, passed, sql, mongo_command, restart_broker, *, python):
    targets = [('sdk-go', 'mysql'), ('sdk-go', 'mongo')]
    if python:
        targets.append(('sdk-python', 'mysql'))
    receipts = []

    def business(storage, identity):
        if storage == 'mysql':
            return sql(f"SELECT COUNT(*) FROM sdk_business WHERE id='{identity}';")
        return mongo_command('db.getSiblingDB("sdkprobe").sdk_business.countDocuments({_id:"'+identity+'"})')

    def stop(probe):
        probe.send('stop'); probe.wait('closed'); probe.finish()

    for language, storage in targets:
        observer = start('sdk-go', 'consume', storage=storage)
        observer.wait('ready')
        for boundary in ('before', 'after'):
            identity = f'packet-{language}-{storage}-db-{boundary}'
            proxy = proxy_start(storage)
            proxy.send(json.dumps({'Action':'arm','Boundary':boundary,'Method':'commit','Nth':1}))
            proxy.wait('armed')
            mode = 'fault-local-committed' if boundary == 'after' else 'fault-local-uncommitted'
            sender = start(language, mode, identity, storage=storage, branches=3,
                           database_proxy=proxy.address)
            sender.wait('half')
            sender.send('commit')
            injection = proxy.wait('injected', timeout=90)
            if injection.get('boundary') != boundary or injection.get('backend_ack') != (boundary == 'after'):
                raise RuntimeError('packet DB injection did not establish the selected commit boundary')
            sender.wait('fault_observed', timeout=120)
            sender.wait('closed'); sender.finish()
            result = json.loads(sender.wait('result')['decision'])
            if result['local_calls'] != 1:
                raise RuntimeError('SDK repeated local executor')
            if storage == 'mongo' and boundary == 'before':
                proxy.send(json.dumps({'Action':'abort-blocked'}))
                proxy.wait('sessions_aborted')
            count = business(storage, identity)
            if count != ('1' if boundary == 'after' else '0'):
                raise RuntimeError('actual database fact differs from packet commit boundary')
            recovery = start(language, 'recover', storage=storage)
            recovery.wait('ready')
            if boundary == 'after':
                for index in range(3):
                    observer.wait('received', f'{identity}-b{index}')
            else:
                if result['local'] == 'unknown':
                    recovery.wait('checked', decision='rollback', timeout=100)
                elif result['local'] != 'aborted':
                    raise RuntimeError('before-commit loss falsely reported committed')
                for index in range(3):
                    assert_absent(observer, f'{identity}-b{index}', 1)
            stop(recovery)
            proxy.send(json.dumps({'Action':'stats'})); stats = proxy.wait('stats')
            receipts.append({'case':identity,'injection':injection,'proxy':stats,
                             'local_result':result,'business_count':int(count)})
            proxy.send(json.dumps({'Action':'stop'})); proxy.wait('closed'); proxy.finish()
            passed(f'public_{language}_{storage}_real_database_commit_{boundary}_tcp_loss')
        stop(observer)

    languages = ['sdk-go'] + (['sdk-python'] if python else [])
    for language in languages:
        observer = start('sdk-go', 'consume')
        observer.wait('ready')
        for method, mode, ordinal in (('SendMessage','fault-half',2),
                                       ('EndTransaction','fault-final',1)):
            identity = f'packet-{language}-{method.lower()}'
            proxy = proxy_start('rocketmq')
            proxy.send(json.dumps({'Action':'arm','Boundary':'after','Method':method,'Nth':ordinal}))
            proxy.wait('armed')
            sender = start(language, mode, identity, branches=3, mq_proxy=proxy.address)
            if method == 'EndTransaction':
                sender.wait('half'); sender.send('commit')
            injection = proxy.wait('injected', timeout=90)
            if not injection.get('backend_ack'):
                raise RuntimeError('Broker packet loss was not after actual successful RPC')
            sender.wait('fault_observed', timeout=120)
            sender.wait('closed'); sender.finish()
            result = json.loads(sender.wait('result')['decision'])
            count = business('mysql', identity)
            recovery = start(language, 'recover')
            recovery.wait('ready')
            if method == 'SendMessage':
                if count != '0' or result['local_calls'] != 0:
                    raise RuntimeError('uncertain partial half started business')
                recovery.wait('checked', decision='rollback', timeout=100)
                for index in range(3):
                    assert_absent(observer, f'{identity}-b{index}', 1)
            else:
                if count != '1' or result['local_calls'] != 1:
                    raise RuntimeError('lost Broker commit response repeated or lost business')
                for index in range(3):
                    observer.wait('received', f'{identity}-b{index}')
            stop(recovery)
            proxy.send(json.dumps({'Action':'stats'})); stats = proxy.wait('stats')
            if method == 'SendMessage' and stats['seen'] != 2:
                raise RuntimeError('transaction half unexpectedly retried or continued after uncertainty')
            receipts.append({'case':identity,'injection':injection,'proxy':stats,
                             'local_result':result,'business_count':int(count)})
            proxy.send(json.dumps({'Action':'stop'})); proxy.wait('closed'); proxy.finish()
            passed(f'public_{language}_{method.lower()}_after_real_broker_ack_tcp_loss')
        stop(observer)

    for language, storage in targets:
        identity = f'packet-{language}-{storage}-broker-restart'
        sender = start(language, 'crash-committed', identity, storage=storage, branches=3)
        sender.wait('half'); sender.send('commit'); sender.finish(expected=23)
        restart_broker()
        recovery = start(language, 'recover', storage=storage)
        recovery.wait('ready')
        observer = start('sdk-go', 'consume', storage=storage)
        observer.wait('ready')
        recovery.wait('checked', decision='commit', timeout=100)
        for index in range(3):
            observer.wait('received', f'{identity}-b{index}')
        if business(storage, identity) != '1':
            raise RuntimeError('Broker restart changed committed business fact')
        stop(recovery); stop(observer)
        passed(f'public_{language}_{storage}_producer_exit_broker_restart_new_checker')
    return receipts
