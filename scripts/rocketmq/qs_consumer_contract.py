"""Validate the manifest against the actual fixed Go event registry export."""
import json

from image_start_fixture import require
from qs_image_pair import QS_SHA
from routes import permissions_v2


def parse_contract(raw):
    rows=[line.removeprefix('QS_CONSUMER_CONTRACT ') for line in raw.splitlines() if line.startswith('QS_CONSUMER_CONTRACT ')]
    require(len(rows)==1 and len(rows[0])<32768,'one_original_consumer_contract_required')
    value=json.loads(rows[0])
    require(set(value)=={'schema','source_sha','consumers'} and value['schema']=='qs-original-consumer-contract/v1'
        and value['source_sha']==QS_SHA and isinstance(value['consumers'],list) and 0<len(value['consumers'])<=32,
        'actual_fixed_qs_consumer_registry_required')
    return value


def validate_manifest(document,contract):
    require(contract['source_sha']==QS_SHA,'original_qs_source_required')
    grants=document['accounts']['m3-qs-apiserver'];subscribed=set(grants['subscriptions'])
    permissions=permissions_v2(document,grants);seen=set()
    for row in contract['consumers']:
        require(set(row)=={'id','runtime','event_type','topic','channel','delivery','outbox_profile'} and row['runtime']=='apiserver',
            'explicit_original_apiserver_consumer_required')
        identity=(row['id'],row['event_type']);require(identity not in seen,'duplicate_original_consumer_forbidden');seen.add(identity)
        if row['delivery']=='best_effort':kind,owner='NORMAL','qs.mysql'
        elif row['delivery']=='durable_outbox' and row['outbox_profile']=='mongo_domain_events':kind,owner='TRANSACTION','qs.mongo'
        elif row['delivery']=='durable_outbox' and row['outbox_profile']=='assessment_mysql_events':kind,owner='TRANSACTION','qs.mysql'
        else:raise RuntimeError('unreviewed_original_consumer_delivery')
        selected=[r for r in document['routes'] if (r['topic'],r['subscription'],r['message_type'],r['owner'],r['route_revision'])
            ==(row['topic'],row['channel'],kind,owner,'m3-1')]
        require(len(selected)==1 and selected[0]['id'] in subscribed,'original_consumer_route_missing')
        route=selected[0]
        require('Sub' in permissions.get('Topic:'+route['physical_topic'],())
            and 'Sub' in permissions.get('Group:'+route['consumer_group'],()),'original_consumer_permission_missing')
        if owner!='qs.mysql':require('Pub' not in permissions.get('Topic:'+route['physical_topic'],()),'cross_owner_publication_forbidden')
    return len(seen)
