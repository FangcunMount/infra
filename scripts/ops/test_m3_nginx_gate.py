import unittest

from m3_nginx_gate import GUARDS, render


ORIGINAL = '''upstream owned_service { server owned:8080; }
server {
    listen 80;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    location / { proxy_pass http://owned_service; }
}
'''


class GateRenderingTest(unittest.TestCase):
    def test_open_preserves_exact_original_bytes(self):
        self.assertEqual(render(ORIGINAL, 'open'), ORIGINAL)

    def test_closed_inserts_only_at_two_servers_preserving_upstream_and_routes(self):
        value = render(ORIGINAL, 'closed')
        insertion = '\n    # M3 reviewed admission gate\n    return 503;'
        self.assertEqual(value.count(insertion), 2)
        self.assertEqual(value.replace(insertion, ''), ORIGINAL)

    def test_login_gate_uses_normalized_uri_and_exact_non_admin_authn_paths(self):
        value = render(ORIGINAL, 'login-only')
        self.assertEqual(value.count(GUARDS['login-only'].replace('\n', '\n    ')), 2)
        self.assertIn('$uri ~ ^/api/v3/authn/(login|refresh_token|verify|logout)$', value)
        self.assertNotIn('$request_uri ~', value)
        self.assertNotIn('authn/admin', value)

    def test_unknown_layout_grpc_and_repeated_render_refused(self):
        for text, mode in ((ORIGINAL, 'unknown'), ('server {}', 'closed'),
                           (ORIGINAL+'grpc_pass grpc://owned;', 'closed'),
                           (render(ORIGINAL, 'closed'), 'closed')):
            with self.assertRaises(ValueError): render(text, mode)


if __name__ == '__main__': unittest.main()
