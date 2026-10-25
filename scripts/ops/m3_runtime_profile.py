#!/usr/bin/env python3
"""Read-only guards for the two M3 production profile relationships.

The caller supplies the effective decoded configuration after env overrides.
This does not replace the SDK codec, provision resources or open admission.
"""
import argparse
import json
from pathlib import Path


class ProfileError(ValueError):
    pass


def validate(role, config, manifest):
    if role == 'worker':
        messaging = config.get('messaging', {})
        rocket = messaging.get('rocketmq', {})
        if (messaging.get('provider') != 'rocketmq'
                or rocket.get('publish_enabled') is not False
                or rocket.get('transactions')):
            raise ProfileError('worker_must_be_consumer_only')
        return {'role': role, 'consumer_only': True, 'transaction_owners': 0}
    if role != 'apiserver':
        raise ProfileError('unsupported_role')
    sync = config.get('iam', {}).get('authz-sync', {})
    rocket = sync.get('rocketmq', {})
    prefix, instance = sync.get('channel-prefix'), rocket.get('instance_id')
    if (sync.get('enabled') is not True or sync.get('provider') != 'rocketmq'
            or not isinstance(prefix, str) or not prefix
            or not isinstance(instance, str) or not instance
            or rocket.get('transactions')):
        raise ProfileError('authz_subscription_binding_required')
    channel = prefix + '-apiserver-' + instance
    routes = manifest.get('routes', [])
    if not isinstance(routes, list):
        raise ProfileError('route_inventory_required')
    matches = [r for r in routes if isinstance(r, dict)
               and r.get('topic') == sync.get('topic')
               and r.get('subscription') == channel]
    if (len(matches) != 1 or matches[0].get('message_type') != 'TRANSACTION'
            or matches[0].get('owner') != 'iam.mysql'
            or not matches[0].get('physical_topic') or not matches[0].get('consumer_group')):
        raise ProfileError('authz_subscription_must_match_one_frozen_route')
    return {'role': role, 'authz_subscription_bound': True, 'transaction_owner': 'iam.mysql'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', required=True, choices=['worker', 'apiserver'])
    parser.add_argument('--effective-config', required=True, type=Path)
    parser.add_argument('--routes', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        config = json.loads(args.effective_config.read_bytes())
        manifest = json.loads(args.routes.read_bytes())
        if not isinstance(config, dict) or not isinstance(manifest, dict):
            raise ProfileError('objects_required')
        result = validate(args.role, config, manifest)
    except ProfileError as error:
        print(json.dumps({'valid': False, 'reason': str(error)}))
        return 1
    except (OSError, ValueError, TypeError, AttributeError):
        # Parsing errors may include raw configuration; never echo them.
        print(json.dumps({'valid': False, 'reason': 'input_unreadable_or_invalid'}))
        return 1
    print(json.dumps({'valid': True, **result, 'production_mutation': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
