"""Bounded maintenance exception for the operator's actual connection peers.

Pure rendering. Backend authentication/TLS/proxy configuration stays unchanged.
The caller records the peer addresses privately and binds the real window times.
"""
import ipaddress

from m3_nginx_gate import render as render_base


def seconds_pattern(starts_at, expires_at):
    """Compact exact decimal interval; Nginx if has no numeric comparisons."""
    trie = {}
    for second in range(starts_at, expires_at):
        node = trie
        for digit in str(second):
            node = node.setdefault(digit, {})

    def encode(node):
        groups = {}
        for digit, child in sorted(node.items()):
            groups.setdefault(encode(child), []).append(digit)
        options = []
        for suffix, digits in groups.items():
            if len(digits) == 1:
                head = digits[0]
            elif digits == list('0123456789'):
                head = '[0-9]'
            else:
                head = '[' + ''.join(digits) + ']'
            options.append(head + suffix)
        return '' if not options else options[0] if len(options) == 1 else '(?:' + '|'.join(options) + ')'

    return encode(trie)


def render(original, site, peers, starts_at, expires_at):
    if (not isinstance(original, str) or '# M3 bounded operator acceptance gate' in original
            or 'm3_epoch_' in original):
        raise ValueError('original site required; do not stack acceptance revisions')
    if site not in {'iam', 'qs', 'collect'}:
        raise ValueError('fixed site identity required')
    if (type(starts_at) is not int or type(expires_at) is not int
            or not 1577836800 <= starts_at < expires_at <= 2147483647
            or expires_at - starts_at > 1800):
        raise ValueError('bounded actual maintenance window required')
    if not isinstance(peers, (list, tuple)) or not 1 <= len(peers) <= 4:
        raise ValueError('bounded exact connection peers required')
    addresses = []
    for value in peers:
        if not isinstance(value, str):
            raise ValueError('literal address required')
        address = ipaddress.ip_address(value)
        if address.is_unspecified or address.is_multicast or '%' in value:
            raise ValueError('exact unicast peer required')
        addresses.append(address.compressed)
    if len(set(addresses)) != len(addresses):
        raise ValueError('distinct peers required')
    closed = render_base(original, 'closed')
    marker = '# M3 reviewed admission gate\n    return 503;'
    if closed.count(marker) != 2:
        raise ValueError('original HTTP/HTTPS pair required')
    clock, allowed = (f'm3_epoch_{site}', f'm3_accept_{site}')
    # https://nginx.org/en/docs/http/ngx_http_map_module.html
    # Keep the complete regex bounded and quoted. No runtime arithmetic/if
    # operator extension or extra module is required.
    pattern = seconds_pattern(starts_at, expires_at)
    prologue = (f'map $msec ${clock} {{\n    default 0;\n'
                f'    "~^(?:{pattern})[.][0-9]+$" 1;\n}}\n')
    guard = [f'set ${allowed} 0;']
    for address in addresses:
        # This variable is the original connection peer even when an existing
        # trusted real-ip configuration has rewritten $remote_addr from XFF.
        guard.append(f'if ($realip_remote_addr = {address}) {{ set ${allowed} 1; }}')
    guard.extend([f'if (${clock} = 0) {{ set ${allowed} 0; }}',
                  f'if (${allowed} = 0) {{ return 503; }}'])
    replacement = '# M3 bounded operator acceptance gate\n    ' + '\n    '.join(guard)
    return prologue + closed.replace(marker, replacement)
