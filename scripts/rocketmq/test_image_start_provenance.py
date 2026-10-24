import copy
import unittest

from image_start_fixture import IMAGE_PROVENANCE, verified_image_inventory


class ImageProvenanceTest(unittest.TestCase):
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
