import unittest
from host_sdk_contract import STABLE_MODULE, stable_module_matches
from qs_runtime_acceptance import validate_module

class StableHostModule(unittest.TestCase):
    def test_exact_stable_publication_is_accepted(self):
        self.assertTrue(stable_module_matches(STABLE_MODULE))
        validate_module(dict(STABLE_MODULE))
        validate_module(dict(STABLE_MODULE), True)

    def test_missing_wrong_sums_path_version_and_replace_are_rejected(self):
        for key in STABLE_MODULE:
            for candidate in ({k:v for k,v in STABLE_MODULE.items() if k!=key}, dict(STABLE_MODULE, **{key:'wrong'})):
                self.assertFalse(stable_module_matches(candidate))
                with self.assertRaises(RuntimeError):validate_module(candidate)
        for value in (None, {}, 'local'):
            candidate=dict(STABLE_MODULE, Replace=value)
            self.assertFalse(stable_module_matches(candidate))
            with self.assertRaises(RuntimeError):validate_module(candidate)

if __name__=='__main__':unittest.main()
