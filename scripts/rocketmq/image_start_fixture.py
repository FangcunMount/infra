"""Owned hosted-runner image fixture. Never imported by a production package."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tarfile
import tempfile

from audit_transaction_limit import write_private
from final_image_candidate import ci_guard, saved_config, sha256
from render import render
from m3_resources import manifest
from provision_v2 import provision


def require(value, reason):
    if not value:raise RuntimeError(reason)


def resource_subset(document, account):
    result=json.loads(json.dumps(document));grants=result['accounts'][account]
    selected=set(grants['publish']+grants['subscriptions'])
    result['routes']=[row for row in result['routes'] if row['id'] in selected]
    result['accounts']={account:grants}
    require({r['id'] for r in result['routes']}==selected,'exact_resources_required')
    return result


class OwnedImageFixture:
    def __init__(self, repo, report):
        ci_guard(os.environ)
        spec=importlib.util.spec_from_file_location('image_ci_common',repo/'scripts/rocketmq/ci-transactions.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.run=module.run;self.port=module.port;self.repo=repo;self.report=report
        contexts=json.loads(self.run(['docker','context','inspect']).stdout)
        require(len(contexts)==1 and contexts[0]['Endpoints']['docker']['Host']=='unix:///var/run/docker.sock','owned_local_daemon_required')
        self.before={kind:self.ids(kind) for kind in ('containers','networks')}
        self.directory=Path(tempfile.mkdtemp(prefix='m3-image-start-'));self.directory.chmod(0o700)
        self.private=self.directory/'fixture';self.private.mkdir(mode=0o700)
        self.project='rocketmq-m2-image-'+secrets.token_hex(6)
        self.network=self.project+'_rocketmq';self.label='com.fangcunmount.m3.fixture='+self.project
        self.image=None;self.compose=None;self.started=False;self.stage='image_verification'

    def ids(self,kind):
        return set(self.run(['docker','ps','-aq'] if kind=='containers' else ['docker','network','ls','-q']).stdout.split())

    def load(self, candidate, target, source_sha):
        value=json.loads((candidate/'image-inventory.json').read_text())
        require(value['target']==target and value['source_sha']==source_sha
            and (value['passed'],value['failed'],value['skipped'])==(1,0,0)
            and value['builder_source_sha']=='9833d67e631587b908df00e2cc21371403912326'
            and value['deferred_tools_absent'] and all(value['cleanup'].get(key) is True for key in
                ('owned_container_absent','owned_image_tag_absent','existing_containers_unchanged')),'exact_verified_image_required')
        files=list(candidate.glob('*.tar.gz'));require(len(files)==1,'one_image_archive_required')
        archive=files[0];require(sha256(archive)==value['archive_sha256'],'archive_digest_differs')
        with tarfile.open(archive) as source:
            rows=json.load(source.extractfile('manifest.json'))
            require(len(rows)==1 and len(rows[0]['RepoTags'])==1,'one_original_image_tag_required')
            self.image=rows[0]['RepoTags'][0]
        require(saved_config(archive,self.image)[0]==value['image_config_id'],'archived_config_digest_differs')
        self.run(['docker','load','-i',str(archive)],timeout=180)
        require(self.run(['docker','image','inspect',self.image,'--format','{{.Id}}']).stdout.strip()==value['engine_image_id'],'loaded_image_differs')
        self.report['candidate']={key:value[key] for key in ('target','source_sha','image_config_id','archive_sha256')}
        return value

    def once(self, entrypoint, arguments, *, environment=None, root=False, network=True, timeout=180):
        env=self.directory/('env-'+secrets.token_hex(5))
        fields=environment or {}
        require(all('\n' not in key+str(value) and '=' not in key for key,value in fields.items()),'single_line_environment_required')
        env.write_text(''.join(key+'='+str(value)+'\n' for key,value in fields.items()));env.chmod(0o600)
        command=['docker','run','--rm','--label',self.label,'--network',self.network if network else 'none',
            '--env-file',str(env),'-v',str(self.private)+':/fixture','--entrypoint',entrypoint]
        if root:command+=['--user','0']
        result=self.run(command+[self.image,*arguments],timeout=timeout,required=False)
        if result.returncode:
            self.report['failed_command']={'exit_code':result.returncode,'entrypoint':Path(entrypoint).name,
                'private_output_sha256':hashlib.sha256((result.stdout+result.stderr).encode()).hexdigest()}
            # The owned QS initializer emits only a phase and Go error type,
            # never an error message or SQL. Do not export captured log lines.
            phases=re.findall(r'QS_IMAGE_FAILURE phase=([a-z_]+) kind=([A-Za-z0-9_.*]+)',result.stdout+result.stderr)
            if phases:self.report['failed_command']['initializer_diagnostic']=[dict(phase=p,kind=k) for p,k in phases[-4:]]
            raise RuntimeError('owned_image_command_failed')
        return result.stdout

    def ownership(self,uid):
        self.once('/bin/sh',['-c',f'chown -R {uid}:{uid} /fixture'],root=True,network=False)

    def dependencies(self):
        self.stage='owned_dependencies'
        broker_image='rocketmq-m3-image-start:5.5.1'
        for image in ('mysql:8.0.44',):self.run(['docker','pull',image],timeout=300)
        config=self.directory/'broker';data=self.directory/'data';data.mkdir()
        accounts={name:dict(username='owned-'+name,password=secrets.token_hex(32)) for name in ('admin','inner')}
        render(accounts,config,'broker',self.repo/'components/rocketmq');(config/'tls').mkdir()
        self.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=broker',
            '-addext','subjectAltName=DNS:broker,DNS:nameserver,IP:127.0.0.1','-keyout',str(config/'tls/server.key'),'-out',str(config/'tls/server.crt')])
        shutil.copyfile(config/'tls/server.crt',self.private/'mq-ca.crt')
        self.run(['docker','run','--rm','--label',self.label,'--user','0','--entrypoint','bash','-v',str(config)+':/config','-v',str(data)+':/data',broker_image,'-c',
            'mkdir -p /data/store /data/auth /data/logs /data/nameserver-logs; chown -R 3000:3000 /data /config; chmod 750 /config /config/tls'])
        env=dict(os.environ,ROCKETMQ_IMAGE=broker_image,ROCKETMQ_BIND_IP='127.0.0.1',ROCKETMQ_GRPC_PORT=str(self.port()),
            ROCKETMQ_METRICS_PORT=str(self.port()),ROCKETMQ_DATA_ROOT=str(data),ROCKETMQ_CONFIG_ROOT=str(config))
        document=json.loads(self.run(['docker','compose','-f',str(self.repo/'components/rocketmq/docker-compose.yml'),'config','--format','json'],env=env).stdout)
        document.pop('name',None)
        for network in document['networks'].values():network.pop('name',None);network['internal']=True
        for service in document['services'].values():service['restart']='no'
        self.password=secrets.token_hex(32)
        document['services']['mysql']=dict(image='mysql:8.0.44',restart='no',networks=['rocketmq'],mem_limit='512m',
            tmpfs=['/var/lib/mysql'],environment=dict(MYSQL_ROOT_PASSWORD=self.password,MYSQL_ROOT_HOST='%'),
            healthcheck=dict(test=['CMD-SHELL','MYSQL_PWD=$$MYSQL_ROOT_PASSWORD mysql -uroot -e "SELECT 1"'],interval='3s',timeout='3s',retries=50))
        file=self.directory/'compose.json';write_private(file,document)
        self.compose=['docker','compose','-p',self.project,'-f',str(file)];self.started=True
        self.run(self.compose+['up','-d','--wait','--wait-timeout','180'],timeout=210)
        self.report['dependency_image_ids']={name:self.run(['docker','image','inspect',tag,'--format','{{.Id}}']).stdout.strip()
            for name,tag in dict(mysql='mysql:8.0.44',rocketmq=broker_image).items()}

    def sql(self, statement):
        return self.run(self.compose+['exec','-T','mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B'],stdin=statement).stdout.strip()

    def dump(self, database):
        return self.run(self.compose+['exec','-T','mysql','sh','-c',
            'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --hex-blob --compact --skip-comments --skip-dump-date --no-tablespaces --set-gtid-purged=OFF --skip-lock-tables --column-statistics=0 "$@"',
            'owned-protection',database]).stdout

    def provision(self, role):
        document=manifest(self.repo);selected=resource_subset(document,role)
        account=dict(username='owned-'+secrets.token_hex(8),password=secrets.token_hex(32))
        proof=provision(self.project+'-broker-1',selected,{role:account})
        write_private(self.private/'credentials.json',account);write_private(self.private/'routes.json',document)
        self.report['resource_provision']=proof

    def cleanup(self):
        clean={}
        helpers=self.run(['docker','ps','-aq','--filter','label='+self.label]).stdout.split()
        if helpers:self.run(['docker','rm','-f',*helpers],required=False)
        clean['compose_down_succeeded']=not self.started or self.run(self.compose+['down','-v','--remove-orphans'],required=False,timeout=150).returncode==0
        if self.image:
            self.run(['docker','run','--rm','--network','none','--user','0','--entrypoint','/bin/sh','-v',str(self.directory)+':/owned',self.image,
                '-c',f'chown -R {os.getuid()}:{os.getgid()} /owned'],required=False)
        shutil.rmtree(self.directory);clean['private_directory_removed']=not self.directory.exists()
        for kind,prior in self.before.items():clean['existing_'+kind+'_unchanged']=self.ids(kind)==prior
        self.report['cleanup']=clean
        require(all(clean.values()),'owned_cleanup_failed')
