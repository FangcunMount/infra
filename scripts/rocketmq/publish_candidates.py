"""CI-only transport of reviewed archives to existing ACR; no build or deployment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

from final_image_candidate import ci_guard, saved_config, sha256
from image_cutover_boundary import COMPONENTS, startup_receipt
from image_start_fixture import verified_image_inventory

REGISTRY = 'crpi-x3r4i68cpfmwtcll.cn-beijing.personal.cr.aliyuncs.com'
NAMESPACE = 'fangcunmount'
REPOSITORIES = dict(iam='iam', ai='qs-ai', **{'qs-api':'qs-apiserver',
    'qs-collection':'qs-collection-server', 'qs-worker':'qs-worker'})
REPO = 'FangcunMount/infra'


def require(value, reason):
    if not value: raise ValueError(reason)


def command(args, timeout=300):
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    require(result.returncode == 0, 'command_failed:' + Path(args[0]).name)
    return result.stdout


def load_plan(path, expected):
    require(re.fullmatch('[0-9a-f]{64}', expected or ''), 'reviewed_plan_digest_required')
    require(sha256(path) == expected, 'reviewed_plan_changed')
    plan = json.loads(path.read_bytes())
    require(plan['schema'] == 'm3-reviewed-candidate-publication/v1'
            and plan['registry'] == REGISTRY and plan['namespace'] == NAMESPACE
            and set(plan['targets']) == set(REPOSITORIES), 'fixed_existing_acr_scope_required')
    for phase in ('build', 'startup', 'cutover'):
        row = plan[phase]
        require(type(row['run_id']) is int and row['run_id'] > 0
                and re.fullmatch('[0-9a-f]{40}', row['head_sha']), 'exact_source_run_required')
    for target, row in plan['targets'].items():
        require(row['repository'] == REPOSITORIES[target]
                and re.fullmatch('[0-9a-f]{40}', row['source_sha'])
                and row['builder_source_sha'] == plan['build']['head_sha']
                and re.fullmatch('sha256:[0-9a-f]{64}', row['image_config_id'])
                and all(re.fullmatch('[0-9a-f]{64}', row[k]) for k in ('archive_sha256', 'inventory_sha256'))
                and type(row['archive_bytes']) is int and row['archive_bytes'] > 0,
                'exact_reviewed_image_required')
    return plan


def validate_reports(plan, startup, cutover):
    require(sha256(startup) == plan['startup']['report_sha256']
            and sha256(cutover) == plan['cutover']['report_sha256'], 'native_report_changed')
    initial, _ = startup_receipt(startup)
    value = json.loads(cutover.read_bytes())
    require((value['passed'], value['failed'], value['skipped']) == (19, 0, 0)
            and len(value['cases']) == 19 and all(v is True for v in value['cases'].values())
            and value['infra_sha'] == plan['cutover']['head_sha']
            and value['sources'] == initial['sources'] and value['candidates'] == initial['candidates']
            and value['startup_receipt_sha256'] == plan['startup']['report_sha256']
            and value['dependency_versions'] == initial['dependency_versions']
            and value['actual_runtime_budgets'] == initial['actual_runtime_budgets']
            and set(value['processes']) == set(value['actual_up_after_marker']) == set(COMPONENTS)
            and value['actual_cutover']['actual_processes'] == len(COMPONENTS) == 8
            and value['actual_cutover']['elapsed_seconds'] < 1800
            and value['coordinator_status']['first_start_recorded'] is True
            and value['coordinator_status']['old_data_restore_eligible'] is False
            and set(value['actual_cutover']['poststart_refused']) == {'old-full-backup','poststart-offline'}
            and value['full_scope_restore']['snapshots_before'] == value['full_scope_restore']['snapshots_after']
            and value['mysql_runtime_ddl_attempts'] == value['mongo_runtime_ddl_attempts'] == 0
            and value['sources_unchanged'] is True
            and all(value['cleanup'].values())
            and not value['production'] and not value['system_acceptance'], 'complete_current_c1_required')
    require(all(p['state'] == dict(Status='exited', ExitCode=0, OOMKilled=False)
                for p in value['processes'].values()), 'all_eight_clean_exits_required')
    for target, row in plan['targets'].items():
        require(all(initial['candidates'][target][key] == row[key] for key in
                    ('source_sha','builder_source_sha','image_config_id','archive_sha256')),
                'reviewed_candidate_differs_from_native_images')


def verify_archive(directory, target, row, *, reviewed_builder=None):
    metadata = directory / 'image-inventory.json'
    require(sha256(metadata) == row['inventory_sha256'], 'image_inventory_changed')
    value = json.loads(metadata.read_bytes())
    verified_image_inventory(value, target, row['source_sha'], reviewed_builder=reviewed_builder)
    require(all(value[k] == row[k] for k in ('builder_source_sha','image_config_id','archive_sha256',
                'archive_bytes','runtime_sdk')), 'reviewed_inventory_differs')
    require(value['expected_sdk_source_sha'] == '1345266aa0e864c46de5d1e3e3c939dd8002a890',
            'fixed_stable_sdk_required')
    archive = directory / (target + '-' + row['source_sha'] + '.tar.gz')
    require(archive.stat().st_size == row['archive_bytes'] and sha256(archive) == row['archive_sha256'],
            'exact_reviewed_archive_required')
    with tarfile.open(archive) as source:
        rows = json.load(source.extractfile('manifest.json'))
    require(len(rows) == 1 and len(rows[0]['RepoTags']) == 1, 'single_archived_image_required')
    tag = rows[0]['RepoTags'][0]
    require(re.fullmatch('m3-final-' + re.escape(target) + ':[0-9a-f]{12}', tag), 'original_archive_tag_required')
    require(saved_config(archive, tag)[0] == row['image_config_id'], 'archived_config_changed')
    return archive


def retrieve(plan, directory, run=command):
    # All source runs, reports and archives are checked before any registry write.
    for phase in ('build', 'startup', 'cutover'):
        row = plan[phase]
        result = json.loads(run(['gh','api',f'repos/{REPO}/actions/runs/{row["run_id"]}']))
        require(result['conclusion'] == 'success' and result['head_sha'] == row['head_sha']
                and result['path'] == '.github/workflows/rocketmq-final-images.yml',
                'successful_exact_producer_run_required')
    def download(run_id, name, dest):
        dest.mkdir(mode=0o700)
        run(['gh','run','download',str(run_id),'--repo',REPO,'--name',name,'--dir',str(dest)])
    for phase in ('startup','cutover'):
        row = plan[phase]
        download(row['run_id'], 'm3-five-image-start-' + str(row['run_id']), directory / phase)
    validate_reports(plan, directory/'startup/five-image-start.json', directory/'cutover/five-image-start.json')
    archives = {}
    for target, row in plan['targets'].items():
        dest = directory / target
        download(plan['build']['run_id'], f'm3-final-image-metadata-{target}-{row["source_sha"]}-{plan["build"]["run_id"]}', dest)
        run(['gh','run','download',str(plan['build']['run_id']),'--repo',REPO,'--name',
             f'm3-final-image-archive-{target}-{row["source_sha"]}-{plan["build"]["run_id"]}','--dir',str(dest)])
        archives[target] = verify_archive(dest, target, row)
    return archives


class Registry:
    def __init__(self, authfile, *, tls=True, run=command):
        self.authfile, self.tls, self.run = authfile, tls, run

    def options(self, reference):
        require(self.tls or re.match(r'127\.0\.0\.1:[0-9]+/', reference), 'plaintext_only_owned_loopback')
        return ['--authfile',str(self.authfile),'--tls-verify=' + str(self.tls).lower()]

    def tags(self, repository):
        result = json.loads(self.run(['skopeo','list-tags',*self.options(repository),'docker://' + repository]))
        tags = result['Tags']
        require(tags is None or isinstance(tags,list) and all(type(t) is str for t in tags), 'valid_remote_tags_required')
        return tags or []

    def copy(self, archive, reference):
        require(self.tls or reference.startswith('127.0.0.1:'), 'plaintext_only_owned_loopback')
        self.run(['skopeo','copy','--authfile',str(self.authfile),'--dest-tls-verify=' + str(self.tls).lower(),
                  '--format','v2s2','docker-archive:' + str(archive),'docker://' + reference], timeout=900)

    def verify(self, reference, config_id):
        raw = self.run(['skopeo','inspect','--raw',*self.options(reference),'docker://' + reference])
        require(len(raw) < 1024*1024, 'bounded_registry_manifest_required')
        value = json.loads(raw)
        require(value.get('schemaVersion') == 2 and value.get('config',{}).get('digest') == config_id
                and isinstance(value.get('layers'),list), 'registry_config_differs_from_tested_archive')
        digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
        immutable = reference.rsplit(':',1)[0] + '@' + digest
        reread = self.run(['skopeo','inspect','--raw',*self.options(immutable),'docker://' + immutable])
        require(reread == raw, 'immutable_registry_readback_differs')
        return immutable


def destinations(plan, run_id, attempt):
    require(re.fullmatch('[1-9][0-9]*', run_id or '') and re.fullmatch('[1-9][0-9]*', attempt or ''),
            'exact_publication_run_attempt_required')
    return {target: REGISTRY + '/' + NAMESPACE + '/' + row['repository'] + ':m3-candidate-'
            + str(plan['build']['run_id']) + '-' + run_id + '-' + attempt + '-' + row['source_sha'][:12]
            for target, row in plan['targets'].items()}


def publish(plan, archives, references, registry, receipt, checkpoint):
    # Authentication/list failures propagate; never reinterpret a failure as absence.
    for reference in references.values():
        repository, tag = reference.rsplit(':',1)
        require(tag not in registry.tags(repository), 'candidate_tag_exists_refusing_overwrite')
    receipt['preflight_complete'] = True
    checkpoint()
    for target, reference in references.items():
        # If transport fails, this target is unknown, not safely absent/rolled back.
        receipt['current_target'] = target
        receipt['registry_write_attempted'] = True
        checkpoint()
        registry.copy(archives[target], reference)
        row = plan['targets'][target]
        immutable = registry.verify(reference, row['image_config_id'])
        receipt['published'][target] = dict(tag=reference, reference=immutable,
            image_config_id=row['image_config_id'], archive_sha256=row['archive_sha256'], source_sha=row['source_sha'])
        receipt['current_target'] = None
        checkpoint()
    receipt.update(passed=5, failed=0, skipped=0, complete=True)
    checkpoint()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--plan-sha256',required=True)
    parser.add_argument('--authfile',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args = parser.parse_args()
    ci_guard(os.environ)
    os.umask(0o077)
    receipt = dict(schema='m3-candidate-publication/v1', plan_sha256=args.plan_sha256,
        registry_write_attempted=False, published={}, complete=False, passed=0, failed=1, skipped=0,
        application_started=False, production_business_cutover=False)
    def checkpoint():
        # Runner-local evidence only; no credential bytes or command output.
        args.report.write_text(json.dumps(receipt,indent=2)+'\n')
    try:
        plan = load_plan(args.plan,args.plan_sha256)
        require(os.environ.get('ALIYUN_ACR_REGISTRY') == REGISTRY
                and os.environ.get('ALIYUN_ACR_NAMESPACE') == NAMESPACE, 'existing_acr_binding_differs')
        references = destinations(plan,os.environ.get('GITHUB_RUN_ID'),os.environ.get('GITHUB_RUN_ATTEMPT'))
        receipt.update(publication_run_id=os.environ['GITHUB_RUN_ID'],publication_attempt=os.environ['GITHUB_RUN_ATTEMPT'])
        with tempfile.TemporaryDirectory(prefix='m3-image-publication-') as temp:
            archives = retrieve(plan,Path(temp))
            receipt['all_source_evidence_verified'] = True
            publish(plan,archives,references,Registry(args.authfile),receipt,checkpoint)
        receipt['private_downloads_removed'] = True
        checkpoint()
    except Exception as error:
        receipt['error_type'] = type(error).__name__
        if type(error) is ValueError and re.fullmatch('[a-z0-9_:]{1,128}',str(error)):
            receipt['error_code'] = str(error)
        checkpoint()
        raise SystemExit('candidate_publication_incomplete; inspect bounded receipt') from None


if __name__ == '__main__':
    main()
