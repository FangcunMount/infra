"""Exact published stable Go SDK contract for current host acceptance."""
STABLE_MODULE = {
    'Path': 'github.com/FangcunMount/reliable-messaging',
    'Version': 'v0.5.0',
    'Sum': 'h1:JUayISCwmVwrLbHfLvgiOo3jr3Dxs7JfWeF3/Br45O0=',
    'GoModSum': 'h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I=',
}


def stable_module_matches(module):
    return isinstance(module, dict) and 'Replace' not in module and all(module.get(k) == v for k, v in STABLE_MODULE.items())
