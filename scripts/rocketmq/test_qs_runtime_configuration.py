import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from five_image_start import FiveImageFixture, qs_metrics
from qs_runtime_configuration import configuration, rocketmq


def base():
    return dict(insecure={}, secure={}, redis={'max-active':384}, mysql={'max-open-connections':150}, mongodb={'max-pool-size':256},
        messaging={}, log={'level':'warn'}, cache={'policy_file':'cache/apiserver.prod.yaml'},
        oss={'enabled':True,'connect-timeout':'3s','read-write-timeout':'10s','retry-max-attempts':2},
        assessment_assets={'enabled':True}, iam=dict(grpc={'tls':{}}, jwks={}, **{'authz-sync':{}}),
        **{'delegated-subject':{}, 'migration':{}, 'grpc':{'mtls':{}, 'acl':{}},
           'ai_workflow':{'management':{}}, 'worker':{'concurrency':48},
           'grpc_client':{'max_inflight':420}, 'backpressure':{'mysql':{'max_inflight':150}}})


class QSRuntimeConfigurationTest(unittest.TestCase):
    def worker_fixture(self, logs):
        fixture=FiveImageFixture.__new__(FiveImageFixture)
        fixture.report={};fixture.applications={'worker1':'owned-worker1'}
        fixture.http=Mock(return_value='healthy')
        values=iter(logs)
        fixture.run=lambda args:SimpleNamespace(stdout='true' if args[1]=='inspect' else next(values),stderr='')
        return fixture

    def test_http_worker_health_waits_for_original_completed_startup_phase(self):
        f=self.worker_fixture(['metrics live only','Worker started, waiting for events...'])
        with patch('five_image_start.time.monotonic',side_effect=[0,1,2]),patch('five_image_start.time.sleep'):
            f.ready('worker1',9092,'/healthz')
        self.assertEqual(f.http.call_count,2)
        self.assertEqual(f.report['workers_prepared'],{'worker1':True})

    def test_http_only_worker_cannot_exceed_the_original_startup_budget(self):
        f=self.worker_fixture(['metrics live only'])
        with patch('five_image_start.time.monotonic',side_effect=[0,1,151]),patch('five_image_start.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'ready_budget_exceeded'):f.ready('worker1',9092,'/healthz')
        self.assertNotIn('workers_prepared',f.report)

    def test_two_owners_distinct_credentials_and_shared_mysql_binding(self):
        original=base(); frozen=copy.deepcopy(original)
        c=configuration(original,'api','qs_m3_image_owned','unused-owned-password','a'*64)
        self.assertEqual(original,frozen)
        owners=c['messaging']['rocketmq']['transactions']
        self.assertEqual(set(owners),{'qs.mysql','qs.mongo'})
        self.assertNotEqual(owners['qs.mysql']['credentials_file'],owners['qs.mongo']['credentials_file'])
        self.assertEqual(c['ai_workflow']['messaging']['rocketmq']['transactions']['qs.mysql'],owners['qs.mysql'])
        self.assertFalse(c['migration']['enabled'])
        self.assertTrue(c['oss']['enabled'])
        self.assertTrue(c['assessment_assets']['enabled'])
        for key in ('connect-timeout','read-write-timeout','retry-max-attempts'):
            self.assertEqual(c['oss'][key],original['oss'][key])
        self.assertEqual(c['oss']['endpoint'],'http://owned-unused-oss.invalid')
        self.assertEqual(c['eventing']['standard_outbox'],{'mongo':False,'assessment':False})
        self.assertEqual(c['cache']['policy_file'],'/app/configs/cache/apiserver.prod.yaml')
        self.assertFalse(c['messaging']['rocketmq']['publish_enabled'])
        self.assertTrue(c['iam']['enabled'])
        self.assertTrue(c['iam']['grpc']['tls']['enabled'])
        self.assertTrue(c['iam']['authz-sync']['enabled'])
        for key in ('backpressure','worker'):self.assertEqual(c[key],original[key])
        self.assertEqual(c['mysql']['max-open-connections'],150)
        self.assertEqual(c['mongodb']['max-pool-size'],256)
        self.assertNotIn('limits',owners['qs.mysql'])

    def test_collection_and_workers_do_not_invent_owner_runtimes(self):
        for component in ('collection','worker'):
            original=base()
            c=configuration(original,component,'qs_m3_image_owned','unused-owned-password','a'*64)
            self.assertEqual(original['log']['level'],'warn')
            self.assertEqual(c['worker']['concurrency'],48)
            self.assertEqual(c['grpc_client']['max_inflight'],420)
            if component=='worker':
                self.assertEqual(c['log']['level'],'info')
                self.assertEqual(c['messaging']['rocketmq']['transactions'],{})
                self.assertEqual(c['messaging']['rocketmq']['credentials_file'],'/fixture/worker-credentials.json')
            else:
                self.assertEqual(c['log']['level'],'warn')
                self.assertTrue(c['iam']['enabled'])

    def test_metrics_require_both_exact_owners_and_closed_admission(self):
        expected=dict(sdk_ready=1,sampler_running=1,observation_available=1,admission_open=0,check_workers_limit=2,check_queue_limit=16)
        raw='\n'.join(f'reliable_messaging_transaction_{key}{{owner="{owner}"}} {value}' for owner in ('qs.mysql','qs.mongo') for key,value in expected.items())
        self.assertEqual(set(qs_metrics(raw)),{'qs.mysql','qs.mongo'})
        for bad in (raw.replace('qs.mongo','qs.mysql'),raw.replace('} 0','} 1'),raw.replace('} 16','} 160')):
            with self.assertRaises(RuntimeError):qs_metrics(bad)

    def test_owned_database_and_fixed_component_required(self):
        with self.assertRaises(RuntimeError):configuration(base(),'api','production','unused','a'*64)
        with self.assertRaises(RuntimeError):configuration(base(),'other','qs_m3_image_owned','unused','a'*64)
        with self.assertRaises(RuntimeError):rocketmq(owners=('iam.mysql',))
