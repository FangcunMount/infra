#!/usr/bin/env python3
"""Build only the managed Java child from the fixed RocketMQ 5.5.1 libraries."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

RELEASE_SHA512 = (
    '21555d9bd79792ac89f246566f19f58e300784c59b96289fd0c74db14787861081'
    'fb60ebb95cf541bf20a3e508bf3b70feb9596ea3ba6dc5dc88fa6081f00577'
)
LIBRARY_DIR = 'rocketmq-all-5.5.1-bin-release/lib/'
MANAGED_CLASSES = ('NativeHalfIdentity', 'NativeHalfManaged')


def build(archive, output):
    repo = Path(__file__).resolve().parents[2]
    source = repo / 'scripts/rocketmq/probes/native-recheck'
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo):
        raise ValueError('clean source required')
    if output.exists() or not output.parent.is_dir():
        raise ValueError('new output in an existing directory required')
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha512').hexdigest() != RELEASE_SHA512:
            raise ValueError('fixed RocketMQ 5.5.1 archive required')
        stream.seek(0)
        with ZipFile(stream) as release, tempfile.TemporaryDirectory(prefix='managed-helper-') as temp:
            root = Path(temp)
            lib, classes = root / 'lib', root / 'classes'
            lib.mkdir()
            classes.mkdir()
            for member in release.infolist():
                if member.filename.startswith(LIBRARY_DIR) and member.filename.endswith('.jar'):
                    name = member.filename.removeprefix(LIBRARY_DIR)
                    if '/' in name or '\\' in name:
                        raise ValueError('unexpected library path')
                    with release.open(member) as jar, (lib / name).open('xb') as dest:
                        shutil.copyfileobj(jar, dest)
            if not any(lib.iterdir()):
                raise ValueError('fixed RocketMQ libraries required')
            command = ['javac', '--release', '17', '-g:none', '-cp', str(lib / '*'),
                       '-d', str(classes), *(str(source / (name + '.java')) for name in MANAGED_CLASSES)]
            subprocess.run(command, check=True)
            expected = {name + '.class' for name in MANAGED_CLASSES}
            if {entry.name for entry in classes.iterdir()} != expected:
                raise ValueError('only the managed helper and pure identity classes may ship')
            with output.open('xb') as jar, ZipFile(jar, 'w', ZIP_DEFLATED) as contents:
                for name in sorted(expected):
                    entry = ZipInfo(name)
                    entry.compress_type = ZIP_DEFLATED
                    entry.external_attr = 0o644 << 16
                    contents.writestr(entry, (classes / name).read_bytes())
    javac = subprocess.check_output(['javac', '-version'], text=True, stderr=subprocess.STDOUT).strip()
    return dict(schema='m3-managed-java-helper-build/v1', source_sha=revision, javac=javac,
                release_sha512=RELEASE_SHA512, jar_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                classes=sorted(expected))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rocketmq-archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.rocketmq_archive, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
