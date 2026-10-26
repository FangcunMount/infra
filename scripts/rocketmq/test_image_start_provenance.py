import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from image_start_fixture import IMAGE_PROVENANCE, OwnedImageFixture, verified_image_inventory


class ImageProvenanceTest(unittest.TestCase):
    def test_offline_failure_exports_only_fixed_stage_and_booleans(self):
        with tempfile.TemporaryDirectory() as root:
            f=OwnedImageFixture.__new__(OwnedImageFixture)
            f.directory=f.private=Path(root); f.report={}; f.label=f.network=f.image='owned-unit'
            outcome=dict(stage='approval',authorization_consumed=False,migration_outcome_unknown=False,
                         verified=False,private_body='unexported-data',initial={'private_dsn':'unexported-dsn'})
            f.run=Mock(return_value=SimpleNamespace(returncode=1,stdout=json.dumps(outcome),stderr='unexported-stderr'))
            with self.assertRaisesRegex(RuntimeError,'owned_image_command_failed'):
                f.once('/fixture/qs-migrate-offline',[])
            safe=f.report['failed_command']['offline_diagnostic']
            self.assertEqual(safe,dict(stage='approval',authorization_consumed=False,migration_outcome_unknown=False,verified=False))
            self.assertNotIn('unexported',json.dumps(f.report))

    def fixture(self, target, source, builder):
        return dict(target=target,source_sha=source,builder_source_sha=builder,passed=1,failed=0,skipped=0,
            deferred_tools_absent=True,cleanup=dict(owned_container_absent=True,owned_image_tag_absent=True,existing_containers_unchanged=True))

    def test_exact_mixed_build_provenance_and_cleanup_are_required(self):
        self.assertEqual(len(IMAGE_PROVENANCE),5)
        for (target,source),builder in IMAGE_PROVENANCE.items():
            original=self.fixture(target,source,builder)
            verified_image_inventory(original,target,source)
            for update in (dict(builder_source_sha='f'*40),dict(source_sha='a'*40),dict(target='other'),
                dict(failed=1),dict(skipped=1),dict(deferred_tools_absent=False),dict(cleanup={})):
                bad=copy.deepcopy(original);bad.update(update)
                with self.subTest(target=target,update=update),self.assertRaises(RuntimeError):
                    verified_image_inventory(bad,target,source)

    def test_supported_builder_cannot_authorize_another_source_or_target(self):
        (target,source),builder=next(iter(IMAGE_PROVENANCE.items()))
        with self.assertRaises(RuntimeError):
            verified_image_inventory(self.fixture(target,source,builder),'qs-api',source)
        with self.assertRaises(RuntimeError):
            verified_image_inventory(self.fixture(target,'a'*40,builder),target,'a'*40)

    def test_new_rehearsal_requires_explicit_reviewed_builder_not_inventory_claim(self):
        source, builder = 'a'*40, 'b'*40
        value = self.fixture('qs-api', source, builder)
        with self.assertRaises(RuntimeError):
            verified_image_inventory(value, 'qs-api', source)
        verified_image_inventory(value, 'qs-api', source, reviewed_builder=builder)
        for altered in (dict(builder_source_sha='c'*40), dict(source_sha='c'*40),
                        dict(target='iam'), dict(failed=1), dict(skipped=1), dict(cleanup={})):
            bad=copy.deepcopy(value); bad.update(altered)
            with self.subTest(altered=altered), self.assertRaises(RuntimeError):
                verified_image_inventory(bad, 'qs-api', source, reviewed_builder=builder)
        for bad in ('', 'b'*39, '../unreviewed', 'B'*40):
            with self.assertRaises(RuntimeError):
                verified_image_inventory(value, 'qs-api', source, reviewed_builder=bad)
