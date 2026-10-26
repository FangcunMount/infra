"""Root helper ONLY for an ephemeral GitHub-hosted M4 image fixture.

Never installed in production. Synthetic files only. Production uses the
independently reviewed m4_material_stage.py and its existing shared lock.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from final_image_candidate import ci_guard

BASE = Path('/var/lib/fangcun-m4-materials')
ROLES = {'iam': ('iam-messaging', 2000), 'api': ('qs-server-messaging', 2000),
         'ai': ('qs-ai-messaging', 10001), 'worker': ('qs-worker-messaging', 2000)}
FILES = {'iam': {'rocketmq/credentials.json', 'rocketmq/ca.crt', 'rocketmq/routes.json'},
         'worker': {'rocketmq/credentials.json', 'rocketmq/ca.crt', 'rocketmq/routes.json'},
         'api': {'rocketmq/credentials.json', 'rocketmq/mongo-credentials.json', 'rocketmq/ca.crt',
                 'rocketmq/routes.json', 'qs.sign.fixture.json', 'qs.encrypt.fixture.json',
                 'ai.sign.fixture.json', 'ai.encrypt.fixture.json'},
         'ai': {'rocketmq/credentials.json', 'rocketmq/ca.crt', 'rocketmq/routes.json',
                'qs.sign.fixture.json', 'qs.encrypt.fixture.json', 'ai.sign.fixture.json', 'ai.encrypt.fixture.json'}}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def owned_fixture(value):
    path = Path(value)
    require(path.is_absolute() and path.parent == Path('/tmp')
            and re.fullmatch('m3-image-start-[a-z0-9_]{8}', path.name), 'exact_owned_fixture_required')
    require(not path.is_symlink(), 'owned_fixture_symlink_refused')
    return path


def validate_plan(plan, fixture):
    require(set(plan) == {'schema', 'project', 'revision', 'files', 'api_binding'}, 'exact_material_plan_required')
    require(plan['schema'] == 'm4-synthetic-image-materials/v1'
            and re.fullmatch('rocketmq-m2-image-[a-f0-9]{12}', plan['project'])
            and plan['revision'] == 'm4-owned-' + plan['project'].rsplit('-', 1)[1], 'owned_material_identity_required')
    require(isinstance(plan['api_binding'], dict)
            and plan['api_binding'].get('binding_revision') == plan['revision']
            and plan['api_binding'].get('provider') == 'rocketmq', 'exact_api_material_revision_required')
    observed = {role: set() for role in ROLES}
    for row in plan['files']:
        require(set(row) == {'role', 'relative', 'source', 'sha256'}, 'exact_material_row_required')
        role, relative = row['role'], row['relative']
        require(role in ROLES and relative in FILES[role] and relative not in observed[role], 'exact_role_file_required')
        observed[role].add(relative)
        source = Path(row['source'])
        require(source.is_relative_to(fixture) and source.resolve() == source and source.is_file()
                and not source.is_symlink() and 0 < source.stat().st_size <= (1 << 20), 'synthetic_owned_source_required')
        require(hashlib.sha256(source.read_bytes()).hexdigest() == row['sha256'], 'synthetic_source_digest_differs')
    require(observed == FILES, 'complete_twenty_one_materials_required')


def owned_marker(fixture):
    path = BASE / '.owned-fixture'
    require(not BASE.is_symlink() and BASE.stat().st_uid == 0
            and path.is_file() and not path.is_symlink() and path.stat().st_uid == 0,
            'foreign_material_root_refused')
    value = json.loads(path.read_bytes())
    require(set(value) == {'fixture', 'project'} and value['fixture'] == str(fixture)
            and re.fullmatch('rocketmq-m2-image-[a-f0-9]{12}', value['project']), 'foreign_material_marker_refused')
    return value


def cleanup(fixture):
    if not BASE.exists():
        return
    owned_marker(fixture)
    require({v.name for v in BASE.iterdir()} == {v[0] for v in ROLES.values()} | {'.owned-fixture'},
            'foreign_material_children_refused')
    for path in BASE.rglob('*'):
        require(not path.is_symlink() and path.stat().st_uid == 0, 'foreign_material_object_refused')
    shutil.rmtree(BASE)


def stage(fixture, plan):
    validate_plan(plan, fixture)
    require(not BASE.exists() and not BASE.is_symlink(), 'existing_material_namespace_refused')
    BASE.mkdir(mode=0o755)
    BASE.chmod(0o755)
    try:
        (BASE / '.owned-fixture').write_text(json.dumps(dict(fixture=str(fixture), project=plan['project'])))
        (BASE / '.owned-fixture').chmod(0o600)
        for role, (stem, gid) in ROLES.items():
            for path in (BASE / stem, BASE / stem / 'versions', BASE / stem / 'versions' / plan['revision'],
                         BASE / stem / 'versions' / plan['revision'] / 'rocketmq'):
                path.mkdir(mode=0o750); path.chmod(0o750); os.chown(path, 0, gid)
        for row in plan['files']:
            stem, gid = ROLES[row['role']]
            path = BASE / stem / 'versions' / plan['revision'] / row['relative']
            raw = Path(row['source']).read_bytes()
            require(hashlib.sha256(raw).hexdigest() == row['sha256'], 'synthetic_source_changed')
            with path.open('xb') as stream:
                stream.write(raw)
            os.chown(path, 0, gid); path.chmod(0o440)
        binding = BASE / ROLES['api'][0] / 'current.json'
        binding.write_text(json.dumps(plan['api_binding'])); os.chown(binding, 0, 2000); binding.chmod(0o440)
    except Exception:
        # All children of this previously absent namespace belong to this run.
        # No production/original namespace, shared lock or asset is touched.
        shutil.rmtree(BASE)
        raise
    return dict(files=21, root_uid=0, file_mode='0440', revision=plan['revision'], production=False)


def prepare_api(fixture, source, image):
    owned_marker(fixture)
    source = Path(source).resolve()
    workspace = Path(os.environ['GITHUB_WORKSPACE']).resolve()
    require(source == workspace / '.five-sources/qs', 'exact_reviewed_qs_checkout_required')
    spec = importlib.util.spec_from_file_location('m4_actual_api_freeze', source / 'scripts/cd/ai-messaging-release.py')
    tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)
    releases = fixture / 'actual-api-releases'
    # The ordinary runner may traverse the non-secret release metadata; actual
    # sensitive material and the image preflight remain under their app UID.
    releases.mkdir(mode=0o755)
    result = tool.prepare(image, fixture / 'api/runtime.json', 2000, 2000, release_root=releases)
    second = tool.prepare(image, fixture / 'api/runtime.json', 2000, 2000, release_root=releases)
    require(result == second, 'actual_api_release_reuse_differs')
    release = releases / result['source_sha']
    rendered = (release / 'apiserver.json').read_bytes()
    (fixture / 'api/runtime.json').write_bytes(rendered)
    composition = json.loads((release / 'compose.json').read_bytes())
    metadata = json.loads((release / 'metadata.json').read_bytes())
    return dict(result=result, volumes=composition['services']['qs-apiserver']['volumes'],
                native_metadata=metadata, rendered_sha256=hashlib.sha256(rendered).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'api', 'cleanup'))
    parser.add_argument('--fixture', required=True)
    parser.add_argument('--source')
    parser.add_argument('--image')
    args = parser.parse_args()
    ci_guard(os.environ); require(os.geteuid() == 0, 'isolated_root_required')
    fixture = owned_fixture(args.fixture)
    if args.action == 'stage':
        result = stage(fixture, json.loads((fixture / 'm4-plan.json').read_bytes()))
    elif args.action == 'api':
        result = prepare_api(fixture, args.source, args.image)
    else:
        # Do not remove materials while any owned image is still running.
        project = owned_marker(fixture)['project']
        result = subprocess.run(['docker', 'ps', '-q', '--filter', 'label=com.fangcunmount.m3.fixture=' + project], capture_output=True, check=True, text=True)
        require(not result.stdout.strip(), 'running_owned_runtime_materials_protected')
        cleanup(fixture); result = dict(owned_material_root_removed=not BASE.exists())
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
