import unittest
import re

from m3_nginx_acceptance_gate import render, seconds_pattern


ORIGINAL = '''server {
    listen 18080;
    location / { proxy_set_header Authorization $http_authorization; proxy_pass http://backend; }
}
server {
    listen 18081;
    location / { proxy_set_header Authorization $http_authorization; proxy_pass http://backend; }
}
'''


class AcceptanceGateTest(unittest.TestCase):
    def test_exact_interval_edges_decimal_carries_and_no_lookalike_seconds(self):
        for start, duration in [(1792919997, 17), (1792999995, 1800), (1800000000, 1)]:
            pattern = seconds_pattern(start, start + duration)
            self.assertLess(len(pattern), 2048)
            for second in range(start - 2, start + duration + 3):
                self.assertEqual(bool(re.fullmatch(pattern, str(second))), start <= second < start + duration)
            self.assertIsNone(re.fullmatch(pattern, '0' + str(start)))

    def test_backend_authorization_and_original_servers_are_retained(self):
        value = render(ORIGINAL, 'iam', ['192.0.2.1'], 1800000000, 1800000300)
        self.assertEqual(value.count('proxy_set_header Authorization $http_authorization;'), 2)
        self.assertEqual(value.count('proxy_pass http://backend;'), 2)
        self.assertEqual(value.count('server {'), 2)
        self.assertNotIn('$http_x_forwarded_for', value)
        self.assertIn('$realip_remote_addr', value)

    def test_no_default_or_unbounded_admission(self):
        for start, end in [(True, 1800000300), (1800000000, False),
                           (1800000000, 1800000000), (1800000000, 1800001801)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                render(ORIGINAL, 'qs', ['192.0.2.1'], start, end)

    def test_address_injection_and_broad_ranges_are_rejected(self):
        for peers in [[], ['0.0.0.0'], ['::'], ['224.0.0.1'], ['192.0.2.1/24'],
                      ['192.0.2.1; return 200;'], ['192.0.2.1'] * 2, [None],
                      [f'192.0.2.{i}' for i in range(1, 6)]]:
            with self.subTest(peers=peers), self.assertRaises(ValueError):
                render(ORIGINAL, 'collect', peers, 1800000000, 1800000300)

    def test_gateway_revision_cannot_be_stacked_or_change_internal_transport(self):
        for original in [ORIGINAL + '# M3 reviewed admission gate',
                         ORIGINAL.replace('proxy_pass', 'grpc_pass'), 'server {\n}\n',
                         render(ORIGINAL, 'iam', ['192.0.2.1'], 1800000000, 1800000300)]:
            with self.subTest(original=original), self.assertRaises(ValueError):
                render(original, 'iam', ['192.0.2.1'], 1800000000, 1800000300)


if __name__ == '__main__':
    unittest.main()
