import unittest

from native_dead_letter_acceptance import manifest, safe_event, require_event, validate_options, SDK
from routes import validate_v2


class NativeDeadLetterAcceptanceTest(unittest.TestCase):
    def test_profile_refuses_other_gates_before_fixture_startup(self):
        options=dict(native_dlq_audit=True,sdk='/fixed/source',image='fixture',mysql_image='mysql:8.0.36',
                     report='report.json',python='uv',qs_deferred_kind='mysql',sdk_api_go=False,iam_host=None)
        validate_options(options)
        for name,value in [('sdk_api_go',True),('iam_host','never-export'),
                           ('python','other-runner'),('qs_deferred_kind','worker'),('native_dlq_audit',False)]:
            mixed=dict(options);mixed[name]=value
            with self.assertRaisesRegex(ValueError,'^native DLQ audit is a standalone fixture profile$'):
                validate_options(mixed)

    def test_manifest_has_one_explicit_normal_group_and_owned_least_privilege_role(self):
        plan=manifest();validate_v2(plan)
        self.assertEqual(len(plan['routes']),1)
        route=plan['routes'][0]
        self.assertEqual((route['message_type'],route['owner'],route['route_revision']),('NORMAL','qs.mysql','m3-1'))
        self.assertEqual(plan['accounts'],{'native-audit':dict(owner='qs.mysql',publish=['native-audit'],subscriptions=['native-audit'])})
        self.assertEqual(SDK['Version'],'v0.5.0-rocketmq-tx.3')
        self.assertTrue(SDK['Sum'].startswith('h1:'))

    def test_child_output_allowlist_never_leaks_unknown_body_or_credential(self):
        events=[{'event':'ready','body':'never-export'},
                {'event':'failed','status':['never-export']},
                {'event':'failed','status':{'credential':'never-export'}},
                {'event':'failed','status':'never-export'},
                {'event':'closed','credential':'never-export'},'never-export',None]
        for event in events:
            with self.subTest(event_type=type(event).__name__):
                self.assertEqual(safe_event(event),dict(event='invalid_native_audit_event'))
                with self.assertRaises(RuntimeError):require_event(event,'ready')

    def test_actual_ready_requires_one_publish_one_slot_and_sha_not_arbitrary_text(self):
        ready=dict(event='ready',ready=True,published=1,max_inflight=1,wire_sha256='a'*64)
        self.assertEqual(require_event(ready,'ready'),ready)
        for field,value in [('published',True),('max_inflight',2),('wire_sha256','never-export'),('body','never-export')]:
            bad=dict(ready);bad[field]=value
            with self.assertRaises(RuntimeError):require_event(bad,'ready')

    def test_closed_requires_failed_handoff_no_application_ack_and_exact_wire(self):
        closed=dict(event='closed',closed=True,published=1,handler_calls=1,failed_handoff_calls=2,
                    wire_mismatches=0,application_ack_calls=0)
        self.assertEqual(require_event(closed,'closed'),closed)
        for field,value in [('handler_calls',0),('failed_handoff_calls',0),('published',2),
                            ('wire_mismatches',1),('application_ack_calls',1),('handler_calls',True)]:
            bad=dict(closed);bad[field]=value
            with self.assertRaises(RuntimeError):require_event(bad,'closed')
        self.assertEqual(safe_event({'event':'exited'}),{'event':'exited'})
