"""Real packet boundaries against ONLY ci-transactions' owned dependencies.

The process proxy observes original witness commit or real Broker response, then
closes TCP. No exception injection stands in for the service-side fact.
"""
import json
import time

from sdk_acceptance import assert_absent, wait_reference_checks


def partial_half_rollback_checks(result, identity):
    """Only unresolved prepared halves need Broker checks after a graceful abort.

    The first half can already have a real Rollback ACK. The second was prepared
    at the Broker but its ACK was lost, so it must be checked by the new instance.
    The third was never sent and must not acquire a fictitious check requirement.
    """
    branches = result.get('branches', [])
    if (result.get('local') != 'not_started' or result.get('local_calls') != 0
            or len(branches) != 3):
        raise RuntimeError('partial half unexpectedly started business or changed branch count')
    checks = []
    for index, (branch, half) in enumerate(zip(branches, ('prepared', 'unknown', 'not_attempted'))):
        message_id = f'{identity}-b{index}'
        allowed_final = {'rollback_confirmed', 'unknown'} if index == 0 else {'not_attempted'}
        if (branch.get('message_id') != message_id or branch.get('half') != half
                or branch.get('final') not in allowed_final):
            raise RuntimeError('partial half stages differ from the exact second-ACK loss boundary')
        if index == 1 or (index == 0 and branch['final'] != 'rollback_confirmed'):
            checks.append(message_id)
    return checks


def recover_after_restart(start, language, storage):
    """TCP health does not prove that all persisted owner routes are ready.

    Retry ONLY a fully drained idle Checker startup with explicit TOPIC_NOT_FOUND;
    never reserve, prepare, invoke business or silently retry arbitrary failures.
    A startup attempt can already handle a check, so retain its actual counters.
    """
    deadline = time.monotonic() + 100
    attempts = []
    commits = 0
    reference_checks = []
    for _ in range(6):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        probe = start(language, 'recover', storage=storage)
        try:
            probe.wait('ready', timeout=min(20, remaining))
        except RuntimeError:
            probe.finish(expected=1)
            codes = {e.get('decision') for e in probe.events if e.get('event') == 'failure_code'}
            if (not codes or not codes <= {'rocketmq_40402', 'half_rejected_40402'}
                    or not any(e.get('event') == 'closed' and e.get('decision') == 'failed_start_drained'
                               for e in probe.events)):
                raise
            metrics = [json.loads(e['decision']) for e in probe.events if e.get('event') == 'metrics']
            if not metrics:
                raise RuntimeError('failed readiness attempt lacks actual drained SDK counters')
            committed = metrics[-1].get('CheckCommit', metrics[-1].get('check_commit', 0))
            commits += committed
            reference_checks.extend(e for e in probe.events if e.get('event') == 'checked_reference')
            attempts.append({'pid':probe.process.pid,'failure_codes':sorted(codes),
                             'commit_checks':committed,'drained':probe.close()})
            if not attempts[-1]['drained']:
                raise RuntimeError('failed idle startup did not drain its owned process group')
            # Broker registration/route caches can remain negative beyond six
            # one-second attempts. Spread the same bounded six idle attempts
            # across the existing 100-second admission window.
            time.sleep(min(15, max(0, deadline - time.monotonic())))
            continue
        return probe, {'drained_topic_not_found_attempts':attempts,
                       'commit_checks_before_ready':commits,
                       'reference_checks_before_ready':reference_checks}
    raise RuntimeError('persisted owner routes did not become ready after Broker restart')


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
                    wait_reference_checks(recovery, [f'{identity}-b{i}' for i in range(3)], 'rollback')
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
                wait_reference_checks(recovery, partial_half_rollback_checks(result, identity), 'rollback')
                if sql(f"SELECT state FROM rm_tx_execution WHERE operation_id='op-{identity}';") != 'aborted':
                    raise RuntimeError('partial ACK loss lacks durable execution abort')
                if sql("SELECT COUNT(*) FROM rm_tx_witness w JOIN rm_tx_execution e USING(execution_key) "
                       f"WHERE e.operation_id='op-{identity}' AND w.state='aborted';") != '3':
                    raise RuntimeError('partial ACK loss lacks all exact aborted witnesses')
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

        # Freeze the second half AFTER its actual Broker ACK but BEFORE that
        # reply can reach the producer. SIGKILL then proves recovery without
        # the old process persisting Unknown or running graceful cleanup.
        identity = f'packet-{language}-partial-half-sigkill'
        proxy = proxy_start('rocketmq')
        proxy.send(json.dumps({'Action':'arm','Boundary':'hold','Method':'SendMessage','Nth':2}))
        proxy.wait('armed')
        sender = start(language, 'fault-half', identity, branches=3, mq_proxy=proxy.address)
        injection = proxy.wait('injected', timeout=90)
        if injection.get('boundary') != 'hold' or not injection.get('backend_ack'):
            raise RuntimeError('partial crash lacks an actually prepared second half')
        sender.kill_group()
        sender.finish(expected=-9)
        if any(e.get('event') in ('half', 'result', 'closed', 'fault_observed') for e in sender.events):
            raise RuntimeError('partial crash occurred after local execution or graceful result cleanup')
        if sql(f"SELECT state FROM rm_tx_execution WHERE operation_id='op-{identity}';") != 'prepared':
            raise RuntimeError('old process settled execution before partial SIGKILL')
        def half_count(outcome):
            return sql("SELECT COUNT(*) FROM rm_tx_witness w JOIN rm_tx_execution e USING(execution_key) "
                       f"WHERE e.operation_id='op-{identity}' AND w.half_outcome='{outcome}';")
        if half_count('prepared') != '1' or half_count('not_attempted') != '2':
            raise RuntimeError('partial SIGKILL did not preserve first ACK and unrecorded remaining branches')
        if business('mysql', identity) != '0':
            raise RuntimeError('partial preparation started business')
        recovery = start(language, 'recover')
        recovery.wait('ready')
        wait_reference_checks(recovery, [f'{identity}-b{i}' for i in range(2)], 'rollback')
        for index in range(3):
            assert_absent(observer, f'{identity}-b{index}', 1)
        if sql(f"SELECT state FROM rm_tx_execution WHERE operation_id='op-{identity}';") != 'aborted':
            raise RuntimeError('new instance did not persist abort for the partial old execution')
        if sql("SELECT COUNT(*) FROM rm_tx_witness w JOIN rm_tx_execution e USING(execution_key) "
               f"WHERE e.operation_id='op-{identity}' AND w.state='aborted';") != '3':
            raise RuntimeError('partial recovery did not retain all three exact aborted witnesses')
        stop(recovery)
        proxy.send(json.dumps({'Action':'stats'})); stats = proxy.wait('stats')
        if stats.get('seen') != 2 or stats.get('backend_commit_acks') != 1:
            raise RuntimeError('partial crash lacks the exact second-send barrier')
        receipts.append({'case':identity,'injection':injection,'proxy':stats,'exit_code':-9,
                         'recorded_half_prepared':1,'recorded_half_not_attempted':2,
                         'before_recovery':'prepared','after_recovery':'aborted',
                         'aborted_witnesses':3,'business_count':0})
        proxy.send(json.dumps({'Action':'stop'})); proxy.wait('closed'); proxy.finish()
        passed(f'public_{language}_partial_half_sigkill_new_instance_rollback')
        stop(observer)

    for language, storage in targets:
        identity = f'packet-{language}-{storage}-broker-restart'
        sender = start(language, 'crash-committed', identity, storage=storage, branches=3)
        sender.wait('half'); sender.send('commit'); sender.finish(expected=23)
        restart_broker()
        recovery, readiness = recover_after_restart(start, language, storage)
        observer = start('sdk-go', 'consume', storage=storage)
        observer.wait('ready')
        wait_reference_checks(recovery, [f'{identity}-b{i}' for i in range(3)], 'commit',
                              observed=readiness['reference_checks_before_ready'])
        for index in range(3):
            observer.wait('received', f'{identity}-b{index}')
        if business(storage, identity) != '1':
            raise RuntimeError('Broker restart changed committed business fact')
        stop(recovery); stop(observer)
        receipts.append({'case':identity,'storage':storage,'producer_exit_code':23,
                         'readiness':readiness,'business_count':1,'public_acknowledged_branches':3})
        passed(f'public_{language}_{storage}_producer_exit_broker_restart_new_checker')
    return receipts
