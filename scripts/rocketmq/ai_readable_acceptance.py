"""Strict opt-in AI host profiles for the published readable-route prerelease."""
from routes import consumer_group_v2, physical_topic_v2
from readable_host_acceptance import readable_manifest

VERSION = '0.5.0rc1'
SHA256 = 'bcee737b8cac54ca0a5a486aa126b9a7323ee980e526006fcd2e4b5763be4f92'
URL = ('https://github.com/FangcunMount/reliable-messaging/releases/download/'
       'python/v0.5.0rc1/fangcun_reliable_messaging-0.5.0rc1-py3-none-any.whl')


def complete_manifest(factory):
    manifest = factory()
    # Even admission/finalization-only fixtures validate the same complete trusted
    # command/ACK capability map as the application. These add no synthetic business.
    for name, topic, subscription in (
            ('command', 'qs.ai.commands.v1', 'qs-ai.commands.v1'),
            ('ack', 'qs.ai.acks.v1', 'qs-ai.acks.v1')):
        if any(route['topic'] == topic for route in manifest['routes']):
            continue
        identifier = 'readable-ai-' + name
        manifest['routes'].append(dict(id=identifier, topic=topic, subscription=subscription,
            message_type='TRANSACTION', owner='qs.mysql', route_revision='m3-1',
            physical_topic=physical_topic_v2(topic, 'TRANSACTION', 'qs.mysql', 'm3-1'),
            consumer_group=consumer_group_v2(topic, subscription)))
        if 'input' in manifest['accounts']:
            manifest['accounts']['input']['publish'].append(identifier)
        manifest['accounts']['ai']['subscriptions'].append(identifier)
    return readable_manifest(manifest)


def readable_profile(kind, original):
    from ai_admission_acceptance import CASES, TESTS, parse_host_receipt, read_host_receipt
    profile = dict(original, readable=True, sdk_version=VERSION, sdk_url=URL, sdk_sha256=SHA256,
                   manifest=lambda: complete_manifest(original['manifest']))
    if kind == 'admission':
        profile['partial'] = lambda output: read_host_receipt(output, sdk_version=VERSION)
        profile['parse'] = lambda output, junit: parse_host_receipt(
            output, junit, cases=CASES, tests=TESTS, sdk_version=VERSION)
    elif kind == 'state':
        from ai_state_acceptance import CASES as STATE_CASES, TESTS as STATE_TESTS
        profile['partial'] = lambda output: read_host_receipt(
            output, marker='M3_AI_STATE_RECEIPT', cases=STATE_CASES, sdk_version=VERSION)
        profile['parse'] = lambda output, junit: parse_host_receipt(
            output, junit, marker='M3_AI_STATE_RECEIPT', cases=STATE_CASES,
            tests=STATE_TESTS, sdk_version=VERSION)
    elif kind == 'finalization':
        from ai_finalization_acceptance import parse_receipt, read_receipt
        profile['partial'] = lambda output: read_receipt(output, sdk_version=VERSION)
        profile['parse'] = lambda output, junit: parse_receipt(output, junit, sdk_version=VERSION)
    elif kind == 'paired':
        import os
        from paired_acceptance import parse_receipt, read_receipt
        from readable_host_acceptance import MODULE
        full = os.environ.get('QS_M3_PAIRED_PROFILE', 'core') == 'full'
        profile['partial'] = lambda output: read_receipt(output, full=full, partial=True,
            sdk_python=VERSION, sdk_go=MODULE['Version'])
        profile['parse'] = lambda output, junit: parse_receipt(output, junit, full=full,
            sdk_python=VERSION, sdk_go=MODULE['Version'])
    elif kind != 'paired_faults':
        raise ValueError('supported named readable AI profile required')
    return profile
