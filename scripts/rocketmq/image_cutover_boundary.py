"""CI-only actual-image C1 adapter; no production inputs or authorization.

The caller must supply real protection/restore evidence and frozen eight-process
specifications. This adapter neither migrates nor restores any database.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import time
from unittest.mock import patch
import urllib.request

from audit_transaction_limit import write_private
import cutover_step
from five_image_start import SOURCES
from final_image_candidate import ci_guard
from image_start_fixture import IMAGE_PROVENANCE, require
import runtime_start
from start_boundary import Boundary, BoundaryError, _encoded, initialize

COMPONENTS = ('iam', 'ai', 'api', 'collection', 'collection2', 'worker1', 'worker2', 'worker3')
IMAGE_TARGETS = dict(iam='iam', ai='ai', api='qs-api', collection='qs-collection', worker='qs-worker')
RUNTIME_INPUTS = {
    'iam': ('runtime.json', 'routes.json', 'mq-ca.crt', 'service-ca.crt', 'iam-apiserver.crt', 'iam-apiserver.key', 'iam-credentials.json'),
    'ai': ('routes.json', 'mq-ca.crt', 'service-ca.crt', 'ai.crt', 'ai.key', 'credentials.json', 'ai-sign-private.json', 'ai-decrypt-private.json', 'qs-sign-public.json', 'qs-recipient-public.json'),
    'api': ('runtime.json', 'routes.json', 'mq-ca.crt', 'service-ca.crt', 'qs-apiserver.crt', 'qs-apiserver.key', 'qs-credentials.json', 'mongo-credentials.json', 'qs-sign-private.json', 'qs-recipient-private.json', 'ai-sign-public.json', 'ai-decrypt-public.json'),
    'collection': ('runtime.json', 'service-ca.crt', 'qs-collection-server.crt', 'qs-collection-server.key'),
    'worker': ('runtime.json', 'routes.json', 'mq-ca.crt', 'service-ca.crt', 'qs-worker.crt', 'qs-worker.key', 'worker-credentials.json'),
}


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'exact_evidence_digest_required')
    return value


def write_reviewed_start_plan(path, value):
    raw = _encoded(value)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return runtime_start.load(path, hashlib.sha256(raw).hexdigest())


def parse_private_hashes(raw, names):
    expected = {'/fixture/' + n for n in names}; result = {}
    for line in raw.splitlines():
        match = re.fullmatch('([0-9a-f]{64})  (/fixture/[a-z0-9.-]+)', line)
        require(match is not None and match[2] in expected and match[2] not in result, 'exact_private_file_hash_required')
        result[match[2]] = match[1]
    require(set(result) == expected, 'complete_private_input_hashes_required')
    return result


def private_input_hashes(fixture):
    # The CI host cannot read private files owned by the actual image UIDs.
    # Root helpers read only their owned mount and return hashes, never bytes.
    prior = fixture.image, fixture.private; result = {}
    try:
        for component, names in RUNTIME_INPUTS.items():
            fixture.select(component)
            result[component] = parse_private_hashes(fixture.once('/usr/bin/sha256sum', ['/fixture/' + name for name in names], root=True, network=False), names)
    finally: fixture.image, fixture.private = prior
    return result


def startup_receipt(path):
    raw = path.read_bytes(); require(len(raw) < 1024 * 1024, 'bounded_startup_receipt_required')
    value = json.loads(raw)
    require(value['schema'] == 'm3-five-actual-image-startup-trial/v4'
            and (value['passed'], value['failed'], value['skipped']) == (16, 0, 0)
            and len(value['cases']) == 16 and all(v is True for v in value['cases'].values())
            and value['sources'] == SOURCES and value['sources_unchanged'] is True
            and value['mysql_runtime_ddl_attempts'] == value['mongo_runtime_ddl_attempts'] == 0
            and value['mongo_ddl_audit']['positive_controls'] == 4
            and value['mongo_ddl_audit']['commands'] == []
            and not any(value[k] for k in ('production', 'system_acceptance', 'combined_cutover_rehearsal_complete', 'c1_cutover_barrier_exercised')),
            'actual_original_startup_trial_required')
    require(value.get('workers_prepared') == {name:True for name in ('worker1','worker2','worker3')},
            'complete_original_worker_startup_required')
    restarts = value.get('worker_restart_checks', [])
    require(len(restarts) == 9 and {(r['component'],r['cycle']) for r in restarts}
            == {(name,cycle) for name in ('worker1','worker2','worker3') for cycle in range(1,4)}
            and all(r['result']['state'] == dict(Status='exited',ExitCode=0,OOMKilled=False) for r in restarts),
            'bounded_actual_worker_restart_evidence_required')
    require(set(value['processes']) == set(COMPONENTS)
            and all(p['state'] == dict(Status='exited', ExitCode=0, OOMKilled=False) for p in value['processes'].values())
            and all(value['cleanup'].get(k) is True for k in ('compose_down_succeeded', 'private_directory_removed', 'existing_containers_unchanged', 'existing_networks_unchanged')),
            'all_actual_processes_and_cleanup_required')
    expected_budgets = {name:dict(memory_bytes=memory*1024*1024,nano_cpus=int(cpu*1_000_000_000))
        for name,memory,cpu in (('iam',1024,1),('ai',768,0.75),('api',1024,2),
            ('collection',320,1),('collection2',320,1),('worker1',768,1),('worker2',768,1),('worker3',768,1))}
    require(value.get('actual_runtime_budgets') == expected_budgets, 'actual_production_replica_and_resource_budgets_required')
    require(value.get('dependency_versions') == dict(mysql='8.0.36',mongo='7.0.31'), 'actual_production_database_versions_required')
    require(set(value['candidates']) == set(IMAGE_TARGETS.values()), 'all_five_actual_candidates_required')
    for target, candidate in value['candidates'].items():
        source = SOURCES['iam' if target == 'iam' else 'ai' if target == 'ai' else 'qs']
        require(candidate['source_sha'] == source, 'startup_source_differs')
        require(candidate['builder_source_sha'] == IMAGE_PROVENANCE.get((target, source)), 'startup_builder_differs')
        digest(candidate['archive_sha256'])
        require(re.fullmatch('sha256:[0-9a-f]{64}', candidate['image_config_id']), 'startup_image_identity_required')
    return value, hashlib.sha256(raw).hexdigest()


def publish_owned_images(fixture):
    """Prepare immutable references on a loopback-only disposable CI registry."""
    ci_guard(os.environ)
    run = fixture.run; port = fixture.port(); registry = '127.0.0.1:' + str(port)
    image = 'registry:2.8.3'; run(['docker', 'pull', image], timeout=300)
    run(['docker', 'run', '-d', '--name', fixture.project + '-registry', '--label', fixture.label,
         '-p', registry + ':5000', '--memory', '128m', '--cpus', '0.25', image])
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen('http://' + registry + '/v2/', timeout=2) as response:
                require(response.status == 200, 'owned_registry_not_ready')
            break
        except (OSError, RuntimeError): time.sleep(1)
    else: raise RuntimeError('owned_registry_ready_budget_exceeded')
    result = {}
    for component, target in IMAGE_TARGETS.items():
        expected = fixture.report['candidates'][target]
        name = registry + '/m3/' + component
        tag = name + ':' + expected['source_sha']
        run(['docker', 'tag', fixture.images[component], tag])
        run(['docker', 'push', tag], timeout=180)
        info = json.loads(run(['docker', 'image', 'inspect', tag]).stdout)[0]
        references = [r for r in info['RepoDigests'] if r.startswith(name + '@sha256:')]
        require(len(references) == 1, 'one_owned_immutable_reference_required')
        reference = references[0]
        request = urllib.request.Request('http://' + registry + '/v2/m3/' + component + '/manifests/' + reference.split('@')[1],
            headers={'Accept': 'application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json'})
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read(1024 * 1024)
            manifest = json.loads(raw)
            require(response.headers['Docker-Content-Digest'] == reference.split('@')[1]
                    == 'sha256:' + hashlib.sha256(raw).hexdigest()
                    and manifest['config']['digest'] == expected['image_config_id'], 'owned_manifest_config_differs')
        fixture.images[component] = reference
        result[component] = dict(reference=reference, image_config_id=expected['image_config_id'])
    fixture.report['owned_registry'] = dict(image_id=run(['docker', 'image', 'inspect', image, '--format', '{{.Id}}']).stdout.strip(),
        references=result, production_published=False, scope='loopback-only owned CI registry, not a production handoff')
    return result


class ActualImageBoundary:
    def __init__(self, fixture, *, scope, protection_sha256, restore_receipt_sha256, source_bundle_sha256, specs):
        ci_guard(os.environ)
        self.window_started = time.monotonic()
        self.window_started_wall = datetime.now(timezone.utc)
        self.f = fixture; self.root = fixture.directory; self.directory = self.root / 'actual-cutover'; self.plans = {}
        self.specs = json.loads(json.dumps(specs))
        require(set(scope) == {'iam.mysql', 'qs.mysql', 'qs.mongo', 'ai.mysql'} and set(specs) == set(COMPONENTS), 'complete_four_store_eight_process_scope_required')
        require(not fixture.applications, 'no_actual_runtime_before_coordinator_required')
        for owner, selected in scope.items():
            require(isinstance(selected, dict) and set(selected) == {'database', 'identity_sha256', 'store_id', 'writer_epoch', 'route_revision'}, 'exact_selected_store_identity_required')
            name = selected['database']
            prefix = 'iam_m3_image_' if owner == 'iam.mysql' else 'ai_m3_image_' if owner == 'ai.mysql' else 'qs_m3_image_'
            require(isinstance(name, str) and re.fullmatch(prefix + '[a-z0-9_]{1,36}', name), 'owned_selected_database_required')
            digest(selected['identity_sha256'])
            require(selected['writer_epoch'] == selected['route_revision'] == 'm3-1'
                    and selected['store_id'] == {'iam.mysql': 'isolated-iam-primary', 'ai.mysql': 'isolated-ai-primary',
                        'qs.mysql': 'isolated-qs-mysql-primary', 'qs.mongo': 'isolated-qs-mongo-primary'}[owner], 'exact_frozen_store_binding_required')
        self.private_inputs = private_input_hashes(fixture)
        source_bundle = dict(reviewed_source_bundle_sha256=digest(source_bundle_sha256), runtime_files=self.private_inputs, runtime_specs=specs)
        binding = dict(schema='m3-start-boundary/v1', operation_id=fixture.project, directory=str(self.directory),
            scope_sha256=hashlib.sha256(_encoded(scope)).hexdigest(), protection_sha256=digest(protection_sha256),
            restore_receipt_sha256=digest(restore_receipt_sha256), source_bundle_sha256=hashlib.sha256(_encoded(source_bundle)).hexdigest(),
            data_owner='owned-isolated-ci', recovery_owner='owned-isolated-ci')
        self.binding_sha = hashlib.sha256(_encoded(binding)).hexdigest()
        initialize(self.directory, binding, self.binding_sha)
        self.global_lock = self.root / 'owned-deploy.lock'; self.global_lock.touch(mode=0o600, exist_ok=False)
        self.ai_lock = self.root / 'owned-ai.lock'; self.ai_lock.touch(mode=0o600, exist_ok=False)
        self.lock_inodes = {str(p): p.stat().st_ino for p in (self.global_lock, self.ai_lock)}
        compose = dict(services={}, networks={'owned': dict(external=True, name=fixture.network)})
        for component in COMPONENTS:
            spec = specs[component]
            image_component = 'worker' if component.startswith('worker') else 'collection' if component == 'collection2' else component
            reference = fixture.images[image_component]
            require(runtime_start.IMAGE.fullmatch(reference), 'immutable_owned_image_required')
            private = fixture.private_dirs[image_component]
            service = dict(image=reference, container_name=fixture.project + '-' + component,
                labels=[fixture.label], restart='no', mem_limit=spec['memory'], cpus=float(spec['cpus']),
                networks={'owned': {'aliases': [spec['alias']]}}, volumes=[str(private) + ':/fixture:ro'], environment=spec.get('environment', {}))
            if component == 'ai':
                service.update(read_only=True, tmpfs=['/tmp:rw,noexec,nosuid,size=64m'], cap_drop=['ALL'], security_opt=['no-new-privileges:true'])
            else: service['command'] = ['--config=/fixture/runtime.json']
            if component == 'iam': service['volumes'].append(str(private / 'keys') + ':/app/data/keys')
            compose['services'][component] = service
        compose_file = self.root / 'actual-runtime-compose.json'; write_private(compose_file, compose)
        environment = self.root / 'actual-runtime.env'; environment.touch(mode=0o600, exist_ok=False)
        for component in COMPONENTS:
            value = dict(schema='m3-runtime-start/v1', coordinator_binding_sha256=self.binding_sha, host=socket.gethostname(),
                project=fixture.project + '-apps', directory=str(self.root), compose_file=str(compose_file),
                compose_sha256=hashlib.sha256(compose_file.read_bytes()).hexdigest(), environment_file=str(environment),
                environment_sha256=hashlib.sha256(b'').hexdigest(), services=[component],
                images={component: compose['services'][component]['image']}, instances={component: 1}, ai_host=component == 'ai')
            plan = self.root / (component + '-actual-start.json')
            self.plans[component] = write_reviewed_start_plan(plan, value)
        self.started = set()

    def maintain(self, name, callback):
        with Boundary(self.directory, self.binding_sha) as operation:
            return operation.maintain_before_start(name, callback)

    def start(self, component):
        require(component in self.plans and component not in self.started, 'one_frozen_component_start_required')
        require(private_input_hashes(self.f) == self.private_inputs, 'frozen_runtime_input_changed')
        original = runtime_start.command
        def observed(plan, argv, timeout=30):
            if 'up' in argv:
                require((self.directory / 'first-runtime-start.json').is_file(), 'actual_up_before_durable_marker_refused')
                self.f.report.setdefault('actual_up_after_marker', []).append(component)
            return original(plan, argv, timeout)
        try:
            with patch.object(cutover_step, 'GLOBAL_LOCK', self.global_lock), patch.object(cutover_step, 'AI_LOCK', self.ai_lock), patch.object(runtime_start, 'command', side_effect=observed):
                with Boundary(self.directory, self.binding_sha) as operation:
                    operation.start('actual-' + component, lambda: runtime_start.execute(self.plans[component]))
        finally:
            # execute can fail after creating a container. Keep that actual
            # process in diagnostics without masking the durable start failure.
            try:
                name = self.f.project + '-' + component
                result = self.f.run(['docker', 'inspect', '--type', 'container', name, '--format',
                    '{{index .Config.Labels "com.fangcunmount.m3.fixture"}}'], required=False)
                if result.returncode == 0 and result.stdout.strip() == self.f.project:
                    self.f.applications[component] = name
            except RuntimeError:
                self.f.report.setdefault('actual_process_readback_unavailable', []).append(component)
        self.started.add(component)
        self.f.applications[component] = self.f.project + '-' + component

    def finish(self):
        require(self.started == set(COMPONENTS), 'all_eight_actual_starts_required')
        require(time.monotonic() - self.window_started < 1800, 'actual_thirty_minute_window_exceeded')
        refused = []
        with Boundary(self.directory, self.binding_sha) as operation:
            for name, call in [('old-full-backup', operation.restore_before_start), ('poststart-offline', operation.maintain_before_start)]:
                invoked = []
                try: call(name, lambda: invoked.append(True))
                except BoundaryError: require(not invoked, 'rejected_poststart_callback_ran'); refused.append(name)
                else: raise RuntimeError('actual_first_start_boundary_bypassed')
            status = operation.status()
            require(not status['old_data_restore_eligible'], 'old_restore_eligibility_must_remain_closed')
        require(all(Path(p).stat().st_ino == inode for p, inode in self.lock_inodes.items()), 'owned_lock_inode_changed')
        return dict(coordinator_binding_sha256=self.binding_sha, actual_processes=7, poststart_refused=refused,
            elapsed_seconds=time.monotonic() - self.window_started, phase=status['phase'], production_authorized=False)

    def status(self):
        """Preserve responsibility even when the first actual up fails."""
        with Boundary(self.directory, self.binding_sha) as operation:
            state = operation.status()
        marker = self.directory / 'first-runtime-start.json'
        return dict(phase=state['phase'], old_data_restore_eligible=state['old_data_restore_eligible'],
            first_start_recorded=marker.is_file(), first_start_sha256=hashlib.sha256(marker.read_bytes()).hexdigest() if marker.is_file() else None)
