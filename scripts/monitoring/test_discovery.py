import importlib.util
from pathlib import Path
import unittest


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


remote = load('remote', 'discovery-remote.py')
local = load('local', 'discover.py')


def container(name, ip, job=None, port=8080, running=True):
    labels = {'prometheus.scrape': 'true', 'prometheus.job': job, 'prometheus.metrics_port': str(port)} if job else {}
    return {'Name': '/' + name, 'State': {'Running': running}, 'Config': {'Labels': labels, 'Env': ['PASSWORD=never-export']},
            'NetworkSettings': {'Networks': {'infra-network': {'IPAddress': ip}}}}


class DiscoveryTests(unittest.TestCase):
    def test_preserves_existing_labels_and_all_replicas(self):
        cs = [container('qs-apiserver', '172.20.0.2', 'qs-apiserver'),
              container('qs-ai', '172.20.0.3')]
        cs += [container(f'qs-collection-server-{i}', f'172.20.0.{10+i}', 'qs-collection-server') for i in range(1, 3)]
        cs += [container(f'qs-worker-runtime-{i}', f'172.20.0.{20+i}', 'qs-worker', 9092) for i in range(1, 4)]
        result = remote.endpoints(cs)
        self.assertEqual(len(result), 7)
        self.assertEqual([x['instance'] for x in result[:2]], ['qs-apiserver:8080', 'qs-ai-api:8000'])
        self.assertEqual(result[2]['instance'], '172.20.0.11:8080')
        self.assertNotIn('component', result[0])
        self.assertEqual(result[4]['component'], 'qs-worker')
        self.assertNotIn('PASSWORD', str(result))
        groups = local.groups(result, '100.85.122.124:443')
        self.assertEqual(groups[4]['labels']['__metrics_path__'], '/metrics/172.20.0.21/9092')
        self.assertEqual(groups[4]['labels']['job'], 'qs-worker')

    def test_iam_exact_original_identity_is_discovered_without_container_relabel(self):
        result = remote.endpoints([container('iam-apiserver', '172.20.0.8')])
        self.assertEqual(result, [{'ip': '172.20.0.8', 'port': 9080, 'job': 'iam', 'instance': 'iam-apiserver:9080'}])
        self.assertEqual(local.groups(result, '100.85.122.124:443')[0]['labels']['__metrics_path__'], '/metrics/172.20.0.8/9080')
        self.assertEqual(remote.endpoints([container('iam-apiserver', '172.20.0.8', running=False)]), [])
        self.assertNotIn('PASSWORD', str(result))

    def test_iam_port_and_identity_cannot_be_reassigned_to_other_jobs(self):
        for name, job, port in [('other', 'iam', 9080), ('other', 'iam', 8080), ('worker', 'qs-worker', 9080)]:
            with self.subTest(name=name, job=job, port=port), self.assertRaises(ValueError):
                remote.endpoints([container(name, '172.20.0.8', job, port)])
        for job, port, instance in [('iam', 8080, 'iam-apiserver:9080'), ('qs-worker', 9080, 'worker'), ('iam', 9080, 'other')]:
            with self.subTest(job=job, port=port), self.assertRaises(ValueError):
                local.groups([{'job': job, 'port': port, 'ip': '172.20.0.8', 'instance': instance}], 'gateway:443')

    def test_new_replica_is_discovered_without_static_target_edits(self):
        self.assertEqual(len(remote.endpoints([container('qs-worker-runtime-4', '172.20.0.24', 'qs-worker', 9092)])), 1)

    def test_unmonitored_and_stopped_containers_are_excluded(self):
        self.assertEqual(remote.endpoints([container('mysql', '172.20.0.3'), container('worker', '172.20.0.4', 'qs-worker', 9092, False)]), [])

    def test_rejects_non_overlay_target_and_other_ports(self):
        for ip, port in [('127.0.0.1', 8080), ('169.254.169.254', 8080), ('172.20.0.2', 22)]:
            with self.subTest(ip=ip, port=port), self.assertRaises(ValueError):
                remote.endpoints([container('worker', ip, 'qs-worker', port)])

    def test_duplicate_instance_is_not_silently_accepted(self):
        item = {'ip': '172.20.0.2', 'port': 9092, 'job': 'qs-worker', 'instance': 'worker'}
        with self.assertRaises(ValueError):
            local.groups([item, item], '100.85.122.124:443')


if __name__ == '__main__':
    unittest.main()
