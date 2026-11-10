"""Use the real Linux launcher on the owned AI acceptance bridge."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess

from final_image_candidate import ci_guard
from native_recovery_container import INPUTS, IPV4_GATEWAY_MODE, ISOLATED_BRIDGE_PLAN
from start_boundary import _digest, _encoded


RECOVERY_BROKER_IP = '172.31.80.10'
RECOVERY_BROKER_HOST = 'fixture-recovery-broker'
RECOVERY_MYSQL_HOST = 'fixture-recovery-mysql'
RECOVERY_NAMESERVER_HOST = 'fixture-recovery-nameserver'


def add_recovery_bridge(spec):
    """Keep published test ports on rocketmq and recovery on its own bridge."""
    spec['networks']['recovery'] = {
        'driver': 'bridge', 'internal': True, 'enable_ipv6': False,
        'driver_opts': {IPV4_GATEWAY_MODE: 'isolated'},
        'ipam': {'config': [{'subnet': '172.31.80.0/24'}]},
    }
    for service, alias in (('broker', RECOVERY_BROKER_HOST), ('mysql', RECOVERY_MYSQL_HOST),
                           ('nameserver', RECOVERY_NAMESERVER_HOST)):
        spec['services'][service]['networks'] = {'rocketmq': {}, 'recovery': {'aliases': [alias]}}
    spec['services']['broker']['networks']['recovery']['ipv4_address'] = RECOVERY_BROKER_IP


class CoordinatedRecovery:
    def __init__(self, root, repo, broker, project, image, proof, run):
        ci_guard(os.environ)
        self.root, self.image, self.proof, self.run = root, image, proof, run
        item, = json.loads(run(['docker', 'container', 'inspect', broker]).stdout)
        assert item['Config']['Labels']['com.docker.compose.project'] == project
        name = project + '_recovery'
        networks = item['NetworkSettings']['Networks']
        assert set(networks) == {project + '_rocketmq', name}
        endpoint = networks[name]
        network, = json.loads(run(['docker', 'network', 'inspect', name]).stdout)
        assert network['Labels']['com.docker.compose.project'] == project
        assert endpoint['IPAddress'] == RECOVERY_BROKER_IP and endpoint['NetworkID'] == network['Id']
        assert network['Internal'] is True and network['EnableIPv4'] is True and network['EnableIPv6'] is False
        assert network['Options'][IPV4_GATEWAY_MODE] == 'isolated'
        self.network, self.name = _digest(network['Id']), name
        self.source = run(['git', 'rev-parse', 'HEAD'], cwd=repo).stdout.strip()
        self.code = root / 'launcher'
        self.code.mkdir(mode=0o700)
        for name in ('native_recovery_container.py', 'cutover_step.py', 'start_boundary.py'):
            shutil.copyfile(Path(__file__).with_name(name), self.code / name)
        sock = Path('/var/run/docker.sock').stat()
        assert stat.S_ISSOCK(sock.st_mode) and sock.st_gid != 0
        self.uid_command = ['/usr/bin/sudo', '-n', '/usr/bin/setpriv', '--reuid=3000', '--regid=3000',
                            '--groups=' + str(sock.st_gid), '/usr/bin/python3']

    def stage_java(self, material, script):
        self.inputs = self.root / 'inputs'
        java = self.inputs / 'java'
        (java / 'tls').mkdir(mode=0o700, parents=True)
        self.inputs.chmod(0o700)
        java.chmod(0o700)
        self.java = {}
        for name, source, target in (
                ('tools', material / 'tools.yml', java / 'tools.yml'),
                ('ca', material / 'tls/server.crt', java / 'tls/server.crt'),
                ('admin_script', script, java / 'native-admin.sh')):
            shutil.copyfile(source, target)
            target.chmod(0o600)
            self.java[name] = hashlib.sha256(target.read_bytes()).hexdigest()

    def plan_command(self, arguments, op, binding, step, host):
        values = dict(zip(arguments[1::2], arguments[2::2], strict=True))
        hashes = {}
        for name in INPUTS:
            raw = Path(values['--' + name]).read_bytes()
            digest = _digest(values['--' + name + '-sha'])
            assert hashlib.sha256(raw).hexdigest() == digest
            path = self.inputs / (name + '.json')
            path.write_bytes(raw)
            path.chmod(0o600)
            hashes[name] = digest
        if arguments[0] != 'recover':
            receipt = Path(values['--receipt'])
            assert receipt.parent.parent == op and receipt.name == 'receipt.json'
            hashes['receipt'] = {'attempt': receipt.parent.name, 'sha256': values['--receipt-sha']}
        plan = dict(schema=ISOLATED_BRIDGE_PLAN, command=arguments[0], directory=str(op),
                    host=host, image_id=self.image, source_sha=self.source, network_id=self.network,
                    network_name=self.name, binding_sha256=binding, step=step, inputs=hashes, java=self.java)
        path = self.root / (step + '-container.json')
        raw = _encoded(plan)
        path.write_bytes(raw)
        path.chmod(0o600)
        return shlex.join(['/usr/bin/python3', str(self.code / 'native_recovery_container.py'),
                           '--plan', str(path), '--reviewed-sha256', hashlib.sha256(raw).hexdigest(), '--execute'])

    def execute(self, plan, digest, op):
        ownership = ['/usr/bin/sudo', '-n', '/usr/bin/chown', '-R']
        self.run([*ownership, '3000:3000', str(self.root)])
        try:
            result = self.run([*self.uid_command, str(self.code / 'cutover_step.py'), '--plan', str(plan),
                               '--reviewed-sha256', digest, '--execute'], required=False, timeout=250)
        finally:
            self.run([*ownership, f'{os.getuid()}:{os.getgid()}', str(self.root)])
        exit_path = op / ('native-container-' + digest + '-exit.json')
        receipt = json.loads(exit_path.read_text()) if exit_path.exists() else None
        if receipt:
            logs = self.run(['docker', 'logs', _digest(receipt['container_id'])], required=False, timeout=10)
            (op / ('container-' + digest + '.log')).write_text(logs.stdout + logs.stderr)
        if result.returncode != 0 or not receipt or receipt['exit_code'] != 0:
            raise RuntimeError('owned Linux recovery launcher rejected or incomplete')
        self.proof.setdefault('coordinated_image_steps', []).append(
            dict(step_plan_sha256=digest, container_id=receipt['container_id'], exit_code=0, uid=3000,
                 container_plan_schema=ISOLATED_BRIDGE_PLAN, network_id=self.network))

    def cleanup(self):
        for issued in sorted((self.root / 'operation').glob('native-container-*-issued.json')):
            name = json.loads(issued.read_text())['name']
            lookup = ['docker', 'ps', '-aq', '--no-trunc', '--filter', 'name=^/' + name + '$']
            ids = self.run(lookup).stdout.splitlines()
            if ids:
                (cid,) = ids
                item, = json.loads(self.run(['docker', 'container', 'inspect', _digest(cid)]).stdout)
                assert item['Name'] == '/' + name and item['Image'] == self.image and not item['State']['Running']
                assert item['Config']['Labels']['native.recovery.step'] == name.removeprefix('native-container-')
                self.run(['docker', 'container', 'rm', cid])
            assert not self.run(lookup).stdout.strip()
        self.proof['coordinated_image_cleanup'] = True
