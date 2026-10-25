#!/usr/bin/env python3
"""Export an immutable official client image on GitHub; never production data."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess

SOURCE='mysql@sha256:65ce0889751900d2dd5fc5aa5a5fb59073d401fc43df2eae6bd6afb18e7626dd'
CONFIG='sha256:f5f171121fa3e572eb30770e3c9a6ca240e822fdaea4e2f44882de402c8ce9d4'
TAG='m3-mysql-client:8.0.36-65ce08897519'


def main():
    if (os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted'
            or os.environ.get('RUNNER_OS')!='Linux'):
        raise RuntimeError('owned GitHub Linux image export required')
    def run(args):
        return subprocess.run(['docker',*args],capture_output=True,check=True,timeout=300).stdout
    existing=subprocess.run(['docker','image','inspect',TAG],capture_output=True)
    if existing.returncode==0:raise RuntimeError('owned export tag already exists')
    run(['pull',SOURCE]);image=json.loads(run(['image','inspect',SOURCE]))[0]
    if image['Id']!=CONFIG or image['Architecture']!='amd64' or image['Os']!='linux' or SOURCE not in image['RepoDigests']:
        raise RuntimeError('official immutable image identity differs')
    output=Path('m3-mysql-client-export');output.mkdir(mode=0o700)
    archive=output/'mysql-client.tar.gz'
    try:
        run(['tag',SOURCE,TAG])
        # Only source-image bytes are exported; no container, secret or database.
        with archive.open('xb') as target:
            process=subprocess.Popen(['docker','save',TAG],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            with gzip.GzipFile(filename='',fileobj=target,mode='wb',compresslevel=1,mtime=0) as compressed:
                while True:
                    part=process.stdout.read(1024*1024)
                    if not part:break
                    compressed.write(part)
            process.stdout.close();error=process.stderr.read();process.stderr.close();code=process.wait(timeout=60)
            if code:raise RuntimeError('owned source-image archive failed')
        archive.chmod(0o600)
        sha=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
        receipt=dict(schema='m3-mysql-client-export/v1',source_reference=SOURCE,config_digest=CONFIG,
                     local_tool_tag=TAG,platform='linux/amd64',archive_sha256=sha,archive_bytes=archive.stat().st_size,
                     source_sha=os.environ['GITHUB_SHA'],production_data=False,database_daemon_started=False)
    finally:
        run(['image','rm','--no-prune',TAG])
    receipt['owned_tag_removed']=subprocess.run(['docker','image','inspect',TAG],capture_output=True).returncode!=0
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'archive_bytes':receipt['archive_bytes'],'archive_sha256':sha,'production_data':False}))


if __name__=='__main__':main()
