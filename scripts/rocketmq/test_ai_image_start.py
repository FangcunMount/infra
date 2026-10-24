import json
from pathlib import Path
import unittest

from ai_image_start import messaging, metrics
from image_start_fixture import resource_subset


class AIImageContractTest(unittest.TestCase):
    def test_closed_owner_and_exact_existing_receive_budget(self):
        value=messaging()
        self.assertTrue(value['enabled'])
        self.assertFalse(value['publish_enabled'])
        self.assertEqual(value['max_in_flight'],1)
        self.assertEqual(set(value['transactions']),{'ai.mysql'})
        self.assertEqual(value['transactions']['ai.mysql']['route_revision'],'m3-1')
        self.assertNotIn('limits',value['transactions']['ai.mysql'])

    def test_readiness_cannot_substitute_other_owner_or_open_admission(self):
        values=dict(sdk_ready=1,sampler_running=1,observation_available=1,admission_open=0,check_workers_limit=1,check_queue_limit=16)
        raw='\n'.join(f'reliable_messaging_transaction_{key}{{owner="ai.mysql"}} {value}' for key,value in values.items())
        self.assertEqual(metrics(raw),values)
        for bad in (raw.replace('ai.mysql','qs.mysql'),raw.replace('admission_open{owner="ai.mysql"} 0','admission_open{owner="ai.mysql"} 1'),raw.replace('sdk_ready{owner="ai.mysql"} 1','sdk_ready{owner="ai.mysql"} 10')):
            with self.assertRaises(RuntimeError):metrics(bad)

    def test_resource_subset_preserves_cross_owner_receive_permissions(self):
        original=json.loads((Path(__file__).resolve().parents[2]/'components/rocketmq/serverd-routes-m3-v2.json').read_text())
        selected=resource_subset(original,'m3-ai')
        self.assertEqual(set(selected['accounts']),{'m3-ai'})
        self.assertEqual(selected['accounts']['m3-ai'],original['accounts']['m3-ai'])
        self.assertEqual({r['id'] for r in selected['routes']},{'ai-qs-event','qs-ai-command','qs-ai-ack'})
        self.assertEqual({r['owner'] for r in selected['routes']},{'ai.mysql','qs.mysql'})
