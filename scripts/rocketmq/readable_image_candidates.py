"""Readable-only candidate provenance. Does not build, load or start an image."""
import hashlib
import json
from pathlib import Path
import re
import tarfile

from final_image_candidate import saved_config, sha256
from image_sdk_profile import sdk_profile
from routes import validate

TARGETS = ('iam', 'qs-api', 'qs-collection', 'qs-worker', 'ai')
SHA = re.compile(r'[0-9a-f]{64}')
COMMIT = re.compile(r'[0-9a-f]{40}')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_readable_candidate_field')
        result[key] = value
    return result


def parse(raw):
    require(isinstance(raw, bytes) and 0 < len(raw) <= 65536, 'bounded_readable_candidate_required')
    value = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(value, dict) and set(value) == {'schema', 'sdk_profile', 'sources', 'builder_sha', 'image_runs',
                           'images', 'go_identity', 'routes_sha256', 'production'}
            and value['schema'] == 'readable-image-candidates/v1', 'exact_readable_candidate_schema_required')
    require(isinstance(value['sdk_profile'], str) and value['sdk_profile'].startswith('readable-'),
            'readable_sdk_profile_required')
    sdk_profile(value['sdk_profile'])  # Unpublished/floating profiles are refused.
    identity = value['go_identity']
    require(isinstance(identity, dict) and set(identity) == {'uid', 'gid'}
            and all(type(v) is int and v > 0 for v in identity.values()), 'explicit_nonroot_go_identity_required')
    require(isinstance(value['sources'], dict) and set(value['sources']) == {'iam', 'qs', 'ai'},
            'three_reviewed_sources_required')
    require(all(isinstance(s, str) and COMMIT.fullmatch(s)
                for s in (value['builder_sha'], *value['sources'].values())), 'exact_source_commits_required')
    runs = value['image_runs']
    require(isinstance(runs, dict) and set(runs) == set(TARGETS)
            and all(isinstance(run, str) and re.fullmatch('[1-9][0-9]{8,15}', run) for run in runs.values())
            and len(set(runs.values())) == 1, 'one_coordinated_five_image_build_required')
    images = value['images']
    require(isinstance(images, dict) and set(images) == set(TARGETS), 'five_frozen_image_identities_required')
    for row in images.values():
        require(isinstance(row, dict) and set(row) == {'inventory_sha256', 'archive_sha256', 'image_config_id', 'archive_bytes'}
                and all(isinstance(row[k], str) and SHA.fullmatch(row[k]) for k in ('inventory_sha256', 'archive_sha256'))
                and isinstance(row['image_config_id'], str) and re.fullmatch('sha256:[0-9a-f]{64}', row['image_config_id'])
                and type(row['archive_bytes']) is int and row['archive_bytes'] > 0, 'immutable_frozen_image_identity_required')
    require(isinstance(value['routes_sha256'], str) and SHA.fullmatch(value['routes_sha256'])
            and value['production'] is False, 'frozen_routes_and_nonproduction_candidate_required')
    return value


def read(path, routes):
    path, routes = Path(path), Path(routes)
    require(path.is_file() and not path.is_symlink() and routes.is_file() and not routes.is_symlink(),
            'regular_candidate_and_route_manifest_required')
    raw, route_bytes = path.read_bytes(), routes.read_bytes()
    value = parse(raw)
    require(0 < len(route_bytes) <= 1024 * 1024, 'bounded_route_manifest_required')
    manifest = json.loads(route_bytes, object_pairs_hook=unique)
    validate(manifest)
    require(manifest['version'] == 3 and hashlib.sha256(route_bytes).hexdigest() == value['routes_sha256'],
            'exact_readable_route_manifest_required')
    return value, hashlib.sha256(raw).hexdigest()


def validate_inventory(candidate, target, inventory):
    parse(json.dumps(candidate).encode())
    require(target in TARGETS and isinstance(inventory, dict), 'named_readable_image_required')
    expected = sdk_profile(candidate['sdk_profile'])
    role = 'qs' if target.startswith('qs-') else target
    require(inventory.get('schema') == 'readable-final-image-inventory/v1'
            and inventory.get('target') == target
            and inventory.get('sdk_profile') == candidate['sdk_profile']
            and inventory.get('expected_sdk_source_sha') == expected['source_sha']
            and inventory.get('source_sha') == candidate['sources'][role]
            and inventory.get('builder_source_sha') == candidate['builder_sha']
            and inventory.get('stable_release') is False, 'readable_image_source_or_profile_differs')
    for field in ('production', 'registry_published', 'application_started', 'runtime_ready',
                  'cutover_rehearsal_complete'):
        require(inventory.get(field) is False, 'inventory_is_not_startup_or_production_acceptance')
    cleanup = inventory.get('cleanup')
    require(all(type(inventory.get(key)) is int for key in ('passed', 'failed', 'skipped'))
            and (inventory.get('passed'), inventory.get('failed'), inventory.get('skipped')) == (1, 0, 0)
            and inventory.get('deferred_tools_absent') is True
            and isinstance(cleanup, dict) and set(cleanup) == {'owned_container_absent', 'owned_image_tag_absent', 'existing_containers_unchanged'}
            and all(value is True for value in cleanup.values()), 'complete_clean_image_inventory_required')
    require(isinstance(inventory.get('archive_bytes'), int) and not isinstance(inventory['archive_bytes'], bool)
            and inventory['archive_bytes'] > 0
            and isinstance(inventory.get('archive_sha256'), str) and SHA.fullmatch(inventory['archive_sha256'])
            and isinstance(inventory.get('image_config_id'), str)
            and re.fullmatch('sha256:[0-9a-f]{64}', inventory['image_config_id']), 'immutable_archive_identity_required')
    require(all(inventory[key] == candidate['images'][target][key]
                for key in ('archive_bytes', 'archive_sha256', 'image_config_id')), 'inventory_differs_from_frozen_candidate')
    runtime = inventory.get('runtime_sdk')
    require(inventory.get('image_user') == ('app' if target == 'ai' else 'www'), 'original_nonroot_image_user_required')
    if target == 'ai':
        require(runtime == dict(uid=10001, version=expected['python'], client='5.1.2',
                                source=candidate['sources']['ai'])
                and inventory.get('python_source_lock') == dict(version=expected['python'],
                    wheel_sha256=expected['wheel_sha256'], editable=False), 'exact_installed_readable_python_sdk_required')
    else:
        require(runtime == dict(version=expected['go'], sum=expected['go_sum'], replace=False),
                'exact_installed_readable_go_sdk_required')
        require(inventory.get('verified_uid_gid') == [candidate['go_identity']['uid'], candidate['go_identity']['gid']]
                and isinstance(inventory.get('runtime_binary_sha256'), str)
                and SHA.fullmatch(inventory['runtime_binary_sha256']), 'actual_nonroot_binary_identity_required')
    return inventory


def verify_archive(candidate, target, directory):
    parse(json.dumps(candidate).encode())
    require(target in TARGETS, 'named_readable_image_required')
    directory = Path(directory)
    metadata = directory / 'image-inventory.json'
    expected = candidate['images'][target]
    require(metadata.is_file() and not metadata.is_symlink() and 0 < metadata.stat().st_size <= 1024 * 1024,
            'bounded_regular_image_inventory_required')
    raw = metadata.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected['inventory_sha256'], 'frozen_image_inventory_changed')
    value = validate_inventory(candidate, target, json.loads(raw, object_pairs_hook=unique))
    role = 'qs' if target.startswith('qs-') else target
    archive = directory / (target + '-' + candidate['sources'][role] + '.tar.gz')
    require(archive.is_file() and not archive.is_symlink()
            and archive.stat().st_size == expected['archive_bytes'] and sha256(archive) == expected['archive_sha256'],
            'frozen_readable_archive_changed')
    with tarfile.open(archive) as saved:
        stream = saved.extractfile('manifest.json')
        require(stream is not None, 'saved_image_manifest_required')
        manifest = stream.read(1024 * 1024 + 1)
        require(len(manifest) <= 1024 * 1024, 'bounded_saved_image_manifest_required')
        entries = json.loads(manifest, object_pairs_hook=unique)
    require(isinstance(entries, list) and len(entries) == 1 and len(entries[0].get('RepoTags', [])) == 1,
            'one_original_readable_image_required')
    tag = entries[0]['RepoTags'][0]
    require(isinstance(tag, str) and re.fullmatch('m3-final-' + re.escape(target) + ':[0-9a-f]{12}', tag),
            'original_readable_archive_tag_required')
    config_id, config = saved_config(archive, tag)
    require(config_id == value['image_config_id'] and config['config'].get('User') == value['image_user'],
            'archived_readable_config_changed')
    return archive
