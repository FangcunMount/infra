import copy
import unittest
from ai44_image_start import CMD, verify_registry_identity

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

if __name__=='__main__':unittest.main()
