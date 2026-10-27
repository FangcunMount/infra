"""Exact readable archives to existing ACR; no build, runtime or cutover action.

RC plans can be reviewed offline. Registry writes require a fixed stable SDK,
matching immutable Go/Python tags and the official Python wheel digest, plus a
successful actual eight-instance receipt for every exact archive.
"""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile

from final_image_candidate import ci_guard, sha256
from image_sdk_profile import sdk_profile
from m4_publish_candidates import bounded_json
from publish_candidates import REGISTRY, NAMESPACE, REPO, REPOSITORIES, Registry, command, publish, require
from readable_image_candidates import parse, verify_archive
from readable_image_start import validate_startup

ROOT = Path(__file__).resolve().parents[2]
SDK_REPO = 'FangcunMount/reliable-messaging'


def load_plan(path, expected):
    require(re.fullmatch('[0-9a-f]{64}', expected or '') and sha256(path) == expected, 'reviewed_plan_changed')
    plan = bounded_json(path)
    require(isinstance(plan, dict) and set(plan) == {'schema','candidate','candidate_sha256','registry','namespace','startup','targets'}
            and plan['schema'] == 'readable-reviewed-candidate-publication/v1'
            and plan['registry'] == REGISTRY and plan['namespace'] == NAMESPACE
            and isinstance(plan['targets'], dict) and set(plan['targets']) == set(REPOSITORIES),
            'fixed_readable_publication_scope_required')
    candidate = parse(json.dumps(plan['candidate']).encode())
    require(isinstance(plan['candidate_sha256'], str) and re.fullmatch('[0-9a-f]{64}', plan['candidate_sha256'])
            and candidate['routes_sha256'] == sha256(ROOT / 'components/rocketmq/serverd-routes-readable-v3.json'),
            'exact_readable_routes_and_candidate_digest_required')
    startup = plan['startup']
    require(isinstance(startup, dict) and set(startup) == {'run_id','head_sha','report_sha256'}
            and type(startup['run_id']) is int and startup['run_id'] > 0
            and isinstance(startup['head_sha'], str) and re.fullmatch('[0-9a-f]{40}', startup['head_sha'])
            and isinstance(startup['report_sha256'], str) and re.fullmatch('[0-9a-f]{64}', startup['report_sha256']),
            'exact_readable_startup_receipt_required')
    for target, row in plan['targets'].items():
        role = 'qs' if target.startswith('qs-') else target
        require(isinstance(row, dict) and set(row) == {'repository','source_sha','builder_source_sha',
                'image_config_id','archive_sha256','archive_bytes','inventory_sha256','runtime_sdk'}
                and row['repository'] == REPOSITORIES[target] and row['source_sha'] == candidate['sources'][role]
                and row['builder_source_sha'] == candidate['builder_sha']
                and all(row[key] == candidate['images'][target][key] for key in
                    ('image_config_id','archive_sha256','archive_bytes','inventory_sha256'))
                and isinstance(row['runtime_sdk'], dict), 'exact_five_readable_archives_required')
    return plan


def validate_report(plan, path):
    require(sha256(path) == plan['startup']['report_sha256'], 'native_readable_startup_report_changed')
    row = bounded_json(path)
    validate_startup(row, plan['candidate'], plan['candidate_sha256'])
    require(row.get('infra_sha') == plan['startup']['head_sha']
            and row.get('shutdown_failed_components') == []
            and isinstance(row.get('candidates'), dict) and set(row['candidates']) == set(REPOSITORIES),
            'actual_readable_startup_source_and_five_images_required')
    for target, selected in plan['targets'].items():
        require(all(row['candidates'][target][key] == selected[key] for key in
            ('source_sha','builder_source_sha','image_config_id','archive_sha256')),
            'readable_publication_differs_from_started_archive')
    return row


def stable_sdk_receipt(candidate, run=command):
    expected = sdk_profile(candidate['sdk_profile'])
    require(re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', expected['go'])
            and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', expected['python']),
            'only_published_stable_sdk_can_reach_registry')
    tags = (expected['go'], 'python/v' + expected['python'])
    for tag in tags:
        ref = json.loads(run(['gh','api',f'repos/{SDK_REPO}/git/ref/tags/{tag}']))
        require(ref.get('ref') == 'refs/tags/' + tag and ref.get('object',{}).get('type') == 'commit'
                and ref['object']['sha'] == expected['source_sha'], 'same_exact_stable_sdk_tag_source_required')
        release = json.loads(run(['gh','api',f'repos/{SDK_REPO}/releases/tags/{tag}']))
        require(release.get('tag_name') == tag and release.get('draft') is False
                and release.get('prerelease') is False, 'official_stable_sdk_release_required')
        if tag.startswith('python/'):
            wheel = expected['wheel_url'].rsplit('/',1)[1]
            assets = [a for a in release.get('assets',[]) if a.get('name') == wheel]
            require(len(assets) == 1 and assets[0].get('digest') == 'sha256:' + expected['wheel_sha256']
                    and assets[0].get('browser_download_url') == expected['wheel_url'],
                    'exact_published_stable_python_wheel_required')
    return dict(source_sha=expected['source_sha'],go=expected['go'],python=expected['python'],
                wheel_sha256=expected['wheel_sha256'],tags_match=True)


def retrieve(plan, directory, run=command):
    candidate = plan['candidate']
    for run_id in sorted(set(candidate['image_runs'].values())):
        value = json.loads(run(['gh','api',f'repos/{REPO}/actions/runs/{run_id}']))
        require(str(value.get('id')) == run_id and value.get('head_sha') == candidate['builder_sha']
                and value.get('conclusion') == 'success' and value.get('event') == 'workflow_dispatch'
                and value.get('path') == '.github/workflows/rocketmq-readable-images.yml',
                'successful_exact_readable_builder_required')
    startup = plan['startup']
    value = json.loads(run(['gh','api',f'repos/{REPO}/actions/runs/{startup["run_id"]}']))
    require(value.get('id') == startup['run_id'] and value.get('head_sha') == startup['head_sha']
            and value.get('conclusion') == 'success' and value.get('event') == 'workflow_dispatch'
            and value.get('path') == '.github/workflows/rocketmq-readable-startup.yml',
            'successful_exact_readable_startup_run_required')
    dest = directory / 'startup'; dest.mkdir(mode=0o700)
    run(['gh','run','download',str(startup['run_id']),'--repo',REPO,'--pattern',
         f'readable-eight-instance-startup-{startup["run_id"]}-*','--dir',str(dest)])
    paths = list(dest.rglob('readable-eight-instance-startup.json'))
    require(len(paths) == 1, 'one_exact_readable_startup_report_required')
    validate_report(plan, paths[0])
    archives = {}
    for target, row in plan['targets'].items():
        run_id = candidate['image_runs'][target]
        dest = directory / target; dest.mkdir(mode=0o700)
        for kind in ('metadata','archive'):
            run(['gh','run','download',run_id,'--repo',REPO,'--name',
                 f'readable-image-{kind}-{target}-{row["source_sha"]}-{run_id}','--dir',str(dest)])
        archive = verify_archive(candidate,target,dest)
        metadata = bounded_json(dest/'image-inventory.json')
        require(metadata['runtime_sdk'] == row['runtime_sdk'], 'reviewed_readable_runtime_sdk_differs')
        archives[target] = archive
    return archives


def destinations(plan, run_id, attempt):
    require(isinstance(run_id,str) and re.fullmatch('[1-9][0-9]*',run_id)
            and isinstance(attempt,str) and re.fullmatch('[1-9][0-9]*',attempt),
            'exact_readable_publication_run_attempt_required')
    return {target:f'{REGISTRY}/{NAMESPACE}/{row["repository"]}:readable-candidate-'
            f'{run_id}-{attempt}-{row["source_sha"][:12]}' for target,row in plan['targets'].items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('plan','authfile','report'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--plan-sha256',required=True)
    args = parser.parse_args()
    ci_guard(os.environ); os.umask(0o077)
    require(not args.report.exists() and not args.report.is_symlink(),'new_readable_publication_report_required')
    receipt = dict(schema='readable-candidate-publication/v1',plan_sha256=args.plan_sha256,
        registry_write_attempted=False,published={},complete=False,passed=0,failed=1,skipped=0,
        application_started=False,production_business_cutover=False,application_rebuilt=False)
    def checkpoint():
        args.report.write_text(json.dumps(receipt,indent=2)+'\n');args.report.chmod(0o600)
    try:
        plan = load_plan(args.plan,args.plan_sha256)
        require(os.environ.get('ALIYUN_ACR_REGISTRY') == REGISTRY
                and os.environ.get('ALIYUN_ACR_NAMESPACE') == NAMESPACE,'existing_acr_binding_differs')
        references = destinations(plan,os.environ.get('GITHUB_RUN_ID'),os.environ.get('GITHUB_RUN_ATTEMPT'))
        receipt['stable_sdk'] = stable_sdk_receipt(plan['candidate'])
        receipt.update(publication_run_id=os.environ['GITHUB_RUN_ID'],publication_attempt=os.environ['GITHUB_RUN_ATTEMPT'])
        with tempfile.TemporaryDirectory(prefix='readable-image-publication-') as temp:
            archives = retrieve(plan,Path(temp))
            receipt['all_source_evidence_verified'] = True
            publish(plan,archives,references,Registry(args.authfile),receipt,checkpoint)
        receipt['private_downloads_removed'] = True;checkpoint()
    except Exception as error:
        receipt['error_type'] = type(error).__name__
        if type(error) is ValueError and re.fullmatch('[a-z0-9_:]{1,128}',str(error)):
            receipt['error_code'] = str(error)
        checkpoint()
        raise SystemExit('readable_candidate_publication_incomplete; inspect bounded receipt') from None


if __name__ == '__main__':main()
