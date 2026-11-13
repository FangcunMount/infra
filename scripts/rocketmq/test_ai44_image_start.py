import copy
import unittest
from ai44_image_start import CMD, verify_registry_identity, lifecycle_diagnostics
from image_sdk_profile import sdk_profile, verify_ai44_python_lock

SOURCE='a'*40
REF='registry.invalid/owned/qs-ai@sha256:'+'b'*64

def image():
    return dict(Os='linux',Architecture='amd64',RepoDigests=[REF],Config=dict(User='app',Cmd=CMD,Entrypoint=None,
        Labels={'org.opencontainers.image.revision':SOURCE},Env=['QS_AI_RELEASE_SHA='+SOURCE]))

class Registry44IdentityTests(unittest.TestCase):
    def test_exact_immutable_source_and_default_runtime_required(self):
        self.assertEqual(verify_registry_identity(image(),REF,SOURCE),'sha256:'+'b'*64)
        for mutate in [lambda v:v.update(Architecture='arm64'),lambda v:v.update(RepoDigests=[]),
                       lambda v:v['Config'].update(User='root'),lambda v:v['Config'].update(Cmd=['sleep','infinity']),
                       lambda v:v['Config'].update(Env=['QS_AI_RELEASE_SHA='+'c'*40]),
                       lambda v:v['Config'].update(Labels={}),lambda v:v['Config'].update(Entrypoint=['sh'])]:
            bad=copy.deepcopy(image());mutate(bad)
            with self.assertRaises(RuntimeError):verify_registry_identity(bad,REF,SOURCE)
    def test_mutable_tags_foreign_source_and_unbound_registry_rejected(self):
        for ref,source in [('registry.invalid/owned/qs-ai:latest',SOURCE),(REF,'main'),(REF.replace('registry.invalid','other.invalid'),SOURCE)]:
            with self.assertRaises(RuntimeError):verify_registry_identity(image(),ref,source)

    def test_diagnostics_never_export_arbitrary_log_fields_or_component_values(self):
        import json
        raw='private-driver-secret\n'+json.dumps(dict(event='drain_timeout',component='private-account-secret',level='WARNING',password='private-password-secret'))
        value=lifecycle_diagnostics(raw)
        self.assertEqual(value,[dict(event='drain_timeout',component='other',level='WARNING')])
        self.assertNotIn('secret',str(value))

    def test_ai44_requires_one_of_the_exact_published_python_locks(self):
        original = sdk_profile('readable-stable')
        recovery = dict(
            python='0.5.1',
            wheel_url='https://github.com/FangcunMount/reliable-messaging/releases/download/python/v0.5.1/fangcun_reliable_messaging-0.5.1-py3-none-any.whl',
            wheel_sha256='8dc13c838fb90f3ed536849b7b33d1e25ce970b11829a1eddb5b989e7e1dceb0',
        )

        def lock(profile):
            return (
                '[[package]]\nname="fangcun-reliable-messaging"\n'
                f'version="{profile["python"]}"\nsource={{url="{profile["wheel_url"]}"}}\n'
                f'wheels=[{{url="{profile["wheel_url"]}",hash="sha256:{profile["wheel_sha256"]}"}}]\n'
            )

        for profile in (original, recovery):
            with self.subTest(version=profile['python']):
                self.assertEqual(verify_ai44_python_lock(lock(profile)),
                    {key: profile[key] for key in ('python', 'wheel_url', 'wheel_sha256')})
        for invalid in (
            lock(sdk_profile('readable-rc1')),
            lock(recovery) + lock(original),
            lock(recovery).replace(recovery['wheel_sha256'], original['wheel_sha256']),
            lock(recovery).replace(recovery['wheel_url'], original['wheel_url']),
            lock(recovery).replace('source={url=', 'source={editable='),
        ):
            with self.subTest(lock=invalid), self.assertRaises(ValueError):
                verify_ai44_python_lock(invalid)

if __name__=='__main__':unittest.main()
