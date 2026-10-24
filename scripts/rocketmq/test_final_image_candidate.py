import io
from pathlib import Path
import tarfile
import tempfile
import unittest

from final_image_candidate import GO_SUM, MODULE, check_go_buildinfo, inventory_names


class FinalImageProofTest(unittest.TestCase):
    def test_binary_rejects_other_version_sum_and_replace(self):
        raw = 'runtime\n\tdep\t' + MODULE + '\tv0.5.0\t' + GO_SUM + '\n'
        self.assertEqual(check_go_buildinfo(raw)['version'], 'v0.5.0')
        for changed in (raw.replace('v0.5.0', 'v0.5.0-rocketmq-tx.4'),
                        raw.replace(GO_SUM, 'h1:other'),
                        raw + '\t=>\t../local-sdk\t(devel)\n', '', raw + raw):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                check_go_buildinfo(changed)

    def test_archive_inventory_never_extracts_or_accepts_deferred_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'rootfs.tar'
            for name in ('app/qs-worker', '../outside', '/outside',
                         'app/host-observer', 'app/native_recovery.py',
                         'app/native-resume-helper', 'app/JavaNativeHalfManaged.class'):
                with tarfile.open(archive, 'w') as output:
                    item = tarfile.TarInfo(name)
                    item.size = 1
                    output.addfile(item, io.BytesIO(b'x'))
                if name == 'app/qs-worker':
                    self.assertEqual(inventory_names(archive), [name])
                else:
                    with self.subTest(name=name), self.assertRaises(ValueError):
                        inventory_names(archive)
            self.assertFalse((Path(directory) / 'app').exists())


if __name__ == '__main__':
    unittest.main()
