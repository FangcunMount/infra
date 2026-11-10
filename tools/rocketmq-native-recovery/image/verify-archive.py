#!/usr/bin/env python3
"""Verify the exact Linux recovery image carried by a Docker image archive."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile


def verify(archive, source, image):
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        names = {member.name: member for member in members}
        if len(members) != len(names):
            raise ValueError('duplicate image archive member')

        def checked(descriptor, *, decode=False):
            digest = descriptor['digest']
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
                raise ValueError('invalid image digest')
            member = names['blobs/' + digest.replace(':', '/')]
            if not member.isfile() or member.size != descriptor['size']:
                raise ValueError('invalid image blob')
            with tar.extractfile(member) as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != digest.split(':')[1]:
                raise ValueError('image blob digest mismatch')
            if decode:
                with tar.extractfile(member) as stream:
                    return json.load(stream)

        with tar.extractfile('oci-layout') as stream:
            if json.load(stream) != {'imageLayoutVersion': '1.0.0'}:
                raise ValueError('OCI image layout required')
        with tar.extractfile('index.json') as stream:
            manifest_descriptor, = json.load(stream)['manifests']
        manifest = checked(manifest_descriptor, decode=True)
        config_descriptor = manifest['config']
        config = checked(config_descriptor, decode=True)
        options = config['config']
        if (config_descriptor['digest'] != image or config['os'] != 'linux'
                or config['architecture'] != 'amd64' or options['User'] != '3000:3000'
                or options['Labels']['org.opencontainers.image.revision'] != source
                or options['Entrypoint'] != ['/opt/native-recovery/native-recovery']):
            raise ValueError('exact source-bound execution image required')
        if not manifest['layers']:
            raise ValueError('empty image layer inventory')
        for layer in manifest['layers']:
            checked(layer)
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(source_sha=source, image_id=image, manifest_digest=manifest_descriptor['digest'],
                layers_verified=len(manifest['layers']), archive_sha256=digest,
                archive_bytes=archive.stat().st_size, platform='linux/amd64')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--source', required=True)
    parser.add_argument('--image', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.archive, args.source, args.image), sort_keys=True))


if __name__ == '__main__':
    main()
