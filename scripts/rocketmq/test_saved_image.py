import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from saved_image import saved_config


class SavedImageTests(unittest.TestCase):
    def test_manifest_must_bind_the_exact_config_and_platform(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.tar.gz"
            config = json.dumps({"os": "linux", "architecture": "amd64", "rootfs": {"diff_ids": ["original-layer"]}}).encode()
            digest = "sha256:" + hashlib.sha256(config).hexdigest()
            manifest = json.dumps({"config": {"digest": digest}}).encode()
            image = "sha256:" + hashlib.sha256(manifest).hexdigest()
            with tarfile.open(path, "w:gz") as archive:
                for key, body in ((digest, config), (image, manifest)):
                    member = tarfile.TarInfo("blobs/sha256/" + key[7:]); member.size = len(body)
                    archive.addfile(member, io.BytesIO(body))
            self.assertEqual(saved_config(path, image, digest)["rootfs"]["diff_ids"], ["original-layer"])
            with self.assertRaises(ValueError):
                saved_config(path, image, "sha256:" + "0" * 64)
