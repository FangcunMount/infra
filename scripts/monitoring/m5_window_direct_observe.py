"""Read the approved QS M5 readiness and owner endpoints from ServerA's AI network."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import re
import signal
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


WORKERS = {f'worker-{n}': f'http://qs-m5-4620d11e2cff-worker-{n}:9092/readyz' for n in (1, 2, 3)}
METRICS = {
    'qs': ('http://qs-m5-4620d11e2cff-apiserver-1:8080/metrics', {'qs.mysql', 'qs.mongo'}),
    'ai': ('http://127.0.0.1:8000/metrics', {'ai.mysql'}),
    'iam': ('http://iam-apiserver:9080/metrics', {'iam.mysql'}),
}
EXPECTED = {'observation_available': 1, 'observation_fresh': 1, 'admission_protected': 0}
PREFIX = 'reliable_messaging_transaction_'
MAX_METRICS_BYTES = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def owner_samples(raw, expected_owners):
    samples = {owner: {} for owner in sorted(expected_owners)}
    for line in raw.splitlines():
        name, delimiter, labels = line.partition('{')
        metric = name.removeprefix(PREFIX)
        if not delimiter or not name.startswith(PREFIX) or metric not in EXPECTED:
            continue
        labels, _, value = labels.rpartition('}')
        owner = re.search(r'(?:^|,)owner="([a-z.]+)"(?:,|$)', labels)
        if not owner or owner[1] not in samples:
            raise ValueError('unexpected_owner')
        result = samples[owner[1]]
        if metric in result or len(value.split()) != 1:
            raise ValueError('duplicate_or_malformed_owner_sample')
        sample = float(value)
        if not math.isfinite(sample):
            raise ValueError('nonfinite_owner_sample')
        result[metric] = sample
    return samples


def query(url, owners):
    try:
        # Ignore inherited proxy configuration and redirects. Only fixed endpoints are read.
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(url, timeout=5) as response:
            result = {'http_status': response.status, 'passed': response.status == 200}
            if owners:
                raw = response.read(MAX_METRICS_BYTES + 1)
                if len(raw) > MAX_METRICS_BYTES:
                    raise ValueError('metrics_budget_exceeded')
                samples = owner_samples(raw.decode(), owners)
                result.update(owner_samples=samples,
                              passed=result['passed'] and all(values == EXPECTED for values in samples.values()))
            return result
    except HTTPError as error:
        return {'passed': False, 'http_status': error.code}
    except (URLError, OSError, ValueError) as error:
        return {'passed': False, 'error_type': type(error).__name__}


def observe():
    rounds = []
    endpoints = {name: (url, ()) for name, url in WORKERS.items()} | METRICS
    with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
        for number in range(2):
            if number:
                time.sleep(15)
            started = datetime.now(timezone.utc).isoformat()
            tasks = {name: pool.submit(query, *target) for name, target in endpoints.items()}
            rounds.append({'started_at': started, 'results': {name: task.result() for name, task in tasks.items()}})
    return {
        'schema': 'ai246-direct-prewindow-observation/v1',
        'read_only': True,
        'qs_runtime_source': '4620d11e2cffbc4b67b43965812cff3340f0be43',
        'rounds': rounds,
        'passed': all(result['passed'] for frame in rounds for result in frame['results'].values()),
        'prometheus_scrape_verified': False,
        'writer_exclusion_verified': False,
        'execution_authorized': False,
    }


if __name__ == '__main__':
    signal.alarm(45)
    receipt = observe()
    print(json.dumps(receipt, allow_nan=False, sort_keys=True))
    raise SystemExit(0 if receipt['passed'] else 1)
