"""Exact published stable Go SDK contract for current host acceptance."""
STABLE_MODULE = {
    'Path': 'github.com/FangcunMount/reliable-messaging',
    'Version': 'v0.5.0',
    'Sum': 'h1:JUayISCwmVwrLbHfLvgiOo3jr3Dxs7JfWeF3/Br45O0=',
    'GoModSum': 'h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I=',
}


def stable_module_matches(module):
    return isinstance(module, dict) and 'Replace' not in module and all(module.get(k) == v for k, v in STABLE_MODULE.items())


# Exact published Go patch for current host-adoption acceptance.
# It never changes the separate historical v0.5.0 contract.
ROTATION_SDK_SHA = '48dfcdafbf29b44e99a5ac8b1ae01e5173138560'
ROTATION_MODULE = dict(Path='github.com/FangcunMount/reliable-messaging',
    Version='v0.6.1',
    Sum='h1:mHj1tReMGHu979OuC/XhFAk13dxsgqTDygZs2WdqVwY=',
    GoModSum='h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I=')


def validate_rotation_module(module):
    if not isinstance(module, dict) or 'Replace' in module or any(
            module.get(k) != v for k, v in ROTATION_MODULE.items()):
        raise RuntimeError('input-rotation profile requires exact published module and sums without replace')
