"""Run a source-bound recovery image only in a GitHub-owned Broker fixture."""
import hashlib
import json
import os
import re
import shutil
import socket

from managed_recovery_acceptance import require


def image_command(repo, image, broker, project, directory, root, index_path, ca, run, proof, *, coordinated=False):
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_OS') == 'Linux'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and not os.environ.get('DOCKER_HOST') and not os.environ.get('DOCKER_CONTEXT'),
            'github_owned_execution_image_fixture_required')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', image) and project.startswith('rocketmq-m2-')
            and broker == project + '-broker-1' and directory.stat().st_mode & 0o077 == 0
            and os.getuid() != 0, 'exact_owned_execution_image_and_fixture_required')
    docker = shutil.which('docker')
    require(docker is not None, 'explicit_local_docker_binary_required')
    docker_config = root / 'docker-config'
    docker_config.mkdir(mode=0o700)
    docker = [docker, '--host', 'unix:///var/run/docker.sock', '--config', str(docker_config)]
    broker_info, = json.loads(run([*docker, 'inspect', broker]).stdout)
    require(broker_info['Config']['Labels']['com.docker.compose.project'] == project
            and broker_info['State']['Running'], 'exact_owned_broker_required')
    networks = broker_info['NetworkSettings']['Networks']
    expected_networks = {project + '_rocketmq'}
    if coordinated:
        expected_networks.add(project + '_recovery')
    require(set(networks) == expected_networks, 'exact_owned_broker_networks_required')
    network_info = json.loads(run([*docker, 'network', 'inspect', *sorted(networks)]).stdout)
    require(len(network_info) == len(networks) and all(
        item['Labels']['com.docker.compose.project'] == project
        and networks[item['Name']]['NetworkID'] == item['Id'] for item in network_info),
        'exact_owned_broker_network_required')

    image_info, = json.loads(run([*docker, 'image', 'inspect', image]).stdout)
    sha = run(['git', 'rev-parse', 'HEAD'], cwd=repo).stdout.strip()
    require(image_info['Id'] == image and image_info['Os'] == 'linux' and image_info['Architecture'] == 'amd64'
            and image_info['Config']['Labels']['org.opencontainers.image.revision'] == sha
            and image_info['Config']['User'] == '3000:3000', 'exact_source_bound_execution_image_required')

    material = directory / 'managed-java-material'
    material.mkdir(mode=0o700)
    tls = material / 'tls'
    tls.mkdir(mode=0o700)
    (tls / 'server.crt').write_bytes(ca.read_bytes())
    admin = run([*docker, 'exec', broker, 'cat', '/opt/rocketmq/conf/tools.yml']).stdout
    (material / 'tools.yml').write_text(admin)
    for file in (material / 'tools.yml', tls / 'server.crt'):
        file.chmod(0o600)

    command = [*docker, 'run', '--rm', '--pull', 'never', '--platform', 'linux/amd64',
               '--network', 'container:' + broker_info['Id'], '--uts', 'host', '--read-only',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
               '--pids-limit', '64', '--memory', '384m', '--cpus', '1',
               '--user', f'{os.getuid()}:{os.getgid()}',
               '--mount', f'type=bind,src={root},dst={root}',
               '--mount', f'type=bind,src={index_path},dst={index_path},readonly',
               '--mount', f'type=bind,src={material},dst=/run/native-recovery,readonly']
    smoke = run([*command, '--entrypoint', '/bin/bash', image, '-euc', r'''
test "$(id -u)" != 0
grep -Eq '^CapEff:[[:space:]]+0000000000000000$' /proc/self/status
test "$(cat /sys/fs/cgroup/pids.max)" = 64
test "$(cat /sys/fs/cgroup/memory.max)" = 402653184
test "$(cat /sys/fs/cgroup/cpu.max)" = '100000 100000'
awk '$5 == "/" && $6 ~ /^ro,/ { found=1 } END { exit !found }' /proc/self/mountinfo
test ! -e /var/run/docker.sock
! command -v docker
sha256sum /opt/native-recovery/managed-java.sh /opt/native-recovery/native-managed.jar
hostname
''']).stdout.splitlines()
    wrapper = (repo / 'tools/rocketmq-native-recovery/image/managed-java.sh').read_bytes()
    wrapper_sha = hashlib.sha256(wrapper).hexdigest()
    require(len(smoke) == 3 and smoke[0].split() == [wrapper_sha, '/opt/native-recovery/managed-java.sh']
            and re.fullmatch(r'[0-9a-f]{64}  /opt/native-recovery/native-managed.jar', smoke[1])
            and smoke[2] == socket.gethostname(), 'actual_owned_image_runtime_limits_required')
    proof['execution_image'] = dict(image_id=image, source_sha=sha, wrapper_sha256=wrapper_sha,
        helper_sha256=smoke[1].split()[0], owned_broker_network=True, fixture_uts_shared=True,
        nonroot=True, no_capabilities=True, read_only=True, docker_socket=False,
        pid_limit=64, memory_bytes=402653184, cpus=1, production=False)
    return [*command, image], wrapper
