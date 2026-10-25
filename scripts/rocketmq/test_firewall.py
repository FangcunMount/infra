"""Exercise the real shell with owned command fakes, never host firewall/Docker."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name('firewall.sh').resolve()


class WorkerBridgeFirewallTests(unittest.TestCase):
    def network(self):
        return {'Name': 'qs-network', 'Id': 'a' * 64, 'Driver': 'bridge', 'Options': {},
                'Containers': {str(i): {'Name': f'qs-worker-runtime-{i}'} for i in [1, 2, 3]}}

    def exercise(self, network, missing=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);bin_dir = root/'bin';bin_dir.mkdir()
            fixture = root/'network.json';fixture.write_text(json.dumps([network]))
            scripts = {
                'id': '#!/bin/sh\necho 0\n',
                'docker': '#!/bin/sh\n' + ("echo 'Error response from daemon: network qs-network not found' >&2\nexit 1\n" if missing else 'cat "$M3_NETWORK_FIXTURE"\n'),
                'iptables': '#!/bin/sh\nprintf "%s\\n" "$*" >> "$M3_IPTABLES_LOG"\nexit 0\n',
                'iptables-restore': '#!/bin/sh\nprintf "%s\\n" "$*" > "$M3_RESTORE_ARGS"\ncat > "$M3_RULES_OUT"\n',
            }
            for name, body in scripts.items():
                p = bin_dir/name;p.write_text(body);p.chmod(0o700)
            env = dict(os.environ, PATH=str(bin_dir)+os.pathsep+os.environ['PATH'],
                       M3_NETWORK_FIXTURE=str(fixture), M3_IPTABLES_LOG=str(root/'calls'),
                       M3_RULES_OUT=str(root/'rules'), M3_RESTORE_ARGS=str(root/'args'))
            p = subprocess.run(['/bin/bash', str(SCRIPT)], capture_output=True, text=True, env=env, timeout=10)
            read = lambda name: (root/name).read_text() if (root/name).exists() else ''
            return p.returncode, read('rules'), read('calls'), read('args')

    def test_exact_dedicated_bridge_reaches_only_private_grpc(self):
        code, rules, calls, args = self.exercise(self.network())
        self.assertEqual(code, 0)
        local = [x for x in rules.splitlines() if 'infra-m3-local-qs-worker' in x]
        self.assertEqual(len(local), 1)
        self.assertIn('-i br-'+'a'*12, local[0])
        self.assertIn('--ctorigdst 100.118.164.39 --ctorigdstport 8081', local[0])
        self.assertIn('--ctdir ORIGINAL', local[0])
        self.assertNotIn('5557', local[0])
        self.assertIn('--noflush', args)
        self.assertNotIn('-F DOCKER-USER', rules+calls)
        self.assertIn('-A INFRA-ROCKETMQ -p tcp -j REJECT --reject-with tcp-reset', rules)
        self.assertEqual(sum('--ctorigdstport 5557' in x for x in rules.splitlines()), 1)

    def test_other_original_tailnet_rules_are_retained(self):
        _, rules, _, _ = self.exercise(self.network())
        for address in ['100.85.122.124', '100.74.123.45', '100.91.31.24', '100.126.200.55']:
            self.assertIn('--ctorigdstport 8081 -s '+address+' -j RETURN', rules)
        self.assertIn('-s 100.118.164.39 -j RETURN', rules)

    def test_missing_network_keeps_broker_only_restriction(self):
        code, rules, _, _ = self.exercise(self.network(), missing=True)
        self.assertEqual(code, 0)
        self.assertNotIn('infra-m3-local-qs-worker', rules)
        self.assertIn('-j REJECT', rules)

    def test_network_exists_before_workers_restart(self):
        n = self.network();n['Containers'] = {}
        self.assertEqual(self.exercise(n)[0], 0)

    def test_unreviewed_member_rejected_before_replacing_filter(self):
        n = self.network();n['Containers']['other'] = {'Name': 'other-service'}
        code, rules, calls, _ = self.exercise(n)
        self.assertNotEqual(code, 0)
        self.assertEqual(rules, '')
        self.assertNotIn('-N INFRA-ROCKETMQ', calls)

    def test_bad_id_driver_or_options_rejected_before_replacing_filter(self):
        for key, value in [('Id', 'x;injection'), ('Driver', 'overlay'), ('Options', {'bridge': 'untrusted'})]:
            n = self.network();n[key] = value
            with self.subTest(key=key):
                code, rules, _, _ = self.exercise(n)
                self.assertNotEqual(code, 0)
                self.assertEqual(rules, '')


if __name__ == '__main__':
    unittest.main()
