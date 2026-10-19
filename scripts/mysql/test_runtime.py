import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('runtime', Path(__file__).with_name('runtime.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RuntimeTest(unittest.TestCase):
    def before(self, name='qs-apiserver'):
        return {'Name': '/'+name, 'Id': 'a'*64,
                'Config': {'Image': 'old', 'Env': ['QS_APISERVER_MYSQL_HOST=mysql-rds-proxy:3306',
                    'REDIS_PASSWORD=literal$secret', 'MESSAGE_CONFIG=unchanged'],
                    'User': '1000', 'Cmd': ['--config=/app/config.yaml']},
                'HostConfig': {'Memory': 734003200, 'NanoCpus': 500000000,
                    'Binds': ['/private/config:/app/config.yaml:ro'],
                    'RestartPolicy': {'Name': 'unless-stopped'}, 'PortBindings': {}},
                'NetworkSettings': {'Networks': {'infra-network': {
                    'Aliases': [name, 'a'*12], 'IPAddress': '172.20.0.5', 'IPAMConfig': None}}}}

    def patch(self, before):
        return m.payload(before, 'sha256:'+'b'*64, 'example.mysql.rds.aliyuncs.com', 3306, 'c'*40)

    def test_only_connection_image_and_ca_change(self):
        before = self.before()
        frozen = copy.deepcopy(before)
        actual = self.patch(before)
        self.assertEqual(before, frozen)
        env = dict(item.split('=', 1) for item in actual['Env'])
        self.assertEqual(env['REDIS_PASSWORD'], 'literal$secret')
        self.assertEqual(env['MESSAGE_CONFIG'], 'unchanged')
        self.assertEqual(env['QS_APISERVER_MYSQL_HOST'], 'example.mysql.rds.aliyuncs.com:3306')
        self.assertEqual(env['QS_APISERVER_MYSQL_TLS_MODE'], 'VERIFY_IDENTITY')
        host = copy.deepcopy(actual['HostConfig'])
        self.assertEqual(host['Binds'].pop(), m.CA+':'+m.CONTAINER_CA+':ro')
        self.assertEqual(host, before['HostConfig'])
        self.assertEqual(actual['Cmd'], before['Config']['Cmd'])
        endpoint = actual['NetworkingConfig']['EndpointsConfig']['infra-network']
        self.assertEqual(endpoint, {'Aliases': ['qs-apiserver']})

    def test_ai_credentials_database_and_url_parameters_preserved(self):
        before = self.before('qs-ai')
        before['Config']['Env'] = ['QS_AI_DATABASE_URL=mysql+asyncmy://u:p%40%24%3A@mysql-rds-proxy:3306/ai?charset=utf8mb4']
        env = dict(item.split('=', 1) for item in self.patch(before)['Env'])
        self.assertEqual(env['QS_AI_DATABASE_URL'], 'mysql+asyncmy://u:p%40%24%3A@example.mysql.rds.aliyuncs.com:3306/ai?charset=utf8mb4')
        self.assertEqual(env['QS_AI_DATABASE_TLS_CA_FILE'], m.CONTAINER_CA)

    def test_other_services_are_rejected(self):
        with self.assertRaises(ValueError):
            self.patch(self.before('miniblog-backend'))

    def test_proxy_endpoint_and_mutable_image_rejected(self):
        for host, image in [('mysql-rds-proxy', 'sha256:'+'b'*64), ('example.com', 'latest')]:
            with self.assertRaises(ValueError):
                m.payload(self.before(), image, host, 3306, 'c'*40)


if __name__ == '__main__':
    unittest.main()
