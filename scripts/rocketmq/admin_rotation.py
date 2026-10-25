"""Explicit admin-password rotation primitives; no implicit host/service actions.

The approved operator owns cold backup, target/hash guards, scoped credential
clients, in-place persistence and restart. This module never prints credentials.
"""
import json
import re


def require(value, reason):
    if not value: raise ValueError(reason)


def prepare(original, password):
    require(set(original)=={'broker.conf','proxy.json','tools.yml'},'exact_three_config_files_required')
    require(re.fullmatch('[0-9a-f]{64}',password or ''),'generated_256bit_password_required')
    broker=original['broker.conf']
    rows=re.findall(r'(?m)^initAuthenticationUser=(.+)$',broker)
    require(len(rows)==1,'one_bootstrap_admin_required')
    old=json.loads(rows[0]);proxy=json.loads(original['proxy.json'])
    tools={}
    for line in original['tools.yml'].splitlines():
        key,sep,value=line.partition(':')
        require(sep and key in ('accessKey','secretKey') and key not in tools,'exact_quoted_tools_required')
        tools[key]=json.loads(value.strip())
    require(set(old)=={'username','password'} and set(tools)=={'accessKey','secretKey'}
            and json.loads(proxy['initAuthenticationUser'])==old
            and tools==dict(accessKey=old['username'],secretKey=old['password'])
            and re.fullmatch('[A-Za-z0-9_.-]{1,80}',old['username'])
            and password!=old['password'],'consistent_original_admin_required')
    new=dict(username=old['username'],password=password)
    proxy['initAuthenticationUser']=json.dumps(new,separators=(',',':'))
    changed={'broker.conf':re.sub(r'(?m)^initAuthenticationUser=.+$',
                'initAuthenticationUser='+json.dumps(new,separators=(',',':')),broker),
             'proxy.json':json.dumps(proxy,indent=2)+'\n',
             'tools.yml':'accessKey: '+json.dumps(new['username'])+'\nsecretKey: '+json.dumps(password)+'\n'}
    return old,new,changed


def rotate(old,new,changed,*,old_admin,new_admin,persist,restart,checkpoint):
    # Fresh admin clients isolate negative authentication from a prior channel.
    def exact(admin,account):
        rows=admin.users()
        require(account['username'] in rows and rows[account['username']][0]==account['password']
                and rows[account['username']][1:]==('Super','Enable'),'exact_enabled_super_user_required')
    exact(old_admin,old)
    checkpoint('original_verified')
    checkpoint('update_user_attempted')
    old_admin('updateUser','-u',new['username'],'-p',new['password'],mutation=True)
    # Never combine -p with -t/-s: those are exclusive in pinned 5.5.1 CLI.
    checkpoint('update_user_confirmed')
    persist(changed)
    checkpoint('new_configuration_persisted')
    restart()
    checkpoint('broker_restarted')
    exact(new_admin,new)
    result=old_admin.raw_users()
    require(re.search(r'CODE:\s*16\b',result) is not None and '#UserName' not in result,
            'old_credentials_must_receive_explicit_no_permission')
    exact(new_admin,new)
    checkpoint('new_success_old_denied_new_success')
