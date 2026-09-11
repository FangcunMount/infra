"""Exercise real signing in a disposable PKI; never use production keys."""
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('grpc-mtls.sh').resolve()


class CertificatePermissionsTest(unittest.TestCase):
    def test_single_service_signing_preserves_existing_pki_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            certs = root / 'certs'
            env = dict(os.environ, CERT_DIR=str(certs),
                       CERT_OWNER=str(os.getuid()), CERT_GROUP=str(os.getgid()))

            def run(*args):
                return subprocess.run(['bash', str(SCRIPT), *args], env=env,
                                      check=True, capture_output=True, text=True)

            run('generate-ca')
            run('generate-server', 'qs-apiserver', 'QS', 'qs-apiserver', 'dual')
            run('generate-server', 'iam-apiserver', 'IAM', 'iam-apiserver', 'dual')
            # Deliberately distinct valid permissions reveal unrelated chmod calls.
            for path in certs.rglob('*'):
                if path.is_file():
                    path.chmod(0o640)
            before = {p: (stat.S_IMODE(p.stat().st_mode), p.stat().st_uid, p.stat().st_gid)
                      for p in [certs, *certs.rglob('*')]}
            unchanged = {p: p.read_bytes() for p in certs.rglob('*')
                         if p.is_file() and p.suffix != '.srl'}
            # Capture chown arguments, including recursion, even when tests run as one user.
            tools = root / 'bin'
            tools.mkdir()
            log = root / 'chown.jsonl'
            wrapper = tools / 'chown'
            wrapper.write_text('#!/usr/bin/env python3\nimport json,os,sys\n'
                               'with open(os.environ["CHOWN_LOG"],"a") as f:\n'
                               ' f.write(json.dumps(sys.argv[1:])+"\\n")\n')
            wrapper.chmod(0o755)
            env.update(PATH=str(tools) + os.pathsep + env['PATH'], CHOWN_LOG=str(log))

            for _ in range(2):  # First issue and renewal must have the same narrow scope.
                run('generate-server', 'qs-ai', 'QS', 'qs-ai-grpc', 'dual')
                for path, expected in before.items():
                    info = path.stat()
                    self.assertEqual((stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid),
                                     expected, str(path))
                for path, content in unchanged.items():
                    self.assertEqual(path.read_bytes(), content, str(path))
                expected_files = [certs / 'server' / ('qs-ai' + suffix)
                                  for suffix in ('.key', '.crt', '-fullchain.crt')]
                for path in expected_files:
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode),
                                     0o600 if path.suffix == '.key' else 0o644)
                calls = [json.loads(line) for line in log.read_text().splitlines()]
                for call in calls:
                    self.assertEqual(call[0], env['CERT_OWNER'] + ':' + env['CERT_GROUP'])
                    self.assertEqual(set(call[1:]), {str(p) for p in expected_files})
                details = subprocess.check_output(
                    ['openssl', 'x509', '-in', str(expected_files[1]), '-noout', '-text'], text=True)
                for value in ('qs-ai.svc', 'qs-ai-grpc', 'TLS Web Server Authentication',
                              'TLS Web Client Authentication'):
                    self.assertIn(value, details)

            wrapper.write_text('#!/bin/sh\nexit 1\n')
            failed = subprocess.run(
                ['bash', str(SCRIPT), 'generate-server', 'qs-ai', 'QS', 'qs-ai-grpc', 'dual'],
                env=env, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn('chown 失败', failed.stdout)
            self.assertNotIn('服务端证书生成完成', failed.stdout)


if __name__ == '__main__':
    unittest.main()
