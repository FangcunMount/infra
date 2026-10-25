import contextlib
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import m3_mysql_credential as tool


def fixture(root):
    value = dict(schema='m3-mysql-self-credential/v1', operation_id='isolated-rotation',
                 host='127.0.0.1', port=3306, username='owned_app', current_account='owned_app@%',
                 server_uuid='11111111-1111-1111-1111-111111111111', server_version='8.0.36',
                 old_password='old-private-value', new_password='a'*64, ca_file='/owned/ca.pem',
                 directory=str(root), expires_at=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat(),
                 coordinator_binding_sha256='b'*64)
    path = root/'plan.json'
    path.write_text(json.dumps(value));path.chmod(0o600)
    return path, tool.digest(path.read_bytes()), value


class CredentialBoundaryTest(unittest.TestCase):
    def test_reviewed_private_current_input_and_exact_identity(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name);root.chmod(0o700);path, sha, value = fixture(root)
            self.assertEqual(tool.load(path, sha), value)
            path.write_text(path.read_text()+' ')
            with self.assertRaises(tool.Refused):tool.load(path, sha)

    def test_unsafe_modes_symlinks_expiry_and_different_account_refused(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name);root.chmod(0o700);path, sha, value = fixture(root)
            path.chmod(0o644)
            with self.assertRaises(tool.Refused):tool.load(path, sha)
            path.chmod(0o600);alias=root/'alias';alias.symlink_to(path)
            with self.assertRaises(OSError):tool.load(alias, sha)
            for key, changed in [('current_account','other@%'), ('expires_at','2000-01-01T00:00:00Z'),
                                 ('new_password',value['old_password']), ('server_version','8.4.1')]:
                bad=dict(value);bad[key]=changed;path.write_text(json.dumps(bad))
                with self.assertRaises(tool.Refused):tool.load(path,tool.digest(path.read_bytes()))

    def test_apply_requires_both_named_attestations_before_network(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);root.chmod(0o700);path,sha,_=fixture(root)
            for extra in ([],['--writers-excluded'],['--coordinated-start-already-issued']):
                with patch.object(tool,'perform',side_effect=AssertionError('network not allowed')):
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(tool.main(['--plan',str(path),'--reviewed-sha256',sha,'--action','apply',*extra]),1)

    def test_issued_marker_prevents_second_apply_and_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);root.chmod(0o700);path,sha,value=fixture(root)
            tool.publish(value,'rotation-issued.json',{'uncertain':True})
            with self.assertRaises(FileExistsError):tool.publish(value,'rotation-issued.json',{'replaced':True})
            with patch.object(tool,'perform',side_effect=AssertionError('no repeat ALTER')):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(tool.main(['--plan',str(path),'--reviewed-sha256',sha,'--action','apply',
                                                '--writers-excluded','--coordinated-start-already-issued']),1)
            self.assertEqual(json.loads((root/'rotation-issued.json').read_text()),{'uncertain':True})

    def test_default_is_preview_and_driver_exceptions_never_print_credentials(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);root.chmod(0o700);path,sha,value=fixture(root)
            async def failed(plan,expected,action):
                self.assertEqual(action,'preview');raise RuntimeError(value['old_password'])
            output=io.StringIO()
            with patch.object(tool,'perform',side_effect=failed),contextlib.redirect_stdout(output):
                self.assertEqual(tool.main(['--plan',str(path),'--reviewed-sha256',sha]),1)
            self.assertNotIn(value['old_password'],output.getvalue())
            self.assertNotIn(value['new_password'],output.getvalue())


if __name__=='__main__':unittest.main()
