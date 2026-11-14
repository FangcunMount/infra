"""Validate and fingerprint every regular file in a cold monitoring archive."""
import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


def digest(stream):
    h = sha256()
    count = 0
    for data in iter(lambda: stream.read(1024 * 1024), b""):
        count += len(data)
        h.update(data)
    return count, h.hexdigest()


def verify(path, role, limit):
    manifest = {}
    paths = set()
    consumed = 0
    with path.open("rb") as f:
        compressed_size, compressed_sha = digest(f)
    assert 0 < compressed_size <= limit
    with tarfile.open(path, "r|gz") as archive:
        for m in archive:
            part = PurePosixPath(m.name)
            assert (
                not part.is_absolute() and ".." not in part.parts and part not in paths
            )
            paths.add(part)
            assert m.isdir() or m.isfile()
            if m.isdir():
                continue
            assert part.parts and m.size >= 0
            consumed += m.size
            assert consumed <= limit
            with archive.extractfile(m) as f:
                size, h = digest(f)
            assert size == m.size
            manifest[str(part)] = dict(
                bytes=size, sha256=h, mode=format(m.mode, "04o"), uid=m.uid, gid=m.gid
            )
    if role == "prometheus":
        blocks = {
            p.split("/")[0]
            for p in manifest
            if re.fullmatch(r"[A-Z0-9]{26}/meta.json", p)
        }
        assert blocks and all(
            b + "/index" in manifest
            and any(p.startswith(b + "/chunks/") for p in manifest)
            for b in blocks
        )
        assert any(re.fullmatch(r"wal/[0-9]{8}", p) for p in manifest)
    else:
        assert manifest["grafana.db"]["bytes"] > 0
    return dict(
        role=role,
        archive_sha256=compressed_sha,
        archive_bytes=compressed_size,
        archive_members_verified=True,
        files=manifest,
        uncompressed_bytes=consumed,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("role", choices=("grafana", "prometheus"))
    parser.add_argument("--max-bytes", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.archive, args.role, args.max_bytes), indent=2))
