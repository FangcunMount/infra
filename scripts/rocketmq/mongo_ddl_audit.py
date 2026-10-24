"""Owned CI-only Mongo DDL audit; never export command bodies or index options."""
import json
import re

from image_start_fixture import require

KINDS = ('create', 'createIndexes', 'drop', 'dropDatabase', 'collMod',
         'dropIndexes', 'renameCollection', 'convertToCapped', 'emptycapped')
CONTROL = 'm3_ci_ddl_audit_control'
FILTER = {'$or': [{'command.' + kind: {'$exists': True}} for kind in KINDS]}


def install(mongo, database):
    require(re.fullmatch(r'qs_m3_image_start_[0-9a-f]{12}', database), 'owned_mongo_audit_database_required')
    # Explicitly create before enabling profiling, so instrumentation setup is
    # outside the measured interval. DDL-only filtering avoids capped rollover
    # from ordinary polls; retained positive controls still prove completeness.
    program = 'const d=db.getSiblingDB(' + json.dumps(database) + ');'
    program += 'assert.commandWorked(d.createCollection("system.profile",{capped:true,size:67108864}));'
    program += 'assert.commandWorked(d.setProfilingLevel(1,{filter:' + json.dumps(FILTER) + '}));'
    program += 'assert.commandWorked(d.createCollection(' + json.dumps(CONTROL) + '));'
    program += 'assert(d.getCollection(' + json.dumps(CONTROL) + ').drop());'
    mongo(program)


def read(mongo, database):
    require(re.fullmatch(r'qs_m3_image_start_[0-9a-f]{12}', database), 'owned_mongo_audit_database_required')
    program = 'const d=db.getSiblingDB(' + json.dumps(database) + ');'
    program += 'assert.commandWorked(d.createCollection(' + json.dumps(CONTROL) + '));'
    program += 'assert(d.getCollection(' + json.dumps(CONTROL) + ').drop());'
    # Projection happens inside Mongo. No original command or document reaches
    # the report parser. Unknown identifier strings are rejected, not printed.
    program += 'const rows=d.system.profile.find(' + json.dumps(FILTER) + ').toArray();'
    program += 'print(JSON.stringify({status:d.getProfilingStatus(),rows:rows.map(r=>{'
    program += 'const k=' + json.dumps(KINDS) + '.find(k=>Object.hasOwn(r.command,k));'
    program += 'return {kind:k,collection:r.command[k],client:r.client||"",error_code:r.errCode||0};})}));'
    result = json.loads(mongo(program))
    require(result['status']['was'] == 1 and result['status']['filter'] == FILTER, 'mongo_ddl_audit_configuration_changed')
    rows = result['rows']
    require(len(rows) <= 1000, 'mongo_ddl_audit_capacity_exceeded')
    controls = []
    attempts = []
    for row in rows:
        require(set(row) == {'kind', 'collection', 'client', 'error_code'} and row['kind'] in KINDS, 'mongo_ddl_audit_projection_invalid')
        require(isinstance(row['collection'], (str, int)) and (isinstance(row['collection'], int) or re.fullmatch(r'[A-Za-z0-9_.$-]{1,200}', row['collection'])), 'mongo_ddl_identifier_invalid')
        require(re.fullmatch(r'[0-9a-fA-F.:]{0,100}', row['client']) and isinstance(row['error_code'], int), 'mongo_ddl_audit_metadata_invalid')
        if row['collection'] == CONTROL and row['kind'] in ('create', 'drop'):
            controls.append(row)
        else:
            attempts.append(row)
    require([r['kind'] for r in controls].count('create') == 2 and [r['kind'] for r in controls].count('drop') == 2
            and all(r['error_code'] == 0 for r in controls), 'mongo_ddl_audit_positive_controls_missing')
    return dict(attempts=len(attempts), commands=attempts, positive_controls=len(controls),
                profile_capacity_bytes=67108864, command_bodies_exported=False)
