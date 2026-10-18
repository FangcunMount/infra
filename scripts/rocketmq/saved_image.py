"""Bind a Docker29 containerd manifest ID to the CI-proven image config ID."""
import hashlib
import json
import re
import tarfile


def saved_config(archive, image, expected_config):
    for digest in (image, expected_config):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("immutable image/config digest required")
    with tarfile.open(archive, "r:gz") as source:
        def blob(digest):
            stream = source.extractfile("blobs/sha256/" + digest.removeprefix("sha256:"))
            if stream is None:
                raise ValueError("saved image blob missing")
            body = stream.read(1 << 20)
            if "sha256:" + hashlib.sha256(body).hexdigest() != digest:
                raise ValueError("saved image blob digest differs")
            return json.loads(body)
        manifest = blob(image)
        if manifest.get("config", {}).get("digest") != expected_config:
            raise ValueError("loaded manifest does not reference the CI-proven config")
        config = blob(expected_config)
        if config.get("os") != "linux" or config.get("architecture") != "amd64":
            raise ValueError("production image must be linux/amd64")
        return config
