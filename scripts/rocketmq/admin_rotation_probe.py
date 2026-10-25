"""Owned 5.5.1 rotation/restart test only; no production endpoints or credentials."""
import json
import os
from pathlib import Path
import secrets
from admin_rotation import prepare,rotate,require
from final_image_candidate import ci_guard
from image_start_fixture import OwnedImageFixture
from provision_v2 import Admin


class ScopedAdmin(Admin):
    def __init__(self,container,home):
        super().__init__(container);self.home=home

    def docker(self,*args,**kwargs):
        if args[0]=='java':args=(args[0],'-Drocketmq.home.dir='+self.home,*args[1:])
        return super().docker(*args,**kwargs)

    def raw_users(self):
        result=self.docker('java','-Xms32m','-Xmx128m','-XX:MaxDirectMemorySize=32m',
            '-cp','/opt/rocketmq/conf:/opt/rocketmq/lib/*',
            'org.apache.rocketmq.tools.command.MQAdminStartup','listUser','-b','127.0.0.1:10911',required=False)
        return result.stdout+result.stderr


def main():
    ci_guard(os.environ)
    repo=Path(__file__).resolve().parents[2]
    report=dict(production=False,production_credentials_used=False,passed=0,failed=1,skipped=0,phases=[])
    fixture=OwnedImageFixture(repo,report)
    # Original fixture cleanup uses this fixed image to return owned mount UIDs.
    fixture.image='rocketmq-m3-image-start:5.5.1'
    try:
        fixture.dependencies();broker=fixture.project+'-broker-1'
        def call(args,**kwargs):return fixture.run(['docker','exec',broker,*args],**kwargs).stdout
        source={name:call(['cat','/etc/rocketmq/'+name]) for name in ('broker.conf','proxy.json','tools.yml')}
        old,new,changed=prepare(source,secrets.token_hex(32))
        homes={}
        for kind,body in (('old',source['tools.yml']),('new',changed['tools.yml'])):
            home='/tmp/m3-rotate-'+secrets.token_hex(8);homes[kind]=home
            fixture.run(['docker','exec','-i',broker,'bash','-ec',
                'umask 077; mkdir -p "$1/conf"; cat > "$1/conf/tools.yml"','owned-auth',home],stdin=body)
        def persist(files):
            for name,body in files.items():
                # Write the existing inode: production has a separate tools.yml bind mount.
                fixture.run(['docker','run','--rm','-i','--label',fixture.label,'--network','none','--user','0',
                    '--entrypoint','bash','-v',str(fixture.directory/'broker')+':/config',fixture.image,
                    '-ec','cat > "$1"','owned-config','/config/'+name],stdin=body)
        def restart():fixture.run(fixture.compose+['restart','broker'],timeout=150);fixture.run(fixture.compose+['up','-d','--wait','--wait-timeout','180'],timeout=210)
        rotate(old,new,changed,old_admin=ScopedAdmin(broker,homes['old']),new_admin=ScopedAdmin(broker,homes['new']),
               persist=persist,restart=restart,checkpoint=report['phases'].append)
        require(all(call(['cat','/etc/rocketmq/'+name])==body for name,body in changed.items()),'new_all_config_copies_not_visible')
        users=Admin(broker).users();require(users[new['username']]==(new['password'],'Super','Enable'),'default_tools_not_rotated')
        report.update(passed=7,failed=0,new_success_old_denied_new_success=True,
            all_config_copies_persisted=True,default_tools_authenticated=True,
            same_container_after_restart=True,application_started=False)
    except Exception as error:
        report['error_type']=type(error).__name__
        # Only literal phase/reason strings authored here may leave private output.
        if type(error) is ValueError:report['error_code']=str(error)
        raise
    finally:
        fixture.cleanup()
        Path('admin-rotation-probe.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
