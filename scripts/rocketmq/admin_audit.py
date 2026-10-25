"""Read-only existing ACL snapshots; never interprets them as provision grants.

Preserve all policies, decisions, source restrictions and repeated resources.
The strict minimum-permission provisioning decoder remains unchanged.
"""
import re


def parse_existing_acl(output,subject):
    rows=[];header=False
    pattern=re.compile(r'^(\S+)\s+(\S+)\s+(\S+)\s+(\[[^]]*\])\s+(\[[^]]*\]|null)\s+(\S+)\s*$')
    for line in output.splitlines():
        line=line.strip()
        if line.startswith('#Subject'):header=True;continue
        if not header or not line or line==subject:continue
        match=pattern.fullmatch(line)
        if not match or match[1]!=subject:raise ValueError('unrecognized_readonly_acl_table')
        # Canonicalize only whitespace; never collapse policies/resources or
        # turn Deny/restricted entries into Allow/unrestricted permissions.
        rows.append([re.sub(r'\s+',' ',part) for part in match.groups()])
    if not header:raise ValueError('authoritative_readonly_acl_header_required')
    return {'kind':'table','rows':sorted(rows)}


def read_existing_acl(admin,username):
    result=admin.docker('java','-Xms32m','-Xmx128m','-XX:MaxDirectMemorySize=32m',
        '-cp','/opt/rocketmq/conf:/opt/rocketmq/lib/*',
        'org.apache.rocketmq.tools.command.MQAdminStartup','getAcl',
        '-b','127.0.0.1:10911','-s','User:'+username,required=False)
    text=result.stdout+result.stderr
    if re.search(r'MQBrokerException:\s*CODE:\s*3002\b',text) and '#Subject' not in text:
        return {'kind':'absent','remoting_code':3002}
    if result.returncode or 'Exception' in text or 'command failed' in text:
        raise RuntimeError('private_readonly_acl_rpc_failed')
    return parse_existing_acl(result.stdout,'User:'+username)


def snapshot_existing_acls(admin,users):
    return {u:read_existing_acl(admin,u) for u,row in users.items() if row[1].lower()!='super'}
