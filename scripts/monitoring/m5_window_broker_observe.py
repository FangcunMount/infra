"""Read the named ServerD Broker metrics endpoint without the central scraper."""
from datetime import datetime, timezone
import json
import re
import signal
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


URL = 'http://100.118.164.39:5557/metrics'
LIMIT = 8 * 1024 * 1024
METRIC = 'rocketmq_broker_permission'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def broker_permission(raw):
    lines = [line for line in raw.splitlines() if line.startswith(METRIC + '{') or line.startswith(METRIC + ' ')]
    if len(lines) != 1:
        raise ValueError('exact_broker_sample_required')
    match = re.fullmatch(METRIC + r'\{([^}]+)\}\s+([0-7](?:\.0+)?)(?:\s+\d+)?', lines[0])
    if not match:
        raise ValueError('malformed_broker_sample')
    for label, expected in (('cluster', 'FangcunMount'), ('node_type', 'broker')):
        values = re.findall(r'(?:^|,)' + label + r'="([^"]*)"(?=,|$)', match[1])
        if values != [expected]:
            raise ValueError('unexpected_broker_sample_identity')
    return float(match[2])


def query():
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(URL, timeout=5) as response:
            raw = response.read(LIMIT + 1)
            if response.status != 200 or len(raw) > LIMIT:
                raise ValueError('broker_response_out_of_bounds')
            permission = broker_permission(raw.decode())
            return {'http_status': response.status, 'permission': permission, 'passed': permission == 6}
    except HTTPError as error:
        return {'passed': False, 'http_status': error.code}
    except (URLError, OSError, ValueError) as error:
        return {'passed': False, 'error_type': type(error).__name__}


def observe():
    rounds = []
    for number in range(2):
        if number:
            time.sleep(15)
        started = datetime.now(timezone.utc).isoformat()
        rounds.append({'started_at': started, **query()})
    return {'schema': 'ai246-direct-broker-prewindow/v1', 'rounds': rounds,
            'passed': all(item['passed'] for item in rounds), 'read_only': True,
            'prometheus_scrape_verified': False, 'broker_pending_verified': False,
            'execution_authorized': False}


if __name__ == '__main__':
    signal.alarm(45)
    result = observe()
    print(json.dumps(result, allow_nan=False, sort_keys=True))
    raise SystemExit(0 if result['passed'] else 1)
