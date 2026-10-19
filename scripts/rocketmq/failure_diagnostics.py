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
