"""Bounded allowlisted transport diagnostics; never exports original log lines."""
import hashlib
import re


PATTERNS = {
    'http2_rst_internal': r'RST_STREAM.{0,100}INTERNAL_ERROR',
    'http2_refused_stream': r'REFUSED_STREAM',
    'http2_protocol_error': r'PROTOCOL_ERROR',
    'too_many_pings': r'too_many_pings|ENHANCE_YOUR_CALM',
    'header_size': r'header.{0,30}(?:size|large|limit)',
    'stream_closed': r'stream.{0,35}(?:closed|reset|terminated)',
    'settings': r'(?:sync|initial).{0,25}settings',
    'deadline': r'deadline|timed out|timeout',
    'connection_reset': r'connection reset|broken pipe',
    'tls_handshake': r'(?:TLS|SSL).{0,25}handshake|x509',
    'authentication': r'authentication|unauthenticated|permission denied',
    'executor_rejected': r'RejectedExecutionException|executor.{0,30}reject',
    'out_of_memory': r'OutOfMemoryError|unable to create native thread',
    'resource_exhausted': r'RESOURCE_EXHAUSTED|too many open files',
    'grpc_internal': r'code\s*[=:]\s*Internal|INTERNAL:',
    'grpc_cancelled': r'code\s*[=:]\s*Canceled|CANCELLED:',
}


def summarize(raw):
    if isinstance(raw, str):
        raw = raw.encode()
    raw = raw[-1048576:]
    text = raw.decode(errors='replace')
    return {'bytes_examined': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
            'signals': {key: len(re.findall(pattern, text, re.I))
                        for key, pattern in PATTERNS.items() if re.search(pattern, text, re.I)}}


def startup_internal_description(raw, secrets):
    """Only for a drained failure before Ready, when no business wire exists."""
    if isinstance(raw, bytes):
        raw = raw.decode(errors='replace')
    match = re.search(r'code\s*=\s*Internal\s+desc\s*=\s*([^\r\n]{1,1024})', raw)
    if not match:
        return None
    text = match.group(1)
    if re.search(r'\b(?:body|payload|wire)\b', text, re.I):
        return None
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, '<redacted>')
    text = re.sub(r'[A-Fa-f0-9]{16,}', '<hex>', text)
    text = re.sub(r'eyJ[A-Za-z0-9_.-]{16,}', '<token>', text)
    text = re.sub(r'(?i)((?:authorization|password|secret|token|credential)\s*[:=]\s*)[^,\s}\]]+',
                  r'\1<redacted>', text)
    return text[:512]


DOCKER_SIGNALS = {
    'compose_wait_timeout': r'wait timeout|wait.*timed out',
    'health_check_failed': r'container [^\r\n]{1,180} (?:is unhealthy|exited)|dependency failed to start',
    'port_in_use': r'port is already allocated|address already in use',
    'network_setup': r'failed to set up container networking|network [^\r\n]{1,128} not found',
    'daemon_unavailable': r'cannot connect to the docker daemon|error during connect',
    'image_unavailable': r'pull access denied|manifest unknown|no such image|toomanyrequests',
    'missing_container': r'no such container|container [^\r\n]{1,128} is not running',
    'disk_full': r'no space left on device',
    'permission_denied': r'permission denied|operation not permitted',
    'broker_rpc_timeout': r'RemotingTimeoutException|wait response on the channel.*timeout',
    'broker_rpc_connection': r'RemotingConnectException|connect to.*failed',
    'database_connection': r"Can't connect to (?:local )?MySQL server|ECONNREFUSED",
    'memory': r'OutOfMemoryError|unable to create native thread|oom-kill',
}

DOCKER_PHASES = {
    'compose_start', 'broker_restart', 'broker_health', 'mysql_query', 'mongo_query',
    'broker_get_config', 'broker_update_config', 'broker_update_topic',
    'broker_update_group', 'broker_create_user', 'broker_create_acl', 'broker_admin_other',
}

DOCKER_VERBS = {
    'compose', 'exec', 'inspect', 'pause', 'unpause', 'ps', 'run', 'pull',
    'image', 'start', 'stop', 'kill', 'restart', 'logs',
}


class DockerCommandError(RuntimeError):
    """Carry only fixed stage labels, exit metadata and bounded output fingerprints."""

    def __init__(self, operation, kind, *, returncode=None, stderr=''):
        super().__init__('Docker operation failed (private output withheld)')
        if isinstance(stderr, str):
            stderr = stderr.encode()
        raw = (stderr or b'')[-262144:]
        decoded = raw.decode(errors='replace')
        self.evidence = {
            'operation': operation if operation in DOCKER_PHASES or operation in DOCKER_VERBS else 'other',
            'kind': kind,
            'returncode': returncode,
            'stderr_bytes_examined': len(raw),
            'stderr_sha256': hashlib.sha256(raw).hexdigest(),
            'stderr_signals': [name for name, pattern in DOCKER_SIGNALS.items()
                               if re.search(pattern, decoded, re.I)],
        }


def compose_service_states(raw):
    """Project-local status without exporting names, commands, paths or raw JSON."""
    import json

    if len(raw) > 524288:
        raise ValueError('Compose status exceeded the private capture limit')
    lines = raw.strip()
    if not lines:
        return []
    rows = json.loads(lines) if lines.startswith('[') else [json.loads(row) for row in lines.splitlines()]
    evidence = []
    for row in rows:
        service, state, health = (row.get(key) for key in ('Service', 'State', 'Health'))
        if service not in ('broker', 'nameserver', 'mysql', 'mongo', 'redis'):
            continue
        exit_code = row.get('ExitCode')
        evidence.append({
            'service': service,
            'state': state if state in ('created', 'running', 'restarting', 'removing',
                                       'paused', 'exited', 'dead') else 'unknown',
            'health': health if health in ('starting', 'healthy', 'unhealthy') else None,
            'exit_code': exit_code if type(exit_code) is int and 0 <= exit_code <= 255 else None,
        })
    return sorted(evidence, key=lambda item: item['service'])
