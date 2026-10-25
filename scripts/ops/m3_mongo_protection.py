"""Mongo business restoration with one explicit, preserved diagnostic namespace.

Pure planning/encoding only. This module never connects to a database, changes
profiling, drops a database or authorizes restoration. The owner supplies the
reviewed migration-created collection list and the pre-start operation barrier.
"""
import json
import re


PROFILE = 'system.profile'
NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,119}')


def database(value):
    if value != 'qs' and not (isinstance(value, str) and re.fullmatch(r'qs_m3_profile_test_[a-z0-9_]{1,40}', value)):
        raise ValueError('exact selected Mongo database required')
    return value


def collection_names(values):
    if not isinstance(values, list) or len(values) > 256:
        raise ValueError('bounded collection inventory required')
    if any(not isinstance(x, str) or not NAME.fullmatch(x) for x in values):
        raise ValueError('exact collection names required')
    if len(set(values)) != len(values):
        raise ValueError('duplicate collection identity')
    if any(x.startswith('system.') and x != PROFILE for x in values):
        raise ValueError('unreviewed system namespace')
    return set(values)


def restore_selection(before, current, declared_new):
    """Reject surprises before returning any drop target; never select profile."""
    original = collection_names(before)
    observed = collection_names(current)
    additions = collection_names(declared_new)
    if not original - {PROFILE} or PROFILE in additions or additions & original:
        raise ValueError('original business inventory and exact new objects required')
    if (PROFILE in original) != (PROFILE in observed):
        raise ValueError('diagnostic collection identity was added or lost')
    if observed - original - additions:
        raise ValueError('unknown post-freeze collection; do not restore')
    # Missing original business collections can be recreated from the archive.
    return sorted(observed - {PROFILE})


def snapshot_program(selected):
    name = json.dumps(database(selected))
    return '''const d=db.getSiblingDB(''' + name + ''');
function ordered(v){if(Array.isArray(v))return v.map(ordered);if(v&&typeof v==='object'){const r={};for(const k of Object.keys(v).sort())r[k]=ordered(v[k]);return r;}return v;}
const infos=d.getCollectionInfos();
if(infos.some(c=>c.type!=='collection'||(c.name.startsWith('system.')&&c.name!=='system.profile')))throw Error('unsupported collection kind or system namespace');
const value=infos.filter(c=>c.name!=='system.profile').sort((a,b)=>a.name.localeCompare(b.name)).map(c=>({
 name:c.name,type:c.type,options:c.options,uuid:c.info.uuid,
 indexes:d.getCollection(c.name).getIndexes().sort((a,b)=>a.name.localeCompare(b.name)).map(i=>({...i,key:Object.entries(i.key)})),
 documents:d.getCollection(c.name).find().sort({_id:1}).toArray()}));
print(JSON.stringify(ordered(JSON.parse(EJSON.stringify(value,{relaxed:false})))));'''


def profile_identity_program(selected):
    name = json.dumps(database(selected))
    # No diagnostic documents, query predicates, user identities or wire bodies.
    return '''const d=db.getSiblingDB(''' + name + ''');
const c=d.getCollectionInfos({name:'system.profile'});
const p=d.getProfilingStatus();
const settings={level:p.was,slowms:p.slowms,sampleRate:p.sampleRate};
if(p.filter!==undefined)settings.filter=p.filter;
const value={settings,collection:c.length?{name:c[0].name,type:c[0].type,options:c[0].options,uuid:c[0].info.uuid,indexes:d.getCollection('system.profile').getIndexes()}:null};
print(EJSON.stringify(value,{relaxed:false}));'''


def drop_program(selected, names):
    database(selected)
    checked = collection_names(names)
    if PROFILE in checked or not checked:
        raise ValueError('only reviewed business collections may be dropped')
    return ('const d=db.getSiblingDB(' + json.dumps(selected) + ');'
            'for(const name of ' + json.dumps(sorted(checked)) + '){'
            "if(name==='system.profile')throw Error('profile must remain in place');"
            "if(!d.getCollection(name).drop())throw Error('selected drop failed');}")
