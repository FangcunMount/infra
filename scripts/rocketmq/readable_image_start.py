"""Explicit readable startup adapter; frozen M3/M4 acceptance stays unchanged."""
import hashlib
import json

from image_sdk_profile import sdk_profile
from readable_image_candidates import TARGETS, require, unique, verify_archive

CASES = {
    'actual_source_registry_consumers_match_manifest', 'all_five_exact_archives_loaded',
    'original_current_qs_pair_prepared', 'original_qs_dual_binding_verified',
    'original_iam_schema45_and_binding_selected', 'original_ai_schema43_and_binding_verified',
    'actual_three_source_packagers_and_root_owned_twenty_one_material_files',
    'actual_current_api_host_freeze_and_native_preflight_repeated',
    'actual_iam_ready_and_paused_checker_live', 'actual_readonly_ai_ready_and_paused_checker_live',
    'actual_qs_api_with_iam_ai_and_both_paused_owners', 'actual_collection_with_required_iam_and_api',
    'actual_second_collection_with_original_replica_budget',
    'all_eight_actual_processes_shutdown_exit_zero', 'actual_all_runtime_start_shutdown_no_ddl_attempts',
    *('actual_worker' + str(i) + '_prepared_http_healthy_original_concurrency48' for i in range(1, 4)),
}


def prepare_candidates(candidate, directory):
    """Validate every archive and companion before the first Docker load."""
    for target in TARGETS:
        verify_archive(candidate, target, directory / target)
    metadata = json.loads((directory / 'qs-api/image-inventory.json').read_bytes(), object_pairs_hook=unique)
    companion = directory / 'qs-api/qs-migrate-offline'
    require(companion.is_file() and not companion.is_symlink()
            and hashlib.sha256(companion.read_bytes()).hexdigest() == metadata.get('offline_tool_sha256'),
            'exact_readable_offline_companion_required')


class ReadableImageLoader:
    def load(self, directory, target, source_sha, *, reviewed_builder=None):
        candidate = self.readable_candidate
        role = 'qs' if target.startswith('qs-') else target
        require(source_sha == candidate['sources'][role] and reviewed_builder == candidate['builder_sha'],
                'reviewed_readable_startup_sources_required')
        archive = verify_archive(candidate, target, directory)
        value = json.loads((directory / 'image-inventory.json').read_bytes(), object_pairs_hook=unique)
        # The original tag is frozen in the archive; never retag to a production
        # repository or substitute an image from the local daemon.
        import tarfile
        with tarfile.open(archive) as saved:
            self.image = json.load(saved.extractfile('manifest.json'))[0]['RepoTags'][0]
        self.run(['docker', 'load', '-i', str(archive)], timeout=180)
        actual = self.run(['docker', 'image', 'inspect', self.image, '--format', '{{.Id}}']).stdout.strip()
        require(actual == value['image_config_id'], 'loaded_readable_image_differs')
        self.report['candidate'] = {key: value[key] for key in
            ('target', 'source_sha', 'builder_source_sha', 'image_config_id', 'archive_sha256')}
        return value


def python_dependencies(f):
    f.select('ai')
    expected = sdk_profile(f.readable_candidate['sdk_profile'])
    value = json.loads(f.once('/app/.venv/bin/python', ['-c',
        'import importlib.metadata as m,importlib.util as u,json; '
        'import reliable_messaging.protected,reliable_messaging.rocketmq_transaction,qs_ai.bootstrap.messaging; '
        'print(json.dumps(dict(sdk=m.version("fangcun-reliable-messaging"),'
        'nsq_absent=u.find_spec("nsq") is None,tornado_absent=u.find_spec("tornado") is None,'
        'current_imports=True)))'], network=False, environment={'PYTHONDONTWRITEBYTECODE': '1'}))
    require(value == dict(sdk=expected['python'], nsq_absent=True, tornado_absent=True, current_imports=True),
            'actual_readable_python_dependencies_required')
    return value


def validate_startup(value, candidate, digest):
    """Startup proof alone cannot pass the separate cutover or business gates."""
    require(value.get('schema') == 'readable-eight-instance-startup/v1'
            and value.get('sdk_profile') == candidate['sdk_profile']
            and value.get('sources') == candidate['sources']
            and value.get('final_candidate_manifest_sha256') == digest
            and value.get('final_candidate_image_runs') == candidate['image_runs']
            and value.get('final_candidate') is True, 'exact_readable_startup_candidate_required')
    require(all(type(value.get(k)) is int for k in ('passed', 'failed', 'skipped'))
            and value['passed'] == len(value.get('cases', {})) == len(CASES)
            and set(value['cases']) == CASES
            and value['failed'] == value['skipped'] == 0 and all(v is True for v in value['cases'].values()),
            'nonempty_zero_skip_readable_startup_required')
    require(all(value.get(k) is False for k in ('production', 'system_acceptance',
                'combined_cutover_rehearsal_complete', 'c1_cutover_barrier_exercised')),
            'startup_cannot_claim_business_or_cutover')
    return validate_runtime(value, candidate)


def validate_runtime(value, candidate):
    """Shared actual runtime evidence; callers separately enforce scope and cases."""
    components = {'iam', 'ai', 'api', 'collection', 'collection2', 'worker1', 'worker2', 'worker3'}
    for key in ('actual_material_mounts', 'actual_runtime_budgets', 'actual_runtime_unix_identity', 'processes'):
        require(set(value.get(key, {})) == components, 'all_eight_original_instances_required')
    for component, result in value['processes'].items():
        require(result['state'] == dict(Status='exited', ExitCode=0, OOMKilled=False),
                'all_eight_processes_shutdown_cleanly_required')
        require(value['actual_runtime_unix_identity'][component] == ([10001, 10001] if component == 'ai' else [2000, 2000]),
                'original_unix_identity_required')
        memory, cpus = ((768, 750000000) if component == 'ai' else (1024, 1000000000) if component == 'iam'
                        else (1024, 2000000000) if component == 'api' else (320, 1000000000)
                        if component.startswith('collection') else (768, 1000000000))
        require(value['actual_runtime_budgets'][component] == dict(memory_bytes=memory * 1024 * 1024, nano_cpus=cpus),
                'original_instance_budget_required')
    restarts = value.get('worker_restart_checks', [])
    require(len(restarts) == 9 and {(r['component'], r['cycle']) for r in restarts} ==
            {(w, c) for w in ('worker1', 'worker2', 'worker3') for c in range(1, 4)}
            and all(r['result']['state'] == dict(Status='exited', ExitCode=0, OOMKilled=False) for r in restarts),
            'bounded_original_worker_restart_proof_required')
    expected = sdk_profile(candidate['sdk_profile'])
    require(value.get('final_python_dependencies') == dict(sdk=expected['python'], nsq_absent=True,
                tornado_absent=True, current_imports=True)
            and value.get('m4_material_stage', {}).get('files') == 21
            and value.get('actual_source_worker_concurrency') == 48
            and type(value.get('mysql_runtime_ddl_attempts')) is int and value['mysql_runtime_ddl_attempts'] == 0
            and type(value.get('mongo_runtime_ddl_attempts')) is int and value['mongo_runtime_ddl_attempts'] == 0,
            'actual_dependencies_materials_no_runtime_ddl_required')
    require(value.get('sources_unchanged') is True and isinstance(value.get('cleanup'), dict)
            and set(value['cleanup']) == {'compose_down_succeeded', 'private_directory_removed',
                'existing_containers_unchanged', 'existing_networks_unchanged', 'owned_m4_material_root_removed'}
            and all(v is True for v in value['cleanup'].values()), 'complete_owned_readable_cleanup_required')
    return value
