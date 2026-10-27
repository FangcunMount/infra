"""Opt-in readable fixtures; never modify legacy manifests or accept local SDK replacements."""
import copy
import hashlib
import json

from routes import consumer_group_v3, physical_topic_v3, validate

MODULE = {
    'Version': 'v0.6.0-rc.1',
    'Sum': 'h1:kGWE8og29Er3UYYaNzPgaXj/T/2ltmQJrb+/iI4+nGo=',
    'GoModSum': 'h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I=',
}


def readable_manifest(original):
    validate(original)
    if original['version'] != 2:
        raise ValueError('explicit original v2 fixture required')
    result = copy.deepcopy(original)
    result['version'] = 3
    for route in result['routes']:
        route['naming_scheme'] = 'readable-v1'
        route['physical_topic'] = physical_topic_v3(
            route['topic'], route['message_type'], route['owner'], route['route_revision'])
        route['consumer_group'] = consumer_group_v3(route['topic'], route['subscription'])
    validate(result)
    return result


def record_readable_fixture(module, manifest, proof):
    if 'Replace' in module or module.get('Path') != 'github.com/FangcunMount/reliable-messaging' or any(
            module.get(key) != value for key, value in MODULE.items()):
        raise RuntimeError('readable host requires exact published prerelease module and sums')
    validate(manifest)
    if manifest['version'] != 3:
        raise RuntimeError('readable host requires v3 fixture')
    proof['manifest_version'] = 3
    proof['naming_scheme'] = 'readable-v1'
    proof['manifest_sha256'] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
