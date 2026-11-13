"""Reviewed image dependency profiles. No version inference or floating inputs."""
PROFILES = {
    'm3-stable': {
        'go': 'v0.5.0', 'python': '0.4.0',
        'source_sha': '1345266aa0e864c46de5d1e3e3c939dd8002a890',
        'go_sum': 'h1:JUayISCwmVwrLbHfLvgiOo3jr3Dxs7JfWeF3/Br45O0=',
    },
    'readable-stable': {
        'go': 'v0.6.0', 'python': '0.5.0',
        'source_sha': '559c735b2ceb11827ffbbd1279808b4164bba3d1',
        'go_sum': 'h1:ncfphXuTE6JtSH9wJTxakZxkLxic4uws15L5dRvYrg0=',
        'wheel_url': 'https://github.com/FangcunMount/reliable-messaging/releases/download/python/v0.5.0/fangcun_reliable_messaging-0.5.0-py3-none-any.whl',
        'wheel_sha256': '6fe1fbf0635d3e2f8ba2f10c12474c39c939ee656f20df7784928f8bd92e88b8',
        'stable_release': True,
    },
    'readable-rc1': {
        'go': 'v0.6.0-rc.1', 'python': '0.5.0rc1',
        'source_sha': '5c2e3cd155e67c0f766e93bf95238b16fc219b5f',
        'go_sum': 'h1:kGWE8og29Er3UYYaNzPgaXj/T/2ltmQJrb+/iI4+nGo=',
        'wheel_url': 'https://github.com/FangcunMount/reliable-messaging/releases/download/python/v0.5.0rc1/fangcun_reliable_messaging-0.5.0rc1-py3-none-any.whl',
        'wheel_sha256': 'bcee737b8cac54ca0a5a486aa126b9a7323ee980e526006fcd2e4b5763be4f92',
    },
}

# AI44 can restart the original release or qualify the independently published
# recovery fix. Keep these Python-only pins separate from the paired Go matrix.
AI44_PYTHON_PROFILES = {
    '0.5.0': PROFILES['readable-stable'],
    '0.5.1': {
        'python': '0.5.1',
        'wheel_url': 'https://github.com/FangcunMount/reliable-messaging/releases/download/python/v0.5.1/fangcun_reliable_messaging-0.5.1-py3-none-any.whl',
        'wheel_sha256': '8dc13c838fb90f3ed536849b7b33d1e25ce970b11829a1eddb5b989e7e1dceb0',
    },
}


def sdk_profile(name):
    if not isinstance(name, str) or name not in PROFILES:
        raise ValueError('reviewed_fixed_sdk_profile_required')
    return dict(PROFILES[name])


def _python_packages(raw):
    import tomllib

    document = tomllib.loads(raw)
    return [package for package in document.get('package', []) if package.get('name') == 'fangcun-reliable-messaging']


def _verify_published_python_lock(packages, expected):
    if (len(packages) != 1 or packages[0].get('version') != expected['python']
            or packages[0].get('source') != {'url': expected['wheel_url']}
            or packages[0].get('wheels') != [dict(url=expected['wheel_url'],
                hash='sha256:' + expected['wheel_sha256'])]):
        raise ValueError('exact_published_readable_wheel_lock_required')
    return dict(version=expected['python'], wheel_sha256=expected['wheel_sha256'], editable=False)


def verify_readable_python_lock(raw, name):
    expected = sdk_profile(name)
    if 'wheel_url' not in expected:
        raise ValueError('readable_prerelease_profile_required')
    return _verify_published_python_lock(_python_packages(raw), expected)


def verify_ai44_python_lock(raw):
    packages = _python_packages(raw)
    version = packages[0].get('version') if len(packages) == 1 else None
    if not isinstance(version, str) or version not in AI44_PYTHON_PROFILES:
        raise ValueError('reviewed_ai44_python_wheel_required')
    expected = AI44_PYTHON_PROFILES[version]
    _verify_published_python_lock(packages, expected)
    return {key: expected[key] for key in ('python', 'wheel_url', 'wheel_sha256')}
