import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('release_assets', Path(__file__).with_name('release_assets.py'))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseAssetsTest(unittest.TestCase):
    def test_changed_assets_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, 'changed since dry-run'):
                release.apply(root, {}, 'wrong', root / 'backup', lambda: self.fail('must not reload'))
            self.assertEqual(list(root.iterdir()), [])

    def test_reload_failure_restores_old_files_and_preserves_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'config'
            before = {}
            for name in [*release.ASSETS, release.REMOVED]:
                release.replace(root / name, ('original:' + name).encode())
                before[name] = (root / name).read_bytes()
            backup = Path(directory) / 'backup'
            with patch.object(release, 'run', return_value=b''):
                with self.assertRaisesRegex(RuntimeError, 'reload failed'):
                    release.apply(root, {n: b'new' for n in release.ASSETS}, release.state_hash(release.state(root)), backup,
                                  lambda: (_ for _ in ()).throw(RuntimeError('reload failed')))
            for name, raw in before.items():
                self.assertEqual((root / name).read_bytes(), raw)
                self.assertEqual((backup / name).read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
