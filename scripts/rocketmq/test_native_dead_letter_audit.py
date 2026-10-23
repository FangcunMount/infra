import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from audit_native_dead_letters import export, main, parse_index, select_route

MANIFEST = Path(__file__).resolve().parents[2]/'components/rocketmq/serverd-routes-m3-v2.json'
HEADER = '#Message ID #QID #Offset #IndexKey\n'
KEY = 'fixture-key'


def manifest():
    return json.loads(MANIFEST.read_text())


def row(topic, identity='A'*32, offset=12):
    return f'{identity} 0 {offset} 123@{topic}@K@{KEY}@{identity}@456\n'


class NativeDeadLetterAuditTest(unittest.TestCase):
    def test_shared_group_reports_both_candidate_owners_without_selecting_database(self):
        selected = select_route(manifest(),'qs-evaluation-mysql')
        self.assertEqual(selected['candidate_owners'],['qs.mongo','qs.mysql'])
        self.assertTrue(selected['owner_scope_ambiguous'])
        self.assertEqual(selected['topic'],select_route(manifest(),'qs-evaluation-mongo')['topic'])
        self.assertNotIn('database',json.dumps(selected))

    def test_unsubscribed_unknown_or_noncanonical_route_rejected(self):
        for route in ('iam-sms','unknown'):
            with self.assertRaises(ValueError):select_route(manifest(),route)
        bad = manifest();bad['routes'][0]['consumer_group'] = 'unreviewed-group'
        with self.assertRaises(ValueError):select_route(bad,'iam-authz-iam')
        bad = manifest();bad['routes'][0]['owner'] = 'other.mysql'
        with self.assertRaises(ValueError):select_route(bad,'iam-authz-iam')

    def test_malformed_manifest_shapes_fail_without_echoing_input(self):
        shapes = [None,[],{'version':2,'routes':['never-export']}]
        bad = manifest();bad['accounts']=['never-export'];shapes.append(bad)
        for value in shapes:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(ValueError,'^canonical v2 manifest required$'):
                    select_route(value,'iam-authz-iam')

    def test_index_only_output_omits_raw_key_body_and_private_diagnostics(self):
        topic = select_route(manifest(),'iam-authz-iam')['topic']
        report = parse_index('credential=never-export\n'+HEADER+row(topic)+'body=never-export',KEY,topic)
        encoded = json.dumps(report)
        self.assertNotIn('never-export',encoded)
        self.assertNotIn(KEY,encoded)
        self.assertFalse(report['body_exported'])
        self.assertEqual(report['records'][0]['commitlog_offset'],456)
        self.assertEqual(report['alert'],'native_dead_letter_records')
        self.assertEqual(report['query_scope'],'one_key_one_group_not_global_inventory')

    def test_malformed_wrong_scope_duplicate_and_missing_header_refused(self):
        topic = select_route(manifest(),'iam-authz-iam')['topic']
        line = row(topic)
        for raw in (line,HEADER+line+line,HEADER+line.replace('@K@','@T@'),
                    HEADER+line.replace('@'+KEY+'@','@different@'),
                    HEADER+line.replace(' 0 12 ',' -1 12 '),
                    HEADER+line.replace(' 0 12 ',' 0 '+str(2**63)+' '),
                    HEADER+line.replace('123@','１２３@'),
                    HEADER+line.replace('@456','@-1')):
            with self.subTest(raw_hash=len(raw)), self.assertRaises(RuntimeError):
                parse_index(raw,KEY,topic)
        with self.assertRaises(ValueError):parse_index(HEADER,'unbounded\nkey',topic)
        with self.assertRaises(ValueError):parse_index(HEADER,KEY,'ordinary-topic')

    def test_empty_keyed_result_never_claims_global_dlq_empty(self):
        topic = select_route(manifest(),'iam-authz-iam')['topic']
        r = parse_index(HEADER,KEY,topic)
        self.assertEqual(r['records'],[])
        self.assertIsNone(r['alert'])
        self.assertEqual(r['query_scope'],'one_key_one_group_not_global_inventory')
        with self.assertRaises(RuntimeError):parse_index('No message found',KEY,topic)

    def test_export_count_is_bounded_and_truncation_explicit(self):
        topic = select_route(manifest(),'iam-authz-iam')['topic']
        raw = HEADER+''.join(row(topic,identity=f'{n:032X}') for n in range(64))
        self.assertTrue(parse_index(raw,KEY,topic)['truncated_possible'])
        with self.assertRaises(RuntimeError):parse_index(raw+row(topic,identity=f'{64:032X}'),KEY,topic)
        with self.assertRaises(RuntimeError):parse_index('x'*1048577,KEY,topic)

    def test_only_inspect_and_bounded_read_command_run_then_private_atomic_export(self):
        topic = select_route(manifest(),'iam-authz-iam')['topic']
        replies = [subprocess.CompletedProcess([],0,'fixture\n',''),
                   subprocess.CompletedProcess([],0,HEADER+row(topic),'')]
        with tempfile.TemporaryDirectory() as directory, patch('audit_native_dead_letters.subprocess.run',side_effect=replies) as run:
            path = Path(directory)/'audit.json'
            report = export('fixture-broker','fixture',MANIFEST,'iam-authz-iam',KEY,path)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(json.loads(path.read_text()),report)
            commands = [c.args[0] for c in run.call_args_list]
            self.assertEqual(commands[0][:2],['docker','inspect'])
            self.assertIn('queryMsgByKey',commands[1])
            self.assertEqual(commands[1][-8:],['-n','nameserver:9876','-t',topic,'-k',KEY,'-m','64'])
            self.assertEqual(len(commands),2)
            for call in run.call_args_list:self.assertEqual(call.kwargs['timeout'],45)

    def test_project_mismatch_refuses_admin_and_creates_no_audit(self):
        with tempfile.TemporaryDirectory() as directory, patch('audit_native_dead_letters.subprocess.run',return_value=subprocess.CompletedProcess([],0,'different\n','')) as run:
            path = Path(directory)/'audit.json'
            with self.assertRaises(RuntimeError):export('fixture-broker','fixture',MANIFEST,'iam-authz-iam',KEY,path)
            self.assertEqual(run.call_count,1)
            self.assertFalse(path.exists())

    def test_existing_file_and_symlink_are_never_replaced(self):
        topic = select_route(manifest(),'iam-authz-iam')['topic']
        replies = [subprocess.CompletedProcess([],0,'fixture\n',''),subprocess.CompletedProcess([],0,HEADER+row(topic),'')]
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'original';target.write_text('preserve')
            link = Path(directory)/'audit';link.symlink_to(target)
            with patch('audit_native_dead_letters.subprocess.run',side_effect=replies),self.assertRaises(FileExistsError):
                export('fixture-broker','fixture',MANIFEST,'iam-authz-iam',KEY,link)
            self.assertEqual(target.read_text(),'preserve')

    def test_cli_hides_private_errors_and_uses_safe_nonzero_status(self):
        output = io.StringIO()
        args=['audit','--container','fixture-broker','--project','fixture','--route','iam-authz-iam',
              '--key',KEY,'--manifest',str(MANIFEST),'--output','/tmp/not-created-audit.json']
        with patch('sys.argv',args),patch('audit_native_dead_letters.export',side_effect=RuntimeError('credential=never-export')),contextlib.redirect_stdout(output):
            self.assertEqual(main(),1)
        self.assertEqual(json.loads(output.getvalue()),dict(status='unavailable',read_only=True,body_exported=False))

    def test_cli_reports_critical_without_echoing_identifiers(self):
        output = io.StringIO();topic = select_route(manifest(),'iam-authz-iam')['topic']
        report = parse_index(HEADER+row(topic),KEY,topic)
        report.update(owner_scope_ambiguous=False)
        args=['audit','--container','fixture-broker','--project','fixture','--route','iam-authz-iam',
              '--key',KEY,'--manifest',str(MANIFEST),'--output','/tmp/not-created-audit.json']
        with patch('sys.argv',args),patch('audit_native_dead_letters.export',return_value=report),contextlib.redirect_stdout(output):
            self.assertEqual(main(),2)
        self.assertNotIn(KEY,output.getvalue())
        self.assertNotIn(topic,output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['records'],1)
