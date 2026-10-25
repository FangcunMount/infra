"""Pure rendering for the three reviewed public IAM/QS/Collection sites.

Deployment, nginx validation/reload and the single cutover boundary belong to
the separately reviewed operator procedure. This module performs no I/O.
"""
import re

GUARDS = {
    'closed': 'return 503;',
    'login-only': '\n'.join([
        'set $m3_iam_block 1;',
        'if ($request_method ~ ^(GET|HEAD|OPTIONS)$) { set $m3_iam_block 0; }',
        'if ($uri ~ ^/api/v3/authn/(login|refresh_token|verify|logout)$) { set $m3_iam_block 0; }',
        'if ($m3_iam_block = 1) { return 503; }',
    ]),
    'open': '',
}


def render(original, mode):
    if mode not in GUARDS or not isinstance(original, str):
        raise ValueError('reviewed gate mode required')
    if 'm3_iam_block' in original or '# M3 reviewed admission gate' in original:
        raise ValueError('original site required; do not stack gate revisions')
    if mode == 'open':
        return original
    if 'grpc_pass' in original:
        raise ValueError('public HTTP sites only; preserve internal peer drain')
    marker = re.compile(r'(?m)^([ \t]*server[ \t]*\{)[ \t]*$')
    if len(marker.findall(original)) != 2:
        raise ValueError('exact reviewed HTTP/HTTPS server pair required')
    guard = '# M3 reviewed admission gate\n' + GUARDS[mode]
    return marker.sub(lambda match: match[1] + '\n    ' + guard.replace('\n', '\n    '), original)
