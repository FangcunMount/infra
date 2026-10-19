import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('ca', Path(__file__).with_name('ca.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class CATest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'components/mysql-client'
        self.source.mkdir(parents=True)
        self.cert = self.source/'ca-chain.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(self.root/'private.key'), '-out', str(self.cert),
                        '-days', '30', '-subj', '/CN=isolated-test-CA',
                        '-addext', 'basicConstraints=critical,CA:TRUE'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.manifest = self.source/'manifest.json'
        self.manifest.write_text(json.dumps({'sha256': hashlib.sha256(self.cert.read_bytes()).hexdigest()}))
        self.git('init', '-q')
        self.git('add', 'components')
        self.git('-c', 'user.name=test', '-c', 'user.email=test@example.com', 'commit', '-qm', 'isolated CA')
        self.ref = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True)

    def test_install_verify_and_drift_rejection(self):
        target = self.root/'installed/ca.pem'
        with patch.object(m, 'ROOT', self.root), patch.object(m, 'TARGET', target):
            m.execute('install', self.ref)
            m.execute('verify', self.ref)
            self.assertEqual(target.stat().st_mode & 0o777, 0o644)
            target.write_text('changed')
            with self.assertRaises(ValueError):
                m.execute('verify', self.ref)

    def test_mutable_ref_and_checksum_mismatch_rejected(self):
        with patch.object(m, 'ROOT', self.root):
            with self.assertRaises(ValueError):
                m.source('main')
            self.manifest.write_text(json.dumps({'sha256': '0'*64}))
            self.git('add', 'components')
            self.git('-c', 'user.name=test', '-c', 'user.email=test@example.com', 'commit', '-qm', 'bad checksum')
            with self.assertRaises(ValueError):
                m.source(self.git('rev-parse', 'HEAD').strip())

    def test_expired_trust_root_is_rejected(self):
        expired = b'-----BEGIN CERTIFICATE-----\nMIIBTTCB9KADAgECAgEBMAoGCCqGSM49BAMCMCYxJDAiBgNVBAMMG2V4cGlyZWQg\naXNvbGF0ZWQgQ0EgZml4dHVyZTAeFw0wMDAxMDEwMDAwMDBaFw0wMDAxMDIwMDAw\nMDBaMCYxJDAiBgNVBAMMG2V4cGlyZWQgaXNvbGF0ZWQgQ0EgZml4dHVyZTBZMBMG\nByqGSM49AgEGCCqGSM49AwEHA0IABDDNQvOxTFcQMP6S91Mwz3DMHtZrBdojZVjw\nmLB7eNiX1lHCEMRg3UnlpL8sD2t5HuKlFG8Jmd2FHE5dS4lm4o6jEzARMA8GA1Ud\nEwEB/wQFMAMBAf8wCgYIKoZIzj0EAwIDSAAwRQIgKoQVkJjzvHGXOvQPinZxncVm\n4RJ3KlLsaVC7Wu8jMuUCIQCHII8hQ9NpPUymKMeFFQuK27ThfTBbjEnZdtQih/oY\nBg==\n-----END CERTIFICATE-----\n'
        with self.assertRaises(ValueError):
            m.validate_ca(expired)

    def test_private_keys_and_non_pem_rejected(self):
        for data in (b'', b'garbage', self.cert.read_bytes()+(self.root/'private.key').read_bytes()):
            with self.assertRaises(ValueError):
                m.validate_ca(data)


if __name__ == '__main__':
    unittest.main()
