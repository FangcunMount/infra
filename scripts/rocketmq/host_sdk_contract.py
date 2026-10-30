"""Exact published stable Go SDK contract for current host acceptance."""
STABLE_MODULE = {
    'Path': 'github.com/FangcunMount/reliable-messaging',
    'Version': 'v0.5.0',
    'Sum': 'h1:JUayISCwmVwrLbHfLvgiOo3jr3Dxs7JfWeF3/Br45O0=',
    'GoModSum': 'h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I=',
}


def stable_module_matches(module):
    return isinstance(module, dict) and 'Replace' not in module and all(module.get(k) == v for k, v in STABLE_MODULE.items())


# Explicit review candidate, downloaded as an immutable Go pseudo-version.
# This is not a stable release and never changes the default historical gates.
ROTATION_SDK_SHA = '48dfcdafbf29b44e99a5ac8b1ae01e5173138560'
ROTATION_MODULE = dict(Path='github.com/FangcunMount/reliable-messaging',
    Version='v0.6.1-0.20261030051625-48dfcdafbf29',
    Sum='h1:CrZw7SsuU96qiSSY1p0ta+XYPjbaG9sdLA2+9OlmFM8=',
    GoModSum='h1:GPiWG8ZsX4pvIZ6QyvLnBVO5iCqNhvsnKwFcg0ftC7I=')


def validate_rotation_module(module):
    if not isinstance(module, dict) or 'Replace' in module or any(
            module.get(k) != v for k, v in ROTATION_MODULE.items()):
        raise RuntimeError('rotation candidate requires exact downloaded module and sums without replace')
