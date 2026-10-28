"""Strict receipt for the owned compatible-v2/readable-v3 runtime trial."""
import hashlib
import json
import math
import re

from readable_image_candidates import require, unique
from readable_image_start import CASES as STARTUP_CASES, validate_runtime, validate_startup
from readable_cutover import CASES, COMPONENTS


def read_startup(path, candidate, digest):
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= 1024 * 1024,
            'bounded_regular_original_startup_receipt_required')
    raw = path.read_bytes()
    value = json.loads(raw, object_pairs_hook=unique)
    validate_startup(value, candidate, digest)
    require(isinstance(value.get('infra_sha'), str)
            and re.fullmatch('[0-9a-f]{40}', value['infra_sha']), 'original_startup_source_required')
    return value, hashlib.sha256(raw).hexdigest()


def validate_cutover(value, candidate, digest, startup_digest):
    require(value.get('schema') == 'readable-eight-instance-cutover/v1'
            and value.get('sdk_profile') == candidate['sdk_profile']
            and value.get('sources') == candidate['sources']
            and value.get('final_candidate_manifest_sha256') == digest
            and value.get('final_candidate_image_runs') == candidate['image_runs']
            and value.get('final_candidate') is True
            and value.get('startup_receipt_sha256') == startup_digest
            and re.fullmatch('[0-9a-f]{64}', startup_digest), 'exact_candidate_and_independent_startup_required')
    expected = STARTUP_CASES | CASES
    require(all(type(value.get(k)) is int for k in ('passed', 'failed', 'skipped'))
            and value['passed'] == len(value.get('cases', {})) == len(expected)
            and set(value['cases']) == expected and all(v is True for v in value['cases'].values())
            and value['failed'] == value['skipped'] == 0, 'complete_zero_skip_cutover_cases_required')
    require(value.get('production') is False and value.get('system_acceptance') is False
            and value.get('combined_cutover_rehearsal_complete') is True
            and value.get('c1_cutover_barrier_exercised') is False,
            'owned_config_switch_cannot_claim_production_data_restore')
    validate_runtime(value, candidate)
    proof = value.get('readable_cutover', {})
    require(all(proof.get(k) is False for k in ('original_production_images_tested', 'production', 'system_acceptance'))
            and proof.get('real_provider_not_claimed') is True, 'compatible_candidate_scope_required')
    for key in ('initial_readable_shutdown', 'compat_shutdown'):
        require(set(proof.get(key, {})) == set(COMPONENTS)
                and all(row['state'] == dict(Status='exited', ExitCode=0, OOMKilled=False)
                        for row in proof[key].values()), 'both_actual_prior_runtime_shutdowns_required')
    before, after = proof.get('bindings_before', {}), proof.get('bindings_after', {})
    require(before == after and set(before) == {'iam.mysql', 'qs.mysql', 'qs.mongo', 'ai.mysql'}
            and all(row.get('protocol_rows') == 0 and type(row.get('protocol_rows')) is int
                    and re.fullmatch('[0-9a-f]{64}', row.get('binding_sha256', '')) for row in before.values()),
            'same_four_exact_empty_original_bindings_required')
    topics = proof.get('empty_inputs', {})
    require(len(topics) == 20 and all(v == dict(min_offset=0, max_offset=0) for v in topics.values()),
            'twenty_actual_empty_inputs_required')
    require(proof.get('poststart_refused') == ['old-config', 'normal-retry']
            and proof.get('actual_failed_start', {}).get('exit_code', 0) != 0
            and proof.get('coordinator_status', {}).get('runtime_may_have_started') is True,
            'actual_failed_start_and_persistent_forward_boundary_required')
    elapsed = proof.get('elapsed_seconds')
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 < elapsed < 1800
            and proof.get('target_seconds') == 900 and proof.get('upper_seconds') == 1800
            and proof.get('within_target') is (elapsed < 900) and proof.get('max_application_slots') == 8,
            'actual_bounded_switch_required')
    return value
