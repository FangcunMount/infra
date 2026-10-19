#!/usr/bin/env python3
"""Install/verify the public RDS CA from one immutable infra commit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TARGET = Path('/data/infra/ssl/mysql/ca-chain.pem')


def validate_ca(ca):
    pattern = rb'-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----'
    certificates = re.findall(pattern, ca)
    if not certificates or re.sub(pattern, b'', ca).strip():
        raise ValueError('Only a public CA PEM chain is accepted')
    valid_roots = 0
    for certificate in certificates:
        result = subprocess.run(['openssl', 'x509', '-noout', '-text', '-subject', '-issuer',
                                 '-nameopt', 'RFC2253'],
                                input=certificate, capture_output=True, check=True)
        if b'CA:TRUE' not in result.stdout:
            raise ValueError('Certificate is not a CA')
        names = dict(line.split(b'=', 1) for line in result.stdout.splitlines()
                     if line.startswith((b'subject=', b'issuer=')))
        if names.get(b'subject') == names.get(b'issuer'):
            status = subprocess.run(['openssl', 'x509', '-checkend', '86400', '-noout'],
                                    input=certificate, capture_output=True)
            valid_roots += status.returncode == 0
    # Official bundles retain retired regional intermediates. They are not the
    # negotiated server chain; Go/OpenSSL still validate that chain and its dates.
    if not valid_roots:
        raise ValueError('CA bundle contains no valid trust root')


def source(ref):
    if not re.fullmatch('[0-9a-f]{40}', ref):
        raise ValueError('An immutable infra commit is required')

    def read(name):
        return subprocess.check_output(['git', '-c', 'safe.directory='+str(ROOT), '-C', str(ROOT),
                                        'show', ref+':components/mysql-client/'+name],
                                       stderr=subprocess.DEVNULL)

    ca = read('ca-chain.pem')
    manifest = json.loads(read('manifest.json'))
    digest = hashlib.sha256(ca).hexdigest()
    if manifest['sha256'] != digest or b'PRIVATE KEY' in ca:
        raise ValueError('CA source checksum is invalid')
    validate_ca(ca)
    return ca, {'infra_ref': ref, 'sha256': digest}


def execute(command, ref):
    ca, receipt = source(ref)
    if command == 'install':
        TARGET.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix='.ca-', dir=TARGET.parent)
        pending = Path(name)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(ca)
                stream.flush()
                os.fsync(stream.fileno())
            pending.chmod(0o644)
            os.replace(pending, TARGET)
        finally:
            pending.unlink(missing_ok=True)
    if TARGET.read_bytes() != ca:
        raise ValueError('Installed MySQL CA differs from the pinned infra commit')
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['install', 'verify'])
    parser.add_argument('--ref', required=True)
    args = parser.parse_args()
    execute(args.command, args.ref)
