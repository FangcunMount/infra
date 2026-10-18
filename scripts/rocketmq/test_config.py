import json
import tempfile
import unittest
from pathlib import Path
from render import render
from routes import validate,physical_topic,consumer_group


class ConfigurationTests(unittest.TestCase):
    def test_private_renderer_enables_flush_auth_and_distinct_accounts(self):
        templates=Path(__file__).resolve().parents[2]/"components/rocketmq"
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)/"config"
            render({"admin":{"username":"admin","password":"a"*32},"inner":{"username":"inner","password":"b"*32}},dest,"127.0.0.1",templates)
            broker=(dest/"broker.conf").read_text()
            self.assertIn("flushDiskType=SYNC_FLUSH",broker)
            self.assertIn("autoCreateTopicEnable=false",broker)
            proxy=json.loads((dest/"proxy.json").read_text())
            self.assertTrue(proxy["authenticationEnabled"])
            self.assertTrue(proxy["authorizationEnabled"])
            self.assertEqual((dest/"broker.conf").stat().st_mode&0o777,0o640)
            self.assertNotEqual(json.loads(proxy["initAuthenticationUser"])["username"],json.loads(proxy["innerClientAuthenticationCredentials"])["accessKey"])

    def test_test_manifest_uses_same_canonical_algorithm(self):
        path=Path(__file__).resolve().parents[2]/"components/rocketmq/test-routes.json"
        value=json.loads(path.read_text()); validate(value)
        self.assertEqual(physical_topic("m1.interop"),"rmq_t_e03f591224481d6461d6d759dc8815c4")
        self.assertEqual(consumer_group("m1.interop","m1-go"),"rmq_g_04d4a0d308d15cf1c93acb7c0b2f7a55")
        value["routes"][0]["physical_topic"]="m1.interop"
        with self.assertRaises(ValueError): validate(value)


if __name__=="__main__":unittest.main()
