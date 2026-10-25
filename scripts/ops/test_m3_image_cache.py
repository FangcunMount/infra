import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from m3_image_cache_target import checked_plan, remove_auth


class CacheBoundary(unittest.TestCase):
    def setUp(self):
        self.raw=(Path(__file__).resolve().parents[2]/'docs/server/evidence/rocketmq-m3-fixed-image-cache-plan-20261025.json').read_text()
        self.sha=hashlib.sha256(self.raw.encode()).hexdigest()

    def test_unreviewed_plan_or_wrong_target_rejected_before_io(self):
        for raw,sha,target in ((self.raw+' ',self.sha,'serverA'),(self.raw,self.sha,'serverB')):
            with self.assertRaises(ValueError): checked_plan(raw,sha,target)

    def test_mutable_tag_and_runtime_action_rejected_even_if_hash_matches(self):
        for change in ('reference','runtime'):
            p=json.loads(self.raw)
            if change=='reference':p['images']['iam']['reference']=p['images']['iam']['tag']
            else:p['runtime_started']=True
            raw=json.dumps(p)
            with self.assertRaises(ValueError):checked_plan(raw,hashlib.sha256(raw.encode()).hexdigest(),'serverA')

    def test_cleanup_is_idempotent_and_preserves_other_private_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'receipt.json').write_text('evidence');(root/'auth').mkdir();(root/'auth/config.json').write_text('owned temporary auth')
            remove_auth(root);remove_auth(root)
            self.assertEqual((root/'receipt.json').read_text(),'evidence')
            self.assertFalse((root/'auth').exists())

    def test_cleanup_refuses_symlink_or_unexpected_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'elsewhere').mkdir();(root/'elsewhere/config.json').write_text('protected');(root/'auth').symlink_to(root/'elsewhere',target_is_directory=True)
            with self.assertRaises(ValueError):remove_auth(root)
            self.assertEqual((root/'elsewhere/config.json').read_text(),'protected')
            (root/'auth').unlink();(root/'auth').mkdir();(root/'auth/unexpected').write_text('protected')
            with self.assertRaises(ValueError):remove_auth(root)


if __name__=='__main__':unittest.main()
