"""Mac mini CI transport for exact reviewed image cache; never runs local Docker."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import socket
import subprocess
import sys
import tempfile

from m3_image_cache_target import checked_plan, require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--cleanup-only', action='store_true')
    args = parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'self-hosted'
            and platform.system() == 'Darwin' and socket.gethostname().split('.')[0] == 'macmini-001', 'existing_mac_mini_ci_ingress_required')
    require(os.environ.get('PRODUCTION_DEPLOY_PAUSED') == 'true', 'business_deployment_pause_required')
    raw = args.plan.read_text(); plan = checked_plan(raw, args.plan_sha256, 'serverA')
    checked_plan(raw, args.plan_sha256, 'serverD')
    require(os.environ['ALIYUN_ACR_REGISTRY'] == plan['registry'], 'fixed_existing_registry_required')
    auth = {'auths': {plan['registry']: {'auth': base64.b64encode((os.environ['ALIYUN_ACR_USERNAME'] + ':' + os.environ['ALIYUN_ACR_PASSWORD']).encode()).decode()}}}
    operation = os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']
    source = Path(__file__).with_name('m3_image_cache_target.py').read_text()
    report = dict(schema='m3-fixed-image-cache-receipt/v1',plan_sha256=args.plan_sha256,operation=operation,passed=0,failed=0,skipped=0,targets={},cleanup={},runtime_started=False,production_business_cutover=False)
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='m3-image-cache-ssh-', dir=os.environ['RUNNER_TEMP']) as temporary:
        root = Path(temporary)
        for target, selected in plan['targets'].items():
            key = root / (target + '.key'); key.write_text(os.environ[target.upper() + '_SSH_KEY'].replace('\r','') + '\n'); key.chmod(0o600)
            hosts = root / (target + '.known_hosts'); hosts.write_text(selected['address'] + ' ' + selected['host_key'] + '\n'); hosts.chmod(0o600)
            ssh = ['ssh','-T','-i',str(key),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=20',
                   '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(hosts),'-o','GlobalKnownHostsFile=/dev/null',
                   selected['user']+'@'+selected['address'],'python3','-c',shlex.quote(source)]
            envelope = dict(plan=raw,plan_sha256=args.plan_sha256,target=target,operation=operation,docker_auth=auth,
                sudo_password=os.environ.get(target.upper() + '_SUDO_PASSWORD',''),cleanup_only=args.cleanup_only)
            try:
                p = subprocess.run(ssh,input=json.dumps(envelope).encode(),capture_output=True,timeout=2500)
                require(p.returncode == 0, 'private_ssh_cache_failed')
                result = json.loads(p.stdout)
                require(result.get('authentication_removed') is True and not result.get('failed'), 'target_cache_or_auth_cleanup_failed')
                if not args.cleanup_only:
                    require(result.get('passed') == len(selected['roles']) and result.get('original_containers_unchanged') is True, 'target_receipt_incomplete')
                    report['passed'] += result['passed']
                report['targets'][target] = result
            except BaseException as error:
                report['failed'] += 1; report['error_type'] = type(error).__name__
                break
            finally:
                # Idempotent additional cleanup also handles an interrupted SSH child.
                envelope['cleanup_only'] = True
                try:
                    cleanup = subprocess.run(ssh,input=json.dumps(envelope).encode(),capture_output=True,timeout=45)
                    report['cleanup'][target] = cleanup.returncode == 0 and json.loads(cleanup.stdout).get('authentication_removed') is True
                except BaseException:
                    report['cleanup'][target] = False
                if not report['cleanup'][target]: report['failed'] += 1
    report['complete'] = report['failed'] == 0 and len(report['targets']) == 2
    args.report.write_text(json.dumps(report,indent=2)+'\n'); args.report.chmod(0o600)
    print(json.dumps({'passed':report['passed'],'failed':report['failed'],'complete':report['complete'],'runtime_started':False}))
    return bool(report['failed'])


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError):
        print('{"failed":1,"runtime_started":false,"status":"private_transport_unavailable"}')
        raise SystemExit(1) from None
