"""Reproduce the exact OCI tar retained for the ServerA query bridge."""

import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
from urllib.request import Request, urlopen


REPOSITORY = "https://registry-1.docker.io/v2/library/nginx"
IMAGE = "docker.io/library/nginx"
TAG = IMAGE + ":servera-monitoring-query-offline"


def sha(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def blob(digest):
    return "blobs/sha256/" + digest.removeprefix("sha256:")


def encoded(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


def add(archive, name, data):
    member = tarfile.TarInfo(name)
    member.mode = 0o644
    member.size = len(data)
    archive.addfile(member, io.BytesIO(data))


def export(reference, output):
    manifest_digest = reference.removeprefix("nginx@")
    if reference != "nginx@" + manifest_digest or not manifest_digest.startswith("sha256:"):
        raise ValueError("expected the exact nginx manifest reference from Compose")
    token_url = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/nginx:pull"
    with urlopen(token_url, timeout=20) as response:
        token = json.load(response)["token"]

    def read(path, size, digest, accept):
        request = Request(REPOSITORY + path, headers={"Accept": accept})
        # urllib omits unredirected headers when the registry hands off a blob to its CDN.
        request.add_unredirected_header("Authorization", "Bearer " + token)
        with urlopen(request, timeout=40) as response:
            data = response.read(size + 1)
        if len(data) > size or sha(data) != digest:
            raise ValueError(f"unexpected registry bytes for {digest}")
        return data

    manifest_type = "application/vnd.oci.image.manifest.v1+json"
    manifest_bytes = read("/manifests/" + manifest_digest, 64 * 1024, manifest_digest, manifest_type)
    manifest = json.loads(manifest_bytes)
    if manifest["mediaType"] != manifest_type:
        raise ValueError("expected a single OCI image manifest")
    descriptor = {
        "mediaType": manifest_type, "digest": manifest_digest, "size": len(manifest_bytes),
        "platform": {"os": "linux", "architecture": "amd64"},
        "annotations": {"org.opencontainers.image.ref.name": TAG, "io.containerd.image.name": TAG},
    }
    with tarfile.open(output, "x") as archive:
        add(archive, "oci-layout", encoded({"imageLayoutVersion": "1.0.0"}))
        add(archive, "index.json", encoded({"schemaVersion": 2, "manifests": [descriptor]}))
        add(archive, blob(manifest_digest), manifest_bytes)
        for item in [manifest["config"], *manifest["layers"]]:
            data = read("/blobs/" + item["digest"], item["size"], item["digest"], "application/octet-stream")
            if len(data) != item["size"]:
                raise ValueError(f"unexpected registry size for {item['digest']}")
            if item == manifest["config"]:
                config = json.loads(data)
                if config["os"] != "linux" or config["architecture"] != "amd64":
                    raise ValueError("unexpected bridge image platform")
                print(json.dumps({"manifest": manifest_digest, "config": item["digest"],
                                  "layers": config["rootfs"]["diff_ids"], "tag": TAG}))
            add(archive, blob(item["digest"]), data)


if __name__ == "__main__":
    export(sys.argv[1], Path(sys.argv[2]))
