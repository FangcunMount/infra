"""Read existing monitoring APIs; emit aggregates, never synthesize absent zeros."""
import datetime
import json
from pathlib import Path
import re
import subprocess
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


def configured_dashboard(uid):
    # Use the already configured account inside Grafana. No credential is read
    # into this process, stored, logged, reset or exported from the container.
    script = r'''
if [ -z "${GF_SECURITY_ADMIN_USER:-}" ] || [ -z "${GF_SECURITY_ADMIN_PASSWORD:-}" ]; then exit 64; fi
basic=$(printf '%s:%s' "$GF_SECURITY_ADMIN_USER" "$GF_SECURITY_ADMIN_PASSWORD" | base64 | tr -d '\r\n')
exec wget -SO- -T 5 --header="Authorization: Basic $basic" "http://127.0.0.1:3000/api/dashboards/uid/$1"
'''
    try:
        result = subprocess.run(['docker', 'exec', 'grafana', 'sh', '-c', script, 'sh', uid],
                                capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return 200, json.loads(result.stdout)
        codes = re.findall(r'HTTP/\S+\s+(\d{3})', result.stderr)
        if codes:
            return int(codes[-1]), None
        return ('configured_auth_unavailable' if result.returncode == 64 else 'configured_auth_execution_failed'), None
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return type(error).__name__, None


def panels(model):
    result = []
    for panel in model:
        result.append(dict(id=panel.get('id'), title=panel.get('title'), type=panel.get('type'),
                           targets=[dict(refId=t.get('refId'), expr=t.get('expr')) for t in panel.get('targets', [])]))
        result.extend(panels(panel.get('panels', [])))
    return sorted(result, key=lambda item: (item['id'] is None, item['id'] or 0))


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
    anonymous_status = status
    authentication = 'anonymous'
    if status == 401:
        status, body = configured_dashboard(uid)
        authentication = 'existing_grafana_runtime_account'
    valid = status == 200 and body is not None and body.get('dashboard', {}).get('uid') == uid
    expected = json.loads(Path('components/grafana/dashboards/'+uid+'.json').read_text())
    actual = body.get('dashboard', {}) if valid else {}
    matches = valid and actual.get('title') == expected.get('title') and panels(actual.get('panels', [])) == panels(expected.get('panels', []))
    report['dashboards'][uid] = dict(status=status, anonymous_status=anonymous_status,
        authentication=authentication, api_verified=valid, frozen_panel_model_matches=matches)
Path('monitoring-observation.json').write_text(json.dumps(report, indent=2) + '\n')
