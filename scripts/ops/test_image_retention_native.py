"""Opt-in real Docker retention check using only this invocation's labeled assets.

python3 scripts/ops/test_image_retention_native.py --helper /reviewed/image-retention.py
Requires a cached redis:7.4.2-alpine image; no pulls, network, database or volumes.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import uuid
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helper', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('retention', args.helper)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    env = {k: v for k, v in os.environ.items() if k not in (
        'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH')}
    owner = 'retention-native-' + uuid.uuid4().hex
    images, owned_containers = {}, []

    def docker(*parts):
        return subprocess.check_output(['docker', '--host=unix:///var/run/docker.sock', *parts],
                                       text=True, env=env, stderr=subprocess.DEVNULL, timeout=120).strip()

    def inventory():
        ids = sorted(set(docker('image', 'ls', '-aq', '--filter', 'label=qlume.retention-test=' + owner).split()))
        return json.loads(docker('image', 'inspect', *ids)) if ids else []

    try:
        docker('info', '--format', '{{.ServerVersion}}')
        docker('image', 'inspect', 'redis:7.4.2-alpine')
        with tempfile.TemporaryDirectory(prefix=owner) as directory:
            root = Path(directory)
            for n in range(1, 7):
                (root / 'Dockerfile').write_text('FROM redis:7.4.2-alpine\nLABEL qlume.retention-test="' + owner + '" qlume.retention-test-sequence="' + str(n) + '"\n')
                tag = 'ghcr.io/fangcunmount/qs-ai:' + owner + '-' + str(n)
                docker('build', '--network=none', '--pull=false', '-q', '-t', tag, str(root))
                images[n] = json.loads(docker('image', 'inspect', tag))[0]['Id']
            # Classic local Docker rejects digest strings in RepoTags on load.
            # The production containerd representation is tested from its actual
            # read-only inventory; exercise real tag deletion here.
            docker('image', 'tag', images[6], helper.ACR + 'qs-ai:' + owner + '-6')
            docker('image', 'tag', images[2], 'unrelated/retention-test:' + owner)
            owned_containers.append(docker('run', '-d', '--network=none', '--label', 'qlume.retention-test=' + owner,
                '--entrypoint', '/bin/sh', images[4], '-c', 'sleep 600'))
            owned_containers.append(docker('create', '--network=none', '--label', 'qlume.retention-test=' + owner,
                '--entrypoint', '/bin/sh', images[5], '-c', 'true'))
            state = root / 'state'
            state.mkdir()
            (state / 'qs-ai.json').write_text(json.dumps(dict(version=1,
                successful=[images[2], images[3]], bootstrap=[])))
            options = SimpleNamespace(service='qs-ai', image_ref=images[4], apply=False,
                                      deployment_locked=True, protect_image_id=[images[1]])
            with patch.object(helper, 'docker', docker), patch.object(helper, 'inventory', inventory), \
                    patch.object(helper, 'STATE', state), patch.object(helper.socket, 'gethostname', return_value='serverA'):
                before = helper.containers()
                helper.execute(options)
                assert not (state / 'qs-ai-last-cleanup.json').exists()
                assert {row['Id'] for row in inventory()} == set(images.values())
                options.apply = True
                helper.execute(options)
                audit = json.loads((state / 'qs-ai-last-cleanup.json').read_text())
                assert audit['status'] == 'success'
                assert audit['candidates'] and {row['id'] for row in audit['candidates']} == {images[6]}
                assert {row['Id'] for row in inventory()} == set(images.values()) - {images[6]}
                assert helper.containers() == before
                print(json.dumps(dict(native_docker=True, network=False, database=False,
                    dry_run_no_mutation=True, digest_alias_reproduced=False,
                    stopped_reference_protected=True, explicit_rollback_after_bootstrap_protected=True,
                    unknown_repository_untouched=True, container_state_unchanged=True,
                    removed_owned_tags=len(audit['removed_tags']), status='passed')))
    finally:
        for cid in owned_containers:
            row = json.loads(docker('inspect', cid))[0]
            assert row['Config']['Labels']['qlume.retention-test'] == owner
            docker('rm', '-f', cid)
        for image in inventory():
            assert image['Config']['Labels']['qlume.retention-test'] == owner
            for tag in image.get('RepoTags') or []:
                docker('image', 'rm', '--no-prune', tag)


if __name__ == '__main__':
    main()
