"""Original offline CLIs on owned old-schema fixtures, under the real C1 barrier.

All approvals here attest synthetic CI facts only. They are never production
approval or backup-retention proof. No journal is rewritten or force-set.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os

from ai_image_start import PYTHON
from audit_transaction_limit import write_private
from image_cutover_boundary import ActualImageBoundary, digest, publish_owned_images, startup_receipt
from image_full_protection import FullImageProtection
from image_start_fixture import require
from qs_image_pair import QS_SHA
from start_boundary import _encoded


def qs_environment(f, database):
    return dict(QS_OFFLINE_MYSQL_DSN=f'root:{f.password}@tcp(mysql:3306)/{database}?parseTime=true',
                QS_OFFLINE_MONGO_URI='mongodb://mongo:27017/?replicaSet=image-proof')


def qs_snapshot(f, database):
    f.select('api')
    result = json.loads(f.once('/fixture/qs-migrate-offline', ['--mysql-database', database,
        '--mongo-database', database, '--timeout', '30s'], environment=qs_environment(f, database)))
    require(result['read_only'] is True, 'original_read_only_pair_snapshot_required')
    snapshot = result['snapshot']
    require(snapshot['source_sha'] == QS_SHA and snapshot['mysql_database'] == snapshot['mongo_database'] == database
            and (snapshot['mysql_version'], snapshot['mongo_version']) == (105, 40)
            and (snapshot['target_mysql_version'], snapshot['target_mongo_version']) == (110, 43), 'original_pre_m3_pair_required')
    for key in ('mysql_identity_sha256', 'mongo_cluster_sha256', 'migration_resources_sha256'): digest(snapshot[key])
    return snapshot


def offline_approval(snapshot, *, operation_id, started, protection, startup_sha, scope_sha, responsibility_sha):
    now = datetime.now(timezone.utc)
    require(started <= now and (now - started).total_seconds() < 1500, 'owned_cutover_window_required')
    return dict(format_version=1, kind='qs_schema_pair_offline_upgrade', operation_id=operation_id,
        expires_at=(now + timedelta(minutes=20)).isoformat(timespec='seconds').replace('+00:00', 'Z'),
        approved_source_sha=snapshot['source_sha'], migration_resources_sha256=snapshot['migration_resources_sha256'],
        mysql_database=snapshot['mysql_database'], mongo_database=snapshot['mongo_database'],
        mysql_identity_sha256=snapshot['mysql_identity_sha256'], mongo_cluster_sha256=snapshot['mongo_cluster_sha256'],
        initial_mysql_version=105, initial_mongo_version=40, target_mysql_version=110, target_mongo_version=43,
        approval_summary_sha256=hashlib.sha256(_encoded(dict(scope='owned-isolated-ci-only', snapshot=snapshot,
            protection=protection.manifest_sha, responsibility=responsibility_sha))).hexdigest(),
        freeze_scope_sha256=digest(scope_sha), protection_scope='full_database_pair',
        protection_manifest_sha256=digest(protection.manifest_sha), restore_receipt_sha256=digest(protection.receipt_sha),
        startup_receipt_sha256=digest(startup_sha), responsibility_sha256=digest(responsibility_sha),
        protection_location=str(protection.f.directory), data_owner='owned-isolated-ci', recovery_owner='owned-isolated-ci',
        runtime_frozen=True, runtime_not_started=True,
        window_started_at=started.isoformat(timespec='seconds').replace('+00:00', 'Z'),
        restore_duration_seconds=protection.restore_seconds, startup_reserve_seconds=300,
        backup_retention_days=30)  # CI attestation required by original CLI; not verified production retention.


def bind_qs(f, database):
    f.select('api'); env = qs_environment(f, database)
    common = ['--mysql-database', database, '--mongo-database', database, '--timeout', '30s']
    for owner in ('qs.mysql', 'qs.mongo'):
        plan = '/fixture/' + owner + '.json'
        f.once('/fixture/qs-migrate-offline', common + ['--binding-action', 'preview', '--binding-plan', plan,
            '--binding-operation-id', f.project, '--binding-owner', owner,
            '--binding-store-id', 'isolated-' + owner.replace('.', '-') + '-primary', '--binding-writer-epoch', 'm3-1'], environment=env)
        sha = f.once('/usr/bin/sha256sum', [plan], network=False).split()[0]
        f.once('/fixture/qs-migrate-offline', common + ['--binding-action', 'apply', '--binding-plan', plan,
            '--binding-reviewed-sha256', sha, '--binding-writers-excluded'], environment=env)
        result = json.loads(f.once('/fixture/qs-migrate-offline', common + ['--binding-action', 'verify', '--binding-plan', plan,
            '--binding-reviewed-sha256', sha], environment=env))
        require(result['verified'] is True, 'original_dual_binding_verified_required')


def bind_ai(f, environment):
    f.select('ai'); command = ['-m', 'qs_ai.maintenance.transaction_binding']
    f.once(PYTHON, command + ['--action', 'preview', '--plan', '/fixture/binding.json', '--operation-id', f.project,
        '--store-id', 'isolated-ai-primary', '--writer-epoch', 'm3-1'], environment=environment)
    sha = f.once('/usr/bin/sha256sum', ['/fixture/binding.json'], network=False).split()[0]
    for action in ('apply', 'verify'):
        f.once(PYTHON, command + ['--action', action, '--plan', '/fixture/binding.json', '--reviewed-sha256', sha]
            + (['--writers-excluded'] if action == 'apply' else []), environment=environment)


def prepare(f, args, databases, ai_admin_environment, specs):
    trial, trial_sha = startup_receipt(args.startup_receipt)
    require(trial['candidates'] == f.report['candidates']
            and trial['original_qs_consumer_contract'] == f.report['original_qs_consumer_contract'], 'independent_original_startup_evidence_differs')
    f.stage = 'full_scope_pre_window_protection_and_restore'
    protection = FullImageProtection(f, databases); manifest, _ = protection.train()
    snapshot = qs_snapshot(f, databases['qs'])
    scope = {}
    for owner, store in [('iam.mysql', 'iam'), ('qs.mysql', 'qs'), ('qs.mongo', 'qs'), ('ai.mysql', 'ai')]:
        identity = snapshot['mongo_cluster_sha256'] if owner == 'qs.mongo' else snapshot['mysql_identity_sha256'] if owner == 'qs.mysql' else manifest['mysql'][store]['selected_identity_sha256']
        scope[owner] = dict(database=databases[store], identity_sha256=identity,
            store_id={'iam.mysql':'isolated-iam-primary','qs.mysql':'isolated-qs-mysql-primary',
                'qs.mongo':'isolated-qs-mongo-primary','ai.mysql':'isolated-ai-primary'}[owner], writer_epoch='m3-1', route_revision='m3-1')
    publish_owned_images(f)
    source_files = ['components/rocketmq/serverd-routes-m3-v2.json'] + ['scripts/rocketmq/' + name + '.py' for name in
        ('start_boundary', 'cutover_step', 'runtime_start', 'nsq_drain_evidence', 'audit_transaction_limit', 'render', 'provision', 'provision_v2', 'routes')]
    bundle_sha = hashlib.sha256(_encoded({name:hashlib.sha256((f.repo / name).read_bytes()).hexdigest() for name in source_files})).hexdigest()
    boundary = ActualImageBoundary(f, scope=scope, protection_sha256=protection.manifest_sha,
        restore_receipt_sha256=protection.receipt_sha, source_bundle_sha256=bundle_sha, specs=specs)
    f.boundary = boundary
    started = boundary.window_started_wall
    f.report.update(startup_receipt_sha256=trial_sha, source_bundle_sha256=bundle_sha,
        production_backup_retention_verified=False, ci_approval_only=True)
    f.stage = 'original_offline_iam45'
    def iam():
        f.select('iam')
        env = {'IAM_APISERVER_MYSQL_' + k:v for k,v in dict(HOST='mysql',PORT='3306',USERNAME='root',PASSWORD=f.password,DATABASE=databases['iam'],TLS_MODE='disabled').items()}
        for action in ('schema', 'select'):
            plan = '/fixture/' + action + '.json'
            f.once('/app/iam-maintenance', ['m3-messaging', '--action', action, '--store-id', 'isolated-iam-primary', '--writer-epoch', 'm3-1', '--export-plan', plan], environment=env)
            sha = f.once('/usr/bin/sha256sum', [plan], network=False).split()[0]
            f.once('/app/iam-maintenance', ['m3-messaging', '--apply', '--writers-excluded', '--plan', plan, '--reviewed-sha256', sha], environment=env)
    boundary.maintain('original-iam45', iam)
    f.stage = 'original_offline_qs10540_to11043'
    def qs():
        f.select('api'); f.ownership(os.getuid())
        approval = offline_approval(snapshot, operation_id=f.project, started=started, protection=protection,
            startup_sha=trial_sha, scope_sha=hashlib.sha256(_encoded(scope)).hexdigest(), responsibility_sha=boundary.binding_sha)
        path = f.private / 'offline-approval.json'; write_private(path, approval)
        sha = hashlib.sha256(path.read_bytes()).hexdigest(); f.ownership(2000)
        result = json.loads(f.once('/fixture/qs-migrate-offline', ['--mysql-database', databases['qs'], '--mongo-database', databases['qs'],
            '--timeout', '10m', '--apply', '--approval-file', '/fixture/offline-approval.json', '--approval-sha256', sha],
            environment=qs_environment(f, databases['qs']), timeout=620))
        require(result['verified'] is True and result['authorization_consumed'] is True and result['migration_outcome_unknown'] is False, 'original_offline_pair_upgrade_verified_required')
        f.report['offline_pair'] = result
        bind_qs(f, databases['qs'])
    boundary.maintain('original-qs10540-to11043', qs)
    f.stage = 'original_offline_ai40_to43'
    def ai():
        f.select('ai')
        f.once(PYTHON, ['-m', 'alembic', 'upgrade', 'head'], environment=ai_admin_environment)
        bind_ai(f, ai_admin_environment)
    boundary.maintain('original-ai40-to43', ai)
    return boundary
