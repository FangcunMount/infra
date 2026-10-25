import contextlib
import hashlib
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import m3_operator_step as operator
from start_boundary import Boundary, BoundaryError, _encoded, initialize


def fixture(root, kind='runtime-start'):
    root=Path(root);directory=root/'coordinator'
    binding=dict(schema='m3-start-boundary/v1',operation_id='owned-operator-fixture',directory=str(directory),
                 scope_sha256='1'*64,protection_sha256='2'*64,restore_receipt_sha256='3'*64,
                 source_bundle_sha256='4'*64,data_owner='owned-test',recovery_owner='owned-test')
    binding_sha=hashlib.sha256(_encoded(binding)).hexdigest();initialize(directory,binding,binding_sha)
    script=b'exit 0\n';source=root/'reviewed.sh';source.write_bytes(script);source.chmod(0o600)
    plan=dict(schema='m3-cutover-step/v1',directory=str(directory),binding_sha256=binding_sha,host=socket.gethostname(),
              step='owned-step',kind=kind,script=str(source),script_sha256=hashlib.sha256(script).hexdigest(),
              cwd=str(root),timeout_seconds=2)
    file=root/'plan.json';file.write_bytes(_encoded(plan));file.chmod(0o600)
    return file,hashlib.sha256(_encoded(plan)).hexdigest(),plan,script


class OperatorBarrierTest(unittest.TestCase):
    def test_default_only_verifies_without_network_or_barrier_change(self):
        with tempfile.TemporaryDirectory() as root:
            path,sha,plan,_=fixture(root)
            with patch.object(operator,'execute',side_effect=AssertionError('no execution')):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(operator.main(['--plan',str(path),'--reviewed-sha256',sha]),0)
            self.assertEqual(json.loads(out.getvalue())['status'],'offline_plan_verified')
            self.assertFalse((Path(plan['directory'])/'first-runtime-start.json').exists())

    def test_wrong_operator_host_platform_and_changed_script_refused_before_callback(self):
        with tempfile.TemporaryDirectory() as root:
            _,sha,plan,script=fixture(root)
            with patch.object(operator,'run_script',side_effect=AssertionError('no remote command')):
                with patch.object(operator.platform,'system',return_value='Linux'):
                    with self.assertRaises(BoundaryError):operator.execute(plan,script,sha)
                with patch.object(operator.platform,'system',return_value='Darwin'),patch.object(operator.socket,'gethostname',return_value='another-operator'):
                    with self.assertRaises(BoundaryError):operator.execute(plan,script,sha)
                with self.assertRaises(BoundaryError):operator.execute(plan,b'changed',sha)

    def test_first_start_is_persistent_before_callback_and_failure_forbids_restore(self):
        with tempfile.TemporaryDirectory() as root:
            _,sha,plan,script=fixture(root)
            def failed(*args):
                self.assertTrue((Path(plan['directory'])/'first-runtime-start.json').is_file())
                raise BoundaryError('controlled SSH failure; remote result unknown')
            with patch.object(operator.platform,'system',return_value='Darwin'),patch.object(operator,'run_script',side_effect=failed):
                with self.assertRaises(BoundaryError):operator.execute(plan,script,sha)
            with Boundary(plan['directory'],plan['binding_sha256']) as boundary:
                with self.assertRaises(BoundaryError):boundary.restore_before_start('forbidden',lambda:self.fail('no restore'))

    def test_maintenance_keeps_original_boundary_and_does_not_mark_start(self):
        with tempfile.TemporaryDirectory() as root:
            _,sha,plan,script=fixture(root,'pre-start-maintenance')
            with patch.object(operator.platform,'system',return_value='Darwin'),patch.object(operator,'run_script') as command:
                operator.execute(plan,script,sha);command.assert_called_once()
            self.assertFalse((Path(plan['directory'])/'first-runtime-start.json').exists())

    def test_actual_bounded_script_on_operator_filesystem_and_private_log(self):
        with tempfile.TemporaryDirectory() as root:
            _,sha,plan,script=fixture(root,'pre-start-maintenance')
            with patch.object(operator.platform,'system',return_value='Darwin'):
                operator.execute(plan,script,sha)
            logs=list(Path(plan['directory']).glob('command-*.log'))
            self.assertEqual(len(logs),1);self.assertEqual(logs[0].stat().st_mode & 0o777,0o600)


if __name__=='__main__':unittest.main()
