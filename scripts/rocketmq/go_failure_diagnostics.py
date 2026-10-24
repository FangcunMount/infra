"""Safe Go termination metadata only; never emit captured log messages/args."""
import hashlib
import json
from pathlib import Path
import re


def diagnostics(raw, source):
    signals = {name: token in raw for name, token in {
        'runtime_fatal': 'fatal error:', 'concurrent_map': 'concurrent map',
        'out_of_memory': 'out of memory', 'deadlock': 'all goroutines are asleep',
        'context_cancelled': 'context canceled', 'shutdown_deadline': 'shutdown deadline',
        'segmentation_violation': 'SIGSEGV', 'quit_signal': 'SIGQUIT',
    }.items()}

    def location(path, line):
        if not re.fullmatch(r'[A-Za-z0-9_./!@+-]{1,700}', path): return None
        for prefix in ('internal/', 'pkg/'):
            offset = path.find(prefix)
            if offset >= 0:
                relative = path[offset:]
                if '..' not in Path(relative).parts and (source / relative).is_file():
                    return dict(origin='host', path=relative, line=int(line))
        normalized = path.replace('!fangcun!mount', 'FangcunMount')
        if 'github.com/FangcunMount/reliable-messaging' in normalized:
            marker = normalized.find('/internal/')
            if marker >= 0: return dict(origin='sdk', path=normalized[marker+1:], line=int(line))
        for prefix in ('internal/runtime/', 'runtime/'):
            offset = path.find(prefix)
            if offset >= 0: return dict(origin='go_runtime', path=path[offset:], line=int(line))
        return dict(origin='dependency', file=Path(path).name, path_sha256=hashlib.sha256(path.encode()).hexdigest(), line=int(line))

    frames = []
    for path, line in re.findall(r'(?m)^\s*((?:[A-Za-z0-9_./!@+-]+/)[A-Za-z0-9_.-]+\.go):([0-9]+)(?:\s+\+0x[0-9a-f]+)?', raw):
        row = location(path, line)
        if row and row not in frames: frames.append(row)
    sites = []
    for line in raw.splitlines():
        if not line.startswith('{'): continue
        try: value = json.loads(line)
        except ValueError: continue
        if not isinstance(value,dict) or str(value.get('level','')).lower() not in ('error','fatal','panic'): continue
        caller = value.get('caller','')
        match = re.fullmatch(r'([A-Za-z0-9_./!@+-]+\.go):([0-9]+)',caller) if isinstance(caller,str) else None
        if match:
            row=location(*match.groups())
            if row:
                row['message_sha256']=hashlib.sha256(str(value.get('msg','')).encode()).hexdigest()
                if row not in sites: sites.append(row)
    return dict(signal_presence=signals,go_frames=frames[-40:],error_log_sites=sites[-20:],raw_messages_exported=False)
