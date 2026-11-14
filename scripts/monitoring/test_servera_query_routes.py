"""Keep rule reads on the existing private, read-only monitoring paths."""
from pathlib import Path
import re
import unittest

FORMAL = Path(__file__).resolve().parents[2] / "deploy/serverA/monitoring"

READ_ONLY_PATHS = (
    "/-/ready",
    "/api/v1/query",
    "/api/v1/query_range",
    "/api/v1/labels",
    "/api/v1/label/instance/values",
    "/api/v1/series",
    "/api/v1/metadata",
    "/api/v1/rules",
    "/api/v1/status/buildinfo",
)
FORBIDDEN_PATHS = (
    "/api/v1/admin/tsdb/snapshot",
    "/api/v1/rules/reload",
    "/api/v1/read",
    "/api/v1/write",
    "/-/reload",
    "/-/quit",
)


class ServerAQueryRoutesTest(unittest.TestCase):
    def test_rule_read_is_an_exact_path_on_both_layers(self):
        for name in ("query-bridge.conf", "grafana-listener.conf"):
            with self.subTest(name=name):
                config = (FORMAL / name).read_text()
                matches = re.findall(r"(?m)^\s*location ~ (\^\S+\$) \{", config)
                self.assertEqual(len(matches), 1)
                whitelist = re.compile(matches[0])
                self.assertTrue(
                    all(whitelist.fullmatch(path) for path in READ_ONLY_PATHS)
                )
                self.assertFalse(
                    any(whitelist.fullmatch(path) for path in FORBIDDEN_PATHS)
                )
                self.assertIn("limit_except GET { deny all; }", config)
                self.assertIn("location / { return 404; }", config)
                self.assertIn("proxy_pass_request_body off;", config)

    def test_candidate_bridge_has_exact_proxy_source(self):
        config = (FORMAL / "query-bridge.conf").read_text()
        self.assertIn("listen 172.31.251.3:19091;", config)
        self.assertIn("allow 172.31.251.2;\n        deny all;", config)
        self.assertIn("proxy_pass http://127.0.0.1:9090;", config)

    def test_private_listener_requires_client_certificate(self):
        config = (FORMAL / "grafana-listener.conf").read_text()
        self.assertIn("listen 19191 ssl;", config)
        self.assertIn("ssl_protocols TLSv1.2 TLSv1.3;", config)
        self.assertIn("ssl_client_certificate /run/h06-tls/client-ca.crt;", config)
        self.assertIn("ssl_verify_client on;", config)
        self.assertIn("proxy_pass http://172.31.251.3:19091;", config)
