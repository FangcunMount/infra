"""Exact post-RPC audit proofs in ci-transactions' owned fixture only."""
import json
from sdk_acceptance import assert_absent, wait_reference_checks


def validate_options(options):
    allowed = {'sdk_recovery_audit','sdk_api_go','sdk_api_python','sdk','image','mysql_image',
               'report','python','qs_deferred_kind'}
    if (not options.get('sdk_api_go') or not options.get('sdk_api_python')
            or any(value for key,value in options.items() if key not in allowed)):
        raise ValueError('recovery audit requires only source Go/Python SDK profile')


def require_records(probe, identities, outcome):
    if outcome not in ('commit_confirmed','rollback_confirmed') or not identities:
        raise ValueError('exact positive recovery receipts required')
    for identity in identities:
        probe.wait('recovery_recorded',identity,outcome,timeout=100)


def run(start,passed,sql,mongo_command):
    receipts=[]
    targets=[('sdk-go','sdk-go','mysql'),('sdk-python','sdk-python','mysql'),
             ('sdk-go','sdk-python','mysql'),('sdk-python','sdk-go','mysql'),
             ('sdk-go','sdk-go','mongo')]
    for language,recovery_language,storage in targets:
        consumer=start('sdk-go','consume',storage=storage);consumer.wait('ready')
        for committed in (True,False):
            action='commit' if committed else 'rollback'
            identity=f'audit-{language}-{recovery_language}-{storage}-{action}'
            identities=[f'{identity}-b{i}' for i in range(3)]
            mode='crash-committed' if committed else 'crash-prepared'
            producer=start(language,mode,identity,storage=storage,branches=3)
            producer.wait('half');producer.send('commit')
            status=23 if committed else 22
            producer.finish(expected=status)
            if storage=='mysql':
                business=lambda:sql(f"SELECT COUNT(*) FROM sdk_business WHERE id='{identity}';")
                executions=lambda:sql('SELECT COUNT(*) FROM rm_tx_execution;')
            else:
                business=lambda:mongo_command('db.getSiblingDB("sdkprobe").sdk_business.countDocuments({_id:'+json.dumps(identity)+'})')
                executions=lambda:mongo_command('db.getSiblingDB("sdkprobe").rm_tx_execution.countDocuments({})')
            before=business();count=executions()
            if before!=('1' if committed else '0'):
                raise RuntimeError('original database fact differs from recovery case')
            recovery=start(recovery_language,'recover',storage=storage);recovery.wait('ready')
            wait_reference_checks(recovery,identities,'commit' if committed else 'rollback')
            require_records(recovery,identities,'commit_confirmed' if committed else 'rollback_confirmed')
            if committed:
                for message_id in identities:consumer.wait('received',message_id)
            else:
                for message_id in identities:assert_absent(consumer,message_id,.25)
            recovery.send('stop');recovery.wait('closed');recovery.finish()
            metrics=[json.loads(e['decision']) for e in recovery.events if e.get('event')=='metrics']
            if not metrics:raise RuntimeError('actual recovery resource counters absent')
            stats=metrics[-1]
            def counter(go,py):return stats.get(go,stats.get(py,0))
            if (counter('RecoveryAuditRecorded','recovery_audit_recorded')<3
                    or counter('RecoveryAuditErrors','recovery_audit_errors')
                    or counter('RecoveryAuditUnsupported','recovery_audit_unsupported')):
                raise RuntimeError('recovery receipt audit missing or failed')
            if business()!=before or executions()!=count:
                raise RuntimeError('idle recovery changed business or created a new execution')
            if producer.process.pid==recovery.process.pid:
                raise RuntimeError('replacement process identity not established')
            receipts.append(dict(sender=language,checker=recovery_language,storage=storage,
                outcome=action,original_exit_code=status,exact_references=3,
                persisted_recovery_receipts=3,business_count=int(before),new_executions=0,
                producer_pid=producer.process.pid,recovery_pid=recovery.process.pid,
                sdk_stats=stats))
            passed(f'positive_recovery_audit_{language}_to_{recovery_language}_{storage}_{action}')
        consumer.close()
    return receipts
