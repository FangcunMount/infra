#!/usr/bin/env python3
"""Build a source-bound prerelease receipt; never creates tags or publishes.

Inputs are downloaded successful CI artifacts at the exact merged SDK SHA.
The output is a new private directory containing immutable release candidates.
"""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

from prepare_published import GO_TAG, PY_TAG, REPO, VERSION, digest, run, source_manifest


def checked_report(path, sha, count, candidate, infra):
    report = json.loads(path.read_text())
    cases = report.get('cases', {})
    if (report.get('sdk_sha') != sha or report.get('passed') != count
            or report.get('failed') != 0 or report.get('skipped') != 0
            or report.get('failure') is not None or len(cases) != count
            or any(value is not True for value in cases.values())):
        raise ValueError('acceptance report is empty, incomplete or from another SDK SHA')
    if report.get('cleanup') != {'project_containers_remaining': False,
                                 'compose_down_succeeded': True,
                                 'private_fixture_directory_removed': True}:
        raise ValueError('acceptance cleanup did not finish')
    if count != 20 and report.get('sdk_tracked_sources_clean') is not True:
        raise ValueError('acceptance used modified SDK sources')
    source_fields = [('sdk_source_sha256', candidate), ('harness_sha256', infra),
                     ('source_sha256', infra)]
    if count != 20:
        source_fields.append(('sdk_api_source_sha256', candidate))
    for field, root in source_fields:
        values = report.get(field, {})
        if not values:
            raise ValueError('acceptance source hashes absent: '+field)
        for name, expected in values.items():
            if Path(name).is_absolute() or '..' in Path(name).parts or digest(root/name) != expected:
                raise ValueError('acceptance source bytes differ from fixed candidate/harness')
    if count == 46:
        runtime = report.get('python_runtime', {})
        if (report.get('clients') != {'go': '5.1.4', 'python': '5.1.2'}
                or runtime.get('client') != '5.1.2' or runtime.get('sdk_version') != VERSION):
            raise ValueError('acceptance did not use the fixed SDK/client versions')
        limits = report.get('proof', {}).get('finite_sdk_limit', [])
        if len(limits) != 2 or any(
                item.get('mode') != '0600' or not item.get('audit', {}).get('records')
                or item.get('audit', {}).get('severity') != 'critical'
                or item.get('business_count') != 0
                or item.get('local_evidence') != 'prepared_retained' for item in limits):
            raise ValueError('real native-limit evidence is incomplete')
        cases_required = {'real_database_commit_': 6, 'after_real_broker_ack_tcp_loss': 4,
                          'producer_exit_broker_restart_new_checker': 3}
        if any(sum(part in name for name in cases) != needed
               for part, needed in cases_required.items()):
            raise ValueError('real database, Broker packet or restart fault cases absent')
    return report


def checked_artifacts(directory, sha, tree):
    review = json.loads((directory/'artifact-review.json').read_text())
    assets = [*directory.glob('dist/*.whl'), *directory.glob('dist/*.tar.gz')]
    values = {p.name: digest(p) for p in assets}
    if (review.get('source') != sha or review.get('source_tree') != tree
            or len(assets) != 2 or len(list(directory.glob('dist/*.whl'))) != 1
            or len(list(directory.glob('dist/*.tar.gz'))) != 1
            or review.get('assets') != values):
        raise ValueError('Python assets are not bound to the exact merged source/tree')
    results = {}
    for filename in ('results.xml', 'wheel-results.xml'):
        report = ET.parse(directory/filename)
        cases = list(report.iter('testcase'))
        suites = list(report.iter('testsuite'))
        if (not cases or not suites
                or any(list(report.iter(tag)) for tag in ('error', 'failure', 'skipped'))
                or any(int(s.get(key, '0')) != 0 for s in suites
                       for key in ('errors', 'failures', 'skipped'))):
            raise ValueError('required source/wheel tests are empty or unsuccessful')
        results[filename] = {'passed': len(cases), 'failed': 0, 'skipped': 0}
    return assets, values, results


def checked_run(repository, identity, name, sha=None):
    if not identity.isdecimal():
        raise ValueError('numeric CI run identity required')
    metadata = json.loads(run(['gh', 'api', f'repos/{repository}/actions/runs/{identity}']))
    if (metadata.get('name') != name or metadata.get('status') != 'completed'
            or metadata.get('conclusion') != 'success'
            or (sha is not None and metadata.get('head_sha') != sha)):
        raise ValueError('required exact-source CI run is not successful: '+name)
    jobs = json.loads(run(['gh', 'api', f'repos/{repository}/actions/runs/{identity}/jobs?per_page=100']))
    if (not jobs.get('jobs') or jobs.get('total_count') != len(jobs['jobs'])
            or any(j.get('conclusion') != 'success' for j in jobs['jobs'])):
        raise ValueError('required CI has missing, skipped or unsuccessful jobs')
    return {key: metadata[key] for key in ('id', 'name', 'head_sha', 'html_url', 'event',
                                          'status', 'conclusion', 'created_at', 'updated_at')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'python-artifacts', 'reports', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-runs', required=True,
                        help='SDK checks,Python messaging SDK,Transaction storage proofs,Isolated infrastructure run IDs')
    parser.add_argument('--acceptance-run', required=True)
    parser.add_argument('--regression-run', required=True)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    sha = run(['git', 'rev-parse', 'HEAD'], cwd=candidate).strip()
    tree = run(['git', 'rev-parse', 'HEAD^{tree}'], cwd=candidate).strip()
    if (sha != run(['git', 'rev-parse', 'origin/main'], cwd=candidate).strip()
            or run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=candidate).strip()):
        raise ValueError('candidate must be the clean exact merged origin/main')
    names = ('SDK checks', 'Python messaging SDK', 'Transaction storage proofs', 'Isolated infrastructure')
    identities = args.source_runs.split(',')
    if len(identities) != len(names):
        raise ValueError('four exact source CI run IDs required')
    source_ci = [checked_run(REPO, identity, name, sha) for identity, name in zip(identities, names)]
    acceptance_ci = checked_run('FangcunMount/infra', args.acceptance_run,
                                'RocketMQ complete transaction acceptance')
    regression_ci = checked_run('FangcunMount/infra', args.regression_run, 'RocketMQ Docker acceptance')
    infra = Path(__file__).resolve().parents[2]
    full = [checked_report(p, sha, 46, candidate, infra)
            for p in sorted(args.reports.rglob('rocketmq-complete-sdk.json'))]
    raw = [checked_report(p, sha, 20, candidate, infra)
           for p in sorted(args.reports.rglob('rocketmq-m2-transactions.json'))]
    go = [checked_report(p, sha, 19, candidate, infra)
          for p in sorted(args.reports.rglob('rocketmq-m2-go-sdk.json'))]
    if (len(full) != 2 or len(raw) != 1 or len(go) != 1
            or {r['go_version'] for r in full} != {'go1.25.9', 'go1.25.12'}
            or {'.'.join(r['python_runtime']['python'].split('.')[:2]) for r in full} != {'3.11', '3.13'}):
        raise ValueError('complete runtime/regression matrix absent')
    profiles = sorted(args.python_artifacts.glob('*/artifact-review.json'))
    if len(profiles) != 2:
        raise ValueError('exactly two Python build profiles required')
    assets, values, results = checked_artifacts(profiles[0].parent, sha, tree)
    _, other_values, other_results = checked_artifacts(profiles[1].parent, sha, tree)
    if values != other_values:
        raise ValueError('wheel/sdist differ across fixed build profiles')
    if not all(f'-{VERSION}' in p.name for p in assets):
        raise ValueError('unexpected Python prerelease version')
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for asset in assets:
        shutil.copyfile(asset, output/asset.name)
    shutil.copyfile(candidate/'python/uv.lock', output/'uv.lock')
    acceptance = {'source_sha': sha, 'source_ci': source_ci,
                  'acceptance_ci': acceptance_ci, 'regression_ci': regression_ci,
                  'full_sdk_reports': full, 'raw_protocol_reports': raw, 'go_sdk_reports': go}
    (output/'transaction-acceptance.json').write_text(json.dumps(acceptance, indent=2)+'\n')
    receipt = {'version': 1, 'source_sha': sha, 'source_tree': tree,
               'go_tag': GO_TAG, 'python_tag': PY_TAG,
               'prepared_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'source_files_sha256': source_manifest(candidate),
               'ci': {'source': source_ci, 'acceptance': acceptance_ci, 'regression': regression_ci},
               'python_profiles': {profiles[0].parent.name: results, profiles[1].parent.name: other_results},
               'assets': {p.name: digest(p) for p in sorted(output.iterdir())}}
    (output/'transaction-release-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in sorted(output.iterdir())))
    print(json.dumps({'source_sha': sha, 'assets': sorted(p.name for p in output.iterdir()),
                      'tags_created': False, 'published': False}))


if __name__ == '__main__':
    main()
