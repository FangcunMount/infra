import copy
import json
from pathlib import Path
import tempfile
import unittest

from m4_final_image_candidates import parse, read
from iam_image_start import seed_receipt
from m4_image_rebuild import SOURCES, BUILDER_SHA, BUILD_RUN

ROOT = Path(__file__).resolve().parents[2]


class FinalCandidateTests(unittest.TestCase):
    def setUp(self):
        self.value = json.loads((ROOT / 'components/rocketmq/m4-final-image-candidates.json').read_bytes())

    def test_exact_current_candidate_does_not_change_frozen_c06_profile(self):
        old = (SOURCES.copy(), BUILDER_SHA, BUILD_RUN)
        value = parse(json.dumps(self.value).encode())
        self.assertEqual(set(value['sources']), {'iam', 'qs', 'ai'})
        self.assertEqual((SOURCES, BUILDER_SHA, BUILD_RUN), old)
        self.assertEqual(BUILD_RUN, '40282528557')
        self.assertNotEqual(value['sources'], SOURCES)

    def test_wrong_schema_sources_and_builder_refused(self):
        for key, bad in [('schema', 'other'), ('sources', {'qs': 'a' * 40}),
                         ('builder_sha', 'main'), ('production', True), ('sdk', {}), ('scope', '')]:
            with self.subTest(key=key):
                value = copy.deepcopy(self.value); value[key] = bad
                with self.assertRaises((RuntimeError, ValueError, TypeError)):
                    parse(json.dumps(value).encode())

    def test_run_ids_and_mixed_qs_builds_refused(self):
        for target, bad in [('iam', '../main'), ('qs-api', '40351033230'), ('ai', 40351033230)]:
            with self.subTest(target=target):
                value = copy.deepcopy(self.value); value['image_runs'][target] = bad
                with self.assertRaises((RuntimeError, ValueError, TypeError)):
                    parse(json.dumps(value).encode())
        value = copy.deepcopy(self.value); value['image_runs'].pop('qs-worker')
        with self.assertRaises(RuntimeError): parse(json.dumps(value).encode())

    def test_mutable_source_and_duplicate_fields_refused(self):
        value = copy.deepcopy(self.value); value['sources']['qs'] = 'main'
        with self.assertRaises(RuntimeError): parse(json.dumps(value).encode())
        raw = json.dumps(self.value).replace('"production": false', '"production": false, "production": false')
        with self.assertRaises(RuntimeError): parse(raw.encode())
        with self.assertRaises(RuntimeError): parse(b' ' * 65537)

    def test_manifest_symlink_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'manifest.json'; p.write_text(json.dumps(self.value))
            self.assertEqual(read(p)[0], self.value)
            alias = p.with_name('alias.json'); alias.symlink_to(p)
            with self.assertRaises(RuntimeError): read(alias)

    def test_current_seed_is_explicit_and_legacy_default_remains_strict(self):
        value = dict(schema_version=45, seed_events_retained=1, controlled_seed=True,
                     publication_intents_created=False, witnesses_created=False, legacy_drain_claimed=False)
        raw = 'IAM_IMAGE_FIXTURE_READY ' + json.dumps(value)
        with self.assertRaises(RuntimeError): seed_receipt(raw)
        self.assertEqual(seed_receipt(raw, expected_schema=45), value)
        for key in ('publication_intents_created', 'witnesses_created', 'legacy_drain_claimed'):
            bad = value.copy(); bad[key] = True
            with self.assertRaises(RuntimeError): seed_receipt('IAM_IMAGE_FIXTURE_READY ' + json.dumps(bad), expected_schema=45)


if __name__ == '__main__': unittest.main()
