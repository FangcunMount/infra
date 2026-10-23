import copy
import json
from types import SimpleNamespace
import unittest
from broker_fault_control import OwnedBrokerFault

PROJECT='rocketmq-m2-test'
PARAMS=dict(transactionTimeOut=6000,transactionCheckInterval=5000,transactionCheckMax=24,fileReservedTime=48)

class BrokerFaultControlTests(unittest.TestCase):
    def fixture(self):
        row=dict(Id='a'*64,Name='/'+PROJECT+'-broker-1',Config=dict(Labels={
            'com.docker.compose.project':PROJECT,'com.docker.compose.service':'broker'}),
            HostConfig=dict(RestartPolicy=dict(Name='no')),
            State=dict(Running=True,Pid=100,Health=dict(Status='healthy'),OOMKilled=False,ExitCode=0))
        calls=[]
        def command(argv,**kwargs):
            calls.append(argv)
            if argv[1]=='kill': row['State'].update(Running=False,Pid=0,ExitCode=137)
            if argv[1]=='start': row['State'].update(Running=True,Pid=101,ExitCode=0)
            return SimpleNamespace(stdout=json.dumps([row]))
        return OwnedBrokerFault(command,PROJECT+'-broker-1',PROJECT,lambda:dict(PARAMS),PARAMS),row,calls

    def test_actual_kill_then_same_container_new_pid_and_parameters(self):
        f,row,calls=self.fixture()
        self.assertEqual(f.kill()['exit_code'],137)
        self.assertTrue(f.start()['pid_changed'])
        self.assertIn(['docker','kill','--signal','SIGKILL',PROJECT+'-broker-1'],calls)
        self.assertIn(['docker','start',PROJECT+'-broker-1'],calls)

    def test_foreign_identity_and_auto_restart_rejected_before_mutation(self):
        for edit in (lambda r:r.update(Name='/foreign'),
                     lambda r:r['Config']['Labels'].update({'com.docker.compose.project':'production'}),
                     lambda r:r['Config']['Labels'].update({'com.docker.compose.service':'mysql'}),
                     lambda r:r['HostConfig']['RestartPolicy'].update(Name='always')):
            f,row,calls=self.fixture();edit(row)
            with self.assertRaises(RuntimeError):f.kill()
            self.assertEqual(len(calls),1)
        with self.assertRaises(RuntimeError):OwnedBrokerFault(None,'serverD','production',None,{})

    def test_changed_container_and_unverified_restart_rejected(self):
        f,row,_=self.fixture()
        with self.assertRaises(RuntimeError):f.start()
        f.kill();row['Id']='b'*64
        with self.assertRaises(RuntimeError):f.start()

    def test_wrong_effective_parameters_fail_after_real_restart(self):
        f,row,_=self.fixture();f.kill()
        f.read_parameters=lambda:dict(PARAMS,transactionCheckMax=2)
        with self.assertRaises(RuntimeError):f.start()

if __name__=='__main__':unittest.main()
