"""Exact old/new capability union for a named v2-to-v3 resource migration."""
import hashlib
import json

from routes import permissions_v2, validate


def digest(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_transition(previous, current):
    validate(previous)
    validate(current)
    if previous['version'] != 2 or current['version'] != 3:
        raise ValueError('explicit v2 to readable v3 transition required')
    if (previous['accounts'] != current['accounts']
            or previous['topic_options'] != current['topic_options']
            or previous['group_options'] != current['group_options']):
        raise ValueError('transition cannot alter principals, responsibilities or resource budgets')
    old = {route['id']: route for route in previous['routes']}
    new = {route['id']: route for route in current['routes']}
    history = {route['id']: route for route in current.get('historical_routes', [])}
    if set(old) != set(new) or history != old:
        raise ValueError('exact old resource map and passive history required')
    for identity, before in old.items():
        after = new[identity]
        fields = ('topic', 'subscription', 'message_type', 'owner', 'route_revision')
        if any(before.get(key, '') != after.get(key, '') for key in fields):
            raise ValueError('transition changes logical responsibility')
        if before['physical_topic'] == after['physical_topic']:
            raise ValueError('transition cannot reuse an old physical topic')
        if before.get('consumer_group') and before['consumer_group'] == after.get('consumer_group'):
            raise ValueError('transition cannot reuse an old consumer group')
    for field in ('physical_topic', 'consumer_group'):
        if ({r[field] for r in old.values() if r.get(field)}
                & {r[field] for r in new.values() if r.get(field)}):
            raise ValueError('old and new Broker resources overlap')
    return {role: permissions_v2(previous, grants) for role, grants in previous['accounts'].items()}


def merged_permissions(current, role, old):
    result = {resource: set(actions) for resource, actions in old[role].items()}
    for resource, actions in permissions_v2(current, current['accounts'][role]).items():
        if resource in result:
            raise ValueError('old and new permission resources overlap')
        result[resource] = set(actions)
    return result
