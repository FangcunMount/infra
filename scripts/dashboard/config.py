"""Render private Dashboard configuration. No network, DDL or implicit login."""
import json
import os
from pathlib import Path
import re

LOGGING = '''<configuration><appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender"><encoder><pattern>%d{ISO8601} %-5level %logger{36} - %msg%n</pattern></encoder></appender><root level="WARN"><appender-ref ref="STDOUT"/></root></configuration>'''


def render(directory, ui, broker, ca):
    for account in (ui, broker):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{3,64}', account['username']):
            raise ValueError('invalid independent account')
        if not re.fullmatch(r'[a-f0-9]{64}', account['password']):
            raise ValueError('64 character generated hexadecimal password required')
    if ui == broker or ui['password'] == broker['password']:
        raise ValueError('UI and Broker credentials must be independent')
    if b'-----BEGIN CERTIFICATE-----' not in ca:
        raise ValueError('Broker CA certificate required')
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    config = {
        'server': {'port': 8082, 'servlet': {'session': {'timeout': '30m',
            'cookie': {'http-only': True, 'same-site': 'strict'}}}},
        'logging': {'config': 'file:/run/dashboard/logback.xml'},
        'rocketmq': {'config': {'namesrvAddrs': ['nameserver:9876'],
            'isVIPChannel': 'false', 'timeoutMillis': 5000,
            'dataPath': '/run/dashboard', 'enableDashBoardCollect': False,
            'loginRequired': True, 'authMode': 'file', 'useTLS': True,
            'accessKey': broker['username'], 'secretKey': broker['password']}},
        'threadpool': {'config': {'coreSize': 2, 'maxSize': 2,
            'keepAliveTime': 3000, 'queueSize': 32}},
    }
    files = {'application.yml': json.dumps(config, indent=2).encode(),
        'users.properties': (ui['username']+'='+ui['password']+',1\n').encode(),
        'ca.crt': ca, 'logback.xml': LOGGING.encode()}
    for name, body in files.items():
        fd = os.open(directory/name, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)

