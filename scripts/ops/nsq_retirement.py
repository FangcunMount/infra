"""Bounded source patches for retaining, but disabling, serverD's retired NSQ."""
import re

SERVICES = ('nsqlookupd', 'nsqd', 'nsqadmin')
PROFILE = 'legacy-nsq-retired'
GUARD = '\t@bash scripts/rocketmq/guard-nsq.sh\n'


def guard_makefile(raw):
    """Preserve the installed Makefile; guard only its three NSQ start targets."""
    text = raw.decode('utf-8')
    for name in ('nsq-start', 'nsq-recreate', 'serverD-up'):
        pattern = r'(?m)^' + re.escape(name) + r':[^\n]*\n'
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1:
            raise ValueError('one reviewed start target required')
        end = matches[0].end()
        if not text[end:].startswith(GUARD):
            text = text[:end] + GUARD + text[end:]
    return text.encode('utf-8')


def retire_serverd_compose(raw):
    """Add only local overrides; generic NSQ and Mac mini are unchanged."""
    text = raw.decode('utf-8')
    for name in SERVICES:
        old = '  ' + name + ':\n'
        if text.count(old) != 1:
            raise ValueError('one reviewed NSQ service required')
        new = old + '    profiles: [' + PROFILE + ']\n    restart: "no"\n'
        if not text[text.index(old):].startswith(new):
            # Refuse to stack overrides onto an unexpected existing definition.
            block = re.split(r'(?m)^(?=  \S|\S)', text.split(old, 1)[1], maxsplit=1)[0]
            if 'profiles:' in block or 'restart:' in block:
                raise ValueError('unexpected existing service override')
            text = text.replace(old, new, 1)
    return text.encode('utf-8')
