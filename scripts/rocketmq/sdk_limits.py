"""Actual native finite-check index evidence with public SDK Unknown checker."""
import stat
import time

from audit_transaction_limit import export
from sdk_acceptance import assert_absent


def run_limits(start, passed, sql, admin, parameters, broker, project, directory, *, python):
    proof = []
    for language in (['sdk-go','sdk-python'] if python else ['sdk-go']):
        admin('updateBrokerConfig','-k','transactionCheckMax','-v','24')
        if parameters(admin('getBrokerConfig'))['transactionCheckMax'] != 24:
            raise RuntimeError('normal isolated check budget not restored')
        identity = 'native-limit-' + language
        # Long lease ensures the healthy SDK reconciler cannot manufacture an
        # abort before the independently measured finite Broker window expires.
        sender = start(language,'crash-prepared',identity,lease_millis=3600000)
        sender.wait('half'); sender.send('commit'); sender.finish(expected=22)
        checker = start(language,'recover',identity,lease_millis=3600000)
        checker.wait('ready')
        observer = start('sdk-go','consume')
        observer.wait('ready')
        checker.wait('checked',decision='unknown',timeout=100)
        admin('updateBrokerConfig','-k','transactionCheckMax','-v','2')
        effective = parameters(admin('getBrokerConfig'))
        if effective['transactionCheckMax'] != 2:
            raise RuntimeError('finite SDK check limit did not become effective')
        audit = None
        deadline = time.monotonic() + 110
        path = directory / (identity + '-audit.json')
        while time.monotonic() < deadline:
            try:
                audit = export(broker,project,identity,path)
                break
            except RuntimeError:
                time.sleep(2)
        if (audit is None or stat.S_IMODE(path.stat().st_mode) != 0o600
                or audit.get('alert') != 'native_transaction_check_limit_reached'
                or audit.get('severity') != 'critical'):
            raise RuntimeError('real SDK native limit index/private audit absent')
        if sql(f"SELECT state FROM rm_tx_execution WHERE operation_id='op-{identity}';") != 'prepared':
            raise RuntimeError('finite Broker limit changed authoritative Prepared evidence')
        if sql(f"SELECT COUNT(*) FROM sdk_business WHERE id='{identity}';") != '0':
            raise RuntimeError('finite Unknown triggered business work')
        assert_absent(observer,identity,2)
        # Alarm is emitted only after actual native index evidence, not a sleep
        # or configuration product; host performs explicit admission protection.
        checker.send('seal'); checker.wait('sealed')
        if not checker.process.poll() is None:
            raise RuntimeError('admission protection killed the checker')
        checker.send('stop'); checker.wait('closed'); checker.finish()
        observer.send('stop'); observer.wait('closed'); observer.finish()
        proof.append({'language':language,'effective_parameters':effective,'audit':audit,
                      'mode':'0600','alert':'native_transaction_check_limit_reached',
                      'admission':'public Reserve refused after explicit StopAdmission',
                      'business_count':0,'local_evidence':'prepared_retained'})
        passed(f'public_{language}_native_limit_unknown_private_audit_and_admission_alarm')
    return proof
