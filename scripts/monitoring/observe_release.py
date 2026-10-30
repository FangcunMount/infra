"""Read existing monitoring APIs; emit aggregates, never synthesize absent zeros."""
import datetime
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

QUERIES = {
    'targets': 'count by (job) (up)',
    'targets_up': 'sum by (job) (up)',
    'qs_business_observation': 'min(qs_server_ai_mq_observation_available)',
    'ai_business_observation': 'min(qs_ai_mq_observation_available)',
    'qs_awaiting_admission': 'sum(qs_server_ai_mq_awaiting_command_receipts)',
    'ai_awaiting_business_ack': 'sum(qs_ai_mq_pending_interpretation_receipts)',
    'transaction_observation': 'min by (owner) (reliable_messaging_transaction_observation_available)',
    'transaction_fresh': 'min by (owner) (reliable_messaging_transaction_observation_fresh)',
    'transaction_protection': 'max by (owner) (reliable_messaging_transaction_admission_protected)',
}


def read(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, None
    except (OSError, ValueError) as error:
        return type(error).__name__, None


report = dict(read_only=True, database_operations=False, configuration_changed=False,
              observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), queries={}, dashboards={})
for name, query in QUERIES.items():
    status, body = read('http://127.0.0.1:19090/api/v1/query?' + urllib.parse.urlencode({'query': query}))
    valid = status == 200 and body is not None and body.get('status') == 'success'
    samples = body.get('data', {}).get('result', []) if valid else []
    report['queries'][name] = dict(query=query, status=status, available=valid,
        present=bool(samples), samples=[dict(labels={k: v for k, v in s.get('metric', {}).items()
        if k in ('owner', 'job')}, value=s['value']) for s in samples])
for uid in ('event-overview', 'event-transactions'):
    status, body = read('http://127.0.0.1:13000/api/dashboards/uid/' + uid)
    valid = status == 200 and body is not None and body.get('dashboard', {}).get('uid') == uid
    report['dashboards'][uid] = dict(status=status, api_verified=valid)
Path('monitoring-observation.json').write_text(json.dumps(report, indent=2) + '\n')
