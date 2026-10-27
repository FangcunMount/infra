"""Build and inventory one isolated image; never publish, deploy or start business."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import uuid

from image_sdk_profile import PROFILES, sdk_profile, verify_readable_python_lock

MODULE = 'github.com/FangcunMount/reliable-messaging'
GO_SUM = sdk_profile('m3-stable')['go_sum']
TARGETS = {
    'iam': ('build/docker/Dockerfile', '/app/apiserver'),
    'qs-api': ('build/docker/Dockerfile.qs-apiserver', '/app/qs-apiserver'),
    'qs-collection': ('build/docker/Dockerfile.collection-server', '/app/collection-server'),
    'qs-worker': ('build/docker/Dockerfile.qs-worker', '/app/qs-worker'),
    'ai': ('Dockerfile', None),
}


def ci_guard(env):
    if (env.get('GITHUB_ACTIONS') != 'true' or env.get('RUNNER_OS') != 'Linux'
            or env.get('RUNNER_ENVIRONMENT') != 'github-hosted'
            or env.get('DOCKER_HOST') or env.get('DOCKER_CONTEXT')):
        raise ValueError('github_hosted_isolated_daemon_required')


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def run(args, *, cwd=None, env=None, timeout=1200):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True,
                            timeout=timeout)
    if result.returncode:
        # Build output may contain registry/URL details. Keep public errors bounded.
        raise RuntimeError('candidate_command_failed:' + Path(args[0]).name)
    return result.stdout


def check_go_buildinfo(raw, *, profile='m3-stable'):
    expected = sdk_profile(profile)
    rows = [line.split() for line in raw.splitlines()]
    deps = [row for row in rows if len(row) >= 2 and row[:2] == ['dep', MODULE]]
    if len(deps) != 1 or deps[0][2:] != [expected['go'], expected['go_sum']] or any(
            row and row[0] == '=>' for row in rows):
        raise ValueError('runtime_binary_requires_exact_stable_module_without_replace' if profile == 'm3-stable'
                         else 'runtime_binary_requires_exact_readable_candidate_module_without_replace')
    return {'version': expected['go'], 'sum': expected['go_sum'], 'replace': False}


def inventory_names(archive):
    """Read names only; never extract an untrusted root filesystem."""
    with tarfile.open(archive) as source:
        names = [item.name.removeprefix('./') for item in source]
    forbidden = []
    for name in names:
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('unsafe_rootfs_member')
        if (path.name in {'host-observer', 'native_recovery.py', 'JavaNativeHalfManaged.class'}
                or path.name.startswith('native-resume')):
            forbidden.append(name)
    if forbidden:
        raise ValueError('deferred_recovery_tool_in_image')
    return names


def saved_config(archive, image):
    # Engine image identity can be a manifest ID. Hash the archived config
    # itself instead of labelling image-inspect.Id as a config digest.
    with tarfile.open(archive) as source:
        manifest = json.load(source.extractfile('manifest.json'))
        if len(manifest) != 1 or manifest[0].get('RepoTags') != [image]:
            raise ValueError('exact_single_image_archive_required')
        name = manifest[0]['Config']
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('unsafe_saved_config_path')
        body = source.extractfile(name).read((1 << 20) + 1)
        if len(body) > 1 << 20:
            raise ValueError('saved_config_too_large')
        config = json.loads(body)
        if (config.get('os'), config.get('architecture')) != ('linux', 'amd64'):
            raise ValueError('saved_config_platform_mismatch')
        return 'sha256:' + hashlib.sha256(body).hexdigest(), config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--target', choices=TARGETS, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-uid', type=int, default=2000)
    parser.add_argument('--run-gid', type=int, default=2000)
    parser.add_argument('--sdk-profile', choices=tuple(PROFILES), default='m3-stable')
    args = parser.parse_args()
    expected_sdk = sdk_profile(args.sdk_profile)
    ci_guard(os.environ)
    if not re.fullmatch('[0-9a-f]{40}', args.source_sha):
        raise ValueError('exact_source_sha_required')
    if min(args.run_uid, args.run_gid) < 1:
        raise ValueError('nonroot_uid_gid_required')
    source = args.source.resolve()
    if (run(['git', 'rev-parse', 'HEAD'], cwd=source).strip() != args.source_sha
            or run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=source)):
        raise ValueError('fixed_clean_source_required')
    python_lock = None
    if args.target == 'ai' and args.sdk_profile != 'm3-stable':
        python_lock = verify_readable_python_lock((source / 'uv.lock').read_text(), args.sdk_profile)
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    builder = Path(__file__).resolve().parents[2]
    builder_sha = run(['git', 'rev-parse', 'HEAD'], cwd=builder).strip()
    if builder_sha != os.environ.get('GITHUB_SHA'):
        raise ValueError('reviewed_workflow_checkout_identity_required')
    suffix = uuid.uuid4().hex[:12]
    image = 'm3-final-' + args.target + ':' + suffix
    container = 'm3-final-inventory-' + suffix
    original = run(['docker', 'ps', '-aq']).split()
    report = {'schema': 'm3-final-image-inventory/v1', 'target': args.target,
              'source_sha': args.source_sha, 'builder_source_sha': builder_sha,
              'expected_sdk_source_sha': expected_sdk['source_sha'],
              'production': False,
              'application_started': False, 'registry_published': False,
              'runtime_ready': False, 'cutover_rehearsal_complete': False}
    if args.sdk_profile != 'm3-stable':
        report.update(schema='readable-final-image-inventory/v1', sdk_profile=args.sdk_profile,
                      stable_release=False, python_source_lock=python_lock)
    try:
        dockerfile, binary = TARGETS[args.target]
        report['dockerfile_sha256'] = sha256(source / dockerfile)
        build_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        run(['docker', 'build', '--platform', 'linux/amd64', '--file', dockerfile,
             '--tag', image, '--build-arg', 'VERSION=m3-' + args.source_sha,
             '--build-arg', 'GIT_COMMIT=' + args.source_sha,
             '--build-arg', 'GIT_BRANCH=main', '--build-arg', 'BUILD_TIME=' + build_time,
             '--build-arg', 'RELEASE_SHA=' + args.source_sha,
             '--build-arg', 'RUN_UID=' + str(args.run_uid),
             '--build-arg', 'RUN_GID=' + str(args.run_gid), '.'], cwd=source)
        inspect = json.loads(run(['docker', 'image', 'inspect', image]))[0]
        if (inspect['Os'], inspect['Architecture']) != ('linux', 'amd64'):
            raise ValueError('linux_amd64_required')
        report['engine_image_id'] = inspect['Id']
        report['entrypoint'] = inspect['Config'].get('Entrypoint')
        report['command'] = inspect['Config'].get('Cmd')
        report['image_user'] = inspect['Config']['User']
        if report['image_user'] != ('app' if args.target == 'ai' else 'www'):
            raise ValueError('expected_nonroot_image_user_required')
        run(['docker', 'create', '--name', container, '--network', 'none', image])
        rootfs = output / 'private-rootfs.tar'
        run(['docker', 'export', '--output', str(rootfs), container])
        names = inventory_names(rootfs)
        report['rootfs_member_count'] = len(names)
        report['deferred_tools_absent'] = True
        rootfs.unlink()
        if binary:
            target = output / 'private-runtime-binary'
            run(['docker', 'cp', container + ':' + binary, str(target)])
            raw = run(['go', 'version', '-m', str(target)])
            report['runtime_sdk'] = check_go_buildinfo(raw, profile=args.sdk_profile)
            if args.source_sha not in raw:
                raise ValueError('runtime_binary_source_ldflags_missing')
            report['runtime_binary_sha256'] = sha256(target)
            target.unlink()
            ids = run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
                       '--entrypoint', '/bin/sh', image, '-ec', 'id -u; id -g']).split()
            if ids != [str(args.run_uid), str(args.run_gid)]:
                raise ValueError('actual_image_uid_gid_mismatch')
            report['verified_uid_gid'] = [args.run_uid, args.run_gid]
        else:
            code = ('import json,os,importlib.metadata as m; '
                    'print(json.dumps(dict(uid=os.getuid(),version=m.version('
                    '"fangcun-reliable-messaging"),client=m.version('
                    '"rocketmq-python-client"),source=os.environ.get("QS_AI_RELEASE_SHA"))))')
            proof = json.loads(run(['docker', 'run', '--rm', '--network', 'none',
                                   '--read-only', '--tmpfs', '/tmp', '--entrypoint',
                                   '/app/.venv/bin/python', image, '-I', '-c', code]))
            if proof != dict(uid=10001, version=expected_sdk['python'], client='5.1.2', source=args.source_sha):
                raise ValueError('python_image_provenance_mismatch')
            report['runtime_sdk'] = proof
        if args.target == 'qs-api':
            # The runtime Dockerfile intentionally does not ship this original
            # offline tool. Freeze it alongside the image, without changing it.
            tool = output / 'qs-migrate-offline'
            run(['go', 'build', '-mod=readonly', '-trimpath', '-ldflags',
                 '-s -w -X github.com/FangcunMount/qs-server/pkg/version.GitCommit=' + args.source_sha,
                 '-o', str(tool), './scripts/maintenance/qs-migrate-offline'], cwd=source,
                env=dict(os.environ, GOWORK='off', CGO_ENABLED='0', GOOS='linux', GOARCH='amd64'))
            report['offline_tool_sha256'] = sha256(tool)
        archive = output / (args.target + '-' + args.source_sha + '.tar.gz')
        raw_archive = output / 'private-image.tar'
        run(['docker', 'save', '--output', str(raw_archive), image])
        config_id, config = saved_config(raw_archive, image)
        if any(config['config'].get(key) != inspect['Config'].get(key)
               for key in ('User', 'Entrypoint', 'Cmd')):
            raise ValueError('saved_config_differs_from_inspected_image')
        report['image_config_id'] = config_id
        with archive.open('wb') as stream:
            subprocess.run(['gzip', '-1', '-c', str(raw_archive)], stdout=stream, check=True)
        raw_archive.unlink()
        report['archive_sha256'] = sha256(archive)
        report['archive_bytes'] = archive.stat().st_size
        report['passed'] = 1
        report['failed'] = report['skipped'] = 0
    finally:
        subprocess.run(['docker', 'rm', '-f', container], capture_output=True, check=False)
        subprocess.run(['docker', 'image', 'rm', '--no-prune', image], capture_output=True, check=False)
        report['cleanup'] = {'owned_container_absent': container not in run(
            ['docker', 'ps', '-a', '--format', '{{.Names}}']).split(),
            'owned_image_tag_absent': image not in run(
                ['docker', 'image', 'ls', '--format', '{{.Repository}}:{{.Tag}}']).split(),
            'existing_containers_unchanged': sorted(original) == sorted(run(['docker', 'ps', '-aq']).split())}
        (output / 'image-inventory.json').write_text(json.dumps(report, indent=2) + '\n')
    if not all(report['cleanup'].values()):
        raise ValueError('candidate_cleanup_incomplete')
    print(json.dumps({'target': args.target, 'source_sha': args.source_sha,
                      'image_config_id': report['image_config_id'], 'passed': 1}))


if __name__ == '__main__':
    main()
