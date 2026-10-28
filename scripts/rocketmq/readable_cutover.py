"""Owned eight-process v2-compatible -> v3 switch, no production/data restore.

Reuse exact candidate images and database bindings. Business admission stays
closed. Original old production images, nonempty schedules and business effects
are separate gates; this trial exercises actual containers/materials and the
persistent first-start/forward-repair boundary within thirty minutes.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time

from final_image_candidate import ci_guard
from image_start_fixture import require
from readable_cutover_materials import COMPONENTS, rebase_mounts
from start_boundary import Boundary, BoundaryError, _encoded, initialize

CASES = frozenset((
    'actual_compatible_v2_eight_instance_startup',
    'actual_v2_v3_empty_inputs_and_exact_binding_snapshot',
    'actual_prestart_compatible_configuration_restore',
    'actual_readable_start_failure_after_persistent_barrier',
    'actual_readable_forward_repair_preserves_original_bindings',
    'actual_readable_v3_eight_instance_restart',
    'actual_readable_switch_within_thirty_minutes'))
ORDER = ('iam','ai','api','collection','collection2','worker1','worker2','worker3')
SPECS = {key:dict(alias=alias,memory=memory,cpus=cpus) for key,alias,memory,cpus in (
    ('iam','iam-apiserver','1024m','1'),('ai','ai','768m','0.75'),('api','qs-apiserver','1024m','2'),
    ('collection','qs-collection','320m','1'),('collection2','qs-collection-2','320m','1'),
    ('worker1','worker1','768m','1'),('worker2','worker2','768m','1'),('worker3','worker3','768m','1'))}
PORTS = dict(iam=9080,ai=8000,api=8080,collection=8080,collection2=8080,worker1=9092,worker2=9092,worker3=9092)


def digest(value):return hashlib.sha256(_encoded(value)).hexdigest()


def prepare_active_configuration(operation, select):
    # Configuration-only restoration is offline maintenance. The data restore
    # API intentionally closes normal starts permanently; never use or weaken it
    # for this route selector rehearsal.
    operation.maintain_before_start('select-active-before-restore',lambda:select('active'))
    operation.maintain_before_start('restore-compatible-config',lambda:select('compat'))
    operation.maintain_before_start('select-final-active',lambda:select('active'))


def root_action(f,action,*,phase=None,source=None):
    ci_guard(os.environ)
    allowed=('GITHUB_ACTIONS','RUNNER_OS','RUNNER_ENVIRONMENT','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_WORKSPACE')
    argv=['sudo','-n','--preserve-env='+','.join(allowed),'python3',str(f.repo/'scripts/rocketmq/readable_cutover_materials.py'),
          action,'--fixture',str(f.directory)]
    if phase:argv+=['--phase',phase,'--source',str(source),'--image',f.images['api']]
    value=f.run(argv,timeout=240,required=False)
    require(value.returncode==0,'owned_readable_material_action_failed')
    return json.loads(value.stdout)


def zero_bindings(f, databases):
    require(set(databases)=={'iam','qs','ai'},'three_exact_owned_databases_required')
    for role,name in databases.items():
        require(re.fullmatch(role+'_m3_image_start_[0-9a-f]{12}',name),'owned_database_identity_required')
    result={}
    for role,owner,store in [('iam','iam.mysql','isolated-iam-primary'),('qs','qs.mysql','isolated-qs-mysql-primary'),
                             ('ai','ai.mysql','isolated-ai-primary')]:
        name=databases[role]
        raw=f.sql(f'SELECT HEX(owner),HEX(store_id),HEX(writer_epoch),schema_version FROM `{name}`.rm_tx_binding;')
        require(raw.split('\t')==[owner.encode().hex().upper(),store.encode().hex().upper(),'m3-1'.encode().hex().upper(),'1'],
                'same_original_binding_required')
        count=f.sql('SELECT '+ '+'.join(f'(SELECT COUNT(*) FROM `{name}`.{table})'
            for table in ('rm_tx_request','rm_tx_execution','rm_tx_witness'))+';')
        require(count=='0','controlled_empty_transaction_scope_required')
        result[owner]=dict(binding_sha256=hashlib.sha256(raw.encode()).hexdigest(),protocol_rows=0)
    name=databases['qs']
    raw=f.mongo(f'const d=db.getSiblingDB("{name}");print(JSON.stringify({{bindings:d.rm_tx_binding.find().sort({{_id:1}}).toArray(),'
        'rows:d.rm_tx_request.countDocuments({})+d.rm_tx_execution.countDocuments({})}));')
    value=json.loads(raw)
    require(value['rows']==0 and len(value['bindings'])==1
            and all(value['bindings'][0].get(k)==v for k,v in dict(_id='qs.mongo',store_id='isolated-qs-mongo-primary',
                writer_epoch='m3-1',schema_version=1).items()),'same_original_mongo_binding_required')
    result['qs.mongo']=dict(binding_sha256=digest(value['bindings']),protocol_rows=0)
    return result


def empty_inputs(f):
    from provision_v2 import Admin
    admin=Admin(f.project+'-broker-1');counts={}
    for filename in ('serverd-routes-m3-v2.json','serverd-routes-readable-v3.json'):
        value=json.loads((f.repo/'components/rocketmq'/filename).read_bytes())
        for name in sorted({r['physical_topic'] for r in value['routes']}):
            raw=admin.docker('java','-Xms32m','-Xmx128m','-cp','/opt/rocketmq/conf:/opt/rocketmq/lib/*',
                'org.apache.rocketmq.tools.command.MQAdminStartup','topicStatus','-n','nameserver:9876','-t',name).stdout
            rows=[]
            for line in raw.splitlines():
                fields=line.split()
                if len(fields)>=4 and all(re.fullmatch('[0-9]{1,12}',v) for v in fields[1:4]):rows.append(fields)
            require(len(rows)==1 and len(rows[0])>=4 and rows[0][1:4]==['0','0','0'],
                    'controlled_zero_original_topic_offsets_required')
            counts[name]=dict(min_offset=0,max_offset=0)
    require(len(counts)==20,'twenty_exact_old_new_physical_inputs_required')
    return counts


def remove_owned(f,name):
    ids=f.run(['docker','ps','-aq','--filter','name=^/'+name+'$']).stdout.split()
    require(len(ids)<=1 and all(re.fullmatch('[0-9a-f]{12,64}',v) for v in ids),'one_owned_container_identity_required')
    if not ids:return
    value=json.loads(f.run(['docker','inspect',ids[0]]).stdout)[0]
    require(value['Name']=='/'+name and value['Config']['Labels'].get('com.fangcunmount.m3.fixture')==f.project
            and value['State']['Running'] is False,'only_stopped_owned_container_removal_allowed')
    f.run(['docker','rm',value['Id']])


def run(f,args,ai_env,databases,stop_actual,case):
    ci_guard(os.environ)
    require(set(f.applications)==set(COMPONENTS),'eight_initial_readable_instances_required')
    original_mounts=json.loads(json.dumps(f.runtime_mounts))
    original_revision=f.report['m4_material_stage']['revision']
    proof=dict(scope='same exact compatible candidate images with v2 then v3 routes; no old production image or business acceptance claim',
        original_production_images_tested=False,production=False,system_acceptance=False,real_provider_not_claimed=True)
    f.report['readable_cutover']=proof
    proof['staged_versions']=root_action(f,'stage')
    before=zero_bindings(f,databases)
    def stop_all():
        values={}
        for component in reversed(ORDER):
            row=stop_actual(component);values[component]=row
            require(row['state']==dict(Status='exited',ExitCode=0,OOMKilled=False),'all_owned_prior_runtimes_must_close_cleanly')
        return values
    def remove_all():
        for component in reversed(ORDER):
            remove_owned(f,f.applications[component]);del f.applications[component]
        f.report['workers_prepared']={}
    def select(phase):
        row=root_action(f,'activate',phase=phase,source=args.sources/'qs')
        require(row['result']['source_sha']==f.readable_candidate['sources']['qs']
                and row['native_metadata']['final_transaction_binding'] is True,'actual_selected_api_preflight_required')
        f.runtime_mounts=rebase_mounts(original_mounts,original_revision,row['revision'])
        f.runtime_mounts['api']=row['volumes']
        return row
    def start(component):
        f.start(component,**SPECS[component],**({'environment':ai_env} if component=='ai' else {}))
        f.ready(component,PORTS[component],'/readyz' if component=='ai' else '/healthz')
        from five_image_start import qs_metrics
        from iam_image_start import protocol_metrics
        from ai_image_start import metrics as ai_metrics
        if component=='iam':f.ready(component,PORTS[component],'/metrics',protocol_metrics)
        elif component=='ai':f.ready(component,PORTS[component],'/metrics',ai_metrics)
        elif component=='api':f.ready(component,PORTS[component],'/metrics',qs_metrics)
    proof['initial_readable_shutdown']=stop_all()
    proof['compat_materials']=select('compat');remove_all()
    for component in ORDER:start(component)
    require(zero_bindings(f,databases)==before,'binding_or_protocol_facts_changed_in_compatibility_start')
    case('actual_compatible_v2_eight_instance_startup')
    proof['empty_inputs']=empty_inputs(f)
    case('actual_v2_v3_empty_inputs_and_exact_binding_snapshot')
    started=time.monotonic()
    proof['compat_shutdown']=stop_all()
    proof['prestart_active']=select('active')
    proof['prestart_compat_restore']=select('compat')
    require(zero_bindings(f,databases)==before,'configuration_restore_changed_original_facts')
    operation_dir=f.directory/'readable-first-start'
    binding=dict(schema='m3-start-boundary/v1',operation_id='readable-'+f.project.rsplit('-',1)[1],directory=str(operation_dir),
        scope_sha256=digest(before),protection_sha256=digest(proof['staged_versions']),
        restore_receipt_sha256=digest(proof['prestart_compat_restore']),source_bundle_sha256=digest(f.readable_candidate),
        data_owner='owned-ci-config-only-no-business-data-restore',recovery_owner='owned-ci-forward-repair')
    binding_sha=digest(binding);initialize(operation_dir,binding,binding_sha)
    refused=[]
    with Boundary(operation_dir,binding_sha) as operation:
        prepare_active_configuration(operation,select)
        case('actual_prestart_compatible_configuration_restore')
        remove_all()
        def initial_start():
            require(operation.status()['runtime_may_have_started'],'marker_must_precede_actual_start')
            start('iam')
        operation.start('readable-iam',initial_start)
        missing=f.project+'-not-created'
        require(missing not in f.run(['docker','network','ls','--format','{{.Name}}']).stdout.splitlines(),
                'owned_missing_network_control_required')
        failed_name=f.project+'-failed-next-start'
        class ExpectedFailure(RuntimeError):pass
        def fail_start():
            value=f.run(['docker','run','--pull','never','--rm','--name',failed_name,'--label',f.label,
                '--network',missing,'--memory','768m','--cpus','0.75',f.images['ai']],required=False,timeout=30)
            require(value.returncode!=0 and missing in value.stdout+value.stderr
                    and 'not found' in (value.stdout+value.stderr).lower(),'actual_missing_network_failure_required')
            proof['actual_failed_start']=dict(exit_code=value.returncode,output_sha256=hashlib.sha256((value.stdout+value.stderr).encode()).hexdigest())
            raise ExpectedFailure()
        try:operation.start('readable-ai-network-fault',fail_start)
        except ExpectedFailure:pass
        else:raise RuntimeError('owned_start_fault_not_observed')
        def forbidden():raise AssertionError('forbidden callback executed')
        for name,callback in [('old-config',lambda:operation.maintain_before_start('forbidden-old-route',forbidden)),
                              ('normal-retry',lambda:operation.start('forbidden-normal-retry',forbidden))]:
            try:callback()
            except BoundaryError:refused.append(name)
            else:raise RuntimeError('persistent_first_start_boundary_bypassed')
        case('actual_readable_start_failure_after_persistent_barrier')
        def repair():
            remove_owned(f,failed_name);start('ai')
        operation.forward_repair('same-active-ai',digest(dict(source=f.readable_candidate,repair='owned-network-only')),repair)
        for component in ORDER[2:]:operation.start('readable-'+component,lambda c=component:start(c))
        proof['coordinator_status']=operation.status();proof['poststart_refused']=refused
    after=zero_bindings(f,databases)
    require(after==before,'readonly_route_switch_changed_original_protocol_facts')
    proof['bindings_before']=before;proof['bindings_after']=after
    case('actual_readable_forward_repair_preserves_original_bindings')
    require(set(f.applications)==set(COMPONENTS),'eight_actual_new_route_instances_required')
    case('actual_readable_v3_eight_instance_restart')
    elapsed=time.monotonic()-started
    require(elapsed<1800,'owned_readable_switch_exceeded_thirty_minutes')
    proof['elapsed_seconds']=elapsed;proof['target_seconds']=900;proof['upper_seconds']=1800
    proof['within_target']=elapsed<900;proof['max_application_slots']=8
    case('actual_readable_switch_within_thirty_minutes')
    return proof
