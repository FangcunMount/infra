from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Event
import time
import unittest
from unittest.mock import patch


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

    def test_slow_source_does_not_block_other_target_file_and_still_expires(self):
        fresh_worker = {'ip': '172.20.0.21', 'port': 9092, 'job': 'qs-worker', 'instance': 'worker'}
        gateway = 'gateway:443'
        for age, expected_a in ((119, ['previous']), (121, [])):
            with self.subTest(age=age), tempfile.TemporaryDirectory() as directory:
                a_file = Path(directory) / 'serverA.json'
                d_file = Path(directory) / 'serverD.json'
                a_file.write_text('["previous"]\n')
                old = time.time() - age
                os.utime(a_file, (old, old))
                fixed_now = old + age
                slow_started = Event()
                healthy_published = Event()
                replace = local.atomic_write

                def ssh(command, **options):
                    self.assertEqual(options['timeout'], 35)
                    if command[-1] == 'root@a':
                        slow_started.set()
                        self.assertTrue(healthy_published.wait(timeout=5))
                        raise subprocess.TimeoutExpired(command, 35)
                    self.assertEqual(command[-1], 'root@d')
                    self.assertTrue(slow_started.wait(timeout=5))
                    return subprocess.CompletedProcess(command, 0, stdout=json.dumps([fresh_worker]))

                def publish(target, groups):
                    replace(target, groups)
                    if target == d_file:
                        healthy_published.set()

                config = {'sources': [{'name': 'serverA', 'host': 'a'}, {'name': 'serverD', 'host': 'd'}],
                          'output': directory, 'gateway': gateway, 'identity': 'identity', 'known_hosts': 'known_hosts'}
                with patch.object(local.subprocess, 'run', side_effect=ssh), \
                     patch.object(local, 'atomic_write', side_effect=publish), \
                     patch.object(local.time, 'time', return_value=fixed_now):
                    self.assertEqual(local.discover(config), 1)
                self.assertEqual(json.loads(d_file.read_text()), local.groups([fresh_worker], gateway))
                self.assertEqual(json.loads(a_file.read_text()), expected_a)

    def test_malformed_inventory_preserves_fresh_targets_and_expires_stale_targets(self):
        fresh = {'ip': '172.20.0.21', 'port': 9092, 'job': 'qs-worker', 'instance': 'worker'}
        for invalid in ({}, None, [None], [dict(fresh, port=None)], [dict(fresh, instance=None)],
                        [dict(fresh, component=7)]):
            for age, expected in ((119, ['previous']), (121, [])):
                with self.subTest(payload=invalid, age=age), tempfile.TemporaryDirectory() as directory:
                    a_file = Path(directory) / 'serverA.json'
                    d_file = Path(directory) / 'serverD.json'
                    a_file.write_text('["previous"]\n')
                    now = time.time()
                    os.utime(a_file, (now - age, now - age))
                    config = {'sources': [{'name': 'serverA', 'host': 'a'}, {'name': 'serverD', 'host': 'd'}],
                              'output': directory, 'gateway': 'gateway:443',
                              'identity': 'identity', 'known_hosts': 'known_hosts'}

                    def ssh(command, **options):
                        payload = invalid if command[-1] == 'root@a' else [fresh]
                        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload))

                    errors = io.StringIO()
                    with patch.object(local.subprocess, 'run', side_effect=ssh), redirect_stderr(errors):
                        self.assertEqual(local.discover(config), 1)
                    self.assertRegex(errors.getvalue(), r' serverA (ValueError|TypeError)\n$')
                    self.assertEqual(json.loads(a_file.read_text()), expected)
                    self.assertEqual(json.loads(d_file.read_text()), local.groups([fresh], config['gateway']))

    def test_refresh_logs_utc_and_only_bounded_source_metadata(self):
        source = {'name': 'serverA', 'host': 'private-host'}
        completed = subprocess.CompletedProcess([], 0, stdout='[]')
        failure = subprocess.CalledProcessError(255, ['private-command'], stderr='private-error')
        stdout, stderr = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as output:
            config = {'output': output, 'gateway': 'gateway:443', 'identity': 'private-identity',
                      'known_hosts': 'private-known-hosts'}
            with redirect_stdout(stdout), redirect_stderr(stderr), \
                 patch.object(local.subprocess, 'run', side_effect=[completed, failure]):
                self.assertTrue(local.refresh_source(config, source))
                self.assertFalse(local.refresh_source(config, source))
        timestamp = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z'
        self.assertRegex(stdout.getvalue(), rf'^{timestamp} serverA targets 0\n$')
        self.assertRegex(stderr.getvalue(), rf'^{timestamp} serverA CalledProcessError\n$')

    def test_duplicate_source_names_cannot_publish_to_the_same_file(self):
        config = {'sources': [{'name': 'serverA'}, {'name': 'servera'}]}
        with patch.object(local.subprocess, 'run') as ssh:
            with self.assertRaisesRegex(ValueError, 'duplicate discovery source name'):
                local.discover(config)
            ssh.assert_not_called()

    def test_direct_discovery_preserves_labels_and_follows_container_replacement(self):
        first = remote.endpoints([container('qs-collection-1', '172.20.0.11', 'qs-collection-server')])
        replacement = remote.endpoints([container('qs-collection-1', '172.20.0.15', 'qs-collection-server')])
        worker = remote.endpoints([container('worker-1', '172.20.0.21', 'qs-worker', 9092)])
        with tempfile.TemporaryDirectory() as output:
            config = {'target_mode': 'direct', 'output': output, 'identity': 'dedicated-key',
                      'known_hosts': 'pinned-hosts', 'sources': [
                          {'name': 'serverA', 'transport': 'local'},
                          {'name': 'serverD', 'host': 'serverd'}]}
            source_a = Path(output) / 'serverA.json'
            source_d = Path(output) / 'serverD.json'
            local_inventories = iter((first, replacement))

            def run(command, **options):
                if command == [local.LOCAL_INVENTORY]:
                    payload = next(local_inventories)
                else:
                    self.assertEqual(command[-1], 'root@serverd')
                    self.assertIn('StrictHostKeyChecking=yes', command)
                    self.assertIn('UserKnownHostsFile=pinned-hosts', command)
                    payload = worker
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload))

            with patch.object(local.subprocess, 'run', side_effect=run):
                self.assertEqual(local.discover(config), 0)
                self.assertEqual(json.loads(source_a.read_text())[0]['targets'], ['172.20.0.11:8080'])
                self.assertEqual(local.discover(config), 0)
            self.assertEqual(json.loads(source_a.read_text()), [{
                'targets': ['172.20.0.15:8080'],
                'labels': {'job': 'qs-collection-server', 'instance': '172.20.0.15:8080'},
            }])
            self.assertEqual(json.loads(source_d.read_text()), [{
                'targets': ['172.20.0.21:9092'],
                'labels': {'job': 'qs-worker', 'instance': 'worker-1', 'component': 'qs-worker'},
            }])

    def test_direct_scrape_rejects_wrong_job_port_and_unknown_transports(self):
        with self.assertRaisesRegex(ValueError, 'unexpected direct scrape port'):
            local.groups([{'job': 'qs-worker', 'port': 8080, 'ip': '172.20.0.21', 'instance': 'worker'}], None)
        config = {'target_mode': 'direct', 'sources': [
            {'name': 'serverA', 'transport': 'local'}, {'name': 'serverD', 'transport': 'other'}]}
        with patch.object(local.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'one local and one SSH source'):
                local.discover(config)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
