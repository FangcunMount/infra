"""Publish the exact C08 archives; never build, migrate or start an application.

M3's full cutover proof remains a separate contract. This profile is explicitly
the current-schema M4 eight-instance proof, not a replacement M3 restore gate.
"""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile

from final_image_candidate import ci_guard, sha256
from image_cutover_boundary import COMPONENTS
from m4_final_image_candidates import parse, unique_object
from publish_candidates import (REGISTRY, NAMESPACE, REPO, REPOSITORIES, Registry,
                                command, publish, require, verify_archive)


def bounded_json(path):
    require(path.is_file() and not path.is_symlink()
            and 0 < path.stat().st_size <= 1024 * 1024, 'regular_bounded_publication_evidence_required')
    return json.loads(path.read_bytes(), object_pairs_hook=unique_object)


def load_plan(path, expected):
    require(re.fullmatch('[0-9a-f]{64}', expected or '') and sha256(path) == expected,
            'reviewed_plan_changed')
    plan = bounded_json(path)
    require(set(plan) == {'schema', 'candidate', 'candidate_sha256', 'registry', 'namespace', 'startup', 'targets'}
            and plan['schema'] == 'm4-reviewed-candidate-publication/v1'
            and plan['registry'] == REGISTRY and plan['namespace'] == NAMESPACE
            and set(plan['targets']) == set(REPOSITORIES), 'fixed_m4_publication_scope_required')
    try:
        candidate = parse(json.dumps(plan['candidate']).encode())
    except RuntimeError as error:
        raise ValueError(str(error)) from error
    require(re.fullmatch('[0-9a-f]{64}', plan['candidate_sha256']), 'candidate_digest_required')
    startup = plan['startup']
    require(set(startup) == {'run_id', 'head_sha', 'report_sha256'}
            and type(startup['run_id']) is int and startup['run_id'] > 0
            and re.fullmatch('[0-9a-f]{40}', startup['head_sha'])
            and re.fullmatch('[0-9a-f]{64}', startup['report_sha256']), 'exact_startup_evidence_required')
    for target, row in plan['targets'].items():
        role = 'qs' if target.startswith('qs-') else target
        require(set(row) == {'repository', 'source_sha', 'builder_source_sha', 'image_config_id',
                            'archive_sha256', 'archive_bytes', 'inventory_sha256', 'runtime_sdk'}
                and row['repository'] == REPOSITORIES[target]
                and row['source_sha'] == candidate['sources'][role]
                and row['builder_source_sha'] == candidate['builder_sha']
                and re.fullmatch('sha256:[0-9a-f]{64}', row['image_config_id'])
                and all(re.fullmatch('[0-9a-f]{64}', row[k]) for k in ('archive_sha256', 'inventory_sha256'))
                and type(row['archive_bytes']) is int and row['archive_bytes'] > 0
                and isinstance(row['runtime_sdk'], dict), 'exact_m4_image_required')
    return plan


def validate_report(plan, path):
    require(sha256(path) == plan['startup']['report_sha256'], 'native_report_changed')
    value = bounded_json(path)
    candidate = plan['candidate']
    require(value['schema'] == 'm4-eight-instance-config-rebuild/v1'
            and value['final_candidate'] is True
            and value['final_python_dependencies'] == dict(sdk='0.4.0', nsq_absent=True, tornado_absent=True, current_imports=True)
            and value['final_candidate_manifest_sha256'] == plan['candidate_sha256']
            and value['final_candidate_image_runs'] == candidate['image_runs']
            and value['sources'] == candidate['sources']
            and value['infra_sha'] == plan['startup']['head_sha']
            and (value['passed'], value['failed'], value['skipped']) == (18, 0, 0)
            and len(value['cases']) == 18 and all(v is True for v in value['cases'].values())
            and value['sources_unchanged'] is True
            and set(value['processes']) == set(value['actual_runtime_budgets'])
                == set(value['actual_material_mounts']) == set(COMPONENTS)
            and value['m4_material_stage']['files'] == 21
            and value['actual_source_worker_concurrency'] == 48
            and value['mysql_runtime_ddl_attempts'] == value['mongo_runtime_ddl_attempts'] == 0
            and value['cleanup'] and all(v is True for v in value['cleanup'].values())
            and value['shutdown_failed_components'] == []
            and value['production'] is False and value['system_acceptance'] is False
            and value['combined_cutover_rehearsal_complete'] is False,
            'complete_current_m4_eight_instance_proof_required')
    require(all(p['state'] == dict(Status='exited', ExitCode=0, OOMKilled=False)
                for p in value['processes'].values()), 'all_eight_clean_exits_required')
    require(set(value['candidates']) == set(REPOSITORIES), 'all_five_started_archives_required')
    for target, row in plan['targets'].items():
        require(all(value['candidates'][target][key] == row[key] for key in
                    ('source_sha', 'builder_source_sha', 'image_config_id', 'archive_sha256')),
                'tested_archive_differs_from_publication')
    return value


def retrieve(plan, directory, run=command):
    candidate = plan['candidate']
    for run_id in sorted(set(candidate['image_runs'].values())):
        result = json.loads(run(['gh', 'api', f'repos/{REPO}/actions/runs/{run_id}']))
        require(str(result['id']) == run_id and result['conclusion'] == 'success'
                and result['head_sha'] == candidate['builder_sha']
                and result['event'] == 'workflow_dispatch'
                and result['path'] == '.github/workflows/rocketmq-final-images.yml',
                'successful_exact_m4_build_required')
    startup = plan['startup']
    result = json.loads(run(['gh', 'api', f'repos/{REPO}/actions/runs/{startup["run_id"]}']))
    require(result['id'] == startup['run_id'] and result['conclusion'] == 'success'
            and result['head_sha'] == startup['head_sha']
            and result['path'] == '.github/workflows/m4-final-image-rebuild.yml',
            'successful_exact_m4_startup_required')
    dest = directory / 'startup'
    dest.mkdir(mode=0o700)
    run(['gh', 'run', 'download', str(startup['run_id']), '--repo', REPO, '--pattern',
         f'm4-final-eight-instance-rebuild-{startup["run_id"]}-*', '--dir', str(dest)])
    reports = list(dest.rglob('m4-eight-instance-rebuild.json'))
    require(len(reports) == 1, 'one_exact_startup_report_required')
    validate_report(plan, reports[0])
    archives = {}
    for target, row in plan['targets'].items():
        run_id = candidate['image_runs'][target]
        dest = directory / target
        dest.mkdir(mode=0o700)
        for kind in ('metadata', 'archive'):
            run(['gh', 'run', 'download', run_id, '--repo', REPO, '--name',
                 f'm3-final-image-{kind}-{target}-{row["source_sha"]}-{run_id}', '--dir', str(dest)])
        archives[target] = verify_archive(dest, target, row, reviewed_builder=candidate['builder_sha'])
    return archives


def destinations(plan, run_id, attempt):
    require(re.fullmatch('[1-9][0-9]*', run_id or '')
            and re.fullmatch('[1-9][0-9]*', attempt or ''), 'exact_publication_run_attempt_required')
    return {target: f'{REGISTRY}/{NAMESPACE}/{row["repository"]}:m4-candidate-'
            f'{run_id}-{attempt}-{row["source_sha"][:12]}' for target, row in plan['targets'].items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--authfile', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    ci_guard(os.environ)
    os.umask(0o077)
    receipt = dict(schema='m4-candidate-publication/v1', plan_sha256=args.plan_sha256,
        registry_write_attempted=False, published={}, complete=False, passed=0, failed=1, skipped=0,
        application_started=False, production_business_cutover=False, application_rebuilt=False)

    def checkpoint():
        args.report.write_text(json.dumps(receipt, indent=2) + '\n')

    try:
        plan = load_plan(args.plan, args.plan_sha256)
        require(os.environ.get('ALIYUN_ACR_REGISTRY') == REGISTRY
                and os.environ.get('ALIYUN_ACR_NAMESPACE') == NAMESPACE, 'existing_acr_binding_differs')
        references = destinations(plan, os.environ.get('GITHUB_RUN_ID'), os.environ.get('GITHUB_RUN_ATTEMPT'))
        receipt.update(publication_run_id=os.environ['GITHUB_RUN_ID'],
                       publication_attempt=os.environ['GITHUB_RUN_ATTEMPT'])
        with tempfile.TemporaryDirectory(prefix='m4-image-publication-') as temp:
            archives = retrieve(plan, Path(temp))
            receipt['all_source_evidence_verified'] = True
            publish(plan, archives, references, Registry(args.authfile), receipt, checkpoint)
        receipt['private_downloads_removed'] = True
        checkpoint()
    except Exception as error:
        receipt['error_type'] = type(error).__name__
        if type(error) is ValueError and re.fullmatch('[a-z0-9_:]{1,128}', str(error)):
            receipt['error_code'] = str(error)
        checkpoint()
        raise SystemExit('m4_candidate_publication_incomplete; inspect bounded receipt') from None


if __name__ == '__main__':
    main()
