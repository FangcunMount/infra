"""Review direct grants for the fixed pre-existing AI maintenance account.

Capability audit only: never grants/revokes, activates roles or executes DDL.
"""
import hashlib
import json
import re


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def review(grants, roles, partial_revokes):
    if roles!='NONE' or partial_revokes or not isinstance(grants,list) or not grants:
        raise ValueError('direct_unrevoked_grants_required')
    scopes={};grant_option=False
    for line in grants:
        match=re.fullmatch(r'GRANT (.+?) ON (.+?) TO (.+)',line)
        if not match:raise ValueError('unknown_grant_shape')
        scope=match[2].replace('`','');privileges={v.strip() for v in match[1].split(',')}
        if not privileges or not all(re.fullmatch('[A-Z_ ]+',v) for v in privileges):raise ValueError('unknown_privilege')
        scopes.setdefault(scope,set()).update(privileges);grant_option|=match[3].endswith(' WITH GRANT OPTION')
    def allowed(privilege,table):
        privileges=set().union(*(scopes.get(s,set()) for s in ('*.*','ai.*','ai.'+table)))
        return privilege in privileges or 'ALL PRIVILEGES' in privileges
    # All51 tables must be readable for full-layout/protection verification.
    read=scopes.get('*.*',set())|scopes.get('ai.*',set())
    requirements=dict(read_all_ai='SELECT' in read or 'ALL PRIVILEGES' in read,
                      drop_target_capability=allowed('DROP','messaging_outbox'),
                      update_ledger_capability=allowed('UPDATE','alembic_version'))
    other=[s for s in scopes if s not in {'*.*','ai.*'} and not s.startswith('ai.')]
    return dict(schema='ai-execution-account-capability/v1',complete=True,capabilities=requirements,
                required_capabilities_present=all(requirements.values()),
                current_roles=roles,partial_revokes=False,grants_sha256=digest(sorted(grants)),
                ai_schema_all_privileges='ALL PRIVILEGES' in scopes.get('ai.*',set()),
                global_privileges=sorted(scopes.get('*.*',set())),other_scope_count=len(other),
                other_scope_fingerprints=sorted(digest(s) for s in other),grant_option=grant_option,
                least_privilege_account=False if other or 'ALL PRIVILEGES' in read else None,
                source_privileges_changed=False,production_DDL_tested=False,execution_authorized=False)
