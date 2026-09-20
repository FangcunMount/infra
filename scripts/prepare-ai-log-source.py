#!/usr/bin/env python3
"""Render an exact Docker log allowlist. Run locally on the collector host."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

NAMES = re.compile(r'^/?(?:qs-ai|qs-apiserver|qs-worker-runtime-[0-9]+)$')

def paths_for(containers):
    paths = []
    for item in containers:
        if not NAMES.fullmatch(item.get('Name', '')):
            continue
        identity = item['Id']
        if not re.fullmatch('[a-f0-9]{64}', identity):
            raise ValueError('Invalid container identity')
        if item['HostConfig']['LogConfig']['Type'] != 'json-file':
            raise ValueError('Approved container does not use json-file logging')
        expected = f'/var/lib/docker/containers/{identity}/{identity}-json.log'
        if item.get('LogPath') != expected:
            raise ValueError('Unsupported Docker log path; explicit mount mapping required')
        paths.append(f'/logs/{identity}/{identity}-json.log*')
    if not paths:
        raise ValueError('No approved source containers; refusing wildcard fallback')
    return sorted(paths)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    ids = subprocess.check_output(['docker', 'ps', '-aq'], text=True).split()
    items = json.loads(subprocess.check_output(['docker', 'inspect', *ids], text=True)) if ids else []
    includes = paths_for(items)
    template = args.template.read_text()
    marker = 'include: [/logs/*/*-json.log*]'
    if template.count(marker) != 1:
        raise ValueError('Unexpected source template')
    body = template.replace(marker, 'include: '+json.dumps(includes))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_text() == body:
        return
    with tempfile.NamedTemporaryFile(mode='w', dir=args.output.parent, delete=False) as target:
        target.write(body)
        target.flush()
        os.fsync(target.fileno())
    os.replace(target.name, args.output)
    print(json.dumps({'approved_containers':len(includes), 'updated':True}))

if __name__ == '__main__':
    main()
