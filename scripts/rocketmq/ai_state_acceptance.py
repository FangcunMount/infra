"""Required worker/governance-state profile: one transaction owner and an event observer only."""

from routes import consumer_group_v2, physical_topic_v2, validate_v2

CASES = frozenset(('constructor_inert', 'halves_before_worker_root', 'half_invisible',
    'worker_original_root', 'first_preflight_evidence', 'no_new_publish_outbox',
    'fresh_checker', 'first_wire', 'duplicate_no_replan', 'no_model_call',
    'lost_final_reply', 'source_conflict_rollback', 'host_pool_retained',
    'governance_half_invisible', 'governance_final_unknown_keeps_commit',
    'governance_finalize_reopen_original_roots', 'review_half_invisible',
    'review_full35_original_root', 'review_first_clocks_and_wire',
    'review_source_conflict_rollback'))
TESTS = frozenset((
    'test_actual_worker_preflight_half_gate_and_duplicate_preserve_original_evidence',
    'test_actual_worker_preflight_lost_final_reply_preserves_local_commit',
    'test_actual_worker_preflight_source_conflict_rolls_back_prepared_half',
    'test_actual_governance_finalize_reopen_halves_and_lost_final_reply',
    'test_actual_review_full35_rpc_half_gate_first_clocks_and_wire',
    'test_actual_review_source_conflict_rolls_back_prepared_half'))


def state_manifest():
    topic, subscription, owner = 'qs.ai.events.v1', 'qs-m3-ai-state-observer', 'ai.mysql'
    route = {'id': 'ai-state-event', 'topic': topic, 'subscription': subscription,
             'message_type': 'TRANSACTION', 'owner': owner, 'route_revision': 'm3-1',
             'physical_topic': physical_topic_v2(topic, 'TRANSACTION', owner, 'm3-1'),
             'consumer_group': consumer_group_v2(topic, subscription)}
    manifest = {'version': 2, 'routes': [route],
        'topic_options': {'read_queue_nums': 1, 'write_queue_nums': 1, 'perm': 6},
        'group_options': {'retry_queue_nums': 8},
        'accounts': {
            'ai': {'owner': owner, 'publish': [route['id']], 'subscriptions': []},
            'observer': {'publish': [], 'subscriptions': [route['id']]}}}
    validate_v2(manifest)
    return manifest
